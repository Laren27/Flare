# FLARE Frontend Design & Engineering Specification

**Status:** audit and proposal. Nothing in Parts 8–22 is implemented.
**Audited against:** commit `fcffdfd`, working tree clean.
**Authority:** `docs/FLARE_Engineering_Blueprint_v2.md`. Where this document and the blueprint disagree, the blueprint wins; every disagreement found is listed in §23 rather than silently resolved.

Every claim below was checked against code. Anything not checkable is marked **UNKNOWN**.

---

## 1. Executive summary

FLARE's frontend is a vanilla, buildless, multi-page app served as static files by FastAPI itself. There is no framework, no bundler, no package.json anywhere in the repository. For a project whose stated values are simplicity, demoability and honest scope, this is the right call and should survive the redesign.

The work is in better shape than most projects at this stage in one specific respect: it already practises the honesty discipline it preaches. Unbuilt navigation items are visibly inert. The verification queue ships with its buttons disabled and a paragraph explaining why. The `no_responder_found` screen is deliberately not styled as an error. Every analytics panel prints the `.sql` filename that produced it. That is a real cultural asset and the redesign must not flatten it.

The problems are concentrated in three places.

**First, the citizen view cannot perform the product's headline story.** There is no free-text description input anywhere in the citizen UI, and `citizen.js` hard-codes `null` as the description on every SOS. `ai_summary.summarise(None)` returns `SKIPPED` immediately. So every real citizen-triggered incident has `ai_category = null` and `ai_status = 'skipped'` — the single bounded AI call of ADR-005 has no input surface in the product. The demo script instructs the operator to "press SOS with a free-text description," which the interface cannot do.

**Second, several components claim capabilities that do not exist.** The volunteer alert card renders hard-coded "CPR / First Aid" skill chips that no backend field produces. The citizen active screen has Call and Message buttons with no handlers and a responder rating that has no column in the schema. The volunteer dashboard headlines three fabricated statistics, one of which is "Lives Impacted." These are Rule 007 violations of exactly the kind the rest of the codebase is scrupulous about.

**Third, the real-time layer is thinner than the UI implies.** The WebSocket carries exactly two server-to-client message types: `auth_ok` and `sos_alert`. Nothing else. There is no event for acceptance, escalation, resolution, or the terminal state. The citizen view therefore polls `GET /sos/{id}` every 2 seconds — which contradicts blueprint Ch. 13 step 9, where polling is explicitly rejected. A volunteer holding an open alert for an incident someone else has already accepted receives no notification at all; they discover it only by pressing ACCEPT and losing.

None of this makes the project unsound. The dispatch engine underneath is genuinely well-built and its correctness claims are tested. The frontend is simply the least-finished layer, and its gaps are the ones most visible in a demo.

The recommended sequence is: fix the honesty violations first (they are cheap and they are the ones that would be caught in a viva), then close the description gap, then decide deliberately whether to build the push events the UI wants or to keep polling and label it.

---

## 2. Current architecture

### 2.1 Framework and tooling

| Concern | Actual |
|---|---|
| Framework | None. Vanilla ES modules, `<script type="module">` |
| Build system | None. No `package.json`, no bundler, no transpiler, no minifier |
| Language | JavaScript, no TypeScript, no JSDoc types |
| CSS strategy | Three hand-written stylesheets + per-page `<style>` blocks + heavy inline `style=` |
| UI library | None |
| Map | Leaflet 1.9.4 from `unpkg.com` CDN, tiles from OpenStreetMap |
| Icons | Unicode emoji as text (🚨 📊 👥 ❤️ 🩸) |
| Charting | None. Hand-rolled inline SVG strings in `admin/admin.js` |
| State management | Module-level `let` variables per page |
| Data fetching | One `fetch` wrapper in `shared/api.js` |
| WebSocket | `RealtimeChannel extends EventTarget` in `shared/ws.js` |
| Auth storage | `localStorage` (`flare.token`, `flare.user`) |
| Serving | FastAPI `StaticFiles(directory=frontend, html=True)` mounted at `/app` |

The buildless choice is load-bearing, not incidental: `main.py` sets a strict CSP with `script-src 'self' https://unpkg.com`, and two commits in the history exist specifically because inline `<script>` blocks broke under it and were extracted to modules rather than the policy being weakened with `'unsafe-inline'`.

### 2.2 Routes

Every route is a static file. There is no client-side router.

| Route | Role | Purpose | API | WS | State |
|---|---|---|---|---|---|
| `/app/` | public | Marketing landing, role chooser | none | none | **IMPLEMENTED**, static |
| `/app/login.html` | public | Sign in / register, tabbed | `POST /auth/signup`, `POST /auth/login`, `GET /auth/me` | none | **IMPLEMENTED** |
| `/app/citizen/` | citizen | SOS trigger + incident lifecycle, four states in one page | `POST /sos`, `GET /sos/{id}` (2s poll), `POST /sos/{id}/resolve` | connects, **receives nothing** | **PARTIAL** |
| `/app/volunteer/` | volunteer | Dashboard + interrupting alert modal | `POST /sos/{id}/accept`, `POST /sos/{id}/decline` | `sos_alert` | **PARTIAL** |
| `/app/volunteer/alert.html` | volunteer | Standalone alert screen, phone-framed, 3 views | `POST /sos/{id}/accept`, `POST /sos/{id}/decline` | none | **PARTIAL** |
| `/app/admin/` | admin | Six analytics panels | `GET /admin/analytics` | none | **IMPLEMENTED** |
| `/app/admin/incidents.html` | admin | Recent incidents table | `GET /admin/incidents` | none | **IMPLEMENTED** |
| `/app/admin/volunteers.html` | admin | Verification queue | none | none | **MOCKED**, labelled |
| `/app/admin/coverage.html` | admin | Coverage gap grid | `GET /admin/analytics` | none | **IMPLEMENTED** |

Preview affordances: `?state=idle|active|expanding|none` on citizen, `?view=incoming|handled|accepted` on the alert page. Both render fixture data and both announce themselves on screen.

