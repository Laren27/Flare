"""N responders accept one incident simultaneously -- Chapter 27, Act 2.

This is the demo's technical centrepiece and the live proof of ADR-010/011.
Unlike `tests/test_accept_lock.py`, which exercises the service directly, this
drives the real HTTP endpoint against a running server, so what is proven is the
deployed path rather than a function call.

Each responder gets its own OS thread and they are aligned on a barrier, so all
N requests leave at genuinely the same moment. `asyncio.gather` over a
thread-pool would cap at the default worker count and quietly batch them, which
would weaken the very race the scenario exists to demonstrate.

    python sim/scenarios/race.py --n 50
"""

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from sim.responder_client import DEFAULT_API, login  # noqa: E402

CITIZEN_PHONE = "+918700000001"
CITIZEN_PASSWORD = "race-citizen-pw"
INCIDENT_LAT, INCIDENT_LNG = 12.9716, 77.5946


def post(api: str, path: str, body=None, token: str | None = None):
    request = urllib.request.Request(api + path, method="POST")
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(request, data) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def ensure_citizen(api: str) -> str:
    post(api, "/auth/signup", {"name": "Race Citizen", "phone": CITIZEN_PHONE,
                               "password": CITIZEN_PASSWORD, "role": "citizen"})
    return login(api, CITIZEN_PHONE, CITIZEN_PASSWORD)


def main() -> int:
    parser = argparse.ArgumentParser(description="Concurrent accept race (ADR-010).")
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--api", default=DEFAULT_API)
    args = parser.parse_args()

    api = args.api
    print(f"logging in {args.n} responders")
    phones = [f"+9199{i:06d}" for i in range(args.n)]
    with ThreadPoolExecutor(max_workers=min(args.n, 32)) as pool:
        tokens = list(pool.map(lambda p: login(api, p), phones))

    citizen_token = ensure_citizen(api)
    status, sos = post(api, "/sos", {"lat": INCIDENT_LAT, "lng": INCIDENT_LNG,
                                     "description": "race scenario"}, token=citizen_token)
    if status != 201:
        print(f"could not create incident: {status} {sos}")
        return 1
    sos_id = sos["id"]
    print(f"incident {sos_id} created; {args.n} responders will now accept simultaneously\n")

    barrier = threading.Barrier(args.n)
    results: list[tuple[int, dict]] = []
    lock = threading.Lock()

    def attempt(token: str) -> None:
        barrier.wait()  # nobody moves until everybody is ready
        outcome = post(api, f"/sos/{sos_id}/accept", token=token)
        with lock:
            results.append(outcome)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.n) as pool:
        list(pool.map(attempt, tokens))
    elapsed = time.perf_counter() - started

    won = [r for _, r in results if r.get("accepted") is True]
    lost = [r for _, r in results if r.get("accepted") is False]

    print(f"  accepted        : {len(won)}")
    print(f"  already handled : {len(lost)}")
    print(f"  window          : {elapsed * 1000:.0f}ms")

    _, final = post(api, f"/sos/{sos_id}/accept", token=tokens[0])
    print(f"  incident status : {final.get('status')}")

    ok = len(won) == 1 and len(lost) == args.n - 1
    print("\n" + ("PASS -- exactly one winner, enforced by the database (ADR-011)"
                  if ok else f"FAIL -- {len(won)} winners, expected exactly 1"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
