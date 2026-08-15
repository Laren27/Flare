/* Value formatting, shared by all three role views.
 *
 * These were spread across three modules that had no business owning them:
 * distance formatting lived in the Leaflet helpers, name initials lived in the
 * API client, and the duration/percentage helpers lived in the admin bundle
 * where the citizen and volunteer views could not reach them. Nothing here
 * touches the DOM, the network or the map -- it is all value in, string out,
 * which is what makes it safe to share.
 *
 * There is deliberately no ETA helper. Straight-line ETA was computable and is
 * now not: nothing writes a responder position after acceptance, so there is no
 * distance to divide. `etaMinutes` and its average-speed constant were deleted
 * with the screens that called them rather than left available, because a live
 * helper is an invitation to put the number back on screen (Ch. 26, Rule 007).
 */

/** Coerce a possibly-null SQL value to a number. Null and undefined become 0. */
export const num = (v) => (v === null || v === undefined ? 0 : Number(v));

/** Metres, at the precision a human actually reads. */
export function formatDistance(distanceM) {
  return distanceM < 1000
    ? `${Math.round(distanceM)} m`
    : `${(distanceM / 1000).toFixed(1)} km`;
}

/** Seconds as minutes and seconds. Whole seconds -- see `latency` below. */
export function duration(seconds) {
  const s = Math.round(num(seconds));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

/**
 * Sub-second-aware duration.
 *
 * Time-to-first-dispatch is measured in milliseconds -- the engine decides a
 * whole dispatch wave in tens of them. Rounding that to whole seconds prints
 * "0s", which reads as broken and throws away the single strongest number the
 * system produces. Anything at or above a second falls through to `duration`.
 */
export function latency(seconds) {
  const s = num(seconds);
  if (s < 1) return `${Math.round(s * 1000)} ms`;
  return duration(s);
}

/** A 0-1 share as a whole percentage. */
export function pct(value) {
  return `${Math.round(num(value) * 100)}%`;
}

/** Up to two initials, for an avatar. */
export function initials(name) {
  return (name || "?")
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