### 2.3 Component inventory

There is no component system. "Components" are CSS classes in `shared/components.css` applied to hand-written markup, plus template-literal render functions.

**Shared CSS components (`components.css`):** `.topbar` `.sidebar` `.sidebar__link` `.card` `.btn` (+7 variants) `.sos-button` `.pill` (+5) `.chip` `.stat` `.avatar` `.responder` `.steps`/`.step` `.map` `.map__fallback` `.map__badge` `.overlay` `.alert-card` `.terminal` `.radius-rings` `.list`/`.list__row` `.table` `.field`/`.input` `.toast` (+3) `.switch` `.state-switch`.

**JS render functions:** `renderSteps` `renderIncident` `drawIncident` `drawResponder` (citizen); `renderStats` `renderRecent` `renderBadges` `openAlert` (volunteer); `renderStats` `renderAcceptance` `renderFunnel` `renderTypes` `renderEscalation` `renderAcceptanceBySkill` `renderCoverage` `renderAiStatus` (admin dashboard), `renderIncidents`, `renderPending`, `renderCoverage`.

**Shared JS modules:** `api.js` (auth store, fetch wrapper, `currentPosition`, `requireAuth`, `initials`), `ws.js` (`RealtimeChannel`), `map.js` (Leaflet helpers, ETA, distance), `nav.js` (`inertUnbuiltLinks`), `mock.js` (fixtures), `admin/shared.js` (chart helpers, admin boot, analytics fetch).

**Duplication that should eventually become shared — do not refactor yet:**

1. The topbar block (avatar + name + role) is written four times across the admin pages and twice more in citizen/volunteer, with slightly different markup each time.
2. The admin sidebar `<nav>` is duplicated across four HTML files. This was a deliberate trade when splitting the pages — four eight-line copies beat a JS-rendered nav that fails when JS fails — but it is drift risk and should be acknowledged.
3. The alert card exists twice, in two incompatible implementations: as a modal in `volunteer/index.html` and as a page section in `volunteer/alert.html`, with separate accept/decline handlers that behave differently on a lost race.
4. `formatDistance` / `etaMinutes` live in `map.js` but are used by non-map code.
5. Both `citizen.js` and `admin/shared.js` define an identical `el()` helper.

---

## 3. Feature matrix

Legend: **IMPL** implemented and wired to a real backend · **PART** partially implemented · **MOCK** fixture data on screen · **MISS** not present · **UNK** unknown.

### Citizen

| Feature | FE | BE | Endpoint / Event | Real? | Problem | Pri |
|---|---|---|---|---|---|---|
| SOS trigger | yes | yes | `POST /sos` | **IMPL** | No confirm step; no undo | — |
| Geolocation capture | yes | n/a | `navigator.geolocation` | **IMPL** | Failure disables SOS silently — button stays enabled, error only appears after press | P1 |
| Free-text description | **no** | yes | `SOSCreateRequest.description` | **MISS** | No input exists; `citizen.js` sends `null`. Disables ADR-005 entirely | **P0** |
| Incident status | yes | yes | `GET /sos/{id}` 2s poll | **PART** | Polling, not push — contradicts Ch. 13 step 9 | P1 |
| Responder assigned | yes | yes | `accepted_by` | **PART** | Renders `Responder #{id}`; no name endpoint exists | P2 |
| Responder live location | yes (UI) | **no** | — | **MISS** | Map markers/`drawResponder` exist but only reachable in preview mode | P1 |
| ETA | yes (UI) | **no** | — | **PART** | Live path sets literal text "Responder en route". Real ETA only in preview. Demo script claims an ETA | **P0** |
| Incident resolution | yes | yes | `POST /sos/{id}/resolve` | **IMPL** | Labelled "Cancel Request" but calls resolve | P2 |
| Incident history | **no** | **no** | — | **MISS** | Nav item marked "soon" | P3 |
| No-responder state | yes | yes | `status=no_responder_found` | **IMPL** | Good; genuinely well done | — |
| Escalation display | yes | yes | `current_radius_m`, `wave_count` | **IMPL** | Elapsed timer only ticks on poll | P2 |
| AI category display | yes | yes | `ai_category` | **PART** | Always "Unspecified" live, because description is always null | **P0** |
| Responder rating | yes | **no** | — | **MOCK** | No such column; shows "—" live, "4.8 ★" in preview | P1 |
| Call / Message responder | yes | **no** | — | **MISS** | Two buttons, no handlers, no phone exposure | **P0** |

### Volunteer

| Feature | FE | BE | Endpoint / Event | Real? | Problem | Pri |
|---|---|---|---|---|---|---|
| Authentication | yes | yes | `POST /auth/login` | **IMPL** | — | — |
| Availability toggle | yes | **no** | — | **MISS** | No volunteers router. Toggle changes its own label only, unlabelled on screen | **P0** |
| Skills declaration | **no** | **no** | — | **MISS** | Blueprint Ch. 14 `POST /volunteers/register` absent | P1 |
| Verification status | partial | yes | `volunteers.verified` | **MOCK** | Badges are fixtures; real flag never displayed | P1 |
| Certificate upload | **no** | **no** | — | **MISS** | Future Scope (Ch. 26), correctly declared | — |
| Incoming SOS alert | yes | yes | WS `sos_alert` | **IMPL** | — | — |
| Accept | yes | yes | `POST /sos/{id}/accept` | **IMPL** | Correct on both branches | — |
| Decline | yes | yes | `POST /sos/{id}/decline` | **IMPL** | Modal closes with no confirmation | P2 |
| Already-handled dismissal | yes | yes | `accepted:false` | **PART** | Only discoverable by pressing ACCEPT — no push, alert sits stale indefinitely | **P0** |
| Required-skills chips | yes | **no** | — | **MOCK** | Hard-coded `CPR`/`First Aid` strings | **P0** |
| Incident details | yes | yes | alert payload | **IMPL** | Description always null live | P1 |
| Navigation to incident | link | **no** | `href="#navigate"` | **MISS** | Dead anchor styled as a primary button | **P0** |
| Own location sharing | **no** | **no** | — | **MISS** | Nothing writes `Locations`; only `sim/seed.py` does | **P0** |
| Active assignment view | partial | yes | — | **PART** | A terminal card, not a working screen |P1 |
| Completion / resolve | **no** | yes | `POST /sos/{id}/resolve` | **MISS** | Responder cannot close their own incident | P1 |
| Stats (responses/lives/rating) | yes | **no** | — | **MOCK** | Tiles unlabelled; "Lives Impacted" is fabricated | **P0** |

