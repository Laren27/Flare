/* Volunteer dashboard -- screen 5, plus the live incoming alert of screen 3.
 *
 * The alert path is real: it arrives on the WebSocket opened per ADR-022, and
 * ACCEPT hits the conditional UPDATE of ADR-011. Losing the race renders the
 * "already handled" state rather than an error, because being second is a
 * correct outcome, not a client mistake.
 *
 * Stats and badges are sample data -- there is no responder-history query yet
 * (week 6), and the page says so rather than implying the numbers were measured.
 */

import { api, auth, initials, requireAuth } from "../shared/api.js";
import { RealtimeChannel } from "../shared/ws.js";
import { createMap, formatDistance, incidentMarker, leafletAvailable } from "../shared/map.js";
import { initNav } from "../shared/nav.js";
import { mockBadges, mockRecentAlerts, mockVolunteerStats } from "../shared/mock.js";

const el = (id) => document.getElementById(id);
let currentAlert = null;
let alertMap = null;

/* ---- static panels ------------------------------------------------------ */

function renderStats() {
  el("stat-responses").textContent = mockVolunteerStats.totalResponses;
  el("stat-lives").textContent = mockVolunteerStats.livesImpacted;
  el("stat-rating").textContent = `${mockVolunteerStats.rating} ★`;
}

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
  el("recent-note").textContent = "Sample data — responder history queries arrive in week 6.";
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

function openAlert(payload) {
  currentAlert = payload;
  el("alert-category").textContent = payload.ai_category || "Unspecified emergency";
  el("alert-description").textContent = payload.description || "No description provided";
  el("alert-distance").textContent = formatDistance(payload.distance_m);
  el("alert-message").hidden = true;

  el("alert-skills").innerHTML = payload.ai_category
    ? '<span class="chip">CPR</span><span class="chip chip--info">First Aid</span>'
    : '<span class="chip chip--info">Any responder</span>';

  el("alert-accept").disabled = false;
  el("alert-decline").disabled = false;
  el("alert-overlay").hidden = false;

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
      setTimeout(() => {
        location.href = `/app/volunteer/alert.html?view=accepted&sos=${currentAlert.sos_id}`;
      }, 900);
    } else {
      // The accept-lock refused a second claim. Not an error.
      alertMessage("Already handled — another responder accepted first.", "info");
      setTimeout(() => { el("alert-overlay").hidden = true; }, 1800);
    }
  } catch (error) {
    alertMessage(error.detail || error.message, "error");
    el("alert-decline").disabled = false;
  }
}

async function declineCurrent() {
  if (currentAlert) await api.declineSos(currentAlert.sos_id).catch(() => {});
  el("alert-overlay").hidden = true;
  currentAlert = null;
}

/* ---- boot --------------------------------------------------------------- */

function boot() {
  const user = requireAuth("volunteer");
  if (!user) return;

  el("user-name").textContent = user.name;
  el("user-initials").textContent = initials(user.name);
  initNav();
  renderStats();
  renderRecent();
  renderBadges();

  el("availability").addEventListener("change", (event) => {
    // PATCH /volunteers/availability is week 6; the control is wired to its own
    // label only, and is not pretending to have changed anything server-side.
    el("availability-text").textContent = event.target.checked ? "Online" : "Offline";
  });

  el("alert-accept").addEventListener("click", acceptCurrent);
  el("alert-decline").addEventListener("click", declineCurrent);
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
  channel.connect();
}

boot();
