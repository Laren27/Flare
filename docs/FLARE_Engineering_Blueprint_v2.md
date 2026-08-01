# FLARE — Fast Local Alert & Response Engine
## Engineering Blueprint v2.0
### System Architecture, Development Guide & Technical Specifications

**Build model:** Solo developer working in pair with an AI collaborator (Claude / Claude Code). All demo choreography, testing strategy, and roadmap in this document assume a single operator, not a four-person team.

**Timeline:** 8 weeks.

---

## How To Use This Document

This is the single source of truth for this project. Any teammate, and any AI assistant helping build this project, should defer to this document before making architectural decisions. If a suggestion (yours, a teammate's, or Claude's) conflicts with this blueprint, the blueprint wins unless the team explicitly votes to amend it — and any amendment gets logged in the ADR (Chapter 4) and Changelog (end of document).

The standard this project is held to:

> **A polished, technically sound, real-time emergency dispatch MVP with a rigorous analytics layer, that demonstrates strong software engineering principles, solves a genuine problem, and is fully achievable by one third-year B.Tech student working with an AI collaborator over eight weeks.**

Every chapter below must satisfy three tests:
1. Is it technically correct?
2. Can one student realistically build it in eight weeks?
3. Will it make an evaluator think "these students designed this like engineers, not just coders"?

---

# PART I — PRODUCT FOUNDATION

## Chapter 1 — Vision

Out-of-hospital emergencies (cardiac arrest, choking, trauma bleeding) are frequently survivable if help arrives within the "Golden Hour" — often the first few minutes. Standard ambulance dispatch takes 8–15 minutes to reach a scene, while large numbers of citizens are CPR/first-aid trained but structurally invisible to emergency dispatch systems. There is no mechanism connecting a citizen in crisis to a nearby trained civilian in real time.

FLARE closes this gap with two tightly coupled capabilities:

1. **A dispatch engine** — real-time, radius- and skill-aware civilian responder dispatch.
2. **A decision-support layer** — every dispatch decision the engine makes is logged as a structured event, and those events are aggregated into operational metrics that answer the question a real deployment would actually be judged on: *where is this network failing, and why?*

These are not two projects. The second is a direct consequence of building the first honestly: a dispatch engine that cannot explain its own decisions is not a system, it is a demo. The analytics layer is what turns the dispatch log into evidence.

FLARE is not an attempt to replace ambulances, hospitals, or emergency medical services. It is a bridging layer — get *someone qualified* to the scene in the minutes before professional help arrives.

## Chapter 2 — Product Philosophy

- **One system, one job, done well.** FLARE is a dispatch engine, not an "emergency ecosystem." Every feature must serve the dispatch loop directly.
- **Honesty over ambition.** We do not claim capabilities we haven't built (e.g., we do not claim clinical-grade AI diagnosis, and we do not claim guaranteed delivery to backgrounded devices unless we've actually implemented Web Push).
- **Demoable over theoretical.** If a feature can't be shown working end-to-end in a live demo, it does not belong in core scope — it belongs in Future Scope (Chapter 26).
- **Judgment is part of the grade.** Explicitly stating what we chose *not* to build, and why, is treated as a deliverable, not an omission.

## Chapter 3 — Engineering Principles (Decision Boundaries)

These rules exist to stop scope creep and stop any contributor — human or AI — from drifting the project into unnecessary complexity.

```
RULE 001 — Never introduce a new technology unless it solves an
           existing, demonstrated problem in this project.

RULE 002 — Always prefer the simpler architecture that satisfies
           the requirement, over the more "impressive" one.

RULE 003 — Every feature must be demoable end-to-end. If it can't
           be shown working live, it is Future Scope, not core scope.

RULE 004 — Never optimize before measurement. Don't build for scale
           this project will never see (e.g., no PostGIS for a
           demo-scale responder table).

RULE 005 — One backend language: Python (FastAPI). No polyglot
           backend services.

RULE 006 — Every major architectural decision must be recorded in
           the ADR (Chapter 4) — including decisions to NOT do
           something, and why.

RULE 007 — Every claim made in the pitch/demo must correspond to
           code that actually exists. No slideware features.

RULE 008 — Prefer one thing built and demoed over three things
           half-built.
```

## Chapter 4 — Architecture Decision Records (ADR)

This is a running log. New entries go at the bottom. Format: Decision → Alternatives considered → Why this one.

**ADR-001: Backend framework**
- Decision: FastAPI (Python)
- Alternatives considered: Node/Express + Socket.io, Django
- Why: Team already has working FastAPI experience (routers, Pydantic, deployment) from prior projects. Native async support makes WebSocket handling straightforward. Keeps the whole backend in one language (Rule 005).

**ADR-002: Radius / proximity computation**
- Decision: Haversine formula computed in application code over a small responder table.
- Alternatives considered: PostGIS, geohashing.
- Why: At demo scale (tens of responder records), a spatial database extension adds infrastructure complexity with no benefit, and the team could not justify it under viva questioning (Rule 002, Rule 004). Geohashing and PostGIS are explicitly named in Future Scope as the correct answer at production scale — this demonstrates awareness without overbuilding.

**ADR-003: Real-time alert delivery — core scope**
- Decision: WebSocket-based broadcast, foreground-app only, for the primary demo.
- Alternatives considered: Plain polling, native push via FCM/APNs (native app).
- Why: WebSockets are sufficient to prove the real-time dispatch concept in a live demo where devices are actively open. Native push requires a native mobile app (React Native/Flutter), which is a separate skill set the team does not currently have, and is disproportionate to a demo-focused deliverable.

**ADR-004: Real-time alert delivery — reliability upgrade (conditional)**
- Decision: Web Push API (service worker + PushManager + VAPID keys via `pywebpush`) is the designated *next* step if time permits, to handle backgrounded/screen-off devices — NOT native push.
- Why: Web Push is a standard browser API achievable without becoming a mobile app project, and meaningfully closes the gap between "demo works" and "would work outside a demo room." This is explicitly conditional — it does not block core delivery.

**ADR-005: AI usage — scope boundary**
- Decision: Exactly one AI touchpoint: free-text incident description → LLM-generated priority/category summary (e.g., "Possible Cardiac Arrest — Priority: High"). No AI-based diagnosis, no AI-based image/document parsing for this module, no voice/emotion analysis.
- Why: A single, well-justified AI call is easy to explain and defend in a viva. Multiple AI features invite questions the team cannot rigorously answer (model accuracy, validation data, clinical claims) and dilute focus from the actual novel engineering (the dispatch engine).

