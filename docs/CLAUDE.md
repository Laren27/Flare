# CLAUDE.md — FLARE

You are a collaborating engineer on FLARE (Fast Local Alert & Response Engine), a real-time civilian emergency dispatch system. Solo developer, 8-week semester project.

**Authoritative spec:** `docs/FLARE_Engineering_Blueprint_v2.md`. Read it before any non-trivial change. If a suggestion conflicts with the blueprint, the blueprint wins unless we explicitly amend it — and amendments get an ADR entry plus a changelog line, in the same commit.

---

## Stack (fixed)

Python 3.11+ / FastAPI · PostgreSQL + SQLAlchemy · WebSockets · JWT auth · Leaflet.js · one bounded LLM call.

**Do not introduce any library, service, or pattern outside this list without stating why it is necessary and getting explicit confirmation first.** No Redis, no Celery, no PostGIS, no ORM alternatives, no frontend framework, no Docker unless asked.

---

## Decision boundaries

```
RULE 001 — No new technology unless it solves a demonstrated problem here.
RULE 002 — Prefer the simpler architecture that satisfies the requirement.
RULE 003 — Every feature must be demoable end-to-end, or it is Future Scope.
RULE 004 — Never optimize before measurement. No building for scale we won't see.
RULE 005 — One backend language: Python. No polyglot services.
RULE 006 — Every architectural decision gets an ADR entry, including decisions NOT to do something.
RULE 007 — Every claim in the pitch must correspond to code that exists.
RULE 008 — One thing built and demoed beats three things half-built.
```

---

## Non-negotiable invariants

These are the correctness claims the project is graded on. Do not weaken them, do not "simplify" them, and flag loudly if a change would violate one.

1. **Accept-lock is enforced by the database, never by application code.** Always:
   ```sql
   UPDATE sos SET status='matched', accepted_by=:rid, matched_at=now()
    WHERE id=:sos_id AND status='pending';
   ```
   Check `rowcount`. Never `if sos.status == 'pending': ...` — that is a TOCTOU race. Never an in-process `asyncio.Lock` — that breaks silently with >1 worker. (ADR-011)

2. **The AI call never blocks dispatch.** Wave 1 alerts go out on radius + declared skills alone. The LLM call runs concurrently, 3s hard timeout, falls back to `{unspecified, medium}`, and logs `ai_status`. (ADR-013)

3. **Escalation has two triggers, not one.** Empty candidate set → expand immediately. Candidates alerted but silent for `ACCEPT_TIMEOUT_SECONDS` (30) → expand. Ladder 1km → 2km → 3km → `no_responder_found`. Escalation tasks are cancelled on acceptance. (ADR-012)

4. **Every candidate evaluation emits a `DispatchEvents` row** — selected or rejected, with the rejection reason. This log is the sole source for the analytics layer. No silent filtering. (ADR-014)

5. **Failure states are explicit, never silent.** `no_responder_found` is a real state with real UI.

---

## Code conventions

- Type-hinted signatures throughout. Pydantic models for every request and response body.
- One router per domain concern. **No business logic in route handlers** — routers call services, services hold logic.
- New external dependency → one-line justification comment at the import site, referencing an ADR if significant.
- Config via environment variables, never hardcoded. Nothing secret in the repo.
- Passwords hashed. JWT expiry enforced. Certificate uploads admin-only, never publicly served.

## Testing

Required, not optional — the headline claim is a concurrency claim, and an untested concurrency claim is a hope.

- `tests/test_haversine.py` — known coordinate pairs, radius boundary conditions
- `tests/test_accept_lock.py` — N concurrent accepts, assert exactly 1 success / N−1 dismissed, at N ∈ {2, 10, 50}
- `tests/test_escalation.py` — both ADR-012 triggers independently

CRUD routes and views are deliberately not unit-tested; they are covered by the demo run-through. Test where correctness is hard, skip where it is obvious.

## Git

- Small, focused commits. One logical change each.
- Format: `<area>: <imperative summary>` — e.g. `dispatch: enforce accept-lock via conditional UPDATE`
- Reference the ADR when implementing one: `dispatch: add escalation state machine (ADR-012)`
- Never commit `.env`, credentials, uploaded certificates, or `__pycache__`.
- Do not push without being asked.

---

## How to work with me

Before implementing anything non-trivial:

1. Restate the problem being solved.
2. Note the possible approaches, briefly.
3. Recommend one, naming the Rule or ADR it aligns with.
4. Only then write code.

When uncertain, default to simplicity, demoability, and honest scope over production-scale optimization. If something I ask for would violate Rule 003 or Rule 004, say so instead of quietly doing it.

Work one roadmap week at a time (blueprint Chapter 24). Do not build ahead.
