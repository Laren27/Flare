/* Volunteer dashboard -- screen 5, plus the live incoming alert of screen 3.
 *
 * The alert path is real: it arrives on the WebSocket opened per ADR-022, and
 * ACCEPT hits the conditional UPDATE of ADR-011. Losing the race renders the
 * "already handled" state rather than an error, because being second is a
 * correct outcome, not a client mistake.
 *
 * Stats and badges are sample data -- there is no responder-history query, and
 * the page says so rather than implying the numbers were measured.
 */

import { announce, trapFocus } from "../shared/a11y.js";
import { api, auth, currentPosition, requireAuth } from "../shared/api.js";
import { duration, formatDistance, initials } from "../shared/format.js";
import { RealtimeChannel } from "../shared/ws.js";
import { createMap, incidentMarker, leafletAvailable } from "../shared/map.js";
import { initNav } from "../shared/nav.js";
import { mockAlert, mockBadges, mockRecentAlerts } from "../shared/mock.js";

const el = (id) => document.getElementById(id);
const preview = new URLSearchParams(location.search).get("preview");
let currentAlert = null;
let alertMap = null;
let elapsedTimer = null;
let releaseFocus = null;

/* ---- availability ------------------------------------------------------- */
/* Going online publishes a position (ADR-026). The server refuses to record
 * availability without one, so this is not a formality: a volunteer who denies
 * location permission genuinely cannot go on duty, and is told exactly that
 * rather than being left online and permanently undispatchable. */

// Chapter 17 asks for location while a session is active. Only while ONLINE --
// tracking someone who has declared themselves off duty is a privacy cost for
// no dispatch benefit, since an offline volunteer is never a candidate.
const LOCATION_REFRESH_MS = 60_000;
let refreshTimer = null;

function renderVolunteerState(state) {
  const online = state.availability;
  el("availability").checked = online;
  el("availability-text").textContent = online ? "Online" : "Offline";
  el("availability-detail").textContent = online
    ? `Visible to the dispatcher at ${state.lat.toFixed(4)}, ${state.lng.toFixed(4)}`
    : "You will not receive alerts while offline.";

  const verified = el("verified-pill");
  verified.textContent = state.verified ? "Verified responder" : "Not yet verified";
  verified.className = `pill ${state.verified ? "pill--success" : "pill--warn"}`;

  el("skill-pill").textContent = state.skills.replace(/_/g, " ");

  // An unverified volunteer is rejected at every dispatch (ADR-021), so being
  // online is not enough on its own and the page should not imply otherwise.
  if (online && !state.verified) {
    el("availability-detail").textContent =
      "Online, but unverified — the dispatcher will not select you until an admin verifies you.";
  }
}

function availabilityError(message) {
  const node = el("availability-error");
  node.textContent = message;
  node.hidden = false;
}

function stopRefreshing() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = null;
}

function startRefreshing() {
  stopRefreshing();
  refreshTimer = setInterval(async () => {
    try {
      const position = await currentPosition();
      await api.setAvailability(true, position);
    } catch {
      // A refresh that fails leaves the last known position in place, which is
      // the honest fallback -- the engine keeps dispatching on where we last
      // genuinely were rather than on a guess.
    }
  }, LOCATION_REFRESH_MS);
}

async function onAvailabilityChange(event) {
  const wantsOnline = event.target.checked;
  const input = el("availability");
  input.disabled = true;
  el("availability-error").hidden = true;

  try {
    if (wantsOnline) {
      el("availability-text").textContent = "Getting your location…";
      const position = await currentPosition();
      renderVolunteerState(await api.setAvailability(true, position));
      startRefreshing();
    } else {
      stopRefreshing();
      renderVolunteerState(await api.setAvailability(false));
    }
  } catch (error) {
    // Put the switch back where the server actually has it. Leaving it flipped
    // would show "Online" for a volunteer the dispatcher will never select.
    input.checked = !wantsOnline;
    el("availability-text").textContent = input.checked ? "Online" : "Offline";
    availabilityError(error.detail || error.message);
  } finally {
    input.disabled = false;
  }
}

/* ---- static panels ------------------------------------------------------ */

function renderRecent() {
  el("recent-alerts").innerHTML = mockRecentAlerts
    .map(
      (alert) => `
      <div class="list__row">
        <span aria-hidden="true">🔴</span>
        <div style="flex:1">
          <div class="strong small">${alert.title}</div>
          <div class="tiny muted">${alert.area}</div>
        </div>
        <div class="tiny muted">${alert.when}</div>
        <span class="pill pill--success">Accepted</span>
      </div>`
    )
    .join("");
  el("recent-note").textContent =
    "Sample data — not built. There is no responder-history query, so these rows " +
    "were never measured.";
}

