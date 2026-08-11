# FLARE — Demo Script

Chapter 27, as a runbook. Four acts, roughly eight minutes, solo operator.

The demo itself is the strongest evidence for this project — stronger than any
slide. Acts 2 and 3 are what separate it from every functionally similar
submission, because almost nobody demonstrates their own failure modes on
purpose.

---

## Before you start

**Screen layout.** Three browser windows — citizen, volunteer, admin — plus one
terminal. The terminal is not hidden; it is part of the pitch.

**Freeze the dataset.** These exact commands rebuild the demo corpus, and the
same seeds produce the same network every time. Run them once before the demo
and do not re-run them during it.

```bash
cd backend && python ../sim/seed.py --count 60 --spread-m 2600 --seed 1337 --reset
cd backend && python ../sim/scenarios/coverage.py --incidents 300 --seed 4242 --clear
```

**Shorten the escalation timeout** so Act 3 fits in the slot. Put this in
`backend/.env` and say out loud that you have done it — the production value is
30 seconds (ADR-012), and shortening it for a demo is a presentation choice, not
a claim about the system:

```
ACCEPT_TIMEOUT_SECONDS=6
```

**Start the server**, then leave it alone:

```bash
cd backend && python run.py
```

**Log in ahead of time** in all three windows. Fumbling a password on stage
costs more time than it takes to prepare.

| Window | Credentials |
|---|---|
| Citizen | your own signup, role `citizen` |
| Volunteer | `+9199000000` / `sim-responder-pw` |
| Admin | the account from `scripts/create_admin.py` |

**Location.** The seeded network is centred on Bengaluru (12.9716, 77.5946). If
your browser reports a real location elsewhere, wave 1 finds nobody and you get
Act 3 during Act 1. Mock the location in devtools (Sensors → custom location)
before you begin, or re-seed around wherever you are.

---

## Act 1 — the happy path (≈2 min)

1. **Terminal:** bring synthetic responders online.
   ```bash
   python sim/responder_client.py --all --limit 20
   ```
   Twenty responders connect and authenticate. Point at the terminal: these are
   real WebSocket clients, not fixtures.

2. **Citizen window:** press SOS with a free-text description — *"elderly man
   collapsed at the bus stop, not breathing"*.

3. **Say the number.** The response comes back in tens of milliseconds. That is
   the dispatch decision, complete, before the AI has answered anything.

4. **Volunteer window:** the alert arrives. Show the distance and the incident
   detail.

5. **Point out who was *not* alerted.** The response reports how many volunteers
   were evaluated versus how many were alerted. Every one of the rejected has a
   row in `DispatchEvents` saying why — out of radius, unverified, offline, no
   location. Nobody is silently filtered.

6. **Accept.** The citizen window flips to *Responder Assigned* with an ETA.

> **The line to say:** every dispatch decision this system makes is recorded
> with its reason. That is what makes the analytics in Act 4 evidence rather
> than decoration.

---

## Act 2 — the correctness claim (≈2 min)

This is the technical centrepiece.

7. **Terminal:**
   ```bash
   python sim/scenarios/race.py --n 50
   ```
   Fifty responders, aligned on a barrier, all accepting one incident at the
   same instant.

8. **Output:** `accepted: 1`, `already handled: 49`.

9. **Show the mechanism.** Put `backend/app/services/acceptance.py` on screen —
   one conditional `UPDATE`, `rowcount` inspected.

10. **Show the test running:**
    ```bash
    cd backend && pytest tests/test_accept_lock.py -v
    ```
    N = 2, 10 and 50, each responder on its own connection.

> **The line to say, plainly:** *the lock is enforced by the database, not by
> application code, because an application-level check is a time-of-check-to-
> time-of-use race.* Then add the part most people miss: each racing responder
> gets its own session on its own connection — sharing one would serialise the
> accepts inside the ORM and the test would pass while proving nothing.

