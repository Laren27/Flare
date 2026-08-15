/* Loading, empty and error states, rendered into a container.
 *
 * These three had been written inline at every call site, slightly differently
 * each time: the admin incidents table said "Unavailable", a failed analytics
 * panel said nothing at all and simply rendered no bars, and an empty coverage
 * grid said "No incidents in window" while an empty acceptance histogram said
 * "No accepted incidents in window." The wording drifting is the small problem.
 * The real one is that a panel which failed and a panel with genuinely no data
 * looked identical, so a broken query read as a quiet network.
 *
 * Empty and error are deliberately different shapes. Empty is a fact about the
 * data and is stated calmly. Error is a fact about the system and says what
 * broke, because a user who cannot tell the two apart cannot tell whether to
 * wait, retry, or go and fix something.
 *
 * Not-built notices are deliberately NOT here. Those are static markup with a
 * `.notice--not-built` class, so they render even when JavaScript does not --
 * the product's honesty disclosures should not depend on the layer most likely
 * to fail.
 */

const escape = (text) =>
  String(text).replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );

/** Work is in flight. Deliberately plain -- a spinner that never resolves is
 *  worse than a sentence. */
export function renderLoading(element, message = "Loading…") {
  if (!element) return;
  element.innerHTML = `<p class="small muted">${escape(message)}</p>`;
}

/**
 * The query ran and there is genuinely nothing to show.
 * `hint` is for the action that would produce data, where one exists.
 */
export function renderEmpty(element, message, hint = null) {
  if (!element) return;
  element.innerHTML =
    `<p class="small muted">${escape(message)}</p>` +
    (hint ? `<p class="tiny muted mt-2">${escape(hint)}</p>` : "");
}

/**
 * Something failed. Names what, so the reader can tell this apart from empty.
 * `detail` is the server's message where there is one.
 */
export function renderError(element, message, detail = null) {
  if (!element) return;
  element.innerHTML =
    `<p class="small strong">${escape(message)}</p>` +
    (detail ? `<p class="tiny muted mt-2">${escape(detail)}</p>` : "");
}