function renderBadges() {
  el("badges").innerHTML = mockBadges
    .map(
      (badge) => `
      <div class="badge-tile">
        <div class="badge-tile__icon">${badge.icon}</div>
        <div class="strong small">${badge.label}</div>
        <div class="tiny muted">${badge.note}</div>
      </div>`
    )
    .join("");
}

/* ---- incoming alert ----------------------------------------------------- */

function showAlertView(name) {
  el("alert-incoming").hidden = name !== "incoming";
  el("alert-handled").hidden = name !== "handled";
  el("alert-overlay").hidden = false;

  // Re-trapped on every view change: the incoming and handled panels contain
  // different controls, so a trap scoped to the old set would leave the new
  // buttons unreachable.
  releaseFocus?.();
  releaseFocus = trapFocus(el("alert-overlay"), { onEscape: closeAlert });
}

/* Why this alert stopped being answerable. Only the first of these is the
 * accept-lock; showing its explanation for the other two would credit a
 * mechanism that had nothing to do with it. */
const CLOSED_COPY = {
  accepted: {
    icon: "✓",
    title: "Already handled",
    body: "Another responder accepted this incident before you. No further action is needed — help is on the way.",
    note: "Only the first acceptance is assigned. The lock is enforced by the database, so exactly one responder is ever dispatched to an incident.",
  },
  cancelled: {
    icon: "✕",
    title: "Request withdrawn",
    body: "The person who raised this cancelled it. Nobody needs to attend.",
    note: "Cancelling is recorded as its own outcome, not as a resolution — it does not count as help having arrived.",
  },
  no_responder_found: {
    icon: "📞",
    title: "Search ended",
    body: "Nobody accepted within 3 km, so this incident was escalated to emergency services.",
    note: "Your alert stayed open the whole time. The search widening does not withdraw it — it adds responders.",
  },
};

function showAlertClosed(reason) {
  const copy = CLOSED_COPY[reason] ?? CLOSED_COPY.accepted;
  announce(`${copy.title}. ${copy.body}`);
  el("closed-icon").textContent = copy.icon;
  el("closed-title").textContent = copy.title;
  el("closed-body").textContent = copy.body;
  el("closed-note").textContent = copy.note;
  showAlertView("handled");
}

function closeAlert() {
  releaseFocus?.();
  releaseFocus = null;
  el("alert-overlay").hidden = true;
  if (elapsedTimer) clearInterval(elapsedTimer);
  elapsedTimer = null;
  currentAlert = null;
}

/* Elapsed since the alert reached us, ticking locally. Not a countdown: the
 * accept timeout expands the radius and alerts more responders, and this
 * responder's alert stays open throughout (ADR-012). */
function startElapsed(since) {
  if (elapsedTimer) clearInterval(elapsedTimer);
  const tick = () => {
    const seconds = Math.max(0, Math.round((Date.now() - since) / 1000));
    el("alert-elapsed").textContent =
      seconds < 5 ? "Alerted just now" : `Alerted ${duration(seconds)} ago`;
  };
  tick();
  elapsedTimer = setInterval(tick, 1000);
}

function openAlert(payload) {
  currentAlert = payload;
  el("alert-category").textContent = payload.ai_category || "Unspecified emergency";
  el("alert-description").textContent = payload.description || "No description provided";
  el("alert-distance").textContent = formatDistance(payload.distance_m);
  el("alert-message").hidden = true;
  el("alert-accept").disabled = false;
  el("alert-decline").disabled = false;
  showAlertView("incoming");
  startElapsed(Date.parse(payload.created_at) || Date.now());

  // Assertive: an emergency alert is the one thing in this product that has
  // earned the right to interrupt whatever a screen reader was saying.
  announce(
    `Incoming emergency alert, ${formatDistance(payload.distance_m)} away. ` +
      `${payload.ai_category || "Unspecified emergency"}.`,
    "assertive"
  );

  if (leafletAvailable() && !alertMap) {
    alertMap = createMap(el("alert-map"), { lat: payload.lat, lng: payload.lng, zoom: 14 });
  }
  if (alertMap) {
    alertMap.setView([payload.lat, payload.lng], 14);
    incidentMarker(alertMap, payload);
    setTimeout(() => alertMap.invalidateSize(), 50);
  }
}

function alertMessage(text, kind) {
  const node = el("alert-message");
  node.textContent = text;
  node.className = `toast toast--${kind}`;
  node.hidden = false;
}