### Admin

| Feature | FE | BE | Endpoint / Event | Real? | Problem | Pri |
|---|---|---|---|---|---|---|
| Authentication | yes | yes | role dependency on router | **IMPL** | — | — |
| Pending volunteers | yes | **no** | — | **MOCK** | Correctly labelled Not built | — |
| Approve / reject | disabled | **no** | — | **MISS** | Correctly disabled | — |
| Active incidents | yes | yes | `GET /admin/incidents` | **IMPL** | Snapshot per load | P2 |
| Live incident updates | **no** | **no** | — | **MISS** | No admin WS channel exists | P1 |
| Candidate visibility | **no** | yes | `DispatchEvents` | **MISS** | Richest table in the system, no endpoint, no UI | P1 |
| Dispatch waves | partial | yes | `wave_count` | **PART** | Count only, no per-wave breakdown | P2 |
| Radius expansion | partial | yes | `current_radius_m` | **PART** | Number in a table, no map | P2 |
| No-responder state | yes | yes | status pill | **IMPL** | — | — |
| Time-to-acceptance p50/p90/max | yes | yes | `time_to_acceptance` | **IMPL** | — | — |
| Time-to-first-dispatch | **no** | yes | `time_to_first_dispatch` | **MISS** | Computed, shipped in payload, **never rendered** | **P0** |
| Dispatch funnel | yes | yes | `dispatch_funnel` | **IMPL** | — | — |
| Coverage gaps | yes | yes | `coverage_gap` | **IMPL** | — | — |
| Acceptance by skill | yes | yes | `acceptance_rate` | **IMPL** | Radius-band cut hidden in table | P3 |
| Escalation rate | yes | yes | `escalation_rate` | **PART** | See §23 — trigger is mis-recorded on resolve | P1 |
| AI degradation | yes | yes | `ai_degradation_rate` | **IMPL** | Will read ~100% for live incidents | P1 |
| Incidents by category | yes | yes | `incidents_by_category` | **IMPL** | Not one of the Ch. 18A seven | — |
| System status | **no** | partial | `GET /health` | **MISS** | No UI | P2 |

---

## 4. Backend / frontend contract

### 4.1 Endpoints that exist

```
GET    /health                        → {status}
POST   /auth/signup                   → UserOut                    201 | 409
POST   /auth/login                    → {access_token, token_type, expires_in}  | 401
GET    /auth/me                       → UserOut                    | 401
POST   /sos                           → SOSCreateResponse          201
GET    /sos/{id}                      → SOSStatusResponse          | 403 | 404
POST   /sos/{id}/accept               → {accepted, sos_id, status, detail}  | 404
POST   /sos/{id}/decline              → 204
POST   /sos/{id}/resolve              → SOSStatusResponse          | 403 | 404 | 409
GET    /admin/analytics?window_days   → {window_days, metrics{}}   admin only
GET    /admin/incidents?limit         → [ … ]                      admin only
GET    /admin/queries                 → {queries:[…]}              admin only
WS     /ws/{user_id}
```

### 4.2 Endpoints the blueprint specifies that do not exist

Chapter 14 lists these. There is no volunteers router in the codebase at all, and `main.py` mounts only `auth`, `sos`, `ws`, `admin`.

```
POST   /volunteers/register           MISSING
POST   /volunteers/certificate        MISSING  (Future Scope, declared)
PATCH  /volunteers/availability       MISSING  (not declared anywhere in product)
GET    /admin/volunteers/pending      MISSING
POST   /admin/volunteers/{id}/approve MISSING  (Future Scope, declared)
POST   /admin/volunteers/{id}/reject  MISSING  (Future Scope, declared)
```

`PATCH /volunteers/availability` and `POST /volunteers/register` are **not** in Future Scope and **not** labelled in the UI. The availability switch on the volunteer dashboard is the visible consequence.

### 4.3 Payload consumption

`POST /sos` returns `candidates[]`, `evaluated_count` and `alerted_count`. **The citizen client discards all three.** `citizen.js` spreads the response into `renderIncident` and reads only `status`, `current_radius_m`, `wave_count`. Demo script Act 1 step 5 — "the response reports how many volunteers were evaluated versus how many were alerted" — is true of the API and false of the UI.

---

## 5. Real-time architecture

### 5.1 The complete event vocabulary

Client → server: `{"type":"auth","token":"<jwt>"}` — required as the first frame within 5s (ADR-022). Nothing else is ever read; `ws.py` loops on `receive_text()` and discards.

Server → client, **exhaustively**:

| Type | Payload | Recipients |
|---|---|---|
| `auth_ok` | `{type, user_id}` | the connecting user |
| `sos_alert` | `{type, sos_id, lat, lng, description, distance_m, wave_number, radius_m, ai_category, ai_priority, created_at}` | selected volunteers only |

That is the entire protocol. There are no other `send_json` call sites.

### 5.2 Connection lifecycle

`RealtimeChannel` opens the socket, sends auth on `open`, dispatches each message as a DOM event named for `message.type`, and on `close` fires `offline`, then reconnects with exponential backoff (1s doubling to 15s) — except on code 1008, which fires `unauthorized` and stops, correctly, since retrying a rejected token would loop.

Citizen and volunteer both open a channel. **The citizen's socket receives `auth_ok` and then nothing, ever.**

