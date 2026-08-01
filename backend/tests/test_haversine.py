"""Distance correctness and radius boundary conditions -- Ch. 21.

Correctness is pinned three ways, because a distance function that is merely
self-consistent is not verified:

1. Analytic cases where the answer follows from the sphere itself and does not
   depend on any reference dataset -- identical points, one degree of arc,
   antipodes.
2. An independent implementation (spherical law of cosines) cross-checked at
   short range, where it is well conditioned.
3. Published coordinate pairs at city and intercontinental scale.

Requires no database, no environment, and no event loop -- see the note in
`app.database` on why that property is worth preserving.
"""

import math

import pytest

from app.models import SkillClass
from app.services.haversine import (
    EARTH_RADIUS_M,
    haversine_distance_m,
    is_skill_match,
    rank_key,
    within_radius,
)

# One degree of arc on a great circle, from the radius alone.
ONE_DEGREE_M = EARTH_RADIUS_M * math.pi / 180

LONDON = (51.5007, -0.1246)
PARIS = (48.8566, 2.3522)
NEW_YORK = (40.7128, -74.0060)
SYDNEY = (-33.8688, 151.2093)


def law_of_cosines_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Independent formula, used only to cross-check at short range."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_lambda = math.radians(lng2 - lng1)
    cosine = math.sin(phi1) * math.sin(phi2) + math.cos(phi1) * math.cos(phi2) * math.cos(
        delta_lambda
    )
    return EARTH_RADIUS_M * math.acos(min(1.0, max(-1.0, cosine)))


class TestAnalyticCases:
    """Answers derivable from the sphere, independent of any reference data."""

    def test_identical_points_are_zero(self):
        assert haversine_distance_m(12.9716, 77.5946, 12.9716, 77.5946) == 0.0

    def test_one_degree_of_longitude_at_the_equator(self):
        assert haversine_distance_m(0.0, 0.0, 0.0, 1.0) == pytest.approx(ONE_DEGREE_M, rel=1e-12)

    def test_one_degree_of_latitude_along_a_meridian(self):
        # True at any longitude on a sphere, unlike on the real ellipsoid.
        assert haversine_distance_m(0.0, 77.0, 1.0, 77.0) == pytest.approx(ONE_DEGREE_M, rel=1e-12)

    def test_longitude_converges_toward_the_pole(self):
        # Exact identity for two points sharing a latitude:
        #     d = 2R * asin(cos(lat) * sin(dlon / 2))
        # Note this is NOT R * dlon * cos(lat) -- that is the small-angle
        # approximation, and it is wrong by ~1e-5 relative at one degree.
        at_sixty = haversine_distance_m(60.0, 0.0, 60.0, 1.0)
        exact = 2 * EARTH_RADIUS_M * math.asin(
            math.cos(math.radians(60)) * math.sin(math.radians(1.0) / 2)
        )
        assert at_sixty == pytest.approx(exact, rel=1e-12)

    def test_longitude_shrinkage_approximates_cosine_of_latitude(self):
        # The familiar approximation, asserted at the accuracy it actually has.
        at_sixty = haversine_distance_m(60.0, 0.0, 60.0, 1.0)
        assert at_sixty == pytest.approx(ONE_DEGREE_M * math.cos(math.radians(60)), rel=1e-4)

    def test_pole_to_pole_is_half_the_circumference(self):
        assert haversine_distance_m(90.0, 0.0, -90.0, 0.0) == pytest.approx(
            math.pi * EARTH_RADIUS_M, rel=1e-12
        )

    def test_antipodal_points_across_the_equator(self):
        # The case that breaks the law of cosines and does not break haversine.
        assert haversine_distance_m(0.0, 0.0, 0.0, 180.0) == pytest.approx(
            math.pi * EARTH_RADIUS_M, rel=1e-12
        )