async function acceptCurrent() {
  if (!currentAlert) return;
  el("alert-accept").disabled = true;
  el("alert-decline").disabled = true;

  try {
    const result = await api.acceptSos(currentAlert.sos_id);
    if (result.accepted) {
      alertMessage("Assigned to you — head to the incident.", "success");
      const id = currentAlert.sos_id;
      setTimeout(() => { location.href = `/app/volunteer/assignment.html?sos=${id}`; }, 900);
    } else {
      // The accept-lock refused a second claim. Its own screen, not a toast
      // that fades: being second is the expected outcome for every responder
      // but one, and it deserves the explanation.
      showAlertClosed("accepted");
    }
  } catch (error) {
    alertMessage(error.detail || error.message, "error");
    el("alert-decline").disabled = false;
  }
}

async function declineCurrent() {
  if (currentAlert) await api.declineSos(currentAlert.sos_id).catch(() => {});
  closeAlert();
}

/* ---- boot --------------------------------------------------------------- */

const PREVIEWS = ["incoming", "handled"];

/* Preview runs before the auth check, matching the citizen view.
 *
 * It used to run after, which made these two screens unreachable for anyone
 * not signed in AS A VOLUNTEER -- an admin opening them was bounced to login on
 * a role mismatch, so the one person rehearsing the demo was the one person who
 * could not see them.
 *
 * The accept and decline handlers are deliberately NOT wired here. mockAlert
 * carries `sos_id: 128`, which is a real id: a signed-in volunteer pressing
 * ACCEPT on a preview screen would have claimed live incident 128. A preview
 * must not be able to reach the dispatch engine at all.
 */
function bootPreview(name) {
  initNav();
  el("user-name").textContent = "Preview";
  el("user-initials").textContent = "P";
  el("conn-pill").textContent = "preview";
  renderRecent();
  renderBadges();

  el("preview-switch").hidden = false;
  el("preview-select").value = name;
  el("preview-select").addEventListener("change", (event) => {
    location.search = event.target.value ? `?preview=${event.target.value}` : "";
  });

  el("alert-dismiss").addEventListener("click", closeAlert);
  for (const id of ["alert-accept", "alert-decline"]) {
    el(id).disabled = true;
    el(id).title = "Disabled in preview — this screen cannot reach the dispatch engine";
  }

  if (name === "incoming") openAlert(mockAlert);
  if (name === "handled") showAlertClosed("accepted");

  // openAlert re-enables the buttons for the live path, so disable again after.
  if (name === "incoming") {
    for (const id of ["alert-accept", "alert-decline"]) el(id).disabled = true;
  }
}

async function boot() {
  if (preview && PREVIEWS.includes(preview)) {
    bootPreview(preview);
    return;
  }

  const user = requireAuth("volunteer");
  if (!user) return;

  el("user-name").textContent = user.name;
  el("user-initials").textContent = initials(user.name);
  initNav();
  renderRecent();
  renderBadges();

  el("availability").addEventListener("change", onAvailabilityChange);

  // Render from the server rather than from a default. The switch must open
  // showing what the dispatcher believes, not what this page assumes.
  try {
    const state = await api.volunteerMe();
    renderVolunteerState(state);
    if (state.availability) startRefreshing();
  } catch (error) {
    availabilityError(`Could not read your availability: ${error.detail || error.message}`);
  }

  el("alert-accept").addEventListener("click", acceptCurrent);
  el("alert-decline").addEventListener("click", declineCurrent);
  el("alert-dismiss").addEventListener("click", closeAlert);

  // The switcher is offered on the live page too, so a rehearsal can jump into
  // a preview from here. Selecting one reloads into `bootPreview`.
  el("preview-switch").hidden = false;
  el("preview-select").value = "";
  el("preview-select").addEventListener("change", (event) => {
    location.search = event.target.value ? `?preview=${event.target.value}` : "";
  });

  el("logout").addEventListener("click", (event) => {
    event.preventDefault();
    auth.clear();
    location.href = "/app/login.html";
  });

  const channel = new RealtimeChannel(user.id);
  channel.addEventListener("ready", () => { el("conn-pill").textContent = "online"; });
  channel.addEventListener("offline", () => { el("conn-pill").textContent = "reconnecting…"; });
  channel.addEventListener("unauthorized", () => { location.href = "/app/login.html"; });
  channel.addEventListener("sos_alert", (event) => openAlert(event.detail));

  // The incident stopped being available while this alert was open (ADR-027).
  // Until this existed a responder found out by pressing ACCEPT and losing --
  // the modal simply sat there, offering a choice that no longer existed.
  channel.addEventListener("alert_closed", (event) => {
    if (!currentAlert || event.detail.sos_id !== currentAlert.sos_id) return;
    showAlertClosed(event.detail.reason);
  });
  channel.connect();
}

boot();
