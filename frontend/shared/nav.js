/* Sidebar navigation behaviour, shared by all three role views.
 *
 * Two jobs, both small, both things the pages were getting wrong:
 *
 *   1. Keep the active item in step with what you are actually looking at.
 *      Anchor links jump but never update `aria-current`, so the highlight
 *      stayed on "Dashboard" no matter where you had scrolled to.
 *   2. Stop links whose feature does not exist from behaving like links.
 *      Marking them inert in markup is not enough -- a click still jumps to
 *      the top of the page, which reads as a broken feature rather than an
 *      unbuilt one.
 */

/** Highlight the sidebar item matching whichever section is in view. */
export function trackSections(root = document) {
  const links = [...root.querySelectorAll('.sidebar__link[href^="#"]')].filter(
    (link) => link.getAttribute("href").length > 1 && !link.classList.contains("sidebar__link--soon")
  );
  if (!links.length) return;

  const sections = links
    .map((link) => ({ link, section: root.getElementById?.(link.getAttribute("href").slice(1))
      ?? document.getElementById(link.getAttribute("href").slice(1)) }))
    .filter((entry) => entry.section);
  if (!sections.length) return;

  const setActive = (activeLink) => {
    for (const { link } of sections) {
      if (link === activeLink) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
  };

  const observer = new IntersectionObserver(
    (entries) => {
      // The topmost section currently intersecting wins. Without picking one,
      // two visible sections fight over the highlight as you scroll.
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (!visible.length) return;
      const match = sections.find((entry) => entry.section === visible[0].target);
      if (match) setActive(match.link);
    },
    // Top-weighted margin: a section counts as "current" once it reaches the
    // upper third, which matches where the eye actually is.
    { rootMargin: "-72px 0px -60% 0px", threshold: 0 }
  );

  for (const { section } of sections) observer.observe(section);

  // Clicking the first link (the page's own "home") should return to the top,
  // which a bare href="#" does inconsistently across browsers.
  const home = root.querySelector('.sidebar__link[href="#"]');
  home?.addEventListener("click", (event) => {
    event.preventDefault();
    window.scrollTo({ top: 0, behavior: "smooth" });
    setActive(null);
    home.setAttribute("aria-current", "page");
  });
}

/** Make unbuilt nav items refuse the click instead of jumping to the top. */
export function inertUnbuiltLinks(root = document) {
  for (const link of root.querySelectorAll(".sidebar__link--soon")) {
    link.setAttribute("aria-disabled", "true");
    link.addEventListener("click", (event) => event.preventDefault());
  }
}

export function initNav(root = document) {
  inertUnbuiltLinks(root);
  trackSections(root);
}
