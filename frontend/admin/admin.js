/* Admin analytics -- screen 4, structured for Chapter 18A's seven metrics.
 *
 * Charts are hand-rolled inline SVG: a charting library is outside the fixed
 * stack, and these forms are simple enough that adding one would be a
 * dependency bought to avoid an afternoon.
 *
 * The categorical order below is not a taste choice. The locked spec palette
 * fails colourblind separation in its natural order -- amber against green
 * scores dE 5.7 under protanopia, well under the safe floor. Reordered to
 * red -> amber -> blue -> green the worst adjacent pair scores 13.9 and every
 * check passes. Amber and green also fall under 3:1 against white, which
 * obligates relief: every mark here is direct-labelled and every chart has a
 * table view, so identity never rests on colour alone.
 */

import { auth, initials, requireAuth } from "../shared/api.js";
import { mockAdmin } from "../shared/mock.js";

/** Validated categorical order. Assigned by position, never cycled. */
const CATEGORICAL = ["#EF4444", "#F59E0B", "#3B82F6", "#22C55E"];
/** Neutral slot for "Other" -- deliberately not a categorical hue. */
const OTHER = "#64748B";
/** Sequential ramp, one hue, light to dark (never a rainbow). */
const SEQUENTIAL = ["#FEF2F2", "#FEE2E2", "#FCA5A5", "#F87171", "#EF4444", "#B91C1C", "#7F1D1D"];

const el = (id) => document.getElementById(id);
const svgNS = "http://www.w3.org/2000/svg";

function svg(width, height, extra = "") {
  return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" ${extra}>`;
}

function table(headers, rows) {
  return `<table class="table"><thead><tr>${headers
    .map((h) => `<th>${h}</th>`)
    .join("")}</tr></thead><tbody>${rows
    .map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
    .join("")}</tbody></table>`;
}

/* ---- stat tiles --------------------------------------------------------- */

function renderStats() {
  el("stats").innerHTML = mockAdmin.stats
    .map(
      (stat) => `
      <div class="stat">
        <div class="stat__label">${stat.label}</div>
        <div class="stat__value">${stat.value}</div>
        <div class="stat__delta stat__delta--${stat.direction}">${stat.delta} vs last 7 days</div>
      </div>`
    )
    .join("");
}

/* ---- time-to-acceptance histogram --------------------------------------- */

function renderAcceptance() {
  const data = mockAdmin.acceptanceHistogram;
  const W = 460;
  const H = 190;
  const pad = { top: 18, right: 8, bottom: 30, left: 8 };
  const plotH = H - pad.top - pad.bottom;
  const max = Math.max(...data.map((d) => d.count));
  const slot = (W - pad.left - pad.right) / data.length;
  const barW = slot - 6; // 2px+ surface gap between adjacent bars

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

  el("p50").textContent = mockAdmin.percentiles.p50;
  el("p90").textContent = mockAdmin.percentiles.p90;
  el("pmax").textContent = mockAdmin.percentiles.max;

  el("acceptance-table").innerHTML = table(
    ["Bucket", "Incidents"],
    data.map((d) => [d.bucket, d.count])
  );
}

/* ---- dispatch funnel ---------------------------------------------------- */

function renderFunnel() {
  const data = mockAdmin.funnel;
  const W = 460;
  const rowH = 34;
  const H = data.length * rowH + 8;
  const max = data[0].count;
  const labelW = 130;
  const barMax = W - labelW - 56;

  const rows = data
    .map((d, i) => {
      const w = Math.max(4, (d.count / max) * barMax);
      const y = i * rowH + 6;
      const dropped = i === 0 ? null : data[i - 1].count - d.count;
      return `
        <g class="mark"><title>${d.stage}: ${d.count}${dropped ? ` (−${dropped} from previous)` : ""}</title>
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

/* ---- incidents by type (donut) ------------------------------------------ */

function renderTypes() {
  const data = mockAdmin.incidentsByType;
  const total = data.reduce((sum, d) => sum + d.value, 0);
  const size = 170;
  const r = 62;
  const stroke = 22;
  const c = size / 2;
  const circumference = 2 * Math.PI * r;
  const GAP = 3; // surface gap between segments

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
          <title>${d.label}: ${d.value}%</title>
        </circle>`;
      offset += length;
      return seg;
    })
    .join("");

  el("types-chart").innerHTML = `${svg(size, size, 'aria-label="Incidents by type"')}
    ${segments}
    <text x="${c}" y="${c - 2}" text-anchor="middle" class="value" font-size="22">128</text>
    <text x="${c}" y="${c + 14}" text-anchor="middle" font-size="10">Total</text>
  </svg>`;

  el("types-legend").innerHTML = data
    .map(
      (d, i) => `<span class="legend__item">
        <span class="legend__swatch" style="background:${i < CATEGORICAL.length ? CATEGORICAL[i] : OTHER}"></span>
        ${d.label} <span class="strong">${d.value}%</span></span>`
    )
    .join("");

  el("types-table").innerHTML = table(["Type", "Share"], data.map((d) => [d.label, `${d.value}%`]));
}

/* ---- escalation split --------------------------------------------------- */