**ADR-006: Volunteer verification**
- Decision: Manual admin approval of uploaded certificates (CPR / blood donor / first-aid / college volunteer ID). No automated document verification, no third-party identity API.
- Why: Automated verification (OCR + validation against an authority database) is a project on its own and out of reach given available data sources. Manual approval is honest about the limitation while still producing a credible "Verified Responder" status in the product.

**ADR-007: Matching algorithm — skill-awareness**
- Decision: Responder matching is radius-filtered AND skill-filtered/ranked (CPR-trained, blood donor, first-aid certified, general volunteer), not purely nearest-distance.
- Why: This is the single highest-leverage, low-cost technical improvement identified — a few extra DB fields and a filter/sort change — that shifts the system's framing from "find nearest volunteer" to "find the nearest *qualified* volunteer," which is both a real technical upgrade and a stronger narrative.

**ADR-008: Fallback / no-responder-found path**
- Decision: If zero responders are found within the initial radius, the system automatically retries with an expanded radius (e.g., 1km → 2km → 3km) before surfacing a "no responder available, escalate to emergency services" state.
- Why: Most comparable student projects only demo the happy path. Building and demoing the failure path signals real systems thinking for negligible extra engineering cost (Rule 003, Rule 008).

**ADR-009: Analytics / admin dashboard**
- Decision: Admin panel includes a lightweight analytics view (average response time, coverage gaps by area, acceptance rate by responder skill type) built from data already captured in Incident History — not a separate BI tool.
- Why: The team has direct prior experience building this kind of analytics layer (a prior dashboard project). It costs little beyond what's already logged and differentiates the project from functionally-similar submissions that stop at "it works."

**ADR-010: Concurrency correctness**
- Decision: The "first-acceptance-lock" behavior (first responder to accept wins; others are notified the incident is already handled) must be explicitly demonstrated under concurrent load (multiple simultaneous SOS events / multiple responders racing to accept), not just a clean 1-on-1 demo.
- Why: This is the actual hard backend-correctness claim in the system (race condition handling). Proving it under concurrency, not just asserting it, is what separates a real claim from a slideware claim (Rule 007).

**ADR-011: Accept-lock enforcement mechanism**
- Decision: The lock is enforced by a single conditional SQL statement at the database layer, not by application-level read-then-write logic:
  ```sql
  UPDATE sos
     SET status = 'matched', accepted_by = :responder_id, matched_at = now()
   WHERE id = :sos_id AND status = 'pending';
  ```
  The service inspects `rowcount`. A value of 1 means this responder won; 0 means another responder already claimed it, and this responder receives an "already handled" dismissal.
- Alternatives considered: Python-level check (`if sos.status == 'pending': ...`), `SELECT ... FOR UPDATE` row locking, an in-process `asyncio.Lock`.
- Why: The naive Python check is a genuine time-of-check-to-time-of-use race and would not survive scrutiny. `SELECT FOR UPDATE` is correct but heavier and holds a transaction open. An in-process lock is wrong in principle — it silently breaks the moment the app runs more than one worker. The conditional UPDATE is atomic by definition of the database's own guarantees, is a single round trip, and remains correct under multiple workers. This ADR exists because ADR-010 mandates *proving* the lock; a claim of correctness requires a stated mechanism.

**ADR-012: Radius expansion trigger**
- Decision: Expansion is triggered by **two distinct conditions**, handled by the same escalation state machine:
  - **Condition A — empty candidate set.** Zero eligible responders in the current radius: expand immediately, no delay.
  - **Condition B — acceptance timeout.** Candidates were alerted but none accepted within `ACCEPT_TIMEOUT_SECONDS` (default 30): expand, and alert the newly-included responders. Previously-alerted responders keep their open alert.
  - Escalation ladder: 1km → 2km → 3km → `no_responder_found`.
- Alternatives considered: empty-set-only expansion (the v1.0 implicit reading); timeout-only expansion.
- Why: Empty-set-only expansion silently assumes that being alerted equals responding, which is the single most unrealistic assumption a dispatch system can make — real responders are asleep, driving, or unwilling. Timeout-only expansion wastes 30 seconds of an emergency when the system already knows nobody is there. Both conditions are cheap once the escalation is modelled as a state machine with a background task rather than as an inline loop, and the resulting behaviour is defensible as *actual dispatch logic* rather than a retry hack.
- Implementation note: this requires a background task per active SOS (`asyncio.create_task`) that sleeps, re-checks status, and escalates. Task handles are held in a registry so they can be cancelled the moment an acceptance lands.

**ADR-013: AI summary removed from the dispatch critical path**
- Decision: The LLM call does **not** block the first dispatch wave. Sequence: SOS is persisted → wave 1 alerts dispatch immediately using radius + declared-skill ranking only → the AI call runs concurrently → its `{category, priority}` result refines ranking for wave 2 (any expanded-radius wave) and is attached to the incident record and the responder-facing alert detail view.
- Constraints: hard timeout of 3 seconds; on timeout or error, category defaults to `unspecified` and priority to `medium`, and this fallback is logged as a dispatch event.
- Alternatives considered: AI call blocking dispatch (the v1.0 reading of Chapter 13 step 4).
- Why: An emergency dispatch system that waits 1–3 seconds on a third-party API before alerting anyone is contradicted by its own premise. Making the AI enrichment asynchronous costs one `asyncio.gather` and converts the project's weakest dependency from a single point of failure into a graceful degradation — which is a stronger engineering story than the blocking version ever was.

**ADR-014: Structured dispatch event log**
- Decision: Every dispatch decision emits a structured event row recording *why* each candidate was or was not selected — distance, radius at evaluation time, skill match, availability, verification status, and outcome. This log is the single source of truth for both debugging and the analytics layer.
- Alternatives considered: plain text application logging; no decision logging (v1.0).
- Why: Without this, the answer to "why didn't responder X get alerted?" is a shrug, and the analytics dashboard has to reconstruct decisions it never observed. With it, the same table serves live debugging, the demo narrative, and every metric in ADR-015 — one artefact, three uses. This is a low-cost, high-credibility addition (Rule 008 in spirit: build one thing that does real work).

