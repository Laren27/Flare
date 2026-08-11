"""Candidate selection for an incident (Ch. 13, steps 1-5).

Persists the incident, evaluates every volunteer against it, delivers wave-1
alerts over live WebSocket connections, and logs every decision (ADR-014).

Order matters here. Selection decides who *should* be alerted; delivery finds
out who actually can be reached. Events are written after delivery so a
candidate whose socket is gone is recorded as `no_socket` rather than as a
successful alert -- the split ADR-021 set up before there was any transport to
fail. The escalation state machine of ADR-012 is week 4.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SOS, DispatchOutcome, Location, RejectionReason, SkillClass, Volunteer
from app.services import events, haversine, notifications
from app.services.websocket_manager import ConnectionRegistry
from app.services.websocket_manager import registry as default_registry

WAVE_ONE = 1


@dataclass(frozen=True, slots=True)
class Candidate:
    """A volunteer selected for alerting, with the facts that selected them."""

    volunteer_id: int
    skill: SkillClass
    skill_match: bool
    distance_m: float


@dataclass(frozen=True, slots=True)
class DispatchResult:
    sos: SOS
    candidates: list[Candidate]
    evaluated_count: int
    # Selected candidates whose alert actually reached a live socket. The gap
    # between this and len(candidates) is the no_socket population.
    alerted_count: int


async def create_sos(
    session: AsyncSession,
    *,
    victim_id: int,
    lat: float,
    lng: float,
    description: str | None,
    radius_m: int,
) -> SOS:
    """Persist the incident as `pending` before any candidate work happens.

    Ordering matters: the incident exists first so that every dispatch event has
    something to reference, and so a crash mid-selection leaves a recorded
    emergency rather than nothing at all.
    """
    sos = SOS(
        victim_id=victim_id,
        lat=lat,
        lng=lng,
        description=description,
        current_radius_m=radius_m,
    )
    session.add(sos)
    await session.flush()
    return sos


def evaluate_volunteer(
    *,
    volunteer_id: int,
    skill: SkillClass,
    verified: bool,
    available: bool,
    volunteer_lat: float | None,
    volunteer_lng: float | None,
    incident_lat: float,
    incident_lng: float,
    radius_m: int,
) -> events.Evaluation:
    """Assess one volunteer against one incident at one radius.

    Collects every reason that applies and resolves them through the ADR-021
    precedence, rather than returning on the first failure -- the precedence is
    then a stated rule in one place instead of an accident of branch order.
    """
    reasons: set[RejectionReason] = set()

    if not verified:
        reasons.add(RejectionReason.UNVERIFIED)
    if not available:
        reasons.add(RejectionReason.UNAVAILABLE)

    distance_m: float | None = None
    if volunteer_lat is None or volunteer_lng is None:
        reasons.add(RejectionReason.NO_LOCATION)
    else:
        distance_m = haversine.haversine_distance_m(
            incident_lat, incident_lng, volunteer_lat, volunteer_lng
        )
        if not haversine.within_radius(distance_m, radius_m):
            reasons.add(RejectionReason.OUT_OF_RADIUS)

    reason = events.first_applicable_reason(reasons)

    return events.Evaluation(
        volunteer_id=volunteer_id,
        skill=skill,
        skill_match=haversine.is_skill_match(skill),
        distance_m=distance_m,
        outcome=DispatchOutcome.REJECTED if reason else DispatchOutcome.ALERTED,
        rejection_reason=reason,
    )


async def dispatch_wave_one(
    session: AsyncSession,
    sos: SOS,
    registry: ConnectionRegistry | None = None,
) -> DispatchResult:
    """Evaluate every volunteer, alert the survivors, log every decision.

    The registry is injectable so tests and the simulation harness can drive
    delivery without a real server; production passes the process-wide one.
    """
    registry = registry if registry is not None else default_registry

    # LEFT JOIN, not JOIN: an inner join would drop volunteers who have never
    # reported a position, and dropping a candidate without recording why is
    # exactly the silent filtering invariant 4 forbids. The victim is excluded
    # outright -- they are the subject of the incident, not a candidate for it.
    rows = await session.execute(
        select(
            Volunteer.user_id,
            Volunteer.skills,
            Volunteer.verified,
            Volunteer.availability,
            Location.lat,
            Location.lng,
        )
        .outerjoin(Location, Location.user_id == Volunteer.user_id)
        .where(Volunteer.user_id != sos.victim_id)
    )

    radius_m = sos.current_radius_m
    evaluations = [
        evaluate_volunteer(
            volunteer_id=user_id,
            skill=skill,
            verified=verified,
            available=available,
            volunteer_lat=lat,
            volunteer_lng=lng,
            incident_lat=sos.lat,
            incident_lng=sos.lng,
            radius_m=radius_m,
        )
        for user_id, skill, verified, available, lat, lng in rows
    ]

    candidates = [
        Candidate(
            volunteer_id=evaluation.volunteer_id,
            skill=evaluation.skill,
            skill_match=evaluation.skill_match,
            # Selected candidates always have a distance: no_location rejects.
            distance_m=evaluation.distance_m,  # type: ignore[arg-type]
        )
        for evaluation in evaluations
        if evaluation.is_selected
    ]
    # Ranked before delivery, so alerts go out best-qualified-first rather than
    # in whatever order the database returned rows.
    candidates.sort(key=lambda c: haversine.rank_key(c.skill, c.distance_m))

    deliveries = await notifications.deliver_alerts(
        session,
        sos=sos,
        wave_number=WAVE_ONE,
        recipients=[(c.volunteer_id, c.distance_m) for c in candidates],
        registry=registry,
    )

    # Only now are the outcomes final. A selected candidate whose socket had gone
    # is downgraded to no_socket -- the reason exists precisely for this, and
    # recording them as alerted would put an alert nobody received into the
    # ADR-015 funnel.
    undeliverable = {d.volunteer_id for d in deliveries if not d.delivered}
    final_evaluations = [
        events.Evaluation(
            volunteer_id=evaluation.volunteer_id,
            skill=evaluation.skill,
            skill_match=evaluation.skill_match,
            distance_m=evaluation.distance_m,
            outcome=DispatchOutcome.REJECTED,
            rejection_reason=RejectionReason.NO_SOCKET,
        )
        if evaluation.volunteer_id in undeliverable
        else evaluation
        for evaluation in evaluations
    ]

    await events.record_evaluations(
        session,
        sos_id=sos.id,
        wave_number=WAVE_ONE,
        radius_m=radius_m,
        evaluations=final_evaluations,
    )

    sos.wave_count = WAVE_ONE
    # Isolates system latency from human latency in ADR-015. Set once wave 1 has
    # been decided, which is the moment the engine's own work is done.
    sos.first_dispatch_at = datetime.now(UTC)

    await session.commit()

    return DispatchResult(
        sos=sos,
        candidates=candidates,
        evaluated_count=len(evaluations),
        alerted_count=len(candidates) - len(undeliverable),
    )
