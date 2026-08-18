/* Leaflet helpers -- Ch. 17.
 *
 * Leaflet and its tiles come from a CDN, which means the map is the one part
 * of the UI that needs network. Ch. 25 lists demo-day network failure as a
 * named risk, so every entry point here degrades to a styled placeholder
 * rather than an empty box or a thrown error. Vendoring is deliberately not
 * done, and recorded as such in Ch. 26.
 *
 * This module draws maps and nothing else. It carried the ETA and distance
 * helpers until the screens that used them were removed; see the note at the
 * foot of the file.
 */

const TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

export const leafletAvailable = () => typeof window.L !== "undefined";

export function createMap(element, { lat, lng, zoom = 15 } = {}) {
  if (!leafletAvailable()) {
    showFallback(element, "Map unavailable offline");
    return null;
  }
  const map = window.L.map(element, { zoomControl: true, attributionControl: true });
  map.setView([lat, lng], zoom);
  window.L.tileLayer(TILE_URL, { attribution: TILE_ATTRIBUTION, maxZoom: 19 }).addTo(map);
  return map;
}

export function showFallback(element, message) {
  const note = document.createElement("div");
  note.className = "map__fallback";
  note.innerHTML = `<div><div style="font-size:1.5rem">🗺️</div><p class="small">${message}</p></div>`;
  element.append(note);
}

function divIcon(html, className, size = 34) {
  return window.L.divIcon({
    html,
    className: `flare-marker ${className}`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

export function incidentMarker(map, { lat, lng }) {
  if (!map) return null;
  return window.L
    .marker([lat, lng], {
      icon: divIcon(
        `<div style="width:34px;height:34px;border-radius:50%;background:#ef4444;color:#fff;
          display:grid;place-items:center;font:700 10px/1 Inter,sans-serif;
          box-shadow:0 4px 12px rgb(239 68 68 / 45%);border:3px solid #fff">SOS</div>`,
        "flare-marker--incident"
      ),
      zIndexOffset: 500,
    })
    .addTo(map);
}

/* `responderMarker` was here, and is gone for the same reason the ETA helpers
 * are: nothing writes a responder's position after acceptance, so there is no
 * coordinate to place it at. It survived the earlier cleanup only because it
 * had no caller to remove alongside it -- which is exactly how a helper for an
 * unbuilt capability stays alive long enough to be picked up by someone who
 * assumes the data must exist because the function does. */

/** The escalation ladder, drawn. One circle per rung; the active one is solid. */
export function radiusCircles(map, { lat, lng }, activeRadiusM, ladder = [1000, 2000, 3000]) {
  if (!map) return [];
  return ladder.map((radius) => {
    const isActive = radius === activeRadiusM;
    return window.L
      .circle([lat, lng], {
        radius,
        color: isActive ? "#3b82f6" : "#94a3b8",
        weight: isActive ? 2 : 1,
        opacity: isActive ? 0.9 : 0.35,
        fillColor: "#3b82f6",
        fillOpacity: isActive ? 0.08 : 0.02,
        dashArray: isActive ? null : "4 6",
      })
      .addTo(map);
  });
}

/* `etaMinutes`, `AVERAGE_SPEED_MPS`, `distanceM` and `formatDistance` used to
 * live here.
 *
 * The first three are gone rather than moved. They existed to render a
 * straight-line ETA and a client-side distance for the responder marker, and
 * nothing writes a responder position after acceptance -- so there is no
 * coordinate to measure from and no ETA to derive. Keeping working helpers for
 * a capability the product declares as not built is how that number finds its
 * way back onto a screen (Ch. 26, Rule 007). The straight-line approach is
 * recorded in the blueprint if it is ever wanted again.
 *
 * `formatDistance` moved to shared/format.js, which is where a string helper
 * belongs -- two pages were importing the map module purely to format a number.
 */