If asked why not `SELECT ... FOR UPDATE`: correct, but heavier, and it holds a
transaction open. If asked why not an `asyncio.Lock`: it silently breaks the
moment you run more than one worker, which is the worst failure mode a
correctness claim can have.

---

## Act 3 — honest failure (≈1 min)

11. **Terminal:**
    ```bash
    python sim/scenarios/timeout.py --n 25
    ```
    Responders are connected and alerted, and every one of them ignores it.

12. **Watch the ladder walk** 1 km → 2 km → 3 km and terminate in
    `no_responder_found`. Show the citizen window: a calm screen directing them
    to emergency services. Not an error page.

13. **Both triggers, in one run.** The first expansion is immediate — the
    candidate set was empty, and waiting 30 seconds to reconfirm an emptiness
    already measured would burn 30 seconds of an emergency. The later ones wait
    the full timeout, because people *were* alerted and stayed silent. Two
    different failures, two different responses.

14. **AI degradation.** Unset `GEMINI_API_KEY` (or just point it at nothing) and
    trigger one more SOS. It dispatches exactly as before; the incident keeps
    `{unspecified, medium}` and `ai_status` records why.

> **The line to say:** being alerted is not the same as responding. A dispatch
> system that assumes otherwise is making the single most unrealistic assumption
> available to it.

---

## Act 4 — the analytics (≈3 min)

15. **Admin dashboard** against the seeded corpus.

16. **Walk the funnel**: created → candidates found → alerted → accepted →
    resolved, and name where it leaks.

17. **Time to acceptance.** Show the histogram, then say why p90 and not mean:
    emergency response is a tail-latency problem, and the mean is the statistic
    that hides exactly the failures that matter.

18. **The coverage grid.** Name the two or three buckets where the network is
    structurally blind. That metric is computable *only* because rejections are
    logged rather than filtered.

19. **Escalation split by trigger.** State the conclusion it supports: whether
    this network's problem is density or responsiveness. Different problems,
    different fixes — and a single "escalation rate" number could not tell you
    which.

20. **Point at the filename under any panel.** Every figure names the `.sql`
    file that produced it. Offer to open one. That is the difference between a
    dashboard that reports and one that can be audited.

---

## Contingency (Ch. 25)

| If this fails | Do this |
|---|---|
| **Network is down** | Everything except the map tiles and the AI call works offline. Leaflet degrades to a styled placeholder; the AI degrades to `{unspecified, medium}` — which *is* Act 3 step 14. Demo the degradation instead of apologising for it. |
| **AI quota exhausted (429)** | Same path as any failure: `ai_status='error'`, dispatch unaffected. Or flip `AI_PROVIDER=groq` beforehand. |
| **Database unreachable** | Nothing works. This is the one hard dependency — have the dataset seeded on a local Postgres as a fallback, not only on a hosted one. |
| **Live SOS finds nobody** | Your browser is reporting a real location outside the seeded area. Mock the location, or run Act 3 early and come back. |
| **Everything is on fire** | Screen recordings of all four acts, made the day before. Record them once the dataset is frozen and do not re-seed afterwards. |

## Rehearsal log

Chapter 24 asks for five clean end-to-end runs before demo day. Track them —
the point is that the fifth is boring.

| # | Date | Result | Fixed since |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |

## Questions worth pre-loading

- **"Why not PostGIS?"** At demo scale a spatial extension is infrastructure
  with no benefit (ADR-002, Rule 004). Named in Future Scope as the correct
  answer at production scale.
- **"Does skill ranking actually help?"** The dashboard answers it — acceptance
  rate by skill class. If the rates are equal, the ranking is cosmetic, and the
  metric exists to be able to say so.
- **"What happens with two app workers?"** The WebSocket registry is
  process-local (Ch. 16), so responders on one worker are invisible to the
  other. Run one worker; Redis pub/sub is the production answer and is named,
  not built.
- **"What isn't built?"** Certificate upload and admin approval, responder live
  location after acceptance, and Web Push. All in Future Scope, none claimed
  anywhere in the product.
