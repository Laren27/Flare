"""Deterministic responder seeding -- ADR-016.

Creates N synthetic volunteers at seeded coordinates with seeded skills and
verification states, so the demo dataset is reproducible: the same `--seed`
produces the same network every time. Chapter 27 Act 1 opens on this.

Writes to the database directly rather than through the API. Seeding is a
developer and demo tool, not a user flow, and going direct means it works with
no server running and no HTTP round trip per volunteer.

    cd backend && python ../sim/seed.py --count 50
    cd backend && python ../sim/seed.py --count 50 --reset
"""

import argparse
import math
import random
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.services.auth import hash_password  # noqa: E402

# Bengaluru city centre. Arbitrary but fixed -- the coverage grid of ADR-015
# needs incidents and responders in the same operating area to mean anything.
CENTRE_LAT, CENTRE_LNG = 12.9716, 77.5946
EARTH_RADIUS_M = 6_371_008.8

SKILLS = ("cpr", "first_aid", "blood_donor", "general")
PASSWORD = "sim-responder-pw"
PHONE_PREFIX = "+9199"

# Proportions chosen to make the analytics layer show something. A network where
# everyone is verified and online has no coverage gaps to find, and a dashboard
# with nothing to report is not evidence of anything (ADR-015).
VERIFIED_RATE = 0.80
AVAILABLE_RATE = 0.70
LOCATED_RATE = 0.95


def offset_coordinate(lat: float, lng: float, bearing_rad: float, distance_m: float):
    """Move a point by distance along a bearing, on a sphere."""
    angular = distance_m / EARTH_RADIUS_M
    phi1, lambda1 = math.radians(lat), math.radians(lng)

    phi2 = math.asin(
        math.sin(phi1) * math.cos(angular)
        + math.cos(phi1) * math.sin(angular) * math.cos(bearing_rad)
    )
    lambda2 = lambda1 + math.atan2(
        math.sin(bearing_rad) * math.sin(angular) * math.cos(phi1),
        math.cos(angular) - math.sin(phi1) * math.sin(phi2),
    )
    return math.degrees(phi2), math.degrees(lambda2)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic responders (ADR-016).")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--seed", type=int, default=1337, help="fixes the generated network")
    parser.add_argument("--spread-m", type=float, default=3000.0, help="max distance from centre")
    parser.add_argument("--reset", action="store_true", help="delete all existing data first")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    engine = create_engine(make_url(get_settings().database_url.get_secret_value()))

    if args.reset:
        with engine.begin() as c:
            # Order matters: dispatch_events pins users, deliberately -- the
            # decision log is append-only and should not be erasable by
            # deleting a user (ADR-014).
            for table in ("dispatch_events", "incident_history", "notifications", "sos", "users"):
                c.execute(text(f"DELETE FROM {table}"))
        print("reset: all tables cleared")

    password_hash = hash_password(PASSWORD)
    created = 0

    with engine.begin() as c:
        for index in range(args.count):
            phone = f"{PHONE_PREFIX}{index:06d}"
            if c.execute(text("SELECT 1 FROM users WHERE phone=:p"), {"p": phone}).scalar():
                continue

            user_id = c.execute(
                text(
                    "INSERT INTO users (name, phone, role, password_hash) "
                    "VALUES (:n, :p, 'volunteer', :h) RETURNING id"
                ),
                {"n": f"Responder {index:03d}", "p": phone, "h": password_hash},
            ).scalar()

            c.execute(
                text(
                    "INSERT INTO volunteers (user_id, verified, skills, availability) "
                    "VALUES (:u, :v, :s, :a)"
                ),
                {
                    "u": user_id,
                    "v": rng.random() < VERIFIED_RATE,
                    "s": rng.choice(SKILLS),
                    "a": rng.random() < AVAILABLE_RATE,
                },
            )

            if rng.random() < LOCATED_RATE:
                # sqrt keeps the scatter uniform by area rather than clustering
                # everyone near the centre, which would hide coverage gaps.
                distance = args.spread_m * math.sqrt(rng.random())
                lat, lng = offset_coordinate(
                    CENTRE_LAT, CENTRE_LNG, rng.uniform(0, 2 * math.pi), distance
                )
                c.execute(
                    text("INSERT INTO locations (user_id, lat, lng) VALUES (:u, :lat, :lng)"),
                    {"u": user_id, "lat": lat, "lng": lng},
                )

            created += 1

    with engine.connect() as c:
        summary = c.execute(
            text(
                "SELECT count(*) FILTER (WHERE v.verified), "
                "       count(*) FILTER (WHERE v.availability), "
                "       count(*) FILTER (WHERE l.user_id IS NULL), count(*) "
                "FROM volunteers v LEFT JOIN locations l ON l.user_id = v.user_id"
            )
        ).one()

    print(f"seeded {created} new responders (seed={args.seed}, spread={args.spread_m:.0f}m)")
    print(f"  total volunteers : {summary[3]}")
    print(f"  verified         : {summary[0]}")
    print(f"  available        : {summary[1]}")
    print(f"  no location      : {summary[2]}")
    print(f"  password         : {PASSWORD}")


if __name__ == "__main__":
    main()