### 5.3 States the frontend cannot currently represent

These are not design omissions; the information does not exist on the client.

| Required state | Blocker |
|---|---|
| Volunteer: your open alert is now dead | No `sos_matched`/`sos_cancelled` event. Alert modal sits stale until the responder acts |
| Citizen: responder accepted (push) | No event. Discovered by 2s poll, so up to 2s late |
| Citizen: radius expanded (push) | No event. Same |
| Citizen: responder position | Nothing writes responder location, and no event carries it |
| Admin: anything live | No admin channel; admins receive no messages at all |
| Any role: server restarted | Socket reconnects, but no resync of missed state |
| Stale data indicator | No server timestamp on the wire to compare against |

### 5.4 How connection state should be represented

Current implementation collapses everything into one `.pill` with text: `Connecting…` → `connected`/`online` → `reconnecting…`. It never shows a hard-failed state, and the citizen's pill says "connected" while the socket is functionally inert.

Recommended six states, all derivable from what `RealtimeChannel` already emits:

1. **connecting** — neutral pill, no dot. First 2s should show nothing at all to avoid flicker.
2. **connected** — green dot, label "Live". On the citizen page this must not be shown, because the channel delivers nothing to citizens; showing "Live" there is a claim about data flow that is false.
3. **disconnected (retrying)** — amber dot, "Reconnecting… (attempt N)". Show the attempt count; a spinner that never resolves is worse than a number.
4. **unauthorized** — terminal, redirect to login. Already handled.
5. **degraded / stale** — if the last successful poll or message is older than 3× the expected interval, mark the data region (not the whole page) with a timestamp: "as of 14:03:22". Requires no new backend.
6. **offline (browser)** — `navigator.onLine === false`, distinct copy, since retrying is pointless.

---

## 6. Current UX audit

### 6.1 Information hierarchy

**Citizen idle — good.** The SOS button is `clamp(180px, 52vw, 240px)`, circular, pulsing, and the only interactive element above the fold. This is correct and should be preserved almost unchanged.

**Citizen active — weak.** The most important fact (a responder is coming, and when) is a `.strong` div at the same visual weight as "Type" and "Location" beside it. On the live path it reads "Responder en route" with no time at all. Meanwhile "Cancel Request" is a full-width outlined button — visually the most prominent control on the panel, which is exactly backwards for an emergency in progress.

**Volunteer dashboard — inverted.** The first thing on the page is three fabricated statistics. Availability, the only control that matters, is one tile among four. The alert modal is the actual product and it only exists as an interruption.

**Admin — improved but flat.** After the page split each screen has one job. Within the dashboard, all six panels carry equal weight; there is no visual answer to "is the network healthy right now?"

### 6.2 Layout, spacing, typography

The spacing scale (`--s-1` … `--s-8`, 4px base) is coherent and used consistently. The type scale is coherent. Headings use Poppins, body Inter, both with system fallbacks — a deliberate hedge against the CDN failing, which Ch. 25 names as a live risk.

The failure is inline styles. `style="font-size:var(--text-lg)"`, `style="max-width:34ch"`, `style="margin-top:var(--s-4)"` appear throughout every HTML file. The tokens are respected, but layout decisions are scattered across markup instead of expressed in classes, so the same intent is re-specified each time it recurs.

Responsive behaviour has exactly one breakpoint, 900px, where the bottom bar becomes a sidebar. There is no tablet treatment. `grid--halves` goes from 1 column to 2 with nothing between.

### 6.3 Colour semantics

| Token | Value | Means | Coherent? |
|---|---|---|---|
| `--flare-red` | `#ef4444` | Emergency, destructive, active nav | **Overloaded** — also the sidebar highlight, which is neither |
| `--navy` | `#0f172a` | Chrome, sidebar, text | Yes |
| `--green` | `#22c55e` | Success, responder, online | Yes |
| `--blue` | `#3b82f6` | Info, radius, links, focus | Yes |
| `--amber` | `#f59e0b` | Warning, timeout trigger | Yes, but only used in admin |
| `--muted` | `#64748b` | Secondary text, inactive | Yes |

The token file states the discipline explicitly: *"Red is reserved. It means emergency… if red is on screen, something is urgent or destructive."* The sidebar's `aria-current` state breaks that rule on every page — a red block sits permanently in the navigation of a calm, idle screen. This is the single largest inconsistency in the colour system and it is self-declared.

There is no dedicated **escalation** colour. Escalation currently borrows blue (radius rings) in the citizen view and amber/red (trigger split) in admin, so the same concept has two different colours in two different roles.

### 6.4 UX defects

- Pressing SOS with no location fires the request, fails server-side, and surfaces a raw error. The button should be disabled until a fix exists, with the reason stated.
- "Cancel Request" calls `resolve`, which means a citizen cancelling records a resolved incident — corrupting the funnel's resolved count and the response-time distribution.
- Decline has no confirmation and no undo.
- The alert modal has no timer, though `ACCEPT_TIMEOUT_SECONDS` governs its lifetime.
- `location.reload()` is used as state management in three places on the citizen page.
- Terminology drifts: "volunteer" vs "responder" vs "Responder #12" in adjacent UI; "Cancel" vs "Resolve" for one action.
- The preview state-switcher (`?state=`) is a fixed overlay that ships in production markup, hidden by a `hidden` attribute.

---

## 7. UX state machines

### Citizen

```
idle ──locating──▶ located ──[SOS pressed]──▶ dispatching
                      │
                      └──[geolocation denied]──▶ blocked (SOS disabled, reason shown)

dispatching ──[201, alerted_count>0]──▶ searching (wave 1)
            └──[201, alerted_count=0]──▶ searching (expanding immediately)

searching ──[status=matched]────────▶ assigned ──▶ en route ──▶ resolved
          └──[radius grows]─────────▶ searching (wave N)
          └──[status=no_responder_found]──▶ terminal
```