class TestProperties:
    def test_distance_is_symmetric(self):
        forward = haversine_distance_m(*LONDON, *PARIS)
        backward = haversine_distance_m(*PARIS, *LONDON)
        assert forward == pytest.approx(backward, rel=1e-12)

    def test_never_negative(self):
        assert haversine_distance_m(*SYDNEY, *NEW_YORK) >= 0

    @pytest.mark.parametrize(
        "point_a,point_b",
        [(LONDON, PARIS), ((12.9716, 77.5946), (13.0827, 80.2707)), ((0.0, 0.0), (0.5, 0.5))],
        ids=["london-paris", "bengaluru-chennai", "near-origin"],
    )
    def test_agrees_with_an_independent_formula(self, point_a, point_b):
        assert haversine_distance_m(*point_a, *point_b) == pytest.approx(
            law_of_cosines_distance_m(*point_a, *point_b), rel=1e-9
        )


class TestKnownPairs:
    """Published great-circle distances. Tolerance is 0.5%, which covers both
    the spherical approximation and disagreement over each city's centre."""

    @pytest.mark.parametrize(
        "point_a,point_b,expected_km",
        [
            (LONDON, PARIS, 343.5),
            (NEW_YORK, LONDON, 5570.0),
            (SYDNEY, NEW_YORK, 15990.0),
        ],
        ids=["london-paris", "new-york-london", "sydney-new-york"],
    )
    def test_matches_published_distance(self, point_a, point_b, expected_km):
        actual_km = haversine_distance_m(*point_a, *point_b) / 1000
        assert actual_km == pytest.approx(expected_km, rel=0.005)


class TestRadiusBoundary:
    """The base radius is 1000m and the ladder steps in whole kilometres
    (ADR-012), so the boundary is a condition the system meets constantly."""

    def test_inside_radius(self):
        assert within_radius(999.0, 1000) is True

    def test_exactly_on_the_boundary_is_inside(self):
        # Inclusive by decision -- "within 1km" includes exactly 1km.
        assert within_radius(1000.0, 1000) is True

    def test_just_outside_the_boundary(self):
        assert within_radius(1000.000001, 1000) is False

    def test_zero_distance_is_inside_any_radius(self):
        assert within_radius(0.0, 1000) is True

    def test_a_degree_of_longitude_at_the_equator_exceeds_the_base_radius(self):
        # Sanity anchor tying the boundary to a real coordinate delta: 0.01
        # degrees is roughly 1.11km, so it must fall outside a 1000m radius.
        distance = haversine_distance_m(0.0, 0.0, 0.0, 0.01)
        assert distance == pytest.approx(1111.9, abs=0.5)
        assert within_radius(distance, 1000) is False


class TestSkillRanking:
    def test_priority_order_is_cpr_first_aid_blood_donor_general(self):
        ordered = sorted(SkillClass, key=lambda skill: rank_key(skill, 0.0))
        assert ordered == [
            SkillClass.CPR,
            SkillClass.FIRST_AID,
            SkillClass.BLOOD_DONOR,
            SkillClass.GENERAL,
        ]

    def test_skill_outranks_distance(self):
        # A CPR responder at 800m sorts above a general volunteer at 200m.
        assert rank_key(SkillClass.CPR, 800.0) < rank_key(SkillClass.GENERAL, 200.0)

    def test_distance_breaks_ties_within_a_skill_class(self):
        assert rank_key(SkillClass.CPR, 200.0) < rank_key(SkillClass.CPR, 800.0)

    @pytest.mark.parametrize(
        "skill,expected",
        [
            (SkillClass.CPR, True),
            (SkillClass.FIRST_AID, True),
            (SkillClass.BLOOD_DONOR, False),
            (SkillClass.GENERAL, False),
        ],
    )
    def test_skill_match_is_top_tier_membership(self, skill, expected):
        assert is_skill_match(skill) is expected

    def test_every_skill_class_has_a_priority(self):
        # Guards against a new SkillClass member silently raising KeyError deep
        # inside a dispatch that is already in flight.
        for skill in SkillClass:
            assert isinstance(rank_key(skill, 0.0)[0], int)
