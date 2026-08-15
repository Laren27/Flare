"""Accept-lock and incident resolution -- ADR-011, invariant 1.

The lock is one conditional UPDATE. Nothing in this module reads the incident
status and then decides what to do about it, because that is a
time-of-check-to-time-of-use race: two responders can both read `pending` before
either writes, and both believe they won. The database decides, once, by
refusing to match a row whose status has already moved.

There is deliberately no `asyncio.Lock` here either. An in-process lock appears
to work and silently stops working the moment the app runs more than one worker,
which is the worst possible failure mode for a correctness claim.
"""

import enum
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SOS, Notification, NotificationStatus, SOSStatus


class AcceptOutcome(enum.StrEnum):
    WON = "won"
    ALREADY_HANDLED = "already_handled"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class AcceptResult:
    outcome: AcceptOutcome
    sos: SOS | None = None

    @property
    def won(self) -> bool:
        return self.outcome is AcceptOutcome.WON


async def accept(session: AsyncSession, *, sos_id: int, responder_id: int) -> AcceptResult:
    """Claim an incident. Exactly one caller can succeed, ever.

    The UPDATE of ADR-011, verbatim in intent:

        UPDATE sos SET status='matched', accepted_by=:rid, matched_at=now()
         WHERE id=:sos_id AND status='pending'

    `rowcount == 1` means this responder won. `0` means the WHERE matched
    nothing -- either another responder already moved the status, or there is no
    such incident. The two are distinguished afterwards, by a read that is now
    safe because it no longer decides anything.
    """
    result = await session.execute(
        update(SOS)
        .where(SOS.id == sos_id, SOS.status == SOSStatus.PENDING)
        .values(
            status=SOSStatus.MATCHED,
            accepted_by=responder_id,
            matched_at=func.now(),
        )
    )

    if result.rowcount == 1:
        await _mark_notification(session, sos_id=sos_id, responder_id=responder_id,
                                 status=NotificationStatus.ACCEPTED)
        await session.commit()
        sos = await session.get(SOS, sos_id)
        return AcceptResult(outcome=AcceptOutcome.WON, sos=sos)

    # Lost, or never existed. Reading now is safe: the answer no longer gates a
    # write, it only decides which message this responder is shown.
    sos = await session.get(SOS, sos_id)
    if sos is None:
        await session.rollback()
        return AcceptResult(outcome=AcceptOutcome.NOT_FOUND)

    await _mark_notification(session, sos_id=sos_id, responder_id=responder_id,
                             status=NotificationStatus.DISMISSED)
    await session.commit()
    return AcceptResult(outcome=AcceptOutcome.ALREADY_HANDLED, sos=sos)


async def decline(session: AsyncSession, *, sos_id: int, responder_id: int) -> bool:
    """Record a decline. Does not touch incident status -- a decline is one
    responder's answer, not the incident's."""
    updated = await _mark_notification(
        session, sos_id=sos_id, responder_id=responder_id, status=NotificationStatus.DECLINED
    )
    await session.commit()
    return updated


async def cancel(session: AsyncSession, *, sos_id: int) -> SOS | None:
    """Withdraw an incident (ADR-025). Returns None if it cannot be cancelled.

    Reachable from `pending` -- triggered by accident, or the situation resolved
    itself -- and from `matched`, where a responder is already on the way and
    needs the incident to stop being live. Terminal states are refused: there is
    nothing left to withdraw.

    Writes no `IncidentHistory` row. That table records how the *system*
    concluded an incident; a citizen changing their mind is not a conclusion the
    system produced, and manufacturing a response time for one would put a
    number into the ADR-015 distribution that describes nobody's rescue.

    The caller cancels the escalation task. That is the router's job for the
    same reason it is on acceptance -- the task registry is process state, not
    database state.
    """
    sos = await session.get(SOS, sos_id)
    if sos is None or sos.status not in {SOSStatus.PENDING, SOSStatus.MATCHED}:
        return None

    sos.status = SOSStatus.CANCELLED
    sos.resolved_at = datetime.now(UTC)

    # Any responder still holding an open alert is told it is over by the same
    # mechanism that tells them somebody else won: their notification stops
    # being `sent`. Without this the alert would sit open for an incident that
    # no longer exists.
    await session.execute(
        update(Notification)
        .where(
            Notification.sos_id == sos_id,
            Notification.status == NotificationStatus.SENT,
        )
        .values(status=NotificationStatus.DISMISSED, responded_at=func.now())
    )

    await session.commit()
    return sos


async def resolve(session: AsyncSession, *, sos_id: int) -> SOS | None:
    """Close a matched incident and write its Incident History row (Ch. 13 step 10)."""
    from app.models import EscalationTrigger, IncidentHistory

    sos = await session.get(SOS, sos_id)
    if sos is None or sos.status is not SOSStatus.MATCHED:
        return None

    now = datetime.now(UTC)
    sos.status = SOSStatus.RESOLVED
    sos.resolved_at = now

    response_time = None
    if sos.matched_at is not None:
        response_time = int((sos.matched_at - sos.created_at).total_seconds())

    existing = await session.scalar(
        select(IncidentHistory).where(IncidentHistory.sos_id == sos_id)
    )
    if existing is None:
        session.add(
            IncidentHistory(
                sos_id=sos_id,
                response_time_seconds=response_time,
                # wave_count counts waves; escalations are the waves after the first.
                escalation_count=max(0, sos.wave_count - 1),
                final_radius_m=sos.current_radius_m,
                escalation_trigger=EscalationTrigger.NONE
                if sos.wave_count <= 1
                else EscalationTrigger.TIMEOUT,
                resolved_at=now,
            )
        )
    else:
        existing.response_time_seconds = response_time
        existing.resolved_at = now

    await session.commit()
    return sos


async def _mark_notification(
    session: AsyncSession, *, sos_id: int, responder_id: int, status: NotificationStatus
) -> bool:
    result = await session.execute(
        update(Notification)
        .where(
            Notification.sos_id == sos_id,
            Notification.volunteer_id == responder_id,
            Notification.status == NotificationStatus.SENT,
        )
        .values(status=status, responded_at=func.now())
    )
    return result.rowcount > 0
