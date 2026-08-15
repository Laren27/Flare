"""Bulk incident corpus for the analytics layer -- ADR-016, Ch. 18A.

A dashboard with three data points is not evidence of anything. This generates a
few hundred synthetic incidents with realistic outcomes so the ADR-015 metrics
have distributions to report rather than single values.

Writes straight to the database rather than driving the API, deliberately. The
API path would need hundreds of live WebSocket responders and real 30-second
escalation timeouts -- hours of wall time to produce data whose shape we are
choosing anyway. What matters is that the ROWS are shaped exactly as the engine
would have written them: same statuses, same DispatchEvents per candidate, same
rejection reasons, same funnel timestamps. The queries cannot tell the
difference, because there is none to tell.

A share of incidents is withdrawn by the citizen (ADR-025), split between those
cancelled while still searching and those cancelled after a responder had
already accepted. The second kind is the reason the share exists: it is the case
that makes the dispatch funnel and the time-to-acceptance distribution disagree
on purpose, and without any in the corpus the dashboard cannot demonstrate that
they disagree correctly.

Deterministic: the same --seed rebuilds the same corpus, so a dashboard figure
quoted on demo day is reproducible.

    cd backend && python ../sim/scenarios/coverage.py --incidents 300
    cd backend && python ../sim/scenarios/coverage.py --incidents 300 --clear
"""

import argparse
import math
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.config import get_settings  # noqa: E402

CENTRE_LAT, CENTRE_LNG = 12.9716, 77.5946
EARTH_RADIUS_M = 6_371_008.8
LADDER = (1000, 2000, 3000)

# Categories the AI service can return, with plausible frequencies. Cardiac
# arrest dominates because that is the emergency Chapter 1 is written about.
CATEGORIES = [
    ("cardiac_arrest", 0.28, "high"),
    ("severe_bleeding", 0.16, "high"),
    ("trauma", 0.14, "high"),
    ("choking", 0.12, "high"),
    ("breathing_difficulty", 0.10, "medium"),
    ("unconscious", 0.08, "high"),
    ("seizure", 0.05, "medium"),
    ("allergic_reaction", 0.04, "medium"),
    ("burn", 0.03, "low"),
]

# Two deliberate coverage holes, so the gap metric has something real to find.
# A coverage map with no gaps proves the map works and nothing else.
DEAD_ZONES = [(0.022, 0.018, 900.0), (-0.019, 0.026, 700.0)]


def offset(lat, lng, bearing_rad, distance_m):
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


def in_dead_zone(lat, lng):
    for d_lat, d_lng, radius in DEAD_ZONES:
        zone_lat, zone_lng = CENTRE_LAT + d_lat, CENTRE_LNG + d_lng
        dy = (lat - zone_lat) * 111_320
        dx = (lng - zone_lng) * 111_320 * math.cos(math.radians(lat))
        if math.hypot(dx, dy) < radius:
            return True
    return False