**ADR-015: Analytics as a co-headline deliverable**
- Decision: The analytics layer is promoted from "lightweight admin view" (ADR-009) to a co-primary deliverable with defined metrics, a documented event schema, and distribution-based rather than average-based reporting. ADR-009 is superseded in scope, not in principle.
- Metrics, defined precisely (see Chapter 18A):
  - **Time-to-acceptance distribution** — p50 / p90 / max, not mean. Emergency response is a tail-latency problem; a mean hides exactly the failures that matter.
  - **Dispatch funnel** — SOS created → candidates found → alerted → accepted → resolved, with drop-off at each stage.
  - **Coverage gap map** — the operating area is bucketed into a fixed geographic grid; a bucket is flagged as a coverage gap if it contains incidents but had zero eligible responders within the base radius at incident time. Computed from the ADR-014 event log.
  - **Acceptance rate by skill class and by radius band** — surfaces whether skill-ranking is actually improving outcomes or just reordering a list.
  - **Escalation rate** — proportion of incidents requiring radius expansion, broken down by trigger condition A vs B (ADR-012). This directly measures whether the network is too sparse or merely unresponsive — two problems with entirely different remedies.
- Why: The dispatch engine is the technical core, but a dispatch engine without measurement cannot be evaluated, tuned, or defended. Every metric above is computed from data the system already emits under ADR-014, so the marginal cost is query work rather than new instrumentation.

**ADR-016: Responder simulation harness**
- Decision: A first-class simulation harness (`sim/`) is core scope, not a testing afterthought. It spawns N concurrent WebSocket clients as synthetic responders with seeded coordinates, skills, and verification states, and can be scripted to accept, decline, or ignore incidents on configurable delays.
- Alternatives considered: multiple human operators on multiple physical devices (the v1.0 assumption); manual browser tabs.
- Why: Three reasons, in ascending order of importance. (1) This is a solo build — there is no second and third person to hold devices. (2) Human operators cannot reliably produce a sub-50ms acceptance race, so the ADR-010 concurrency claim is *unprovable* by hand; a script proves it deterministically and repeatably. (3) It permits demonstration at a scale that makes the analytics meaningful — 50 seeded responders and a few hundred synthetic incidents produce a dashboard with real distributions, rather than a dashboard with three data points. The harness is also what makes seeded demo data reproducible on demo day.

