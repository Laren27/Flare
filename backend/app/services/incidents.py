"""Incident detail for the admin view -- the reader ADR-014 was written for.

`DispatchEvents` records why every candidate was or was not selected, and until
now nothing read it back. That made the answer to "why didn't responder X get
alerted?" a shrug in front of a table that already knew, which is the one
question this log exists to answer.

Everything here is a read. The per-wave rollup is computed rather than stored,
exactly as Chapter 12 says it should be: `wave_number` and `radius_m_at_eval`
are on every event row, so both are a GROUP BY away and neither needs a column
of its own.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    SOS,
    DispatchEvent,
    IncidentHistory,
    Notification,
    User,
)


def _seconds_between(later: Any, earlier: Any) -> float | None:
    if later is None or earlier is None:
        return None
    return (later - earlier).total_seconds()


async def get_detail(session: AsyncSession, *, sos_id: int) -> dict[str, Any] | None:
    """One incident, its dispatch decisions, and the outcome of each alert.

    Returns None when there is no such incident, so the router can answer 404
    rather than an empty body that reads as "no decisions were made".
    """
    sos = await session.get(SOS, sos_id)
    if sos is None:
        return None

    history = await session.scalar(
        select(IncidentHistory).where(IncidentHistory.sos_id == sos_id)
    )

    # Volunteer names come along because the question this page answers is about
    # a person, not an id. Admin-only endpoint, and an admin already sees
    # volunteer identities in the verification queue.
    event_rows = (
        await session.execute(
            select(DispatchEvent, User.name)
            .join(User, User.id == DispatchEvent.volunteer_id)
            .where(DispatchEvent.sos_id == sos_id)
            .order_by(
                DispatchEvent.wave_number,
                # Selected first, then by how close they were -- the reading
                # order for "who did we pick, and who was next".
                DispatchEvent.outcome,
                DispatchEvent.distance_m,
            )
        )
    ).all()

    events = [
        {
            "volunteer_id": event.volunteer_id,
            "volunteer_name": name,
            "wave_number": event.wave_number,
            "radius_m_at_eval": event.radius_m_at_eval,
            "distance_m": event.distance_m,
            "skill_match": event.skill_match,
            "outcome": event.outcome.value,
            "rejection_reason": event.rejection_reason.value if event.rejection_reason else None,
            "evaluated_at": event.evaluated_at.isoformat(),
        }
        for event, name in event_rows
    ]

    notification_rows = (
        await session.execute(
            select(Notification, User.name)
            .join(User, User.id == Notification.volunteer_id)
            .where(Notification.sos_id == sos_id)
            .order_by(Notification.wave_number, Notification.sent_at)
        )
    ).all()

    notifications = [
        {
            "volunteer_id": n.volunteer_id,
            "volunteer_name": name,
            "wave_number": n.wave_number,
            "status": n.status.value,
            "sent_at": n.sent_at.isoformat(),
            "responded_at": n.responded_at.isoformat() if n.responded_at else None,
        }
        for n, name in notification_rows
    ]

    # Per-wave rollup. Chapter 12 keeps this derived rather than stored.
    waves: dict[int, dict[str, Any]] = {}
    for event in events:
        wave = waves.setdefault(
            event["wave_number"],
            {
                "wave_number": event["wave_number"],
                "radius_m": event["radius_m_at_eval"],
                "evaluated": 0,
                "alerted": 0,
                "rejections": {},
            },
        )
        wave["evaluated"] += 1
        if event["outcome"] == "alerted":
            wave["alerted"] += 1
        else:
            reason = event["rejection_reason"] or "unspecified"
            wave["rejections"][reason] = wave["rejections"].get(reason, 0) + 1

    return {
        "incident": {
            "id": sos.id,
            "status": sos.status.value,
            "lat": sos.lat,
            "lng": sos.lng,
            "description": sos.description,
            "current_radius_m": sos.current_radius_m,
            "wave_count": sos.wave_count,
            "ai_category": sos.ai_category,
            "ai_priority": sos.ai_priority.value if sos.ai_priority else None,
            "ai_status": sos.ai_status.value,
            "created_at": sos.created_at.isoformat(),
            "first_dispatch_at": sos.first_dispatch_at.isoformat() if sos.first_dispatch_at else None,
            "matched_at": sos.matched_at.isoformat() if sos.matched_at else None,
            "resolved_at": sos.resolved_at.isoformat() if sos.resolved_at else None,
            "accepted_by": sos.accepted_by,
        },
        # The funnel timestamps as intervals, so the page does not have to
        # re-derive what the analytics layer already defines this way.
        "timings": {
            "to_first_dispatch_seconds": _seconds_between(sos.first_dispatch_at, sos.created_at),
            "to_acceptance_seconds": _seconds_between(sos.matched_at, sos.created_at),
            "to_resolution_seconds": _seconds_between(sos.resolved_at, sos.created_at),
        },
        "history": None
        if history is None
        else {
            "response_time_seconds": history.response_time_seconds,
            "escalation_count": history.escalation_count,
            "final_radius_m": history.final_radius_m,
            "escalation_trigger": history.escalation_trigger.value,
            "resolved_at": history.resolved_at.isoformat() if history.resolved_at else None,
        },
        "waves": [waves[key] for key in sorted(waves)],
        "events": events,
        "notifications": notifications,
    }
