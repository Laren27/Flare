/* Citizen view -- screens 2, 6, 7 and 8 as states of one page.
 *
 * Live against the dispatch engine: POST /sos really dispatches, and the
 * status the page renders is polled from GET /sos/{id}. The escalation states
 * are real -- they appear because the ADR-012 state machine actually widened
 * the radius, not because a timer here pretended it did.
 *
 * `?state=` forces a state with fixture data, because reviewing the
 * no-responder-found screen should not require waiting out three 30s rungs.
 */

import { api, auth, currentPosition, initials, requireAuth } from "../shared/api.js";
import { RealtimeChannel } from "../shared/ws.js";
import {
  createMap,
  etaMinutes,
  formatDistance,
  incidentMarker,
  leafletAvailable,
  radiusCircles,
  responderMarker,
  showFallback,
} from "../shared/map.js";
import { initNav } from "../shared/nav.js";
import { CENTRE, mockIncident, mockResponder } from "../shared/mock.js";

const STATES = ["idle", "active", "expanding", "none"];
const POLL_MS = 2000;
const STEP_LABELS = ["SOS Sent", "Alerting Volunteers", "Responder Assigned", "On the Way", "Help Arrived"];

const el = (id) => document.getElementById(id);
const forcedState = new URLSearchParams(location.search).get("state");

let user = null;
let position = null;
let incident = null;
let pollTimer = null;
let startedAt = null;
let map = null;
let markers = { incident: null, responder: null, circles: [] };

/* ---- state rendering --------------------------------------------------- */

function showState(name) {
  for (const state of STATES) {
    el(`state-${state}`).hidden = state !== name;
  }
  el("live-pill").hidden = !(name === "active" || name === "expanding");
  el("page-title").textContent =
    name === "active" ? "Emergency in Progress"
    : name === "expanding" ? "Searching for a responder"
    : name === "none" ? "No responder found"
    : "Emergency";
}

function renderSteps(stage) {
  el("steps").innerHTML = STEP_LABELS.map((label, index) => {
    const state = index < stage ? "done" : index === stage ? "current" : "";
    return `
      <div class="step ${state ? `step--${state}` : ""}">
        <span class="step__dot">${index < stage ? "✓" : index + 1}</span>
        <span>${label}</span>
        ${index < STEP_LABELS.length - 1 ? '<span class="step__line"></span>' : ""}
      </div>`;
  }).join("");
}

/* ---- map --------------------------------------------------------------- */

function ensureMap(centre) {
  if (map) return map;
  const element = el("map");
  if (!leafletAvailable()) {
    showFallback(element, "Map unavailable — check your connection");
    return null;
  }
  map = createMap(element, { ...centre, zoom: 15 });
  return map;
}

function drawIncident(centre, radiusM) {
  if (!ensureMap(centre)) return;
  markers.circles.forEach((circle) => circle.remove());
  markers.circles = radiusCircles(map, centre, radiusM);
  if (!markers.incident) markers.incident = incidentMarker(map, centre);
}

function drawResponder(point, label, centre) {
  if (!map) return;
  markers.responder?.remove();
  markers.responder = responderMarker(map, point, label);
  const badge = el("map-badge");
  const distance = window.L.latLng(point.lat, point.lng)
    .distanceTo(window.L.latLng(centre.lat, centre.lng));
  badge.textContent = `ETA ${etaMinutes(distance)} min · ${formatDistance(distance)}`;
  badge.hidden = false;
  map.fitBounds(
    window.L.latLngBounds([point.lat, point.lng], [centre.lat, centre.lng]).pad(0.45)
  );
}

/* ---- live incident ----------------------------------------------------- */

function renderIncident(sos) {
  incident = sos;
  const centre = { lat: sos.lat ?? position.lat, lng: sos.lng ?? position.lng };

  if (sos.status === "matched") {
    showState("active");
    renderSteps(2);
    el("active-status").textContent = "✓ Responder Assigned";
    el("incident-location").textContent = `${centre.lat.toFixed(4)}, ${centre.lng.toFixed(4)}`;
    el("incident-type").textContent = sos.ai_category || "Unspecified";
    drawIncident(centre, sos.current_radius_m);
    // Responder live location is not built (Ch. 26) -- nothing pushes the
    // responder's position to the citizen's socket, so the assignment itself is
    // what is real here.
    el("responder-name").textContent = `Responder #${sos.accepted_by}`;
    el("responder-initials").textContent = "R";
    el("responder-rating").textContent = "—";
    el("eta-text").textContent = "Responder en route";
    return;
  }

  if (sos.status === "no_responder_found") {
    showState("none");
    stopPolling();
    return;
  }

  if (sos.status === "resolved") {
    showState("idle");
    stopPolling();
    return;
  }

  // pending
  showState("expanding");
  el("expand-radius").textContent = `${sos.current_radius_m} m`;
  el("expand-wave").textContent = sos.wave_count;
  el("rings-label").textContent = `${(sos.current_radius_m / 1000).toFixed(0)} km`;
  const index = [1000, 2000, 3000].indexOf(sos.current_radius_m);
  el("rings").querySelectorAll("span").forEach((ring, i) => {
    ring.classList.toggle("is-active", i === Math.max(0, index));
  });
  if (startedAt) {
    el("expand-elapsed").textContent = `${Math.round((Date.now() - startedAt) / 1000)}s`;
  }
}