**ADR-017: Schema migrations**
- Decision: Alembic, with the initial revision creating all seven Chapter 12 tables. `sqlalchemy.url` is never written into `alembic.ini` — `env.py` reads `DATABASE_URL` from the environment, so no credential enters the repository.
- Alternatives considered: `Base.metadata.create_all()` at startup or in a small init script; hand-written SQL DDL files.
- Why: `create_all` is genuinely simpler and would satisfy Rule 002 if the schema were static — but it is not. It creates missing tables and silently ignores changes to existing ones, so every later schema change (the `certificate_path` column that Chapter 14's certificate upload needs, and any analytics column week 6 wants) would mean dropping and recreating the database, destroying the seeded demo corpus that ADR-016 exists to make reproducible. That is a demonstrated problem in this project, not a hypothetical one, which is what Rule 001 asks for. Alembic costs one dependency and a ~40-line `env.py`. Migrations run with `alembic upgrade head` from `backend/`; the migration engine is sync even though the application is async (ADR-018), because async migrations buy nothing and cost boilerplate.

**ADR-018: Database session style — async**
- Decision: SQLAlchemy 2.0 `AsyncSession` over the `psycopg` (v3) async driver, `postgresql+psycopg://`. All route handlers and services are `async def`.
- Alternatives considered: synchronous `Session` with `def` route handlers (FastAPI runs these in a threadpool); asyncpg instead of psycopg 3.
- Why: two concrete forces, both from decisions already made. ADR-012's escalation state machine runs inside `asyncio.create_task`; a blocking database call inside one of those tasks stalls the same event loop that is delivering WebSocket alerts, which converts a background timer into a system-wide pause. And ADR-010 mandates proving the accept-lock at N=50 concurrent accepts — FastAPI's default threadpool is 40 threads, so a synchronous implementation would partially serialise the exact race the test exists to exercise, weakening the proof without failing it. Sync sessions would be simpler for weeks 1–2 and then fought for weeks 3–4; the cost of switching later is every service signature in the codebase. psycopg 3 is chosen over asyncpg because SQLAlchemy drives it both async (the app) and sync (Alembic, per ADR-017) from a single dependency, and because `psycopg2-binary` has no wheels for the Python version in use here.

**ADR-019: Authentication mechanics**
- Decision: `PyJWT` for HS256 tokens (claims: `sub`, `role`, `iat`, `exp`; expiry enforced on decode) and the `bcrypt` library directly for password hashing. Login accepts a JSON body, not an OAuth2 password form. `POST /auth/signup` accepts `citizen` and `volunteer` only; admin accounts are created out-of-band by `backend/scripts/create_admin.py`.
- Alternatives considered: `python-jose` for JWT; `passlib[bcrypt]` for hashing; `OAuth2PasswordRequestForm` for login; allowing `role=admin` at signup.
- Why: `python-jose` is effectively unmaintained and `passlib` breaks against modern bcrypt releases — both are inherited defaults from older FastAPI tutorials rather than considered choices, and neither is worth a dependency that fails at an inconvenient moment. `OAuth2PasswordRequestForm` requires `python-multipart` and takes `username`/`password` form fields, which contradicts the Chapter 20 convention of a Pydantic model for every request body and misnames the identifier (this system logs in by phone — Chapter 12 gives `users` no email column). Self-registering admins would be the simplest option and is the one to reject: admins approve volunteer certificates under ADR-006, so an open admin signup route makes the entire verification-trust story unfalsifiable. A bootstrap script is honest about where trust originates.

**ADR-020: Event loop selection on Windows**
- Decision: the development server is started by `backend/run.py`, which runs uvicorn on a `SelectorEventLoop`. `app.main`'s lifespan asserts at startup that the running loop is usable and refuses to serve otherwise.
- Context: psycopg's async mode (ADR-018) cannot run on Windows' default `ProactorEventLoop`, and uvicorn creates its event loop *before* it imports the application — so the loop cannot be chosen from inside `app`, only at the process entry point.
- Alternatives considered: switching the application driver to asyncpg, which tolerates the Proactor loop; calling the deprecated `asyncio.set_event_loop_policy`; documenting `uvicorn app.main:app --reload` as the only supported command, since uvicorn's reload mode already selects a `SelectorEventLoop` on Windows.
- Why: asyncpg would mean two database drivers — asyncpg for the app, psycopg for Alembic — which discards the single-driver argument ADR-018 was chosen for. Event loop policies are deprecated as of Python 3.14 and scheduled for removal, so building on them buys a fix with a known expiry date. Relying on `--reload` works today but depends on a uvicorn implementation detail that is not part of its contract, and would fail silently and confusingly the first time anyone ran the server without reload. An explicit entry point states the requirement in the one place that can satisfy it. The startup assertion exists because the failure otherwise appears as an opaque driver error on the first query that touches the database, several layers away from the cause — the same objection this project raises to silent failure everywhere else.
- Note: `SelectorEventLoop` on Windows is bounded by `select()` at 512 sockets. The simulation harness of ADR-016 targets 50 concurrent responders, so this does not bind at demo scale (Rule 004), and Linux deployment (Ch. 23) uses `SelectorEventLoop` by default with no such limit.

**ADR-021: Candidate evaluation semantics**
- Decision: five rulings that together define what "evaluate a candidate" means, all of them implied by existing decisions but none of them previously stated.
  - **Skill ranks, it does not filter.** ADR-007's "skill-filtered/ranked" is resolved in favour of ranking. The evidence is the schema itself: `rejection_reason` (ADR-014) has no value for a skill mismatch, and invariant 4 requires every rejection to record why — so if skill excluded anyone, the enum would be incomplete. A general volunteer 200m away is still alerted; a CPR-trained volunteer 800m away simply sorts above them. This is also what makes ADR-015's "acceptance rate by skill class" a real test of whether ranking improves outcomes rather than a tautology.
  - **Wave 1 sorts by `(skill priority, distance)`**, with the static priority `cpr > first_aid > blood_donor > general`. ADR-013 requires wave 1 to rank on declared skills, but the AI category that would make relevance meaningful does not exist yet at that point, so the ordering has to come from somewhere. It comes from Chapter 1's stated problem domain — cardiac arrest, choking, trauma bleeding. `skill_match` records membership of the top tier (`cpr`, `first_aid`). Wave 2 replaces this with ranking against the real `ai_category`.
  - **`no_location` is added to `rejection_reason`,** and `dispatch_events.distance_m` becomes nullable. A verified, available volunteer with no `Locations` row cannot have a distance computed. The natural `JOIN` would drop them silently, which invariant 4 forbids; reusing `unavailable` would conflate "went offline" with "never located", which are different failures with different remedies — exactly the distinction ADR-015's coverage-gap metric exists to draw.
  - **Rejection precedence is eligibility before geography:** `unverified` → `unavailable` → `no_location` → `out_of_radius`. When more than one reason applies, the most fundamental disqualifier is recorded, so `out_of_radius` counts only volunteers who genuinely could have responded but were too far. The alternative inflates the coverage-gap metric with people who were never eligible, which would route recruitment to areas that are dense but unverified.
  - **`outcome = 'alerted'` records the dispatch decision, not delivery.** It means the engine selected this candidate for alerting. `no_socket` retains its precise meaning — delivery was attempted and no live connection existed — which only becomes a real condition in week 3. Without this split, every dispatch performed before the WebSocket layer exists would read as a total delivery failure in the funnel.
- Alternatives considered: skill as a hard filter; distance-only wave 1; a citizen-declared incident category at SOS time (a new column, and friction on the one-button SOS of Chapter 8); reusing `unavailable` for missing locations; geography-first rejection precedence.
- Why: each of these was a fork the implementation could not proceed past, and every one of them silently changes what the ADR-015 metrics mean. Recording them makes the analytics layer's numbers interpretable rather than merely computable — a coverage-gap figure whose rejection precedence is undocumented is a number nobody can defend under questioning.

---

# PART II — PRODUCT DESIGN

## Chapter 5 — Problem Statement

Every year, large numbers of preventable deaths occur during out-of-hospital emergencies due to delay in the first minutes of response — the "Golden Hour." Standard ambulance networks take 8–15 minutes to arrive. Meanwhile:
- Many citizens are CPR/first-aid trained but have no channel through which emergency dispatch can reach them.
- Responders who do arrive have zero visibility into the patient's condition beyond what's visually apparent.
- There is no unified, real-time bridge between "citizen in crisis" and "nearby trained civilian."

## Chapter 6 — Stakeholders

| Stakeholder | Need |
|---|---|
| Citizen (victim / bystander reporting) | Fastest possible qualified help, minimal friction to trigger SOS |
| Verified Responder (volunteer) | Clear, timely, relevant alerts; no alert fatigue from irrelevant/out-of-range incidents |
| Admin | Ability to verify responders, monitor active incidents, view system health/analytics |
| Evaluators (for this project's purposes) | Evidence of real engineering: correctness, restraint, demonstrable working system |

## Chapter 7 — Requirements

**Functional**
- Citizens can trigger an SOS with captured location.
- System identifies nearby, available, skill-matched verified responders.
- Responders receive real-time alerts and can accept/decline.
- First acceptance locks the incident; other responders are informed it's handled.
- Citizen sees live responder location and ETA after acceptance.
- Admin can review and approve/reject volunteer verification submissions.
- Admin can view incident history and basic analytics.
- If no responder is found in the initial radius, the system automatically retries at an expanded radius.

**Non-functional**
- Real-time behavior must be demonstrably correct under concurrent SOS events.
- System must degrade honestly (explicit "no responder found" state, not a silent failure).
- Codebase must stay within one backend language and a minimal, justified stack (Chapter 3).

## Chapter 8 — User Stories

- As a **citizen**, I want to press one button to broadcast my emergency and location, so that nearby help can reach me without me having to explain or search for it.
- As a **volunteer**, I want to declare my skills and certification once, so that I'm only alerted for emergencies I'm actually equipped to help with.
- As a **volunteer**, I want to see incident alerts only when I'm within a relevant radius and marked available, so I'm not overwhelmed by irrelevant notifications.
- As an **admin**, I want to verify volunteer credentials before they can respond, so the network maintains basic trust.
- As an **admin**, I want to see response-time trends and coverage gaps, so I understand where the system is/isn't working.

---

# PART III — ARCHITECTURE

## Chapter 9 — High-Level Architecture

```
                    ┌────────────────────┐
                    │   Citizen Client    │
                    │ (Browser Geolocation)│
                    └─────────┬───────────┘
                              │ SOS + lat/long
                              ▼
                    ┌────────────────────┐
                    │     FastAPI App     │
                    │  ┌──────────────┐  │
                    │  │ Auth Router  │  │
                    │  │ SOS Router   │  │
                    │  │ Volunteer Rtr│  │
                    │  │ Admin Router │  │
                    │  ├──────────────┤  │
                    │  │ Haversine Svc│  │
                    │  │ Notification │  │
                    │  │ WebSocket Mgr│  │
                    │  │ AI Summary Svc│ │
                    │  └──────────────┘  │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │   PostgreSQL DB      │
                    └──────────────────────┘
                              ▲
                              │ live location + accept/decline
                    ┌─────────┴───────────┐
                    │  Responder Client(s) │
                    │ (Browser Geolocation) │
                    └──────────────────────┘
```

## Chapter 10 — Backend Architecture

```
FastAPI
│
├── Auth Router          (signup, login, JWT issuance, role checks)
├── SOS Router           (create SOS, expand-radius retry, resolve)
├── Volunteer Router     (register skills, upload certificate, availability toggle)
├── Admin Router         (approve/reject volunteers, view incidents, analytics endpoints)
├── WebSocket Manager    (connection registry: responder_id -> active socket)
├── Haversine Service    (distance calc + radius filtering + skill ranking)
├── Notification Service(constructs and dispatches alert payloads)
├── AI Summary Service   (single LLM call: free-text -> priority/category)
└── Database Layer       (SQLAlchemy models + session handling)
```

## Chapter 11 — Frontend Architecture

Three role-based views, deliberately minimal:

**Citizen View**
- SOS trigger button
- Current location display
- Live map once a responder accepts (responder marker + ETA)
- Past request history

**Volunteer View**
- Availability toggle ("Go Online" / "Go Offline")
- Skill/certification declaration (set once, editable)
- Incoming alert popup with accept/decline
- Navigate-to-incident map view

**Admin View**
- Pending volunteer verification queue (approve/reject)
- Active incidents list
- Analytics dashboard (response times, coverage gaps, acceptance rate by skill)

## Chapter 12 — Database Architecture

```
Users
  id, name, phone, role (citizen | volunteer | admin), password_hash,
  created_at
  (phone is the login identifier and is unique — there is deliberately
   no email column)

Volunteers
  user_id, verified (bool), certificate_type, skills (cpr | blood_donor |
  first_aid | general), availability (bool)
  (single-valued: one skill class per volunteer, so that ADR-015's
   "acceptance rate by skill class" is an unambiguous GROUP BY and
   ADR-007's ranking is a sort key. Multi-skill volunteers are Future Scope.)

Locations
  user_id, lat, lng, updated_at
  (latest location only — no history table, by design; see Rule 004)

SOS
  id, victim_id, lat, lng, description,
  status (pending | matched | resolved | no_responder_found),
  current_radius_m, wave_count,
  ai_category, ai_priority (low | medium | high),
  ai_status (ok | timeout | error | skipped),
  created_at, first_dispatch_at, matched_at, resolved_at, accepted_by

Notifications
  id, sos_id, volunteer_id, wave_number,
  status (sent | accepted | declined | dismissed), sent_at, responded_at

DispatchEvents                                        -- ADR-014
  id, sos_id, volunteer_id, wave_number, evaluated_at,
  radius_m_at_eval, distance_m, skill_match (bool),
  outcome (alerted | rejected),
  rejection_reason (out_of_radius | unavailable | unverified |
                    already_alerted | no_socket | no_location | null)
  (distance_m is null exactly when rejection_reason is no_location —
   a volunteer with no fix has no distance. See ADR-021 for the
   precedence when several reasons apply.)

Incident History
  id, sos_id (unique — one history row per incident),
  response_time_seconds, escalation_count,
  final_radius_m, escalation_trigger (none | empty_set | timeout),
  resolved_at
```

The "per-wave radius and candidate counts" named at the end of Chapter 13 are
deliberately *not* a separate table or a set of `SOS` columns: `DispatchEvents`
already carries `wave_number` and `radius_m_at_eval` on every row, so both are a
`GROUP BY wave_number` away, and `SOS.wave_count` holds the total. One artefact,
several uses — the same argument ADR-014 makes.

`DispatchEvents` is the one table added relative to v1.0, justified by ADR-014. It is deliberately append-only and denormalised — it is an event log, not a normalised entity, and every metric in ADR-015 is a query over it. Any further table requires its own ADR entry (Rule 006).

## Chapter 13 — Real-Time Dispatch Engine

This is the core of the system and the primary technical claim of the project. Sequence:

1. Citizen triggers SOS → client captures `lat`/`long` via browser Geolocation API → POST to SOS Router. Incident persisted with status `pending`, `radius_m = 1000`.
2. **Immediately** (no AI wait — ADR-013): backend queries `Locations` + `Volunteers` for all available, verified responders.
3. Haversine Service computes distance to each candidate and filters to the current radius. **Every candidate evaluated — selected or rejected — emits a dispatch event row with its rejection reason** (ADR-014).
4. Surviving candidates are ranked by declared skill relevance (ADR-007). Wave 1 uses declared skills only.
5. Notification Service dispatches wave-1 alerts over open WebSocket connections. An escalation task is registered for this incident.
6. **Concurrently**, the AI Summary Service runs its single bounded call with a 3-second timeout. Result attaches to the incident and refines ranking for any subsequent wave. On timeout/failure it degrades to `{unspecified, medium}` and logs the degradation.
7. **Escalation state machine** (ADR-012) runs until terminal state:
   - Condition A — candidate set for the current radius is empty → expand immediately.
   - Condition B — `ACCEPT_TIMEOUT_SECONDS` (30) elapses with no acceptance → expand and alert newly-included responders only.
   - Ladder exhausted at 3km → status `no_responder_found`, citizen sees an explicit escalate-to-emergency-services state.
8. First responder to accept executes the conditional UPDATE of ADR-011. Exactly one responder observes `rowcount == 1` and is assigned; every other responder observes `0` and receives an "already handled" dismissal. The escalation task is cancelled on success.
9. Citizen client receives the accepted responder's live location over its own WebSocket channel (push, not polling — polling is explicitly rejected here since the socket already exists), rendering marker + straight-line ETA.
10. On completion, incident is marked `resolved`; response time and full funnel timestamps are written for the analytics layer.

**Timestamps captured per incident** (these are the raw material for every metric in ADR-015, so they are captured whether or not the dashboard consumes them yet): `created_at`, `first_dispatch_at`, `matched_at`, `resolved_at`, plus per-wave radius and candidate counts.

---

# PART IV — IMPLEMENTATION

## Chapter 14 — API Design (representative endpoints)

```
POST   /auth/signup
POST   /auth/login

POST   /sos                       — create SOS, triggers dispatch engine
GET    /sos/{id}                  — status/details
POST   /sos/{id}/resolve          — mark resolved

POST   /volunteers/register       — declare skills
POST   /volunteers/certificate    — upload certificate for verification
PATCH  /volunteers/availability    — toggle online/offline

GET    /admin/volunteers/pending
POST   /admin/volunteers/{id}/approve
POST   /admin/volunteers/{id}/reject
GET    /admin/incidents
GET    /admin/analytics

WS     /ws/{user_id}              — real-time channel for alerts/updates
```

## Chapter 15 — Authentication

JWT-based auth with three roles (citizen, volunteer, admin). No OAuth, no third-party identity providers — deliberately (Rule 002): added complexity with no benefit at this scope, and easy to defend in a viva as a conscious simplification rather than an oversight.

## Chapter 16 — WebSocket Communication

A single WebSocket Manager maintains an in-memory mapping of `user_id -> active connection`. On disconnect, the entry is cleared; on reconnect, it's re-registered. This is explicitly acceptable for demo scale (Rule 004) — a production version would need a connection registry backed by Redis pub/sub for multi-instance deployment, which is named in Future Scope, not built here.

## Chapter 17 — Maps & Location

Browser Geolocation API (`navigator.geolocation`) on both citizen and volunteer clients, polled at a defined interval while a session is active. Leaflet.js (or Google Maps embed) for map rendering — moving marker for the responder, ETA display based on straight-line distance / average speed estimate (not full routing — routing APIs are named in Future Scope).

## Chapter 18 — AI Module

Single, bounded use case (ADR-005): citizen optionally provides free-text description of the emergency; one LLM API call converts this into a structured `{category, priority}` object. Per ADR-013 this call is **off the dispatch critical path** — it runs concurrently with wave 1 and refines ranking for subsequent waves only. Hard 3s timeout, explicit fallback, degradation logged. No other AI functionality exists in core scope.

## Chapter 18A — Analytics Layer Specification

Co-headline deliverable per ADR-015. All metrics are queries over `DispatchEvents`, `SOS`, `Notifications`, and `Incident History`. No separate BI tool, no separate pipeline, no data warehouse — the operational tables *are* the source.

**Metric definitions (these are the contract; the dashboard renders them, it does not define them):**

| Metric | Definition | Why it matters |
|---|---|---|
| Time-to-acceptance | `matched_at − created_at`, reported as p50 / p90 / max over a window | Mean response time is the metric that hides every failure; tail latency is the one that kills people |
| Time-to-first-dispatch | `first_dispatch_at − created_at` | Isolates *system* latency from *human* latency — separates an engineering problem from a network-density problem |
| Dispatch funnel | Counts at: created → candidates found → alerted → accepted → resolved | Locates precisely where the system leaks |
| Coverage gap | Fixed grid over the operating area (default ~500m buckets). A bucket is a gap if it contains ≥1 incident and had 0 eligible responders within base radius at incident time | The only metric that answers "where should we recruit responders?" |
| Acceptance rate | Accepted ÷ alerted, sliced by skill class and by radius band | Tests whether skill-ranking (ADR-007) actually improves outcomes or merely reorders |
| Escalation rate | Incidents requiring expansion ÷ total, split by trigger A (empty set) vs B (timeout) | Distinguishes *too few responders* from *unresponsive responders* — different problems, different fixes |
| AI degradation rate | `ai_status != 'ok'` ÷ total | Honest reporting of the system's weakest dependency |

**Presentation:** distributions over averages wherever a distribution exists. A histogram of time-to-acceptance is more informative and more defensible than a single number, and saying so out loud is part of the deliverable.

**Reproducibility:** every dashboard figure must be traceable to a named query in `analytics/queries/`. If a number on screen cannot be traced to a query file, it does not ship.

---

# PART V — ENGINEERING STANDARDS

## Chapter 19 — Folder Structure

```
flare/
├── backend/
│   ├── app/
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── sos.py
│   │   │   ├── volunteers.py
│   │   │   └── admin.py
│   │   ├── services/
│   │   │   ├── haversine.py
│   │   │   ├── notifications.py
│   │   │   ├── websocket_manager.py
│   │   │   ├── dispatch.py          (escalation state machine — ADR-012)
│   │   │   ├── events.py            (dispatch event logging — ADR-014)
│   │   │   └── ai_summary.py
│   │   ├── models.py
│   │   ├── database.py
│   │   └── main.py
│   ├── tests/
│   │   ├── test_haversine.py
│   │   ├── test_accept_lock.py      (concurrency — ADR-010/011)
│   │   └── test_escalation.py       (ADR-012)
│   └── requirements.txt
├── analytics/
│   └── queries/                     (one .sql per metric — ADR-015)
├── sim/                             (ADR-016)
│   ├── seed.py                      (deterministic responder/incident seeding)
│   ├── responder_client.py          (single synthetic WS responder)
│   └── scenarios/
│       ├── race.py                  (N responders accept simultaneously)
│       ├── timeout.py               (nobody accepts → escalation)
│       └── coverage.py              (bulk incidents for dashboard data)
├── frontend/
│   ├── citizen/
│   ├── volunteer/
│   └── admin/
├── CLAUDE.md                        (Appendix B, lifted to repo root)
└── docs/
    └── FLARE_Engineering_Blueprint_v2.md   (this document)
```

**Note on `CLAUDE.md`:** Appendix B is duplicated at the repo root because Claude Code reads that file automatically at the start of every session. This is the mechanism that prevents scope drift across sessions — the decision boundaries are re-asserted without you having to re-paste them.

## Chapter 20 — Coding Standards

- Python: type-hinted function signatures, Pydantic models for all request/response bodies.
- One router per domain concern (no monolithic route files).
- No business logic inside route handlers — routers call services, services contain logic.
- Every new external dependency requires a one-line justification comment at import site, tying back to an ADR if it's a significant addition.

## Chapter 21 — Testing Strategy

Automated tests are **not** optional in v2.0, for a narrow and specific reason: the project's headline claim (ADR-010) is a concurrency-correctness claim, and a concurrency claim asserted without a test is not a claim, it is a hope.

**Required (core scope):**
- `test_haversine.py` — distance correctness against known coordinate pairs; radius boundary conditions.
- `test_accept_lock.py` — fire N concurrent accept requests at one incident via the simulation harness; assert exactly one returns success and exactly N−1 return "already handled". Run it at N=2, N=10, N=50. **This test is the proof of ADR-010/011** and should be shown running, live, during the demo.
- `test_escalation.py` — both trigger conditions of ADR-012 independently: empty candidate set expands immediately; populated-but-silent set expands at timeout.

**Manual:** scripted run-throughs of the happy path, the no-responder-found terminal state, and the AI-degradation fallback.

The rest of the codebase is not unit-tested, deliberately and stated openly: CRUD routes and view rendering are verified by the demo run-through. Testing where correctness is *hard* and skipping where it is *obvious* is the judgement call being demonstrated (Rule 002, Rule 008).

## Chapter 22 — Security

- Passwords hashed (not plaintext) — non-negotiable regardless of scope constraints.
- JWT expiry enforced.
- Certificate uploads stored, not publicly exposed — admin-only access.
- No claim of HIPAA-grade or production-grade data security is made anywhere in the project materials; this is explicitly out of scope and should be stated as such if asked.

## Chapter 23 — Deployment

- Backend: same pattern as prior team projects (e.g., Render-style deployment) — reuse known-working deployment knowledge rather than exploring new platforms (Rule 002).
- Database: hosted Postgres instance.
- Frontend: static hosting per role view, or a single served app with role-based routing.

---

# PART VI — PROJECT MANAGEMENT

## Chapter 24 — Development Roadmap

Eight weeks, solo, working with Claude Code. Weeks 7–8 are deliberately protected as buffer and rehearsal — the most common failure mode for this category of project is arriving at demo day with untested integration, not with missing features.

| Week | Goal | Definition of done |
|---|---|---|
| **1** | Foundation | Repo initialised, `CLAUDE.md` in place, FastAPI skeleton running, Postgres connected, SQLAlchemy models for all tables (Ch. 12) migrated, JWT auth with three roles working. A user can sign up and log in. |
| **2** | Dispatch core, offline | Haversine service + tests passing. `POST /sos` persists an incident and returns a ranked candidate list. `DispatchEvents` rows emitted for every evaluation. No WebSockets yet — this is deliberately proven as a pure function first. |
| **3** | Real-time layer | WebSocket manager, connection registry, wave-1 alert dispatch. Simulation harness v1 (`sim/responder_client.py`) can connect synthetic responders and receive alerts. **First end-to-end moment.** |
| **4** | Correctness | Accept-lock via conditional UPDATE (ADR-011). `test_accept_lock.py` passing at N=50. Escalation state machine (ADR-012), both trigger conditions, with `test_escalation.py` passing. **This is the hardest week — protect it.** |
| **5** | Clients | Citizen, volunteer, and admin views. Leaflet maps, live responder marker, ETA. Certificate upload + admin approval queue. AI summary service with timeout and fallback (ADR-013). |
| **6** | Analytics | `sim/scenarios/coverage.py` generates a realistic incident corpus. All seven metrics of Ch. 18A implemented as traceable queries. Dashboard renders distributions, funnel, and coverage grid. |
| **7** | Harden + deploy | Deploy backend and DB. Bug fixing, edge cases, error states. Security pass (Ch. 22). Documentation and README. **No new features after Monday of week 7.** |
| **8** | Rehearse | Demo script written and rehearsed end to end at least five times. Seeded demo dataset frozen. Contingency plan for network/API failure on demo day. Slides built *from* the working system, not ahead of it. |

**Sequencing rationale:** correctness (week 4) lands before polish (week 5) so that if time is lost, what survives is the technically defensible core rather than a pretty shell. The analytics week sits after the simulation harness because meaningful analytics require volume, and volume requires the harness.

## Chapter 25 — Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| WebSocket doesn't survive backgrounded/locked devices | Medium — affects realism of "always-on" claim | Explicitly scoped as foreground-only for core demo (ADR-003); Web Push is a named, honest stretch goal (ADR-004), not a core promise |
| Team over-scopes and under-delivers | High — most common failure mode for this category of project | This blueprint's Decision Boundaries (Chapter 3) and Future Scope (Chapter 26) exist specifically to prevent this |
| AI summary produces unreliable/embarrassing output live in demo | Medium | Keep AI role narrow and bounded (ADR-005); test with a curated set of example inputs before demo day; have a fallback manual "priority" selector if the LLM call fails |
| Concurrency bug in accept-lock during live demo | Medium — this is the most "showable" technical claim | Rehearse the concurrent-SOS demo scenario specifically and repeatedly before presenting (ADR-010) |
| Volunteer verification data (certificates) mishandled | Low for a demo, but should still be handled correctly | Admin-only access to uploads; no public exposure of certificate images |

## Chapter 26 — Future Scope

Explicitly named as *not built*, to demonstrate awareness without overclaiming:

- Native mobile app (React Native/Flutter) + FCM/APNs push for true background reliability
- Web Push (service worker + VAPID) as an intermediate reliability upgrade — conditional core stretch, see ADR-004
- PostGIS / geospatial indexing for production-scale responder tables (ADR-002)
- Geohash-based candidate pre-filtering at larger scale
- Automated OCR-based certificate verification against an authority database
- AI-based medical triage beyond the single priority-summary call
- Ambulance dispatch integration / hospital system integration
- Responder reputation/trust scoring based on incident history
- Offline/low-connectivity SMS fallback for SOS triggering
- Voice-based SOS activation
- Full routing-based ETA (vs. current straight-line estimate)

## Chapter 27 — Demo Strategy

Solo operation. Screen layout: three browser windows (citizen, volunteer, admin) plus one terminal running the simulation harness. The terminal is not hidden — it is part of the pitch.

**Act 1 — the happy path (≈2 min).**
1. Terminal: `python sim/seed.py` brings 50 synthetic responders online at seeded coordinates. Admin map visibly populates.
2. Citizen window: press SOS with a free-text description.
3. Admin window shows the incident appear and the candidate set resolve live. Point out that responders outside 1km are visibly *not* alerted.
4. Volunteer window (a real browser client, you) receives the alert and accepts.
5. Citizen sees "Responder assigned, ETA X min," marker begins moving. Incident resolves.

**Act 2 — the correctness claim (≈2 min).** This is the technical centrepiece.
6. Terminal: `python sim/scenarios/race.py --n 50` — fifty synthetic responders attempt to accept one incident simultaneously.
7. Output shows exactly one success and forty-nine "already handled." Then show the mechanism on screen: the conditional UPDATE of ADR-011, and `test_accept_lock.py` running green.
8. Say the sentence plainly: *the lock is enforced by the database, not by application code, because application-level checks are a time-of-check-to-time-of-use race.*

**Act 3 — honest failure (≈1 min).**
9. `python sim/scenarios/timeout.py` — responders are alerted but nobody accepts. Watch the radius expand 1km → 2km → 3km on the admin map, then terminate in an explicit `no_responder_found` state escalating to emergency services.
10. Trigger an SOS with the AI service unreachable; show it degrade to `{unspecified, medium}` and dispatch anyway, with the degradation logged.

**Act 4 — the analytics (≈3 min).**
11. Admin dashboard against the seeded corpus. Walk the funnel. Show the time-to-acceptance histogram and explain why p90 rather than mean. Show the coverage grid and name the two or three buckets where the network is structurally blind.
12. Show escalation rate split by trigger condition, and state the conclusion it supports: whether this simulated network's problem is *density* or *responsiveness*.

Target: a tight, dead-time-free run of roughly eight minutes. The demo itself should be the strongest evidence for the project, stronger than any slide — and Acts 2 and 3 are what separate it from every functionally similar submission, because almost nobody demonstrates their own failure modes on purpose.

---

## Appendix A — Glossary

- **SOS** — the emergency event triggered by a citizen.
- **Responder / Volunteer** — a verified civilian able to receive and accept SOS alerts.
- **Radius filtering** — restricting alert recipients to those within a defined distance of the incident.
- **Accept-lock** — the mechanism ensuring only the first accepting responder is assigned, with others notified the incident is handled.
- **Golden Hour** — the critical early window after an emergency during which intervention is most likely to be effective.

## Appendix B — Claude Collaboration Guide

This section governs how any AI assistant (Claude) should behave when contributing to this project.

```
You are acting as a collaborating engineer on this project, not an
autonomous decision-maker. Before implementing any non-trivial
feature:

1. Restate the problem being solved.
2. Note the possible approaches, briefly.
3. Recommend one, referencing the relevant Decision Boundary
   (Chapter 3) or ADR (Chapter 4) it aligns with.
4. Only then produce implementation.

Do not introduce any technology outside the approved stack
(Python/FastAPI backend, PostgreSQL, WebSockets, Leaflet/Maps,
JWT auth) without first explaining why it's necessary and getting
explicit confirmation.

When uncertain, default to: simplicity, demoability, and honest
scope over production-scale optimization. If a suggestion would
violate Rule 003 (must be demoable) or Rule 004 (no premature
optimization), say so explicitly rather than proceeding.

Any new architectural decision, once agreed, should be added to
Chapter 4 (ADR) in the same format as existing entries.
```

## Changelog

- v1.0 — Initial blueprint established, incorporating: core dispatch engine scope, skill-aware matching, single-bounded AI use case, admin analytics dashboard, fallback/radius-expansion path, and concurrency-correctness as an explicit demo requirement.
- v2.0 — Build model corrected from four-person team to solo + AI collaborator; 8-week timeline fixed. Added ADR-011 (accept-lock enforced by atomic conditional UPDATE, replacing unspecified mechanism), ADR-012 (radius expansion triggered by both empty-candidate-set and acceptance-timeout, via an escalation state machine), ADR-013 (AI summary removed from dispatch critical path, made concurrent with timeout and fallback), ADR-014 (structured dispatch event log), ADR-015 (analytics promoted to co-headline deliverable with seven precisely defined metrics, superseding ADR-009 in scope), ADR-016 (responder simulation harness as core scope). Added Chapter 18A (analytics specification). Rewrote Chapter 13 dispatch sequence, Chapter 12 schema (+`DispatchEvents`, funnel timestamps), Chapter 19 folder structure (+`sim/`, `tests/`, `analytics/`, `CLAUDE.md`), Chapter 21 testing (automated tests moved to required), Chapter 24 roadmap (filled: 8-week plan), Chapter 27 demo strategy (four-act solo run).
- v2.1 — Week 1 foundation decisions recorded: ADR-017 (Alembic for schema migrations), ADR-018 (async SQLAlchemy sessions over psycopg 3), ADR-019 (PyJWT + bcrypt, JSON login body, admin accounts created out-of-band rather than by signup). Chapter 12 annotated to resolve four ambiguities surfaced while implementing it: `phone` is the unique login identifier, `Volunteers.skills` is single-valued, `ai_priority` values are `{low, medium, high}`, `IncidentHistory.sos_id` is unique. Added `Users.created_at`. Recorded that per-wave radius and candidate counts are derived from `DispatchEvents`, not stored separately.
- v2.2 — ADR-020 (event loop selection on Windows: `backend/run.py` entry point plus a startup assertion, constraining ADR-018's async driver choice on the development platform).
- v2.3 — ADR-021 (candidate evaluation semantics: skill ranks rather than filters, static wave-1 skill priority, `no_location` rejection reason with nullable `distance_m`, eligibility-before-geography rejection precedence, and `alerted` as a record of the dispatch decision rather than of delivery). Chapter 12 `DispatchEvents` updated accordingly.
