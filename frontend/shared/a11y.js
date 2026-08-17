/* Keyboard containment for modal dialogs.
 *
 * The volunteer alert declares `role="dialog" aria-modal="true"` and confined
 * nothing: focus stayed wherever it was, Tab walked straight out into the page
 * behind, and Escape did nothing. A screen-reader user was told a modal had
 * opened and then had to hunt for it -- while an emergency alert counted down
 * behind the announcement.
 *
 * `aria-modal` is a promise to assistive technology about where focus is. This
 * is the code that makes the promise true.
 */

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function focusable(container) {
  return [...container.querySelectorAll(FOCUSABLE)].filter(
    (node) => node.offsetParent !== null || node === document.activeElement
  );
}

/**
 * Trap keyboard focus inside `container` until the returned function is called.
 *
 * Returns a release function that restores focus to wherever it was, because a
 * dialog that closes and drops focus onto <body> leaves a keyboard user at the
 * top of the document with no idea where they are.
 */
export function trapFocus(container, { onEscape } = {}) {
  const previous = document.activeElement;

  const first = focusable(container)[0];
  // The dialog itself if it has nothing focusable yet -- better than leaving
  // focus outside an element that claims to be modal.
  (first ?? container).focus?.();

  function onKeydown(event) {
    if (event.key === "Escape" && onEscape) {
      event.preventDefault();
      onEscape();
      return;
    }
    if (event.key !== "Tab") return;

    const nodes = focusable(container);
    if (!nodes.length) {
      event.preventDefault();
      return;
    }

    const firstNode = nodes[0];
    const lastNode = nodes[nodes.length - 1];

    // Wrap at both ends. Without this Tab escapes forward and Shift+Tab
    // escapes backward, which is the same bug twice.
    if (event.shiftKey && document.activeElement === firstNode) {
      event.preventDefault();
      lastNode.focus();
    } else if (!event.shiftKey && document.activeElement === lastNode) {
      event.preventDefault();
      firstNode.focus();
    }
  }

  document.addEventListener("keydown", onKeydown, true);

  return function release() {
    document.removeEventListener("keydown", onKeydown, true);
    previous?.focus?.();
  };
}

/**
 * Announce a message to screen readers without moving focus.
 *
 * State in this product changes underneath the reader -- a responder is
 * assigned, the radius widens, the search ends -- and none of it was announced
 * to anybody. `polite` waits for a pause; `assertive` interrupts, and is for
 * the states a person genuinely needs to hear about immediately.
 */
export function announce(message, priority = "polite") {
  let region = document.getElementById(`flare-live-${priority}`);

  if (!region) {
    region = document.createElement("div");
    region.id = `flare-live-${priority}`;
    region.className = "visually-hidden";
    region.setAttribute("role", "status");
    region.setAttribute("aria-live", priority);
    document.body.append(region);
  }

  // Clearing first forces a re-announcement when the same text repeats, which
  // otherwise stays silent -- an escalation from 2km to 3km reads the same as
  // the one before it and still needs saying.
  region.textContent = "";
  window.setTimeout(() => {
    region.textContent = message;
  }, 50);
}
