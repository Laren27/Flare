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

export function initNav(root = document) {
  inertUnbuiltLinks(root);
}