function startPolling(id) {
  stopPolling();
  pollTimer = setInterval(async () => {
    try {
      renderIncident(await api.getSos(id));
    } catch {
      /* transient; the next tick retries */
    }
  }, POLL_MS);
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

/* ---- actions ----------------------------------------------------------- */

async function triggerSos() {
  const button = el("sos-button");
  button.disabled = true;
  el("idle-error").hidden = true;

  try {
    if (!position) position = await currentPosition();
    const sos = await api.createSos(position.lat, position.lng, null);
    startedAt = Date.now();
    renderIncident({ ...sos, lat: position.lat, lng: position.lng });
    startPolling(sos.id);
  } catch (error) {
    el("idle-error").textContent = error.detail || error.message;
    el("idle-error").hidden = false;
  } finally {
    button.disabled = false;
  }
}

/* ---- forced preview states --------------------------------------------- */

function renderMockState(name) {
  el("state-switch").hidden = false;
  el("state-select").value = name;
  showState(name);

  if (name === "active") {
    renderSteps(2);
    el("responder-name").textContent = mockResponder.name;
    el("responder-initials").textContent = initials(mockResponder.name);
    el("responder-rating").textContent = mockResponder.rating.toFixed(1);
    el("eta-text").textContent = `${etaMinutes(mockResponder.distance_m)} min (${formatDistance(mockResponder.distance_m)} away)`;
    el("incident-type").textContent = "Cardiac Arrest";
    el("incident-location").textContent = "MG Road, Bangalore";
    drawIncident(CENTRE, mockIncident.current_radius_m);
    drawResponder(mockResponder, initials(mockResponder.name), CENTRE);
  }

  if (name === "expanding") {
    el("expand-radius").textContent = "2000 m";
    el("expand-wave").textContent = "2";
    el("expand-elapsed").textContent = "34s";
    el("rings-label").textContent = "2 km";
    el("rings").querySelectorAll("span")[1].classList.add("is-active");
  }
}

/* ---- boot -------------------------------------------------------------- */

function wireStateSwitch() {
  el("state-switch").hidden = false;
  el("state-select").addEventListener("change", (event) => {
    const value = event.target.value;
    location.search = value ? `?state=${value}` : "";
  });
}

async function boot() {
  // Before the preview-state early return: the sidebar exists on every
  // path, so its behaviour has to be wired on every path.
  initNav();
  el("state-select").value = forcedState ?? "";

  if (forcedState && STATES.includes(forcedState)) {
    el("user-name").textContent = "Preview";
    el("user-initials").textContent = "P";
    el("conn-pill").textContent = "preview";
    wireStateSwitch();
    renderMockState(forcedState);
    return;
  }

  user = requireAuth("citizen");
  if (!user) return;

  el("user-name").textContent = user.name;
  el("user-initials").textContent = initials(user.name);
  wireStateSwitch();
  showState("idle");

  el("sos-button").addEventListener("click", triggerSos);
  el("restart-button").addEventListener("click", () => location.reload());
  el("cancel-button").addEventListener("click", async () => {
    if (incident) await api.resolveSos(incident.id).catch(() => {});
    location.reload();
  });
  el("logout").addEventListener("click", (event) => {
    event.preventDefault();
    auth.clear();
    location.href = "/app/login.html";
  });

  currentPosition()
    .then((point) => {
      position = point;
      el("location-note").textContent =
        `Location ready — ${point.lat.toFixed(4)}, ${point.lng.toFixed(4)}`;
    })
    .catch((error) => {
      // Honest, not silent: without a location there is nothing to dispatch on.
      position = null;
      el("location-note").textContent = error.message;
    });

  const channel = new RealtimeChannel(user.id);
  channel.addEventListener("ready", () => { el("conn-pill").textContent = "connected"; });
  channel.addEventListener("offline", () => { el("conn-pill").textContent = "reconnecting…"; });
  channel.connect();
}

boot();
