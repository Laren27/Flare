/* Admin verification queue.
 *
 * Certificate upload and approval are Future Scope (Ch. 26): the flow needs a
 * certificate_path column that does not exist, so there is nothing to approve.
 * The rows are sample data and the buttons are rendered DISABLED rather than
 * omitted or left looking live -- a control that does nothing when clicked
 * reads as broken, and a control that isn't there hides the shape of the
 * intended feature (Rule 007).
 */

import { mockAdmin } from "../shared/mock.js";
import { bootAdmin, el } from "./shared.js";

function renderPending() {
  el("pending-table").innerHTML = `
    <thead><tr><th>Name</th><th>Skill</th><th>Certificate</th><th>Waiting</th><th></th></tr></thead>
    <tbody>${mockAdmin.pendingVolunteers
      .map(
        (v) => `<tr>
          <td class="strong">${v.name}</td>
          <td><span class="chip chip--info">${v.skill.replace("_", " ")}</span></td>
          <td class="muted">${v.certificate}</td>
          <td class="muted">${v.when}</td>
          <td>
            <button class="btn btn--success" style="padding:4px 10px" disabled
                    title="Certificate upload and approval are Future Scope — see README">
              Approve
            </button>
          </td>
        </tr>`
      )
      .join("")}</tbody>`;
}

function boot() {
  if (!bootAdmin()) return;
  renderPending();
}

boot();
