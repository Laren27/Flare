/* Admin dashboard -- the Chapter 18A metrics that describe the dispatch loop.
 *
 * Every figure is fetched from /admin/analytics, which executes a named .sql
 * file per metric. Each card shows the filename that produced its numbers,
 * because Ch. 18A's rule is that a figure which cannot be traced to a query
 * does not ship -- and printing the filename is what makes that checkable from
 * the dashboard rather than from the source tree.
 *
 * Coverage gaps live on their own page: the grid is the one panel that wants
 * width, and it answers a different question (where to recruit) from the rest
 * of this page (how the loop is performing).
 */

import { renderEmpty } from "../shared/states.js";
import {
  CATEGORICAL,
  OTHER,
  bootAdmin,
  duration,
  el,
  latency,
  loadAnalytics,
  num,
  pct,
  svg,
  table,
  trace,
  wireTableToggles,
} from "./shared.js";

/* ---- stat tiles --------------------------------------------------------- */

function renderStats(m) {
  const funnel = m.dispatch_funnel.rows;
  const created = num(funnel.find((r) => r.stage === "SOS created")?.count);
  const alerted = num(funnel.find((r) => r.stage === "Alerted")?.count);
  const accepted = num(funnel.find((r) => r.stage === "Accepted")?.count);
  const acceptance = m.time_to_acceptance.rows[0] ?? {};
  const noEscalation = num(
    m.escalation_rate.rows.find((r) => r.trigger === "none")?.share
  );

  const stats = [
    { label: "Total Incidents", value: String(created), note: "in window" },
    { label: "Time to Acceptance (p90)", value: duration(acceptance.p90_seconds), note: "tail, not mean" },
    { label: "Acceptance Rate", value: alerted ? pct(accepted / alerted) : "—", note: "accepted ÷ alerted" },
    { label: "Escalation Rate", value: pct(1 - noEscalation), note: "needed expansion" },
  ];

  el("stats").innerHTML = stats
    .map(
      (s) => `
      <div class="stat">
        <div class="stat__label">${s.label}</div>
        <div class="stat__value">${s.value}</div>
        <div class="stat__delta muted">${s.note}</div>
      </div>`
    )
    .join("");
}

/* ---- time-to-acceptance histogram --------------------------------------- */

function renderAcceptance(m) {
  const data = m.time_to_acceptance_histogram.rows.map((r) => ({
    bucket: r.bucket,
    count: num(r.count),
  }));
  const summary = m.time_to_acceptance.rows[0] ?? {};

  el("p50").textContent = duration(summary.p50_seconds);
  el("p90").textContent = duration(summary.p90_seconds);
  el("pmax").textContent = duration(summary.max_seconds);
  trace("acceptance-trace", m.time_to_acceptance_histogram.query_file);

  if (!data.length) {
    renderEmpty(el("acceptance-chart"), "No incident has been accepted in this window.");
    return;
  }

  const W = 460, H = 190;
  const pad = { top: 18, right: 8, bottom: 30, left: 8 };
  const plotH = H - pad.top - pad.bottom;
  const max = Math.max(...data.map((d) => d.count), 1);
  const slot = (W - pad.left - pad.right) / data.length;
  const barW = slot - 6;

  const bars = data
    .map((d, i) => {
      const h = Math.max(3, (d.count / max) * plotH);
      const x = pad.left + i * slot + 3;
      const y = pad.top + plotH - h;
      return `
        <g class="mark"><title>${d.bucket}: ${d.count} incidents</title>
          <rect x="${x}" y="${y}" width="${barW}" height="${h}" rx="4" fill="${CATEGORICAL[0]}"/>
          <text class="value" x="${x + barW / 2}" y="${y - 5}" text-anchor="middle" font-size="11">${d.count}</text>
          <text x="${x + barW / 2}" y="${H - 10}" text-anchor="middle" font-size="10">${d.bucket}</text>
        </g>`;
    })
    .join("");

  el("acceptance-chart").innerHTML = `${svg(W, H, 'aria-label="Time to acceptance distribution"')}
    <line x1="${pad.left}" y1="${pad.top + plotH}" x2="${W - pad.right}" y2="${pad.top + plotH}"
          stroke="#e2e8f0" stroke-width="1"/>${bars}</svg>`;

  el("acceptance-table").innerHTML = table(["Bucket", "Incidents"], data.map((d) => [d.bucket, d.count]));
}

/* ---- time to first dispatch --------------------------------------------- */

function renderFirstDispatch(m) {
  const row = m.time_to_first_dispatch.rows[0] ?? {};
  const accepted = m.time_to_acceptance.rows[0] ?? {};
  trace("dispatch-trace", m.time_to_first_dispatch.query_file);

  const dispatched = num(row.dispatched_count);
  if (!dispatched) {
    renderEmpty(el("dispatch-body"), "No incident has been dispatched in this window.");
    return;
  }

  el("fd-count").textContent = dispatched;
  el("fd-p50").textContent = latency(row.p50_seconds);
  el("fd-p90").textContent = latency(row.p90_seconds);
  el("fd-max").textContent = latency(row.max_seconds);

  // Acceptance includes the time a human took to answer; this metric does not.
  // The difference is the human part, which is the comparison the metric exists
  // to support -- arithmetic on two displayed figures, and labelled as such on
  // the card rather than presented as a query result of its own.
  const acceptP90 = num(accepted.p90_seconds);
  el("fd-human").textContent = acceptP90
    ? duration(Math.max(0, acceptP90 - num(row.p90_seconds)))
    : "—";
}