| State | Sees | Primary action | Secondary | Priority | Transition source |
|---|---|---|---|---|---|
| idle/located | SOS button, location line | **SOS** | — | Max | `navigator.geolocation` |
| blocked | Reason, retry | Enable location | Call 112 | High | geolocation error |
| dispatching | Button busy | — | — | Max | `POST /sos` pending |
| searching | Radius, wave, elapsed, ring | Call 112 | Cancel | High | poll `status=pending` |
| assigned | Responder, **ETA**, map | Call 112 | Cancel | Max | poll `status=matched` |
| terminal | Calm explanation | **Call 112** | New request | Max | poll `no_responder_found` |
| resolved | Confirmation | New request | History | Low | poll `status=resolved` |

**Missing today:** `blocked`, and a real `assigned` (no ETA, no responder identity, no movement). `resolved` currently falls through to `idle` with no acknowledgement that anything happened.

### Volunteer

```
offline ──[toggle]──▶ online ──▶ waiting ──[sos_alert]──▶ reviewing
reviewing ──[accept, rowcount=1]──▶ assigned ──▶ navigating ──▶ completing ──▶ resolved
          ├─[accept, rowcount=0]──▶ dismissed ("already handled")
          ├─[decline]────────────▶ waiting
          └─[timeout / someone else won]──▶ dismissed   ◀── NOT REACHABLE TODAY
```

The last transition is the gap: nothing pushes it, so a stale alert never resolves itself.

| State | Sees | Primary | Secondary | Priority | Source |
|---|---|---|---|---|---|
| offline | Toggle off | **Go Online** | — | Med | *(no endpoint)* |
| waiting | Coverage, verification | — | Edit skills | Low | — |
| reviewing | Category, distance, description, map, **countdown** | **ACCEPT** | Decline | Max | `sos_alert` |
| assigned | Incident, navigation | **Navigate** | Call citizen | Max | `accepted:true` |
| dismissed | "Already handled" | Back | — | Low | `accepted:false` |
| completing | Arrived | **Mark resolved** | — | High | *(no responder resolve UI)* |

### Admin

```
monitoring ──▶ incident appears ──▶ candidates evaluated ──▶ wave 1
wave 1 ──[timeout]──▶ wave 2 ──[timeout]──▶ wave 3 ──▶ no_responder_found
       └──[accepted]──▶ tracking ──▶ resolved
```

Admin currently has no live transitions at all — every state is discovered by reloading.

---

## 8. Information architecture

```
/app/
├── (public)      landing, login
├── citizen/      one page, state-driven          ← keep
├── volunteer/    dashboard · alert · assignment  ← alert should merge into one implementation
└── admin/        dashboard · incidents · incident detail · volunteers · coverage
```

Recommended additions, in dependency order: **volunteer → assignment** (a real screen, replacing the terminal card), and **admin → incident detail** (`/app/admin/incident.html?id=N`), which is where the `DispatchEvents` log belongs — the single richest artefact in the system, currently invisible.

Role boundaries stay enforced client-side by `requireAuth(role)` and server-side by the router dependency. Keep both; the client check is a redirect convenience, the server check is the security boundary.

---

## 9. Design system

Most of this exists. The proposal is mostly **subtraction and naming**, not replacement.

### Colour — changes only

| Token | Now | Proposed | Why |
|---|---|---|---|
| `--flare-red` | emergency + nav highlight | **emergency only** | Restores the file's own stated rule |
| `--nav-active` | — | `--navy-soft` + 3px `--flare-red` left rule | Highlights without a red block on a calm screen |
| `--escalation` | — | `--amber` | Escalation is neither emergency nor info; it currently borrows both |
| `--surface-2` | — | `#f8fafc` | For nested panels; today everything is white on `--surface-alt` |

Keep every other token. The palette is locked by the design spec and the colourblind-ordering work already done in `admin/shared.js` (red → amber → blue → green, worst adjacent pair ΔE 13.9) is sound and should be preserved verbatim.

### Typography, spacing, radius, shadow

Unchanged — all four scales are coherent. Add one rule: **numerics that change over time use `font-variant-numeric: tabular-nums`**. The class exists (`.numeric`) and is applied inconsistently; the elapsed timer and ETA jitter without it.

### Motion

| Element | Duration | Rule |
|---|---|---|
| SOS pulse | 2.2s loop | Keep. The one decorative animation that earns its place |
| Alert arrival | 220ms slide+fade | Keep |
| Status change | 150ms colour only | Never animate position on a status change |
| Radius ring | 1.8s loop | Keep, but only while actually expanding |
| Map pan | 400ms ease | Never animate a marker jump > 200m; teleport and let the trail show |
| Numbers | **none** | Never count up. A counting ETA is unreadable under stress |

`prefers-reduced-motion` is already honoured globally in `tokens.css`. Keep it as the first rule, not an afterthought.

### Iconography

Currently Unicode emoji, which render differently per platform and are announced verbosely by screen readers. They are also, at ~14 glyphs, not worth a dependency to replace. **Recommendation: keep emoji, but mark every decorative one `aria-hidden="true"`** — several already are, most are not. Revisit only if the inconsistency becomes visible on the demo machine.

---

## 10. Citizen design

The citizen interface must not become a dashboard. Its whole job is one button, then one honest answer.

**Idle.** Unchanged in structure. Add: a description field, optional, collapsed to a single tap-to-expand line beneath the button — *"Add a detail (optional)"*. This is the minimum surface that makes ADR-005 real. It must not gate the SOS: pressing SOS with the field untouched must behave exactly as today.

**Blocked (new).** When geolocation fails, the SOS button is disabled and beneath it: the reason, a Retry, and Call 112. Today the button stays live and fails after the press.

**Searching.** Keep the ring and the radius/wave/elapsed triplet — this screen is genuinely good. Fix the elapsed timer to tick locally every second rather than only on the 2s poll.

**Assigned.** Restructure so the ETA is the largest element on the panel, with the responder beneath it and the map beside. Remove the Call and Message buttons until a channel exists. Demote Cancel to a text link.

