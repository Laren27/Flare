"""Incident updates pushed over the socket -- ADR-027.

Two audiences, and they need different things.

The **victim** needs to know what their incident is doing: somebody accepted,
the search widened, it ended. They get a full status snapshot on every event,
the same fields `GET /sos/{id}` returns, because the socket has no replay and a
client that missed an event must not have to reconstruct state from a diff it
never saw.

Every **volunteer still holding an open alert** needs to know when the incident
stops being available. That is the sharper of the two: until this existed, a
responder learned their alert was dead by pressing ACCEPT and losing.

Delivery is best-effort, exactly as alert delivery is. A socket that is down
misses the frame, and the responder finds out on their next accept attempt --
the path that already existed. This removes the wait; it does not replace the
guarantee.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SOS, Notification, NotificationStatus
from app.services.websocket_manager import ConnectionRegistry
from app.services.websocket_manager import registry as default_registry

logger = logging.getLogger(__name__)

# What the victim's client listens for. Distinct names even though the payload
# is uniform: the citizen view reacts differently to each -- an escalation must
# not clear the map, an acceptance must -- and branching on a name reads better
# than branching on a status field (ADR-027).
MATCHED = "sos_matched"
ESCALATED = "sos_escalated"
RESOLVED = "sos_resolved"
CANCELLED = "sos_cancelled"
NO_RESPONDER = "sos_no_responder"

ALERT_CLOSED = "alert_closed"


def incident_snapshot(sos: SOS) -> dict[str, Any]:
    """The same shape as SOSStatusResponse, so the client renders one way.

    Deliberately identical to what the reconciliation fetch returns: a snapshot
    that arrives over the socket and one that arrives over HTTP must not need
    two code paths to apply, or the rarely-exercised one rots.
    """
    return {
        "id": sos.id,
        "status": sos.status.value,
        "current_radius_m": sos.current_radius_m,
        "wave_count": sos.wave_count,
        "created_at": sos.created_at.isoformat(),
        "first_dispatch_at": sos.first_dispatch_at.isoformat() if sos.first_dispatch_at else None,
        "matched_at": sos.matched_at.isoformat() if sos.matched_at else None,
        "resolved_at": sos.resolved_at.isoformat() if sos.resolved_at else None,
        "accepted_by": sos.accepted_by,
        "ai_category": sos.ai_category,
        "ai_priority": sos.ai_priority.value if sos.ai_priority else None,
        "ai_status": sos.ai_status.value,
    }


async def notify_victim(
    sos: SOS, *, event: str, registry: ConnectionRegistry | None = None
) -> bool:
    """Push one incident event to whoever raised it."""
    registry = registry if registry is not None else default_registry
    payload = {"type": event, **incident_snapshot(sos)}
    delivered = await registry.send(sos.victim_id, payload)
    if not delivered:
        # Not an error. The citizen may have closed the tab, and the
        # reconciliation fetch on their next connect will catch them up.
        logger.info("no live socket for victim %s of sos %s", sos.victim_id, sos.id)
    return delivered


async def close_alerts_for(
    volunteer_ids: list[int],
    *,
    sos_id: int,
    reason: str,
    registry: ConnectionRegistry | None = None,
) -> int:
    """Push `alert_closed` to an explicit list of responders.

    Exists because cancellation dismisses the open notifications as part of the
    same transaction that ends the incident, so by the time the push happens
    there is no longer a record of who was waiting. The recipients are captured
    before that update and handed here.
    """
    registry = registry if registry is not None else default_registry
    payload = {"type": ALERT_CLOSED, "sos_id": sos_id, "reason": reason}

    delivered = 0
    for volunteer_id in volunteer_ids:
        if await registry.send(volunteer_id, payload):
            delivered += 1

    if volunteer_ids:
        logger.info(
            "sos %s closed (%s): told %s of %s open alerts",
            sos_id, reason, delivered, len(volunteer_ids),
        )
    return delivered


async def close_open_alerts(
    session: AsyncSession,
    sos: SOS,
    *,
    reason: str,
    exclude: int | None = None,
    registry: ConnectionRegistry | None = None,
) -> int:
    """Tell every responder still holding an open alert that it is over.

    `exclude` is the responder who caused it -- the one who accepted already has
    their answer from the accept response, and telling them their own alert was
    closed would be confusing rather than informative.

    Reads Notifications rather than re-deriving who was alerted: that table is
    the record of what was actually delivered, and re-computing candidates here
    would re-answer a question the dispatch already settled.
    """
    registry = registry if registry is not None else default_registry

    volunteer_ids = (
        await session.execute(
            select(Notification.volunteer_id).where(
                Notification.sos_id == sos.id,
                Notification.status == NotificationStatus.SENT,
            )
        )
    ).scalars().all()

    payload = {"type": ALERT_CLOSED, "sos_id": sos.id, "reason": reason}
    delivered = 0

    for volunteer_id in volunteer_ids:
        if volunteer_id == exclude:
            continue
        if await registry.send(volunteer_id, payload):
            delivered += 1

    if volunteer_ids:
        logger.info(
            "sos %s closed (%s): told %s of %s open alerts",
            sos.id, reason, delivered, len(volunteer_ids),
        )
    return delivered
