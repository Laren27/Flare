# Deploying FLARE

Chapter 23 says: reuse known-working deployment knowledge rather than exploring
new platforms (Rule 002). That means a Render-style Python service and a hosted
Postgres instance — no Docker, no orchestration, no CI pipeline. If the platform
can run `pip install` and a start command, it can run this.

---

## 1. Database

Create a hosted Postgres instance and take its connection string.

Two things the string usually needs before it will work here:

- **Driver suffix.** SQLAlchemy needs `postgresql+psycopg://`, not
  `postgres://` or `postgresql://`. Providers hand out the latter.
- **Percent-encoding.** Reserved characters in the password must be escaped, or
  the URL is silently mis-parsed and you get a DNS error instead of an auth
  error (`@` → `%40`, `:` → `%3A`, `/` → `%2F`, `#` → `%23`, `?` → `%3F`,
  `%` → `%25`).

```bash
python -c "import urllib.parse,getpass; print(urllib.parse.quote(getpass.getpass(), safe=''))"
```

## 2. Environment variables

Set these on the service. Never commit them; `backend/.env.example` is the
template and holds only `CHANGE_ME`.

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql+psycopg://user:pass@host:5432/db` |
| `JWT_SECRET` | yes | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ENVIRONMENT` | **yes** | set to `production` — see below |
| `JWT_EXPIRY_MINUTES` | no | default 60 |
| `BASE_RADIUS_M` | no | default 1000 |
| `ACCEPT_TIMEOUT_SECONDS` | no | default 30 (ADR-012) |
| `AI_PROVIDER` | no | `gemini` (default) or `groq` |
| `GEMINI_API_KEY` | no | absent ⇒ `ai_status='skipped'`, dispatch unaffected |
| `GEMINI_MODEL` | no | default `gemini-3.5-flash-lite` |
| `AI_TIMEOUT_SECONDS` | no | default 3.0 (ADR-013) |

`ENVIRONMENT` defaults to `development` deliberately: a forgotten variable
should make local work easy, not make production insecure. But it means you
**must** set it explicitly in production, where it:

- closes `/docs`, `/redoc` and `/openapi.json`, which otherwise enumerate every
  endpoint and schema in the system to anyone who asks;
- adds `Strict-Transport-Security`.

## 3. Build and start

```
Build:  pip install -r backend/requirements.txt
Start:  cd backend && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

`uvicorn` directly is correct here, unlike locally. ADR-020's `run.py` exists
because Windows defaults to a `ProactorEventLoop` that psycopg cannot use; Linux
already defaults to `SelectorEventLoop`. The startup assertion in
`app.main.lifespan` will refuse to serve if that ever stops being true, so a
misconfigured host fails loudly rather than at the first query.

Run `alembic upgrade head` as part of the start command, not manually — a
deploy that ships code ahead of its schema is the failure this prevents.

## 4. First admin

`POST /auth/signup` accepts citizens and volunteers only (ADR-019). Admins
approve responder credentials, so that trust cannot be self-granted. Create the
first one over a shell on the host:

```bash
cd backend && python -m scripts.create_admin --name "Your Name" --phone "+91XXXXXXXXXX"
```

## 5. Verify the deploy

```bash
curl -s https://<host>/health                      # {"status":"ok"}
curl -s -o /dev/null -w "%{http_code}\n" https://<host>/docs   # 404 in production
curl -sI https://<host>/app/ | grep -i "content-security-policy\|strict-transport"
```

Then sign in at `https://<host>/app/` and press SOS. If no responders are
seeded, you should see the search widen and terminate in
`no responder found` — which is the system working correctly, not failing.

---

## What is not set up, and why

- **No Docker.** Not needed for a single Python service (Rule 002), and
  explicitly out of scope in `CLAUDE.md` unless asked.
- **No CI.** The suite is `pytest` and runs in seconds locally. A pipeline is
  process, not correctness, at this scale.
- **No Redis.** The WebSocket registry is process-local by design (Ch. 16).
  **This is the one thing that constrains deployment**: run **one instance with
  one worker**. Two workers means a responder connected to worker A is
  invisible to a dispatch running on worker B, and would be recorded
  `no_socket`. Redis pub/sub is the production answer and is named in Future
  Scope (Ch. 26), not built.
- **No rate limiting** on `/auth/login`. Named in the security notes below.

## Security posture (Ch. 22)

Done:

- Passwords bcrypt-hashed; the 72-byte limit enforced rather than silently
  truncating.
- JWT expiry enforced on decode, with `exp`, `sub` and `role` required claims.
- Credentials are `SecretStr` and engines are built from `URL` objects, so a
  traceback renders `***` rather than the password. Guarded by
  `tests/test_secret_handling.py`.
- WebSocket authenticated by first frame, never a query string (ADR-022), with
  the path `user_id` checked against the token subject.
- Admin endpoints gated at the router, so a new one is protected by existing
  rather than by remembering a decorator.
- `GET /sos/{id}` restricted to the victim, the assigned responder, and admins.
- Security headers on every response; interactive docs closed in production.

Not done, stated openly:

- **No rate limiting on login.** A meaningful limiter needs shared state, which
  means Redis, which is Future Scope. An in-process counter would look like
  protection and silently stop working with more than one worker — the same
  objection ADR-011 makes to an in-process lock.
- **No HIPAA-grade or production-grade data-security claim.** Chapter 22 says
  this explicitly and it is repeated here so nobody infers otherwise.
- **Leaflet and fonts load from CDN.** Vendoring is the fix; see the demo
  contingency in `DEMO_SCRIPT.md` for the meantime.