/* ---- dispatch funnel ---------------------------------------------------- */

function renderFunnel(m) {
  const data = m.dispatch_funnel.rows.map((r) => ({ stage: r.stage, count: num(r.count) }));
  trace("funnel-trace", m.dispatch_funnel.query_file);
  if (!data.length) return;

  const W = 460, rowH = 34;
  const H = data.length * rowH + 8;
  const max = Math.max(data[0].count, 1);
  const labelW = 130;
  const barMax = W - labelW - 56;

  const rows = data
    .map((d, i) => {
      const w = Math.max(4, (d.count / max) * barMax);
      const y = i * rowH + 6;
      const dropped = i === 0 ? null : data[i - 1].count - d.count;
      return `
        <g class="mark"><title>${d.stage}: ${d.count}${dropped ? ` (−${dropped})` : ""}</title>
          <text x="0" y="${y + 15}" font-size="11">${d.stage}</text>
          <rect x="${labelW}" y="${y + 4}" width="${w}" height="16" rx="4" fill="${CATEGORICAL[2]}"/>
          <text class="value" x="${labelW + w + 8}" y="${y + 16}" font-size="11">${d.count}</text>
          ${dropped ? `<text x="${W - 4}" y="${y + 16}" text-anchor="end" font-size="10" fill="${CATEGORICAL[0]}">−${dropped}</text>` : ""}
        </g>`;
    })
    .join("");

  el("funnel-chart").innerHTML = `${svg(W, H, 'aria-label="Dispatch funnel"')}${rows}</svg>`;
  el("funnel-table").innerHTML = table(
    ["Stage", "Count", "Drop-off"],
    data.map((d, i) => [d.stage, d.count, i === 0 ? "—" : data[i - 1].count - d.count])
  );
}

/* ---- incidents by category (donut) -------------------------------------- */

function renderTypes(m) {
  const rows = m.incidents_by_category.rows;
  trace("types-trace", m.incidents_by_category.query_file);
  if (!rows.length) return;

  // Top four keep a categorical hue; the rest fold into a neutral "Other",
  // because a fifth generated hue is never the right answer.
  const top = rows.slice(0, 4).map((r) => ({ label: r.category, value: num(r.incidents) }));
  const restTotal = rows.slice(4).reduce((sum, r) => sum + num(r.incidents), 0);
  const data = restTotal ? [...top, { label: "other", value: restTotal }] : top;
  const total = data.reduce((sum, d) => sum + d.value, 0) || 1;

  const size = 170, r = 62, stroke = 22, c = size / 2;
  const circumference = 2 * Math.PI * r;
  const GAP = 3;

  let offset = 0;
  const segments = data
    .map((d, i) => {
      const colour = i < CATEGORICAL.length ? CATEGORICAL[i] : OTHER;
      const length = (d.value / total) * circumference;
      const dash = `${Math.max(0, length - GAP)} ${circumference - Math.max(0, length - GAP)}`;
      const seg = `
        <circle class="mark" cx="${c}" cy="${c}" r="${r}" fill="none"
                stroke="${colour}" stroke-width="${stroke}"
                stroke-dasharray="${dash}" stroke-dashoffset="${-offset}"
                transform="rotate(-90 ${c} ${c})">
          <title>${d.label}: ${d.value}</title>
        </circle>`;
      offset += length;
      return seg;
    })
    .join("");

  el("types-chart").innerHTML = `${svg(size, size, 'aria-label="Incidents by category"')}
    ${segments}
    <text x="${c}" y="${c - 2}" text-anchor="middle" class="value" font-size="22">${total}</text>
    <text x="${c}" y="${c + 14}" text-anchor="middle" font-size="10">Total</text></svg>`;

  el("types-legend").innerHTML = data
    .map(
      (d, i) => `<span class="legend__item">
        <span class="legend__swatch" style="background:${i < CATEGORICAL.length ? CATEGORICAL[i] : OTHER}"></span>
        ${d.label.replace(/_/g, " ")} <span class="strong">${d.value}</span></span>`
    )
    .join("");

  el("types-table").innerHTML = table(
    ["Category", "Incidents", "Share"],
    rows.map((r) => [r.category.replace(/_/g, " "), num(r.incidents), pct(r.share)])
  );
}

/* ---- escalation split --------------------------------------------------- */

