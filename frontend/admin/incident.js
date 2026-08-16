/* One incident, and every dispatch decision made about it.
 *
 * This is the reader ADR-014 was written for. The event log has recorded why
 * each candidate was or was not selected since week 2, and nothing has ever
 * shown it -- so "why didn't responder X get alerted?" was answerable only by
 * opening psql. That is the question this page exists to answer on screen.
 *
 * Rejection reasons are given their plain-English meaning rather than printed
 * raw. `no_location` versus `unavailable` is the distinction ADR-021 went out
 * of its way to preserve, and it is worth nothing if the interface renders both
 * as lowercase enum values and leaves the reader to guess.
 */

import { api } from "../shared/api.js";
import { duration, formatDistance, latency } from "../shared/format.js";
import { renderEmpty, renderError } from "../shared/states.js";
import { bootAdmin, el, num, table } from "./shared.js";

const sosId = Number(new URLSearchParams(location.search).get("id"));
let allEvents = [];
let alertedOnly = false;

const REASON_TEXT = {
  out_of_radius: "Too far — outside the radius at that wave",
  unavailable: "Offline — had not gone on duty",
  unverified: "Not verified — an admin has not approved them",
  already_alerted: "Already held an open alert from an earlier wave",
  no_socket: "Selected, but no live connection to deliver to",
  no_location: "Never reported a position, so no distance could be computed",
};

const STATUS_PILL = {
  matched: "pill--success",
  pending: "pill--warn",
  resolved: "pill--info",
  cancelled: "pill--muted",
  no_responder_found: "pill--live",
};

function row(label, value) {
  return `<div class="list__row">
    <span class="small muted">${label}</span>
    <span class="spacer"></span>
    <span class="small strong">${value}</span>
  </div>`;
}

function renderSummary(d) {
  const i = d.incident;
  const pill = STATUS_PILL[i.status] ?? "";
  el("page-title").textContent = `Incident #${i.id}`;

  el("summary").innerHTML = [
    row("Status", `<span class="pill ${pill}">${i.status.replace(/_/g, " ")}</span>`),
    row("Reported", i.description || "<span class='muted'>no description given</span>"),
    row("Category", (i.ai_category || "unspecified").replace(/_/g, " ")),
    // ai_status is shown next to the category on purpose: a category is worth
    // less if the call that produced it degraded, and the two belong together.
    row("AI", `${i.ai_status}${i.ai_priority ? ` · ${i.ai_priority}` : ""}`),
    row("Location", `${i.lat.toFixed(5)}, ${i.lng.toFixed(5)}`),
    row("Final radius", `${i.current_radius_m} m`),
    row("Waves", String(i.wave_count)),
    row("Assigned to", i.accepted_by ? `Responder #${i.accepted_by}` : "—"),
  ].join("");
}

function renderTimeline(d) {
  const t = d.timings;
  const h = d.history;

  const rows = [
    row(
      "To first dispatch",
      t.to_first_dispatch_seconds === null ? "—" : latency(t.to_first_dispatch_seconds)
    ),
    row(
      "To acceptance",
      t.to_acceptance_seconds === null ? "—" : duration(t.to_acceptance_seconds)
    ),
    row(
      "To resolution",
      t.to_resolution_seconds === null ? "—" : duration(t.to_resolution_seconds)
    ),
  ];

  if (h) {
    rows.push(
      row("Escalations", String(h.escalation_count)),
      row("Escalation trigger", h.escalation_trigger.replace(/_/g, " "))
    );
  } else {
    // Absent for pending incidents and for cancellations (ADR-025), which is a
    // fact about the outcome rather than missing data.
    rows.push(
      row(
        "Incident history",
        "<span class='muted'>not written — the incident has no system-produced conclusion</span>"
      )
    );
  }

  el("timeline").innerHTML = rows.join("");
}

function renderWaves(d) {
  if (!d.waves.length) {
    renderEmpty(el("waves"), "No candidate was ever evaluated for this incident.");
    return;
  }

  el("waves").innerHTML = d.waves
    .map((w) => {
      const rejections = Object.entries(w.rejections)
        .sort((a, b) => b[1] - a[1])
        .map(
          ([reason, count]) =>
            `<span class="pill pill--muted" title="${REASON_TEXT[reason] ?? reason}">
               ${reason.replace(/_/g, " ")} ${count}
             </span>`
        )
        .join(" ");

      return `<div class="card" style="box-shadow:none">
        <div class="row row--between">
          <div>
            <span class="strong">Wave ${w.wave_number}</span>
            <span class="small muted"> at ${w.radius_m} m</span>
          </div>
          <div class="small">
            <span class="strong numeric">${w.alerted}</span> alerted of
            <span class="numeric">${w.evaluated}</span> evaluated
          </div>
        </div>
        <div class="row row--tight mt-2">${rejections || '<span class="tiny muted">no rejections</span>'}</div>
      </div>`;
    })
    .join("");
}

function renderEvents() {
  const events = alertedOnly
    ? allEvents.filter((e) => e.outcome === "alerted")
    : allEvents;

  el("events-table").innerHTML = table(
    ["Wave", "Responder", "Distance", "Skill", "Outcome", "Why"],
    events.map((e) => [
      e.wave_number,
      `${e.volunteer_name} <span class="tiny muted">#${e.volunteer_id}</span>`,
      e.distance_m === null
        ? '<span class="muted">—</span>'
        : formatDistance(num(e.distance_m)),
      e.skill_match ? '<span class="chip">top tier</span>' : '<span class="tiny muted">—</span>',
      e.outcome === "alerted"
        ? '<span class="pill pill--success">alerted</span>'
        : '<span class="pill pill--muted">rejected</span>',
      e.rejection_reason
        ? `<span title="${e.rejection_reason}">${REASON_TEXT[e.rejection_reason] ?? e.rejection_reason}</span>`
        : "—",
    ])
  );
}

function renderNotifications(d) {
  if (!d.notifications.length) {
    renderEmpty(
      el("notifications-table"),
      "No alert was delivered — nobody had a live connection when this dispatched."
    );
    return;
  }

  const pill = {
    accepted: "pill--success",
    declined: "pill--warn",
    dismissed: "pill--muted",
    sent: "pill--info",
  };

  el("notifications-table").innerHTML = table(
    ["Wave", "Responder", "Outcome", "Answered after"],
    d.notifications.map((n) => [
      n.wave_number,
      `${n.volunteer_name} <span class="tiny muted">#${n.volunteer_id}</span>`,
      `<span class="pill ${pill[n.status] ?? ""}">${n.status}</span>`,
      n.responded_at
        ? duration((Date.parse(n.responded_at) - Date.parse(n.sent_at)) / 1000)
        : '<span class="muted">no answer</span>',
    ])
  );
}

async function boot() {
  if (!bootAdmin()) return;

  if (!sosId) {
    renderError(el("detail-error"), "No incident id in the address.");
    el("detail-error").hidden = false;
    return;
  }

  let detail;
  try {
    detail = await api.adminIncident(sosId);
  } catch (error) {
    el("detail-error").hidden = false;
    renderError(
      el("detail-error"),
      "Could not load this incident.",
      error.detail || error.message
    );
    return;
  }

  allEvents = detail.events;
  el("detail").hidden = false;

  renderSummary(detail);
  renderTimeline(detail);
  renderWaves(detail);
  renderEvents();
  renderNotifications(detail);

  el("filter-toggle").addEventListener("click", (event) => {
    alertedOnly = !alertedOnly;
    event.target.textContent = alertedOnly ? "Show all evaluated" : "Alerted only";
    renderEvents();
  });
}

boot();
