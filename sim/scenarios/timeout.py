"""Nobody accepts -- Chapter 27, Act 3: the honest failure.

Responders are connected and alerted, and every one of them ignores the alert.
The radius walks 1km -> 2km -> 3km and the incident terminates in
`no_responder_found`, which is a real state with real UI, not an error
(invariant 5).

Almost no comparable project demonstrates its own failure mode on purpose. That
is the point of this scenario.

    python sim/scenarios/timeout.py --n 10
"""

import argparse
import asyncio
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from sim.responder_client import DEFAULT_API, SyntheticResponder, login  # noqa: E402

CITIZEN_PHONE = "+918700000002"
CITIZEN_PASSWORD = "timeout-citizen-pw"
INCIDENT_LAT, INCIDENT_LNG = 12.9716, 77.5946


def call(api, method, path, body=None, token=None):
    request = urllib.request.Request(api + path, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(request, data) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Escalation to no_responder_found (ADR-012).")
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--api", default=DEFAULT_API)
    parser.add_argument("--watch-seconds", type=float, default=120.0)
    args = parser.parse_args()

    api = args.api
    loop = asyncio.get_running_loop()

    responders = [SyntheticResponder(phone=f"+9199{i:06d}", api=api) for i in range(args.n)]
    tasks = [asyncio.create_task(r.run()) for r in responders]
    await asyncio.wait_for(
        asyncio.gather(*(r.connected.wait() for r in responders)), timeout=30
    )
    print(f"{args.n} responders connected -- all of them will ignore the alert\n")

    call(api, "POST", "/auth/signup", {"name": "Timeout Citizen", "phone": CITIZEN_PHONE,
                                       "password": CITIZEN_PASSWORD, "role": "citizen"})
    token = await loop.run_in_executor(None, login, api, CITIZEN_PHONE, CITIZEN_PASSWORD)

    status, sos = call(api, "POST", "/sos", {"lat": INCIDENT_LAT, "lng": INCIDENT_LNG,
                                             "description": "timeout scenario"}, token=token)
    if status != 201:
        print(f"could not create incident: {status} {sos}")
        return 1

    sos_id = sos["id"]
    print(f"incident {sos_id}: radius {sos['current_radius_m']}m, "
          f"{sos['alerted_count']} alerted\n")

    seen = (sos["current_radius_m"], sos["status"])
    print(f"  {'0.0s':>7}  {seen[0]:>5}m  {seen[1]}")

    started = loop.time()
    while loop.time() - started < args.watch_seconds:
        await asyncio.sleep(1.0)
        _, current = call(api, "GET", f"/sos/{sos_id}", token=token)
        state = (current["current_radius_m"], current["status"])
        if state != seen:
            seen = state
            print(f"  {loop.time() - started:>6.1f}s  {state[0]:>5}m  {state[1]}")
        if current["status"] == "no_responder_found":
            break

    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    ok = seen[1] == "no_responder_found" and seen[0] == 3000
    print("\n" + ("PASS -- ladder exhausted, terminated in an explicit state (ADR-012)"
                  if ok else f"FAIL -- ended at {seen[0]}m in state {seen[1]!r}"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
