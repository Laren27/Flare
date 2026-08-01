# FLARE — Fast Local Alert & Response Engine

Real-time civilian emergency dispatch: a citizen triggers an SOS, the system
finds nearby verified responders with relevant skills, alerts them over
WebSockets, and logs every dispatch decision so the network's failures can be
measured rather than guessed at.

**Status: week 1 of 8.** Foundation only — auth and schema. The dispatch engine,
real-time layer, and analytics land in later weeks; see the roadmap in
[Chapter 24 of the blueprint](docs/FLARE_Engineering_Blueprint_v2.md).

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

Deliberately narrow (Ch. 21): concurrency and distance correctness are tested,
CRUD and views are covered by the demo run-through. Nothing to run yet — the
first tests arrive in week 2.