**Terminal.** Unchanged. This screen is the best-designed thing in the product.

---

## 11. Volunteer design

The alert must answer five questions in the order a responder asks them: **What? Where? How far? Am I qualified? What do I do?**

Current order is category → distance → description → skills → map → actions, which is nearly right. Two changes: distance should be as prominent as category (it is the accept/decline determinant), and the skills row must either reflect real data or be removed — today it is invented.

**Dashboard.** Availability becomes the hero: a full-width card, large toggle, with verification state and coverage radius beneath. The three fabricated stat tiles are removed, not relabelled — a statistic that was never measured has no honest presentation at dashboard scale.

**Alert.** One implementation, not two. Add a countdown ring showing time remaining against `ACCEPT_TIMEOUT_SECONDS`, and a stale state for when the incident is gone.

**Assigned.** A real screen: incident location, distance, description, a map, and **Mark resolved**. Currently a terminal card with a dead `href="#navigate"`.

---

## 12. Admin design

The four-page split is done. What remains:

**Dashboard** gains a status strip above the panels: active incidents, responders connected, oldest pending incident age. All three are cheap and turn a report into an operations view.

**Incident detail (new)** — the highest-value addition in this document. One incident, its wave timeline, and every `DispatchEvents` row with its rejection reason. This is the artefact ADR-014 exists to produce and it currently has no reader. It is also the single best answer to "why didn't responder X get alerted?" in a viva.

**Coverage** unchanged; the grid is correct and the explanatory copy is good.

**Volunteers** unchanged until a backend exists.

---

## 13. Analytics design

Every metric below already has a query file and returns real rows. Nothing here invents a metric.

| Metric | Question | Chart | Empty state |
|---|---|---|---|
| `time_to_acceptance` p50/p90/max | How bad is the tail? | Three numerics + histogram | "No accepted incidents in window" |
| `time_to_acceptance_histogram` | Where does the mass sit? | Vertical bars, direct-labelled | as above |
| **`time_to_first_dispatch`** | **Is latency ours or the network's?** | **Numeric pair vs time-to-acceptance** | **NOT RENDERED — must be added** |
| `dispatch_funnel` | Where does it leak? | Horizontal bars + drop-off deltas | Zero row shown, not hidden |
| `coverage_gap` | Where do we recruit? | Sequential heat grid | "No incidents in window" |
| `acceptance_rate` | Does skill ranking work? | Bars by skill, band in table | — |
| `escalation_rate` | Sparse or unresponsive? | Stacked bar, A vs B | — |
| `ai_degradation_rate` | How often does the weak dep fail? | Headline % + breakdown | — |

Every panel already prints its `.sql` filename. Keep that; it is the most defensible thing on the screen.

**Two caveats that must be shown on screen, not just known:**

1. `escalation_rate` LEFT JOINs `incident_history`, which is written only on resolve or exhaustion. Incidents still pending or matched-but-unresolved therefore report `trigger='none'` regardless of how far they escalated. The panel understates escalation for any live window.
2. AI degradation will read close to 100% for organically-created incidents, because no description is ever submitted (§3). Until the description input exists, this panel measures the missing input, not the AI.

---

## 14. Map design

Current implementation (`shared/map.js`) is sound: CDN Leaflet with a styled fallback on failure, `divIcon` markers, a three-circle radius ladder with the active rung solid, and an explicitly straight-line ETA at 5.5 m/s.

**Respect the limitation.** ETA is `distance / average speed`. Never label it "arrival time", never draw a route line, never animate a marker along a path — all three would imply routing that Ch. 26 names as not built. Label it *"~4 min (straight line)"*.

| Role | Shows | Interaction |
|---|---|---|
| Citizen | Incident pin, radius ladder, responder marker when one exists | Fit bounds to both; no free pan needed |
| Volunteer | Incident pin, own position, distance line | Tap to open native maps |
| Admin (detail) | Incident, radius rings per wave, alerted vs rejected candidates | Hover a candidate → its rejection reason |

Do not add clustering, heatmap layers, or a second tile provider.

---

## 15. Error / empty / loading / degraded states

The mandate is that no feature ships with only a happy path. Current coverage:

| Feature | Loading | Empty | Error | Offline | Unauthorized | Special |
|---|---|---|---|---|---|---|
| Login | ✅ button disabled | n/a | ✅ toast | ❌ | n/a | — |
| SOS trigger | ✅ button disabled | n/a | ✅ toast | ❌ | ✅ redirect | ❌ no-location |
| Incident poll | ❌ | n/a | ❌ silent catch | ❌ | ✅ | ✅ terminal |
| Volunteer alert | ✅ | ❌ no "no alerts" state | ✅ | ❌ | ✅ | ✅ already-handled |
| Admin analytics | ✅ banner | ⚠️ per-panel, inconsistent | ✅ banner | ❌ | ✅ | ❌ partial-failure |
| Admin incidents | ❌ | ✅ | ✅ | ❌ | ✅ | — |
| Map | ❌ | n/a | ✅ fallback | ✅ fallback | n/a | — |

**The two worst gaps:** the citizen incident poll swallows every error silently (`catch { /* transient */ }`), so a citizen whose session dies mid-emergency sees a frozen screen that looks live; and `analytics.metric()` degrades a failed query to empty rows, so a broken panel is indistinguishable from a panel with no data. The second needs a per-panel "this query failed" state, since the backend already distinguishes the cases.

---

## 16. Accessibility

**Present:** semantic `<nav>`/`<main>`/`<header>`, `aria-label` on all three sidebars, `role="dialog"`/`aria-modal` on the alert, `aria-current` for nav state, `:focus-visible` with a 2px blue outline, `.visually-hidden`, `prefers-reduced-motion` honoured globally, `aria-disabled` on unbuilt links, chart `<title>` elements plus a table view for every chart.

That is a stronger baseline than most projects at this stage.

**Gaps, in severity order:**

