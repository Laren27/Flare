/* The rehearsal index. Deliberately almost empty.
 *
 * Every link on this page is a plain anchor written into the markup, so this
 * module exists only to gate the page behind an admin session and fill in the
 * signed-in identity. It calls no API, holds no state, and imports nothing from
 * the dispatch path -- if this file ever needs to grow, that is the signal that
 * the panel has started becoming a feature rather than a shortcut.
 */

import { bootAdmin } from "./shared.js";

bootAdmin();
