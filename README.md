# FLARE — Fast Local Alert & Response Engine

Real-time civilian emergency dispatch: a citizen triggers an SOS, the system
finds nearby verified responders with relevant skills, alerts them over
WebSockets, and logs every dispatch decision so the network's failures can be
measured rather than guessed at.

**Status: complete.** An SOS reaches nearby responders over WebSockets, exactly
one can claim it, an incident nobody takes escalates 1km → 2km → 3km before
terminating in an explicit `no_responder_found`, a single bounded LLM call
enriches it off the critical path, and the admin dashboard reports all seven
Chapter 18A metrics from named SQL files.

- [Deployment](docs/DEPLOYMENT.md) — hosted Postgres, environment, security posture
- [Demo script](docs/DEMO_SCRIPT.md) — the four acts of Chapter 27, as a runbook
- [Blueprint](docs/FLARE_Engineering_Blueprint_v2.md) — the authoritative spec and every ADR

**Not built, and not claimed anywhere in the product:** certificate upload and
admin approval (the queue is shown with its controls disabled and labelled),
responder live location after acceptance, and Web Push. All are in Future Scope
(Ch. 26).

## Analytics (Ch. 18A)

Every figure on the dashboard is produced by a named query in
`analytics/queries/`, and the filename is printed under each panel — so any
number on screen can be checked against the SQL that made it.

```bash
cd backend && python ../sim/seed.py --count 60 --spread-m 2600 --reset
cd backend && python ../sim/scenarios/coverage.py --incidents 300 --clear
```

That builds a reproducible corpus with two deliberate coverage holes, so the gap
metric has something real to find.

## The app

With the server running, open **http://127.0.0.1:8000/app/**.

| View | Path | Live or mock |
|---|---|---|
| Landing | `/app/` | static |
| Sign in / register | `/app/login.html` | live |
| Citizen | `/app/citizen/` | **live** — SOS, escalation, terminal states |
| Volunteer | `/app/volunteer/` | **live** — WebSocket alerts, accept-lock |
| Volunteer alert | `/app/volunteer/alert.html` | live, with preview states |
| Admin | `/app/admin/` | **live** — all seven metrics from `analytics/queries/` |

Hard-to-summon states can be previewed without staging an incident:
`/app/citizen/?state=expanding`, `?state=none`, and
`/app/volunteer/alert.html?view=handled`.

The blueprint is the authoritative spec. Architectural decisions, including the
decisions *not* to build things, live in its Chapter 4 (ADR).

## Stack

Python 3.11+ · FastAPI · PostgreSQL + SQLAlchemy (async) · Alembic · JWT ·
WebSockets · Leaflet.js · one bounded LLM call.

## Local setup

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -r backend/requirements.txt
```

Create the database:

```bash
createdb -U postgres flare
```

Then copy `backend/.env.example` to `backend/.env` and fill it in. The real
`.env` is gitignored and must never be committed (Ch. 22).

```bash
cp backend/.env.example backend/.env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # JWT_SECRET
```

Apply the schema:

```bash
cd backend && alembic upgrade head
```

Create the first admin — `POST /auth/signup` accepts citizens and volunteers
only, by design (ADR-019):

```bash
cd backend && python -m scripts.create_admin --name "Your Name" --phone "+910000000000"
```

## Running

```bash
cd backend && python run.py --reload
```

Interactive API docs at `http://127.0.0.1:8000/docs`.

Use `run.py` rather than invoking `uvicorn` directly. uvicorn creates its event
loop before importing the app, and on Windows the default one cannot run
psycopg in async mode — `run.py` is the only place that can choose correctly
(ADR-020). The app refuses to start on an incompatible loop rather than failing
later on the first query.

## Endpoints so far

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | liveness |
| `POST` | `/auth/signup` | citizen or volunteer; volunteers get an unverified, offline volunteer record |
| `POST` | `/auth/login` | phone + password → bearer token |
| `GET` | `/auth/me` | requires a valid, unexpired token |
| `POST` | `/sos` | creates an incident, alerts nearby responders, returns the ranked candidate list |
| `GET` | `/sos/{id}` | status; victim, assigned responder, or admin only |
| `POST` | `/sos/{id}/accept` | conditional UPDATE; exactly one responder wins (ADR-011) |
| `POST` | `/sos/{id}/decline` | records one responder's answer, not the incident's |
| `POST` | `/sos/{id}/resolve` | closes a matched incident and writes Incident History |
| `GET` | `/admin/analytics` | all seven Ch. 18A metrics, each labelled with its query file |
| `GET` | `/admin/incidents` | recent incidents for the admin table |
| `GET` | `/admin/queries` | the traceability index of query files |
| `WS` | `/ws/{user_id}` | real-time channel; first frame must be `{"type":"auth","token":…}` (ADR-022) |

## Simulation harness (ADR-016)

```bash
cd backend && python ../sim/seed.py --count 50 --spread-m 1200 --reset
cd backend && python ../sim/responder_client.py --all --limit 20
```

`seed.py` is deterministic — the same `--seed` rebuilds the same network, which
is what makes the demo dataset reproducible.

Demo scenarios (Chapter 27, Acts 2 and 3):

```bash
python sim/scenarios/race.py --n 50
python sim/scenarios/timeout.py --n 25
```

`race.py` fires 50 simultaneous accepts at one incident and expects exactly one
winner. `timeout.py` connects responders who all ignore the alert, so the radius
walks the ladder and terminates in `no_responder_found`. Shorten
`ACCEPT_TIMEOUT_SECONDS` in `.env` to watch it without waiting 30s a rung.

## Layout

```
backend/app/routers/    HTTP only — no business logic (Ch. 20)
backend/app/services/   the logic
backend/app/models.py   all seven Chapter 12 tables
backend/alembic/        schema migrations (ADR-017)
analytics/queries/      one .sql per metric (ADR-015)     — week 6
sim/                    responder simulation harness (ADR-016) — week 3
frontend/               citizen / volunteer / admin views  — week 5
```

## Tests

```bash
cd backend && pytest
```

Deliberately narrow (Ch. 21): concurrency and distance correctness are tested,
CRUD and views are covered by the demo run-through.

- `test_haversine.py` — no database, no environment. The dispatch core is proven
  as a pure function before any transport exists.
- `test_accept_lock.py` — N concurrent accepts at N ∈ {2, 10, 50}, each on its
  own connection, asserting exactly one winner (ADR-010/011).
- `test_escalation.py` — both ADR-012 triggers independently, plus cancellation
  on acceptance.

The database-backed tests create and migrate a separate `flare_test` database
automatically. Your `flare` database is never touched by the test suite.
