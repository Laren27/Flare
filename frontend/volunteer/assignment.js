/* The screen a responder sees after winning an incident.
 *
 * This replaces the `view=accepted` panel of the old alert page, which was a
 * terminal card with a dead "Navigate to incident" anchor. What a responder
 * actually needs after accepting is where the incident is, what was reported,
 * a way to get there, and a way to close it -- so those are the four things
 * here and there is nothing else.
 *
 * GET /sos/{id} permits the victim, the assigned responder and admins, so this
 * page reads the incident directly rather than being handed it through a URL.
 * That also means a responder who did not win cannot open somebody else's
 * assignment by editing the address bar -- the server refuses with 403.
 */

import { api, auth, requireAuth } from "../shared/api.js";
import { initials } from "../shared/format.js";
import { createMap, incidentMarker, leafletAvailable, showFallback } from "../shared/map.js";
import { initNav } from "../shared/nav.js";

const el = (id) => document.getElementById(id);
const sosId = Number(new URLSearchParams(location.search).get("sos"));

function fail(message) {
  el("assignment-error").textContent = message;
  el("assignment-error").hidden = false;
  el("live-pill").hidden = true;
}

function showClosed(title, body, icon) {
  el("assignment").hidden = true;
  el("closed").hidden = false;
  el("live-pill").hidden = true;
  el("closed-title").textContent = title;
  el("closed-body").textContent = body;
  el("closed-icon").textContent = icon;
}

function renderIncident(sos) {
  // Terminal states are not assignments. Reaching this page for one means the
  // incident ended while the responder was on their way, and saying so plainly
  // beats rendering a live-looking screen for something that is over.
  if (sos.status === "resolved") {
    showClosed("Incident resolved", "This incident has been closed.", "✓");
    return;
  }
  if (sos.status === "cancelled") {
    showClosed(
      "Request withdrawn",
      "The person who raised this cancelled it. No further action is needed.",
      "✕"
    );
    return;
  }

  el("assignment").hidden = false;
  el("category").textContent = sos.ai_category
    ? sos.ai_category.replace(/_/g, " ")
    : "Unspecified emergency";
  el("description").textContent = sos.description || "No description was given.";
  el("coords").textContent = `${sos.lat.toFixed(5)}, ${sos.lng.toFixed(5)}`;
  el("open-maps").href =
    `https://www.google.com/maps/search/?api=1&query=${sos.lat},${sos.lng}`;

  const element = el("map");
  if (!leafletAvailable()) {
    showFallback(element, "Map unavailable — the coordinates above still work");
    return;
  }
  const map = createMap(element, { lat: sos.lat, lng: sos.lng, zoom: 16 });
  incidentMarker(map, sos);
}

async function resolveIncident() {
  const button = el("resolve-button");
  button.disabled = true;
  try {
    renderIncident(await api.resolveSos(sosId));
  } catch (error) {
    fail(error.detail || error.message);
    button.disabled = false;
  }
}

async function boot() {
  const user = requireAuth("volunteer");
  if (!user) return;

  el("user-initials").textContent = initials(user.name);
  initNav();

  el("logout").addEventListener("click", (event) => {
    event.preventDefault();
    auth.clear();
    location.href = "/app/login.html";
  });

  if (!sosId) {
    fail("No incident was named in the address. Open this from an alert you accepted.");
    return;
  }

  el("resolve-button").addEventListener("click", resolveIncident);

  try {
    renderIncident(await api.getSos(sosId));
  } catch (error) {
    // 403 here means the accept-lock gave this incident to somebody else.
    fail(
      error.status === 403
        ? "This incident is not assigned to you."
        : error.detail || error.message
    );
  }
}

boot();
