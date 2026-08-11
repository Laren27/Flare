"""Candidate selection for an incident (Ch. 13, steps 1-5).

Persists the incident, evaluates every volunteer against it, delivers wave-1
alerts over live WebSocket connections, and logs every decision (ADR-014).

Order matters here. Selection decides who *should* be alerted; delivery finds
out who actually can be reached. Events are written after delivery so a
candidate whose socket is gone is recorded as `no_socket` rather than as a
successful alert -- the split ADR-021 set up before there was any transport to
fail. The escalation state machine of ADR-012 is week 4.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.database import get_session_factory
from app.models import (
    SOS,
    DispatchOutcome,
    Location,
    Notification,
    RejectionReason,
    SkillClass,
    Volunteer,
)
from app.services import events, haversine, notifications
from app.services.websocket_manager import ConnectionRegistry
from app.services.websocket_manager import registry as default_registry

logger = logging.getLogger(__name__)

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


async def dispatch_wave(
    session: AsyncSession,
    sos: SOS,
    registry: ConnectionRegistry | None = None,
) -> DispatchResult:
    """Evaluate every volunteer, alert the newly eligible, log every decision.

    Runs for every wave, not just the first. On an expanded radius (ADR-012)
    responders already holding an open alert are recorded `already_alerted`
    rather than alerted twice -- their alert is still live, and re-sending it
    would double-count them in the ADR-015 funnel.

    The registry is injectable so tests and the simulation harness can drive
    delivery without a real server; production passes the process-wide one.
    """
    registry = registry if registry is not None else default_registry
    wave_number = sos.wave_count + 1

    # Everyone already holding an open alert for this incident, from any
    # previous wave.
    already_alerted = set(
        (
            await session.execute(
                select(Notification.volunteer_id).where(Notification.sos_id == sos.id)
            )
        ).scalars()
    )

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

    # An otherwise-eligible responder who already holds an open alert is not a
    # new recipient. Applied after evaluation so the reason is recorded rather
    # than the person quietly skipped (invariant 4).
    evaluations = [
        events.Evaluation(
            volunteer_id=evaluation.volunteer_id,
            skill=evaluation.skill,
            skill_match=evaluation.skill_match,
            distance_m=evaluation.distance_m,
            outcome=DispatchOutcome.REJECTED,
            rejection_reason=RejectionReason.ALREADY_ALERTED,
        )
        if evaluation.is_selected and evaluation.volunteer_id in already_alerted
        else evaluation
        for evaluation in evaluations
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
    # Wave 1 ranks on declared skills alone; later waves rank against whatever
    # the AI call decided the emergency is, if it landed in time (ADR-013).
    candidates.sort(
        key=lambda c: haversine.rank_key(c.skill, c.distance_m)
        if wave_number == WAVE_ONE
        else haversine.rank_key_for_category(sos.ai_category, c.skill, c.distance_m)
    )

    deliveries = await notifications.deliver_alerts(
        session,
        sos=sos,
        wave_number=wave_number,
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
        wave_number=wave_number,
        radius_m=radius_m,
        evaluations=final_evaluations,
    )

    sos.wave_count = wave_number
    if wave_number == WAVE_ONE:
        # Isolates system latency from human latency in ADR-015. Set once wave 1
        # has been decided, which is the moment the engine's own work is done.
        sos.first_dispatch_at = datetime.now(UTC)

    await session.commit()

    return DispatchResult(
        sos=sos,
        candidates=candidates,
        evaluated_count=len(evaluations),
        alerted_count=len(candidates) - len(undeliverable),
    )


async def start_incident(
    session: AsyncSession,
    *,
    victim_id: int,
    lat: float,
    lng: float,
    description: str | None,
    registry: ConnectionRegistry | None = None,
) -> DispatchResult:
    """Create an incident, run wave 1, and arm its escalation task (Ch. 13 1-7).

    The escalation task is registered here rather than in the router because
    arming it is part of dispatching, not part of speaking HTTP -- and because
    every path that creates an incident must arm it, including the simulation
    harness.
    """
    # Local import: escalation imports this module to run subsequent waves.
    from app.services import escalation

    settings = get_settings()
    registry = registry if registry is not None else default_registry

    sos = await create_sos(
        session,
        victim_id=victim_id,
        lat=lat,
        lng=lng,
        description=description,
        radius_m=settings.base_radius_m,
    )
    result = await dispatch_wave(session, sos, registry=registry)

    # ADR-013: the AI call starts only AFTER wave 1 has gone out, and its result
    # is never awaited here. An emergency dispatch system that waits on a
    # third-party API before alerting anyone is contradicted by its own premise.
    asyncio.create_task(
        enrich_incident(sos.id, description=description, session_factory=get_session_factory())
    )

    task = asyncio.create_task(
        escalation.run_escalation(
            sos.id,
            session_factory=get_session_factory(),
            registry=registry,
            ladder=settings.radius_ladder_m,
            accept_timeout_seconds=settings.accept_timeout_seconds,
            # Condition A: nobody was alerted, so there is nothing to wait for.
            empty_first_wave=result.alerted_count == 0,
        )
    )
    escalation.tasks.register(sos.id, task)

    return result


async def enrich_incident(
    sos_id: int,
    *,
    description: str | None,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Attach the AI summary to an incident, out of band (ADR-013).

    Runs as its own task with its own session: the request that created the
    incident has already returned by the time this finishes, and its session is
    closed. Nothing downstream waits on this -- if it never completes, the
    incident simply keeps {unspecified, medium} and `ai_status` says why.
    """
    from app.services import ai_summary

    summary = await ai_summary.summarise(description)

    async with session_factory() as session:
        sos = await session.get(SOS, sos_id)
        if sos is None:
            return
        sos.ai_category = summary.category
        sos.ai_priority = summary.priority
        sos.ai_status = summary.status
        await session.commit()

    if summary.degraded:
        logger.info("sos %s ai degraded: %s", sos_id, summary.status.value)