function renderEscalation(m) {
  const order = ["none", "empty_set", "timeout"];
  const labels = {
    none: "No escalation",
    empty_set: "Empty set (condition A — too few responders)",
    timeout: "Timeout (condition B — unresponsive)",
  };
  const colours = { none: "#22C55E", empty_set: "#EF4444", timeout: "#F59E0B" };

  const rows = m.escalation_rate.rows;
  trace("escalation-trace", m.escalation_rate.query_file);
  const data = order
    .map((key) => {
      const row = rows.find((r) => r.trigger === key);
      return row ? { key, label: labels[key], count: num(row.count ?? row.incidents), expansions: row.mean_expansions } : null;
    })
    .filter(Boolean);
  const total = data.reduce((sum, d) => sum + d.count, 0) || 1;

  const W = 460, H = 132, barY = 18, barH = 26, GAP = 3;
  let x = 0;
  const segments = data
    .map((d) => {
      const w = (d.count / total) * W - GAP;
      const seg = `
        <g class="mark"><title>${d.label}: ${d.count} (${pct(d.count / total)})</title>
          <rect x="${x}" y="${barY}" width="${Math.max(2, w)}" height="${barH}" rx="4" fill="${colours[d.key]}"/>
        </g>`;
      x += w + GAP;
      return seg;
    })
    .join("");

  const legend = data
    .map(
      (d, i) => `<text x="0" y="${barY + barH + 22 + i * 17}" font-size="11">
        <tspan fill="${colours[d.key]}">●</tspan> ${d.label} — <tspan class="value">${d.count}</tspan>
      </text>`
    )
    .join("");

  el("escalation-chart").innerHTML =
    `${svg(W, H, 'aria-label="Escalation rate by trigger"')}${segments}${legend}</svg>`;

  el("escalation-table").innerHTML = table(
    ["Trigger", "Incidents", "Share", "Mean expansions"],
    data.map((d) => [d.label, d.count, pct(d.count / total), d.expansions ?? "—"])
  );
}

/* ---- acceptance rate by skill ------------------------------------------- */

function renderAcceptanceBySkill(m) {
  const rows = m.acceptance_rate.rows;
  trace("skill-trace", m.acceptance_rate.query_file);

  // Aggregate the radius bands: the headline question is whether skill class
  // changes acceptance, and the band split is a second cut available in the table.
  const bySkill = new Map();
  for (const row of rows) {
    const entry = bySkill.get(row.skill_class) ?? { alerted: 0, accepted: 0 };
    entry.alerted += num(row.alerted);
    entry.accepted += num(row.accepted);
    bySkill.set(row.skill_class, entry);
  }

  const data = [...bySkill.entries()]
    .map(([skill, v]) => ({ skill, rate: v.alerted ? v.accepted / v.alerted : 0, ...v }))
    .sort((a, b) => b.rate - a.rate);

  const max = Math.max(...data.map((d) => d.rate), 0.01);
  el("skill-chart").innerHTML = data
    .map(
      (d) => `
      <div class="row row--nowrap" style="gap:var(--s-3);padding:var(--s-2) 0">
        <span class="small" style="width:7rem">${d.skill.replace(/_/g, " ")}</span>
        <span style="flex:1;height:10px;background:var(--surface-alt);border-radius:4px;overflow:hidden">
          <span style="display:block;height:100%;width:${(d.rate / max) * 100}%;
                background:${CATEGORICAL[0]};border-radius:4px"></span>
        </span>
        <span class="small strong numeric" style="width:3rem;text-align:right">${pct(d.rate)}</span>
        <span class="tiny muted numeric" style="width:5rem;text-align:right">${d.accepted}/${d.alerted}</span>
      </div>`
    )
    .join("");

  el("skill-table").innerHTML = table(
    ["Skill", "Band", "Alerted", "Accepted", "Rate"],
    rows.map((r) => [
      r.skill_class.replace(/_/g, " "), r.radius_band,
      num(r.alerted), num(r.accepted), pct(r.acceptance_rate),
    ])
  );
}

/* ---- AI degradation ----------------------------------------------------- */

function renderAiStatus(m) {
  const rows = m.ai_degradation_rate.rows;
  trace("ai-trace", m.ai_degradation_rate.query_file);
  const total = rows.reduce((sum, r) => sum + num(r.incidents), 0) || 1;
  const ok = num(rows.find((r) => r.ai_status === "ok")?.incidents);

  el("ai-headline").textContent = pct(1 - ok / total);
  el("ai-breakdown").innerHTML = rows
    .map(
      (r) => `<div class="list__row">
        <span class="small strong">${r.ai_status}</span>
        <span class="spacer"></span>
        <span class="small numeric">${num(r.incidents)}</span>
        <span class="tiny muted numeric" style="width:3rem;text-align:right">${pct(r.share)}</span>
      </div>`
    )
    .join("");
}

/* ---- boot --------------------------------------------------------------- */

async function boot() {
  if (!bootAdmin()) return;

  const m = await loadAnalytics();
  if (!m) return;

  renderStats(m);
  renderAcceptance(m);
  renderFirstDispatch(m);
  renderFunnel(m);
  renderTypes(m);
  renderEscalation(m);
  renderAcceptanceBySkill(m);
  renderAiStatus(m);

  wireTableToggles();
}

boot();
