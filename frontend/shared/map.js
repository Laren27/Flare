/* Leaflet helpers -- Ch. 17.
 *
 * Leaflet and its tiles come from a CDN, which means the map is the one part
 * of the UI that needs network. Ch. 25 lists demo-day network failure as a
 * named risk, so every entry point here degrades to a styled placeholder
 * rather than an empty box or a thrown error. Vendoring is deliberately not
 * done, and recorded as such in Ch. 26.
 *
 * ETA is straight-line distance over an average speed, not routing. Routing
 * APIs are named in Future Scope (Ch. 26); claiming a routed ETA we have not
 * built would be exactly the slideware Rule 007 forbids.
 */

const TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

/** Average responder speed on foot/two-wheeler through city streets, m/s. */
export const AVERAGE_SPEED_MPS = 5.5;

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

export function responderMarker(map, { lat, lng }, label = "R") {
  if (!map) return null;
  return window.L
    .marker([lat, lng], {
      icon: divIcon(
        `<div style="width:30px;height:30px;border-radius:50%;background:#22c55e;color:#fff;
          display:grid;place-items:center;font:700 11px/1 Inter,sans-serif;
          box-shadow:0 4px 12px rgb(34 197 94 / 45%);border:3px solid #fff">${label}</div>`,
        "flare-marker--responder",
        30
      ),
    })
    .addTo(map);
}

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

export function etaMinutes(distanceM, speedMps = AVERAGE_SPEED_MPS) {
  return Math.max(1, Math.round(distanceM / speedMps / 60));
}

export function formatDistance(distanceM) {
  return distanceM < 1000
    ? `${Math.round(distanceM)} m`
    : `${(distanceM / 1000).toFixed(1)} km`;
}

/** Haversine, mirroring backend/app/services/haversine.py so the client can
 *  show a distance without a round trip. The server remains authoritative. */
export function distanceM(a, b) {
  const R = 6371008.8;
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dPhi = toRad(b.lat - a.lat);
  const dLambda = toRad(b.lng - a.lng);
  const phi1 = toRad(a.lat);
  const phi2 = toRad(b.lat);
  const h =
    Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(Math.min(1, h)));
}
