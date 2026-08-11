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

  // Every link that can carry the highlight, including the page's own "home"
  // link. Clearing only the section links left the hardcoded aria-current on
  // "Dashboard" in place, so scrolling to another section lit up two items at
  // once -- which is what "the red background is not consistent" looks like.
  const home = root.querySelector('.sidebar__link[href="#"]');
  const highlightable = home ? [home, ...sections.map((s) => s.link)] : sections.map((s) => s.link);

  const setActive = (activeLink) => {
    for (const link of highlightable) {
      if (link === activeLink) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    }
  };

  // At the very top of the page nothing has scrolled into view yet, so "home"
  // is the honest answer rather than whichever section observes first. Guarded
  // so it cannot fight a click the user just made.
  let clickedRecently = 0;
  window.addEventListener(
    "scroll",
    () => {
      if (Date.now() - clickedRecently < 800) return;
      if (window.scrollY < 80 && home) setActive(home);
    },
    { passive: true }
  );
  for (const { link } of sections) {
    link.addEventListener("click", () => {
      clickedRecently = Date.now();
    });
  }

  // Clicking a nav item highlights it immediately. This is the part that
  // matters: "the highlight should follow what you chose" is a statement about
  // the click, not about the scroll. Waiting for an observer to catch up leaves
  // the red block sitting on the previous item while you look at a new section.
  for (const { link } of sections) {
    link.addEventListener("click", () => setActive(link));
  }

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

  // Clicking the page's own "home" returns to the top, which a bare href="#"
  // does inconsistently across browsers.
  home?.addEventListener("click", (event) => {
    event.preventDefault();
    window.scrollTo({ top: 0, behavior: "smooth" });
    setActive(home);
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