1. **No focus trap in the alert modal.** It is `aria-modal="true"` but focus is neither moved into it nor confined. A keyboard user is interrupted by an emergency they cannot reach.
2. **No live regions.** Status changes — responder assigned, radius expanded, no responder found — are announced to nobody. Each state container needs `aria-live="polite"`; the terminal state warrants `assertive`.
3. **Decorative emoji unlabelled.** Most sidebar icons lack `aria-hidden`, so navigation is read as "fire Emergency, clipboard My Requests".
4. **Contrast.** `--muted #64748b` on `--surface-alt #f1f5f9` is ≈4.3:1 — passes AA for body text, fails for the `--text-xs` labels it is most used on.
5. **Touch targets.** Bottom-bar items compute below 44px on small screens.
6. **`.steps` has `min-width: 520px`** inside a scroll container, so the citizen progress stepper is horizontally scrollable on every phone.

---

## 17. Responsive strategy

One breakpoint today (900px). Proposed three:

| Range | Layout |
|---|---|
| < 600px | Single column, bottom nav, SOS fills the viewport, map ≤ 40vh |
| 600–899px | Single column, bottom nav, two-up stat tiles, map beside panel in landscape |
| ≥ 900px | Sidebar, two-column grids, map persistent |

The citizen view is the one that must be perfect at < 600px — it is the only role likely to be used on a phone in the situation it was designed for.

---

## 18. Component architecture

Proposed shared set, promoted from what already exists. No new concepts.

**Layout:** `AppShell` `Sidebar` `Topbar` `Card` `StatTile`
**Status:** `ConnectionPill` `StatusPill` `SkillChip` `VerificationBadge`
**Emergency:** `SosButton` `AlertCard` `RadiusRings` `Stepper` `TerminalState`
**Data:** `DataTable` `Histogram` `FunnelChart` `Donut` `HeatGrid` `TraceLabel`
**Feedback:** `Toast` `EmptyState` `ErrorState` `LoadingState` `NotBuiltNotice`
**Map:** `MapCanvas` `IncidentMarker` `ResponderMarker` `RadiusOverlay` `MapFallback`

`NotBuiltNotice` deserves naming: the pattern already exists three times (the disabled approval queue, the "soon" nav items, the sample-data note) with three different implementations. It is this project's signature move and it should be one component.

---

## 19. Proposed folder structure

```
frontend/
├── shared/
│   ├── tokens.css          design tokens          (exists)
│   ├── base.css            reset, shell, helpers  (exists)
│   ├── components.css      component classes      (exists)
│   ├── api.js              fetch + auth           (exists)
│   ├── ws.js               RealtimeChannel        (exists)
│   ├── map.js              Leaflet helpers        (exists)
│   ├── nav.js              inert links            (exists)
│   ├── format.js           NEW  distance/duration/eta/initials
│   └── states.js           NEW  loading/empty/error/not-built renderers
├── citizen/    index.html  citizen.js
├── volunteer/  index.html  volunteer.js  alert.html  alert.js  assignment.html  assignment.js
└── admin/      index.html  admin.js  shared.js  admin.css
                incidents.html  incidents.js  incident.html  incident.js
                volunteers.html volunteers.js  coverage.html  coverage.js
```

Three new files, two new pages, no new dependencies, no build step. `mock.js` shrinks to only what the declared-unbuilt features need.

**No new dependency is recommended.** The two that might tempt: a charting library (rejected — the six charts are ~200 lines of SVG and a library is a dependency bought to avoid an afternoon, per the existing comment) and a router (rejected — there is nothing to route; static files and `html=True` already work).

---

## 20. Design debt, ranked

### P0 — misleading functionality

| # | Problem | Evidence | Fix |
|---|---|---|---|
| 1 | No description input; every live SOS is `ai_status='skipped'` | `citizen.js:175` sends `null`; `ai_summary.py:164` | Add optional field to citizen idle |
| 2 | Fabricated skill chips on the alert | `volunteer.js:70-72` hard-codes CPR/First Aid | Remove or bind to real data |
| 3 | Call / Message buttons with no handlers | `citizen/index.html:89-90` | Remove until a channel exists |
| 4 | `href="#navigate"` styled as a primary button | `alert.html:106` | Remove or wire to a maps URL |
| 5 | Availability toggle changes only its own label | `volunteer.js:137-141`; no volunteers router | Label as not built, or build `PATCH` |
| 6 | Three fabricated volunteer statistics, tiles unlabelled | `volunteer/index.html:62-64` | Remove the tiles |
| 7 | `time_to_first_dispatch` computed, shipped, never rendered | `analytics.py:91`; absent from all frontend | Add panel — one of the Ch. 18A seven |
| 8 | README claims "all seven Ch. 18A metrics" | `README.md:11-12`; six are rendered | Render the seventh, or correct the claim |
| 9 | Volunteer never told their alert died | No such WS event | Add event, or add a stale state |
| 10 | Demo script instructs actions the UI cannot perform | `DEMO_SCRIPT.md:66` (description), `:80` (ETA) | Fix UI or fix script |

### P1 — major UX / architecture

| # | Problem | Fix |
|---|---|---|
| 11 | Citizen polls despite Ch. 13 step 9 rejecting polling | Decide: build push, or amend the blueprint |
| 12 | "Cancel Request" calls `resolve`, corrupting the funnel | Separate cancel from resolve |
| 13 | Live ETA never shown; only in preview | Compute from `accepted_by` position — needs responder location |
| 14 | No responder location writer anywhere | Build, or declare in-product |
| 15 | Poll errors swallowed silently | Surface a stale-data indicator |
| 16 | `escalation_trigger` mis-recorded on resolve (see §23) | Backend fix; corrupts an admin panel |
| 17 | No focus trap in the alert modal | Trap and restore focus |
| 18 | No `aria-live` on any state change | Add to state containers |
| 19 | Alert card exists in two divergent implementations | Merge |
| 20 | `DispatchEvents` has no reader | Build admin incident detail |

### P2 — polish

