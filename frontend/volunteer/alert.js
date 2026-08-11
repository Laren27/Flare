/* Extracted from the page so the Content-Security-Policy can stay strict.
 * script-src 'self' blocks inline execution -- which silently broke this
 * page the moment security headers were added, because all of its logic
 * lived in an inline <script>. Weakening the policy with 'unsafe-inline'
 * would have fixed the symptom and removed the protection.
 */

import { api, auth } from "/app/shared/api.js";
import { formatDistance } from "/app/shared/map.js";
import { mockAlert } from "/app/shared/mock.js";

const params = new URLSearchParams(location.search);
const views = ["incoming", "handled", "accepted"];
const show = (name) => views.forEach((v) => {
  document.getElementById(`view-${v}`).hidden = v !== name;
});

const sosId = Number(params.get("sos"));
const alertData = sosId
  ? {
      sos_id: sosId,
      distance_m: Number(params.get("distance") || 0),
      description: params.get("description") || "No description provided",
      ai_category: params.get("category") || "Unspecified emergency",
    }
  : mockAlert;

document.getElementById("category").textContent = alertData.ai_category || "Unspecified emergency";
document.getElementById("description").textContent = alertData.description || "No description provided";
document.getElementById("distance").textContent = formatDistance(alertData.distance_m || 0);

show(params.get("view") && views.includes(params.get("view")) ? params.get("view") : "incoming");

function message(text, kind) {
  const node = document.getElementById("message");
  node.textContent = text;
  node.className = `toast toast--${kind}`;
  node.hidden = false;
}

document.getElementById("accept").addEventListener("click", async () => {
  if (!sosId) { show("accepted"); return; }        // preview mode
  if (!auth.isAuthenticated) { location.href = "/app/login.html"; return; }
  try {
    const result = await api.acceptSos(sosId);
    // `accepted: false` is a normal outcome of a race, not an error -- the
    // endpoint returns 200 for both sides precisely so the UI can say this.
    show(result.accepted ? "accepted" : "handled");
  } catch (error) {
    message(error.detail || error.message, "error");
  }
});

document.getElementById("decline").addEventListener("click", async () => {
  if (sosId && auth.isAuthenticated) await api.declineSos(sosId).catch(() => {});
  location.href = "/app/volunteer/";
});