def pick_category(rng):
    roll = rng.random()
    cumulative = 0.0
    for name, weight, priority in CATEGORIES:
        cumulative += weight
        if roll <= cumulative:
            return name, priority
    return CATEGORIES[-1][0], CATEGORIES[-1][2]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an incident corpus (Ch. 18A).")
    parser.add_argument("--incidents", type=int, default=300)
    parser.add_argument("--seed", type=int, default=4242)
    parser.add_argument("--days", type=int, default=21, help="spread incidents over N days")
    parser.add_argument("--spread-m", type=float, default=3200.0)
    # Applied among incidents that had a reachable responder -- see the branch
    # below for why the no_responder_found population is left alone. The
    # achieved overall share is printed at the end so it can be checked.
    parser.add_argument(
        "--cancelled-share",
        type=float,
        default=0.045,
        help="fraction of reachable incidents the citizen withdraws (ADR-025)",
    )
    parser.add_argument("--clear", action="store_true", help="delete existing incidents first")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    engine = create_engine(make_url(get_settings().database_url.get_secret_value()))

    with engine.connect() as c:
        volunteers = list(c.execute(text(
            "SELECT v.user_id, v.skills, v.verified, v.availability, l.lat, l.lng "
            "FROM volunteers v LEFT JOIN locations l ON l.user_id = v.user_id"
        )))
        citizen = c.execute(text(
            "SELECT id FROM users WHERE role='citizen' ORDER BY id LIMIT 1"
        )).scalar()

    if not volunteers:
        sys.exit("No volunteers. Run sim/seed.py first.")

    with engine.begin() as c:
        if args.clear:
            for table in ("dispatch_events", "incident_history", "notifications", "sos"):
                c.execute(text(f"DELETE FROM {table}"))
            print("cleared existing incidents")

        if citizen is None:
            citizen = c.execute(text(
                "INSERT INTO users (name, phone, role, password_hash) "
                "VALUES ('Corpus Citizen', '+910000009999', 'citizen', 'x') RETURNING id"
            )).scalar()

    created = matched = resolved = unmatched = cancelled_count = 0
    cancelled_after_match = 0
    now = datetime.now(UTC)

    with engine.begin() as c:
        for _ in range(args.incidents):
            created_at = now - timedelta(
                seconds=rng.uniform(0, args.days * 86400)
            )
            distance = args.spread_m * math.sqrt(rng.random())
            lat, lng = offset(CENTRE_LAT, CENTRE_LNG, rng.uniform(0, 2 * math.pi), distance)
            category, priority = pick_category(rng)

            # Who would the engine have found? Same rules as dispatch.py.
            evaluations = []
            for user_id, skill, verified, available, v_lat, v_lng in volunteers:
                if v_lat is None:
                    evaluations.append((user_id, None, "no_location", skill))
                    continue
                d = 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, (
                    math.sin(math.radians(v_lat - lat) / 2) ** 2
                    + math.cos(math.radians(lat)) * math.cos(math.radians(v_lat))
                    * math.sin(math.radians(v_lng - lng) / 2) ** 2
                ))))
                if not verified:
                    evaluations.append((user_id, d, "unverified", skill))
                elif not available:
                    evaluations.append((user_id, d, "unavailable", skill))
                else:
                    evaluations.append((user_id, d, None, skill))

            dead = in_dead_zone(lat, lng)
            radius = LADDER[0]
            wave = 1
            trigger = None

            # Walk the ladder exactly as the escalation machine would.
            while True:
                reachable = [
                    e for e in evaluations
                    if e[2] is None and e[1] is not None and e[1] <= radius and not dead
                ]
                if reachable:
                    break
                if trigger is None:
                    trigger = "empty_set"
                nxt = next((r for r in LADDER if r > radius), None)
                if nxt is None:
                    break
                radius, wave = nxt, wave + 1

            reachable = [
                e for e in evaluations
                if e[2] is None and e[1] is not None and e[1] <= radius and not dead
            ]

            # Outcome. Responders ignore alerts sometimes -- assuming otherwise
            # is the most unrealistic thing a dispatch model can do (ADR-012).
            cancelled = False

            if not reachable:
                status, unmatched = "no_responder_found", unmatched + 1
                accepted_by = matched_at = None
                trigger = trigger or "empty_set"
            elif rng.random() < args.cancelled_share:
                # The citizen withdrew (ADR-025). Applied only where a responder
                # was actually reachable, which keeps the no_responder_found
                # population -- the evidence Act 3 rests on -- untouched, and
                # matches the likelier story: you cancel because help is coming
                # or because you realise you do not need it, not because the
                # search found nobody.
                cancelled = True
                cancelled_count += 1
                status = "cancelled"

                if rng.random() < 0.4:
                    # Cancelled after a responder had already accepted. This is
                    # the case that makes the funnel and the acceptance
                    # distribution disagree on purpose: it counts as Accepted,
                    # and is excluded from time-to-acceptance.
                    cancelled_after_match += 1
                    winner = min(reachable, key=lambda e: e[1])
                    accepted_by = winner[0]
                    matched_at = created_at + timedelta(
                        seconds=min(rng.lognormvariate(4.6, 0.65), 700)
                    )
                    withdrawn_at = matched_at + timedelta(seconds=rng.uniform(60, 600))
                else:
                    # Cancelled while still searching.
                    accepted_by = matched_at = None
                    withdrawn_at = created_at + timedelta(seconds=rng.uniform(30, 300))

                if wave > 1 and trigger is None:
                    trigger = "timeout"
            elif rng.random() < 0.82:
                winner = min(reachable, key=lambda e: e[1])
                accepted_by = winner[0]
                delay = rng.lognormvariate(4.6, 0.65)  # seconds, right-skewed
                matched_at = created_at + timedelta(seconds=min(delay, 700))
                if rng.random() < 0.94:
                    status, resolved = "resolved", resolved + 1
                else:
                    status, matched = "matched", matched + 1
                if wave > 1 and trigger is None:
                    trigger = "timeout"
            else:
                # Alerted, but nobody answered. Condition B ALWAYS expands
                # (ADR-012) -- an incident cannot be filed under trigger
                # 'timeout' having never widened, so walk the remaining ladder
                # exactly as the state machine would before giving up.
                trigger = trigger or "timeout"
                while (nxt := next((r for r in LADDER if r > radius), None)) is not None:
                    radius, wave = nxt, wave + 1
                status, unmatched = "no_responder_found", unmatched + 1
                accepted_by = matched_at = None

            first_dispatch = created_at + timedelta(milliseconds=rng.uniform(40, 260))
            if cancelled:
                # cancel() stamps resolved_at on withdrawal too -- the column is
                # "when this incident stopped being live", not "when help
                # finished". The status is what distinguishes the two.
                resolved_at = withdrawn_at
            elif status == "resolved" and matched_at:
                resolved_at = matched_at + timedelta(seconds=rng.uniform(240, 1500))
            else:
                resolved_at = None

            sos_id = c.execute(text("""
                INSERT INTO sos (victim_id, lat, lng, description, status, current_radius_m,
                                 wave_count, ai_category, ai_priority, ai_status,
                                 created_at, first_dispatch_at, matched_at, resolved_at,
                                 accepted_by)
                VALUES (:v, :lat, :lng, :desc, :st, :rad, :wave, :cat, :pri, :ai,
                        :created, :first, :matched, :resolved, :acc)
                RETURNING id
            """), {
                "v": citizen, "lat": lat, "lng": lng,
                "desc": f"{category.replace('_', ' ')} reported",
                "st": status, "rad": radius, "wave": wave,
                "cat": category, "pri": priority,
                # Mirrors the real degradation mix: mostly ok, occasionally not.
                "ai": rng.choices(["ok", "timeout", "error", "skipped"],
                                  [0.88, 0.05, 0.03, 0.04])[0],
                "created": created_at, "first": first_dispatch,
                "matched": matched_at, "resolved": resolved_at,
                "acc": accepted_by,
            }).scalar()
            created += 1

            # One DispatchEvents row per candidate evaluated -- invariant 4 holds
            # for generated data too, or the queries would read a different
            # world from the one the engine writes.
            for user_id, d, reason, _skill in evaluations:
                if reason is None and d is not None and d <= radius and not dead:
                    outcome, final_reason = "alerted", None
                elif reason is None:
                    outcome, final_reason = "rejected", "out_of_radius"
                else:
                    outcome, final_reason = "rejected", reason
                c.execute(text("""
                    INSERT INTO dispatch_events (sos_id, volunteer_id, wave_number,
                        evaluated_at, radius_m_at_eval, distance_m, skill_match,
                        outcome, rejection_reason)
                    VALUES (:s, :v, :w, :at, :rad, :d, :sm, :o, :r)
                """), {
                    "s": sos_id, "v": user_id, "w": wave, "at": first_dispatch,
                    "rad": radius, "d": d, "sm": _skill in ("cpr", "first_aid"),
                    "o": outcome, "r": final_reason,
                })

            for user_id, d, reason, _skill in evaluations:
                if reason is None and d is not None and d <= radius and not dead:
                    if user_id == accepted_by:
                        n_status, responded = "accepted", matched_at
                    elif accepted_by is not None:
                        n_status, responded = "dismissed", matched_at
                    elif cancelled:
                        # cancel() dismisses every alert still open, so no
                        # responder is left holding one for an incident that no
                        # longer exists. A decline that landed first stands.
                        n_status, responded = rng.choices(
                            ["dismissed", "declined"], [0.75, 0.25]
                        )[0], withdrawn_at
                    else:
                        n_status, responded = rng.choices(
                            ["sent", "declined"], [0.75, 0.25]
                        )[0], None
                    c.execute(text("""
                        INSERT INTO notifications (sos_id, volunteer_id, wave_number,
                                                   status, sent_at, responded_at)
                        VALUES (:s, :v, :w, :st, :sent, :resp)
                    """), {"s": sos_id, "v": user_id, "w": wave, "st": n_status,
                           "sent": first_dispatch, "resp": responded})

            # Cancelled incidents are absent from this table on purpose
            # (ADR-025): Incident History records how the system concluded an
            # incident, and a citizen changing their mind is not a conclusion
            # the system produced.
            if status in ("resolved", "no_responder_found"):
                c.execute(text("""
                    INSERT INTO incident_history (sos_id, response_time_seconds,
                        escalation_count, final_radius_m, escalation_trigger, resolved_at)
                    VALUES (:s, :rt, :ec, :fr, :tr, :ra)
                """), {
                    "s": sos_id,
                    "rt": int((matched_at - created_at).total_seconds()) if matched_at else None,
                    "ec": wave - 1, "fr": radius,
                    "tr": trigger or "none", "ra": resolved_at,
                })

    share = (cancelled_count / created * 100) if created else 0.0
    print(f"generated {created} incidents (seed={args.seed}, {args.days}d window)")
    print(f"  resolved            : {resolved}")
    print(f"  matched, unresolved : {matched}")
    print(f"  no_responder_found  : {unmatched}")
    print(f"  cancelled           : {cancelled_count} ({share:.1f}% of all incidents)")
    print(f"    of which accepted first : {cancelled_after_match}")
    print(f"  dead zones          : {len(DEAD_ZONES)} (coverage gaps to find)")


if __name__ == "__main__":
    main()