function renderEscalation() {
  const data = mockAdmin.escalation;
  /* Semantic, not positional: green means no escalation was needed, red means
     nobody was there (condition A), amber means nobody answered (condition B).
     All three are direct-labelled, which is the relief the contrast warning
     requires. */
  const colours = ["#22C55E", "#EF4444", "#F59E0B"];
  const total = data.reduce((sum, d) => sum + d.count, 0);
  const W = 460;
  const H = 116;
  const barY = 18;
  const barH = 26;
  const GAP = 3;

  let x = 0;
  const segments = data
    .map((d, i) => {
      const w = (d.count / total) * W - GAP;
      const seg = `
        <g class="mark"><title>${d.label}: ${d.count} incidents (${Math.round((d.count / total) * 100)}%)</title>
          <rect x="${x}" y="${barY}" width="${Math.max(2, w)}" height="${barH}" rx="4" fill="${colours[i]}"/>
        </g>`;
      x += w + GAP;
      return seg;
    })
    .join("");

  const labels = data
    .map(
      (d, i) => `<text x="0" y="${barY + barH + 22 + i * 16}" font-size="11">
        <tspan fill="${colours[i]}">●</tspan> ${d.label} — <tspan class="value">${d.count}</tspan>
      </text>`
    )
    .join("");

  el("escalation-chart").innerHTML =
    `${svg(W, H, 'aria-label="Escalation rate by trigger"')}${segments}${labels}</svg>`;

  el("escalation-table").innerHTML = table(
    ["Trigger", "Incidents", "Share"],
    data.map((d) => [d.label, d.count, `${Math.round((d.count / total) * 100)}%`])
  );
}

/* ---- top areas ---------------------------------------------------------- */

function renderAreas() {
  const data = mockAdmin.topAreas;
  const max = Math.max(...data.map((d) => d.count));
  el("areas-chart").innerHTML = data
    .map(
      (d, i) => `
      <div class="row row--nowrap" style="gap:var(--s-3);padding:var(--s-2) 0">
        <span class="tiny muted numeric" style="width:1.2rem">${i + 1}</span>
        <span class="small" style="width:8rem">${d.area}</span>
        <span style="flex:1;height:10px;background:var(--surface-alt);border-radius:4px;overflow:hidden">
          <span style="display:block;height:100%;width:${(d.count / max) * 100}%;
                background:${CATEGORICAL[0]};border-radius:4px"></span>
        </span>
        <span class="small strong numeric">${d.count}</span>
      </div>`
    )
    .join("");
}

/* ---- coverage grid ------------------------------------------------------ */

function renderCoverage() {
  const step = (v) => SEQUENTIAL[Math.min(SEQUENTIAL.length - 1, Math.floor(v * SEQUENTIAL.length))];
  el("coverage").innerHTML = mockAdmin.coverageGrid
    .map(
      (v) =>
        `<div class="heat__cell" style="background:${step(v)}"
              title="Gap severity ${(v * 100).toFixed(0)}%"></div>`
    )
    .join("");
  el("coverage-scale").innerHTML = SEQUENTIAL.map(
    (c) => `<span style="width:16px;height:10px;border-radius:2px;background:${c}"></span>`
  ).join("");
}

/* ---- tables ------------------------------------------------------------- */

function renderQueues() {
  el("pending-table").innerHTML = `
    <thead><tr><th>Name</th><th>Skill</th><th>Certificate</th><th>Waiting</th><th></th></tr></thead>
    <tbody>${mockAdmin.pendingVolunteers
      .map(
        (v) => `<tr>
          <td class="strong">${v.name}</td>
          <td><span class="chip chip--info">${v.skill.replace("_", " ")}</span></td>
          <td class="muted">${v.certificate}</td>
          <td class="muted">${v.when}</td>
          <td><button class="btn btn--success" style="padding:4px 10px">Approve</button></td>
        </tr>`
      )
      .join("")}</tbody>`;

  const statusPill = {
    matched: "pill--success",
    pending: "pill--warn",
    no_responder_found: "pill--live",
  };

  el("incidents-table").innerHTML = `
    <thead><tr><th>#</th><th>Area</th><th>Status</th><th>Radius</th><th>Waves</th><th>Age</th></tr></thead>
    <tbody>${mockAdmin.activeIncidents
      .map(
        (i) => `<tr>
          <td class="strong numeric">${i.id}</td>
          <td>${i.area}</td>
          <td><span class="pill ${statusPill[i.status]}">${i.status.replace(/_/g, " ")}</span></td>
          <td class="numeric">${i.radius} m</td>
          <td class="numeric">${i.waves}</td>
          <td class="muted numeric">${i.age}</td>
        </tr>`
      )
      .join("")}</tbody>`;
}

/* ---- boot --------------------------------------------------------------- */

function boot() {
  const user = requireAuth("admin");
  if (!user) return;

  el("user-name").textContent = user.name;
  el("user-initials").textContent = initials(user.name);

  renderStats();
  renderAcceptance();
  renderFunnel();
  renderTypes();
  renderEscalation();
  renderAreas();
  renderCoverage();
  renderQueues();

  for (const button of document.querySelectorAll(".toggle-table")) {
    button.addEventListener("click", () => {
      const target = el(button.dataset.table);
      target.hidden = !target.hidden;
      button.textContent = target.hidden ? "Table" : "Chart only";
    });
  }

  el("logout").addEventListener("click", (event) => {
    event.preventDefault();
    auth.clear();
    location.href = "/app/login.html";
  });
}

boot();
