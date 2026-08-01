"""Distance, radius filtering, and skill ranking (Ch. 10).

Deliberately pure: this module imports nothing from `app.config` or
`app.database`, so it can be reasoned about and tested without an environment,
a connection, or a running loop. Chapter 24 sequences the dispatch core ahead of
the real-time layer precisely so its correctness is settled before any transport
exists, and `tests/test_haversine.py` is where that is cashed in.

Haversine over a sphere rather than PostGIS or a geodesic model: at demo scale
the spatial extension is infrastructure with no benefit (ADR-002, Rule 004), and
a spherical earth is accurate to roughly 0.3% against the WGS-84 ellipsoid --
three metres in a kilometre, against a radius the system expands in 1000m steps.
"""

import math

from app.models import SkillClass

# IUGG mean earth radius. The choice of radius, not the formula, is the dominant
# error term in any spherical distance; naming it here keeps that visible.
EARTH_RADIUS_M = 6_371_008.8

# Wave 1 has no AI category to rank relevance against (ADR-013), so the ordering
# comes from the problem domain of Chapter 1 -- cardiac arrest, choking, trauma
# bleeding. Wave 2 replaces this with ranking against the real ai_category.
# Lower sorts first (ADR-021).
SKILL_PRIORITY: dict[SkillClass, int] = {
    SkillClass.CPR: 0,
    SkillClass.FIRST_AID: 1,
    SkillClass.BLOOD_DONOR: 2,
    SkillClass.GENERAL: 3,
}

# What `DispatchEvents.skill_match` records in wave 1: membership of the tier
# whose training addresses the emergencies above directly.
TOP_TIER_SKILLS = frozenset({SkillClass.CPR, SkillClass.FIRST_AID})


def haversine_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres between two WGS-84 coordinates.

    Haversine rather than the spherical law of cosines: the two agree to within
    floating-point noise at short range, but the law of cosines loses precision
    catastrophically for near-antipodal pairs, and costs nothing to avoid.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = phi2 - phi1
    delta_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    # asin(sqrt(a)) clamped implicitly: a can exceed 1 only by rounding error.
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, a)))


def within_radius(distance_m: float, radius_m: float) -> bool:
    """Inclusive at the boundary -- "within 1km" includes exactly 1km.

    Stated rather than left to the reader because Chapter 21 requires the
    boundary condition to be tested, and a test needs a defined answer.
    """
    return distance_m <= radius_m


def skill_priority(skill: SkillClass) -> int:
    return SKILL_PRIORITY[skill]


def is_skill_match(skill: SkillClass) -> bool:
    return skill in TOP_TIER_SKILLS


def rank_key(skill: SkillClass, distance_m: float) -> tuple[int, float]:
    """Sort key for wave 1: skill tier first, then proximity (ADR-021).

    Skill ranks, it does not filter -- a general volunteer 200m away is still
    alerted, they simply sort below a CPR-trained volunteer 800m away. The
    rejection_reason vocabulary has no value for a skill mismatch, which is what
    settles the question (ADR-007 read through ADR-014).
    """
    return (SKILL_PRIORITY[skill], distance_m)
