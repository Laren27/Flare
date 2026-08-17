/* Sidebar navigation behaviour, shared by all three role views.
 *
 * This used to also carry a scroll-spy, because the admin view was one long
 * page whose sidebar pointed at anchor sections. It was never reliable and
 * could not be made so: with several sections visible at once the highlight is
 * a guess, and the last sections on the page can never reach the top of the
 * viewport, so clicking them moved nothing and lit up the section above.
 *
 * The admin view is four pages now, so every sidebar link is a real
 * destination and `aria-current` is written into the markup of the page it
 * belongs to. A fact, rather than an inference from scroll position.
 */

/** Make unbuilt nav items refuse the click instead of jumping to the top. */
export function inertUnbuiltLinks(root = document) {
  for (const link of root.querySelectorAll(".sidebar__link--soon")) {
    link.setAttribute("aria-disabled", "true");
    link.addEventListener("click", (event) => event.preventDefault());
  }
}

/* The rehearsal shortcut, added to the admin sidebar at runtime.
 *
 * Injected rather than written into the five admin pages, and that is the point
 * rather than a shortcut: this is a QA affordance, not product navigation, so
 * it does not belong in the markup the product ships. It also means it costs
 * one file instead of five, and vanishes cleanly if it is ever dropped.
 *
 * The other sidebar items stay static deliberately -- navigation should survive
 * a JavaScript failure. A demo tool that disappears when scripts break is
 * behaving correctly: at that point nobody is rehearsing.
 */
function addPreviewLink(root) {
  const sidebar = root.querySelector('.sidebar[aria-label="Admin navigation"]');
  if (!sidebar || sidebar.querySelector('[data-preview-link]')) return;

  const link = document.createElement("a");
  link.className = "sidebar__link";
  link.href = "/app/admin/preview.html";
  link.dataset.previewLink = "true";
  link.innerHTML =
    '<span class="sidebar__icon" aria-hidden="true">🎬</span>' +
    '<span class="sidebar__label">Preview</span>';

  if (location.pathname.endsWith("/admin/preview.html")) {
    link.setAttribute("aria-current", "page");
  }

  // Above the spacer, so it sits with the navigation rather than beside logout.
  const spacer = sidebar.querySelector(".sidebar__spacer");
  sidebar.insertBefore(link, spacer);
}

export function initNav(root = document) {
  inertUnbuiltLinks(root);
  addPreviewLink(root);
}
