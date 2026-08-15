/* Shared by the four admin pages.
 *
 * The admin view used to be one long page with Dashboard, Incidents,
 * Volunteers and Coverage as anchor sections. That made the sidebar highlight
 * unreliable by construction: a scroll-spy has to guess which of several
 * simultaneously-visible sections you meant, and the two bottom sections could
 * never reach the top of the viewport at all, so clicking them moved nothing
 * and lit up the wrong item. Four pages have no such ambiguity -- the current
 * page is a fact, not an inference -- so `aria-current` is written into each
 * page's markup and the observer is gone.
 *
 * Charts are hand-rolled inline SVG: a charting library is outside the fixed
 * stack, and these forms are simple enough that adding one would be a
 * dependency bought to avoid an afternoon.
 *
 * The categorical order below is not a taste choice. The locked spec palette
 * fails colourblind separation in its natural order -- amber against green
 * scores dE 5.7 under protanopia. Reordered to red -> amber -> blue -> green
 * the worst adjacent pair scores 13.9 and every check passes. Amber and green
 * also fall under 3:1 against white, which obligates relief: every mark is
 * direct-labelled and every chart has a table view.
 */

import { api, auth, requireAuth } from "../shared/api.js";
import { initials } from "../shared/format.js";
import { initNav } from "../shared/nav.js";

// Re-exported rather than redefined: the admin pages keep one import surface,
// and the formatters themselves now live where the citizen and volunteer views
// can reach them too.
export { duration, latency, num, pct } from "../shared/format.js";

export const CATEGORICAL = ["#EF4444", "#F59E0B", "#3B82F6", "#22C55E"];
export const OTHER = "#64748B";
export const SEQUENTIAL = ["#FEF2F2", "#FEE2E2", "#FCA5A5", "#F87171", "#EF4444", "#B91C1C", "#7F1D1D"];

export const el = (id) => document.getElementById(id);

export function svg(width, height, extra = "") {
  return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img" ${extra}>`;
}

export function table(headers, rows) {
  return `<table class="table"><thead><tr>${headers
    .map((h) => `<th>${h}</th>`)
    .join("")}</tr></thead><tbody>${rows
    .map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`)
    .join("")}</tbody></table>`;
}

/** Stamp the query file onto a card, per Ch. 18A traceability. */
export function trace(cardId, queryFile) {
  const node = el(cardId);
  if (node) node.textContent = queryFile;
}

/** Auth, identity and logout -- the part every admin page repeats. */
export function bootAdmin() {
  const user = requireAuth("admin");
  if (!user) return null;

  el("user-name").textContent = user.name;
  el("user-initials").textContent = initials(user.name);
  initNav();

  el("logout").addEventListener("click", (event) => {
    event.preventDefault();
    auth.clear();
    location.href = "/app/login.html";
  });

  return user;
}

/** Show/hide the table view behind each chart. */
export function wireTableToggles(root = document) {
  for (const button of root.querySelectorAll(".toggle-table")) {
    button.addEventListener("click", () => {
      const target = el(button.dataset.table);
      target.hidden = !target.hidden;
      button.textContent = target.hidden ? "Table" : "Chart only";
    });
  }
}

/**
 * Fetch /admin/analytics and report the outcome in the page banner.
 * Returns the metrics map, or null if the request failed -- callers render
 * nothing rather than rendering zeros, because a chart of zeros claims a
 * measurement that was never taken.
 */
export async function loadAnalytics() {
  const banner = el("banner");
  let payload;

  try {
    payload = await api.analytics();
  } catch (error) {
    banner.className = "toast toast--error";
    banner.textContent = `Analytics unavailable: ${error.detail || error.message}`;
    return null;
  }

  banner.innerHTML =
    `<strong>Live data.</strong> ${payload.window_days}-day window. Every figure below is ` +
    `produced by a named query in <code>analytics/queries/</code> — the filename is printed ` +
    `under each panel, so any number here can be checked against the SQL that made it.`;

  return payload.metrics;
}
