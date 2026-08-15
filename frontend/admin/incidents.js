/* Admin incidents table.
 *
 * Live against GET /admin/incidents. A snapshot, not a feed: alerts are pushed
 * to the selected volunteers only (`sos_alert` in services/notifications.py),
 * and nothing broadcasts to admins, so claiming a live table here would be
 * claiming a channel that does not exist. The page says so instead.
 */

import { api } from "../shared/api.js";
import { renderEmpty, renderError } from "../shared/states.js";
import { bootAdmin, el } from "./shared.js";

const STATUS_PILL = {
  matched: "pill--success",
  pending: "pill--warn",
  resolved: "pill--info",
  // Neutral on purpose (ADR-025). A withdrawn request is not a failure of the
  // dispatch engine, and colouring it as one would read as a fault where none
  // occurred.
  cancelled: "pill--muted",
  no_responder_found: "pill--live",
};

function renderIncidents(incidents) {
  el("incident-count").textContent = `${incidents.length} shown`;

  if (!incidents.length) {
    renderEmpty(
      el("incidents-table"),
      "No incidents recorded yet.",
      "Trigger an SOS, or seed a corpus with sim/scenarios/coverage.py."
    );
    return;
  }

  el("incidents-table").innerHTML = `
    <thead><tr><th>#</th><th>Category</th><th>Status</th><th>Radius</th><th>Waves</th><th>AI</th><th>Created</th></tr></thead>
    <tbody>${incidents
      .map(
        (i) => `<tr>
          <td class="strong numeric">${i.id}</td>
          <td>${(i.ai_category || "unspecified").replace(/_/g, " ")}</td>
          <td><span class="pill ${STATUS_PILL[i.status] ?? ""}">${i.status.replace(/_/g, " ")}</span></td>
          <td class="numeric">${i.current_radius_m} m</td>
          <td class="numeric">${i.wave_count}</td>
          <td class="tiny muted">${i.ai_status}</td>
          <td class="tiny muted numeric">${new Date(i.created_at).toLocaleString()}</td>
        </tr>`
      )
      .join("")}</tbody>`;
}

async function boot() {
  if (!bootAdmin()) return;

  try {
    renderIncidents(await api.adminIncidents());
  } catch (error) {
    el("incident-count").textContent = "unavailable";
    // Distinct from the empty state on purpose: a failed request and an empty
    // table are different facts, and reading one as the other sends you looking
    // in the wrong place.
    renderError(
      el("incidents-table"),
      "Could not load incidents.",
      error.detail || error.message
    );
  }
}

boot();
