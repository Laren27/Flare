/* Coverage gap grid -- the metric that answers "where should we recruit?".
 *
 * On its own page because it is the one panel that wants width, and because it
 * asks a different question from the dashboard: not how the dispatch loop is
 * performing, but where the network is structurally blind.
 */

import { SEQUENTIAL, bootAdmin, el, loadAnalytics, num, pct, trace } from "./shared.js";

function renderCoverage(m) {
  const rows = m.coverage_gap.rows;
  trace("coverage-trace", m.coverage_gap.query_file);

  if (!rows.length) {
    el("coverage").innerHTML = '<p class="small muted">No incidents in window.</p>';
    el("coverage-worst").innerHTML =
      '<p class="tiny muted">Nothing to rank until incidents exist. Seed a corpus with sim/scenarios/coverage.py.</p>';
    return;
  }

  // Normalise the sparse (grid_x, grid_y) rows onto a dense rectangle.
  const xs = rows.map((r) => num(r.grid_x));
  const ys = rows.map((r) => num(r.grid_y));
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const cols = Math.min(maxX - minX + 1, 20);
  const rowsCount = Math.min(maxY - minY + 1, 14);

  const lookup = new Map(rows.map((r) => [`${num(r.grid_x)},${num(r.grid_y)}`, r]));
  const step = (v) => SEQUENTIAL[Math.min(SEQUENTIAL.length - 1, Math.floor(v * SEQUENTIAL.length))];

  const cells = [];
  // Rendered top-down, so north is up rather than the raw index order.
  for (let y = rowsCount - 1; y >= 0; y -= 1) {
    for (let x = 0; x < cols; x += 1) {
      const row = lookup.get(`${minX + x},${minY + y}`);
      if (!row) {
        cells.push('<div class="heat__cell" style="background:var(--surface-alt)" title="no incidents"></div>');
      } else {
        const severity = num(row.gap_severity);
        cells.push(
          `<div class="heat__cell" style="background:${step(severity)}"
                title="${row.incident_count} incidents, ${row.uncovered_count} with no responder in range (${pct(severity)})"></div>`
        );
      }
    }
  }

  el("coverage").style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
  el("coverage").innerHTML = cells.join("");
  el("coverage-scale").innerHTML = SEQUENTIAL.map(
    (c) => `<span style="width:16px;height:10px;border-radius:2px;background:${c}"></span>`
  ).join("");

  const worst = rows.filter((r) => num(r.incident_count) > 1).slice(0, 5);
  el("coverage-worst").innerHTML = worst.length
    ? worst
        .map(
          (r) => `<div class="list__row">
            <span class="small numeric">${Number(r.centre_lat).toFixed(4)}, ${Number(r.centre_lng).toFixed(4)}</span>
            <span class="spacer"></span>
            <span class="tiny muted">${r.incident_count} incidents</span>
            <span class="pill pill--live">${pct(r.gap_severity)} uncovered</span>
          </div>`
        )
        .join("")
    : '<p class="tiny muted">No bucket has more than one incident yet.</p>';
}

async function boot() {
  if (!bootAdmin()) return;

  const m = await loadAnalytics();
  if (!m) return;

  renderCoverage(m);
}

boot();