Sidebar red block contradicts the token file's own rule · no tablet breakpoint · `.steps` overflows every phone · `location.reload()` as state management · terminology drift (volunteer/responder/Responder #12) · muted-on-tint contrast at `--text-xs` · elapsed timer ticks only on poll · admin incidents table has no refresh · inline styles scattered across markup.

### P3 — optional

Incident history for citizens · per-wave breakdown in admin · radius-band cut promoted out of the table · system-status panel · vendoring Leaflet (already a settled Future Scope decision).

---

## 21. Redesign roadmap

Ordered by dependency, not by appearance.

| Phase | Work | Files | Backend needed | Risk | Done when |
|---|---|---|---|---|---|
| **0** | Remove every P0 claim: fake chips, dead buttons, dead anchor, fabricated stats; label the availability toggle | `citizen/index.html`, `volunteer/*`, `alert.html` | none | **Low** | No control on screen does nothing; no number on screen was never measured |
| **1** | Description input; render `time_to_first_dispatch`; correct the README claim | `citizen/*`, `admin/*`, `README.md` | none | Low | An SOS can carry text; seven metrics on screen |
| **2** | Token additions (`--nav-active`, `--escalation`, `--surface-2`); pull inline styles into classes | `shared/*.css` | none | Low | Red appears only on emergency/destructive |
| **3** | State primitives: `states.js`, `format.js`, `NotBuiltNotice` | `shared/` | none | Low | Every feature has loading/empty/error |
| **4** | Citizen: blocked state, ETA hierarchy, cancel≠resolve, local timer | `citizen/*` | cancel endpoint | Med | State machine of §7 fully reachable |
| **5** | Volunteer: merge alert implementations, availability hero, assignment screen, countdown | `volunteer/*` | `PATCH /volunteers/availability` | Med | Volunteer machine reachable end to end |
| **6** | Admin incident detail + `DispatchEvents` view | `admin/incident.*` | `GET /admin/incidents/{id}/events` | Med | "Why wasn't X alerted?" answerable on screen |
| **7** | Real-time: decide push vs poll; connection states; stale indicators; volunteer stale-alert | `shared/ws.js`, all roles | new WS events | **High** | §5.3 table has no blockers left |
| **8** | Map: responder marker on live data, per-wave rings in admin | `shared/map.js` | responder location | High | Depends on 7 |
| **9** | Accessibility: focus trap, live regions, `aria-hidden`, contrast, touch targets | all | none | Low | Keyboard-only run of all three roles |
| **10** | Responsive: three breakpoints, `.steps` fix | `base.css` | none | Low | Citizen flawless < 600px |

Phases 0–3 are pure subtraction and cost little. Phase 7 is the fork that needs your decision before anything after it can be scoped.

---

## 22. Demo choreography

| Act | Needs | Exists? |
|---|---|---|
| **1** Happy path | SOS with description | ❌ **no input** |
| | Alert with category | ⚠️ null live |
| | Evaluated vs alerted counts visible | ❌ returned, discarded |
| | Assignment + **ETA** | ❌ "Responder en route" |
| | Responder marker moving | ❌ not built |
| **2** Concurrency | One winner | ✅ |
| | Others see "already handled" | ⚠️ only on click |
| | 49 losers in browser | ❌ terminal only |
| **3** Honest failure | Ladder 1→2→3 km | ✅ |
| | `no_responder_found` screen | ✅ **best screen in the product** |
| | AI degradation visible | ⚠️ indistinguishable from the always-skipped default |
| **4** Analytics | Funnel, histogram, coverage, escalation split | ✅ |
| | Query filename per panel | ✅ |
| | Seven metrics | ❌ six |

Acts 3 and 4 are demo-ready today. Act 1 has four gaps, three of which Phase 0–1 closes. Act 2's weakness is that the correctness claim — the project's centrepiece — is proven in a terminal while the browser shows nothing.

---

## 23. Blueprint vs code discrepancies

Per Rule 13 these are surfaced, not resolved.

**D1 — Polling vs push.** Ch. 13 step 9: the citizen receives updates "over its own WebSocket channel (push, not polling — polling is explicitly rejected here since the socket already exists)". The code polls `GET /sos/{id}` every 2s and the citizen socket delivers nothing. Either the code is wrong or the blueprint needs an ADR amendment.

**D2 — Volunteers router absent.** Ch. 14 specifies `POST /volunteers/register` and `PATCH /volunteers/availability`. Neither exists, and neither is in Ch. 26 Future Scope. They are simply missing, and the UI has a control for one of them.

**D3 — `escalation_trigger` on resolve contradicts ADR-023.** `acceptance.resolve()` writes `TIMEOUT` whenever `wave_count > 1`, unconditionally. ADR-023 requires the trigger that *initiated* escalation. An incident that escalated under condition A (empty set) and was then accepted is filed as `timeout` — the opposite diagnosis, in the exact metric ADR-015 built to distinguish the two. `escalation.py` gets this right via `initial_trigger`; `acceptance.py` does not.

**D4 — Seven metrics claimed, six rendered.** README states the dashboard "reports all seven Chapter 18A metrics". `time_to_first_dispatch` is queried and returned but never displayed.

**D5 — ADR-005's AI touchpoint has no input.** The single bounded call is defined as free-text → `{category, priority}`. The product collects no free text.

**D6 — Certificate upload.** Ch. 26 correctly moves it to Future Scope, but Ch. 11 still lists "Skill/certification declaration (set once, editable)" as a core volunteer view. Nothing implements it.

---

## 24. Open questions

- **UNKNOWN:** whether any responder location writer was ever intended for the browser, or whether `sim/seed.py` was always the only source. Nothing in the repo settles it.
- **UNKNOWN:** whether the volunteer stat tiles were meant to become real (a responder-history query) or were always placeholder chrome.
- **UNKNOWN:** the intended lifetime of an unanswered alert modal on screen. `ACCEPT_TIMEOUT_SECONDS` governs escalation, not the UI.
- **UNKNOWN:** whether admins are expected to observe incidents live for the demo, or reload deliberately.
