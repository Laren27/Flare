"""Radius expansion state machine -- ADR-012, invariant 3.

Two triggers, one machine:

  Condition A -- the candidate set at the current radius is empty. Expand
  immediately, with no delay. Waiting 30 seconds when the system already knows
  nobody is there wastes 30 seconds of an emergency.

  Condition B -- candidates were alerted and nobody accepted within
  ACCEPT_TIMEOUT_SECONDS. Expand and alert only the newly-included responders;
  everyone already alerted keeps their open alert.

Ladder 1km -> 2km -> 3km -> `no_responder_found`. The terminal state is real and
has real UI (invariant 5) -- it is not an error, it is the system saying so.

One background task per active incident, held in a registry so acceptance can
cancel it. Without the registry an accepted incident would keep escalating in
the background and alert responders to an emergency that already has help.
"""

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import SOS, EscalationTrigger, IncidentHistory, SOSStatus
from app.services.websocket_manager import ConnectionRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EscalationOutcome:
    """What one escalation step did, for tests and for the admin view."""

    wave_number: int
    radius_m: int
    trigger: EscalationTrigger
    newly_alerted: int
    terminal: bool


class TaskRegistry:
    """Live escalation tasks, keyed by incident."""

    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task] = {}

    def register(self, sos_id: int, task: asyncio.Task) -> None:
        self._tasks[sos_id] = task
        task.add_done_callback(lambda _: self._tasks.pop(sos_id, None))

    def cancel(self, sos_id: int) -> bool:
        """Cancel on acceptance (ADR-012). Returns whether anything was running."""
        task = self._tasks.pop(sos_id, None)
        if task is None or task.done():
            return False
        task.cancel()
        return True

    def is_running(self, sos_id: int) -> bool:
        task = self._tasks.get(sos_id)
        return task is not None and not task.done()

    @property
    def active_ids(self) -> set[int]:
        return set(self._tasks)


tasks = TaskRegistry()


def next_radius(current_radius_m: int, ladder: tuple[int, ...]) -> int | None:
    """The next rung above the current radius, or None at the top."""
    for rung in ladder:
        if rung > current_radius_m:
            return rung
    return None


async def escalate_once(
    session: AsyncSession,
    *,
    sos_id: int,
    trigger: EscalationTrigger,
    ladder: tuple[int, ...],
    registry: ConnectionRegistry,
    initial_trigger: EscalationTrigger | None = None,
) -> EscalationOutcome | None:
    """Advance one rung and alert the newly included. None if already settled.

    `initial_trigger` is what gets written to Incident History if the ladder
    runs out here -- see `_mark_exhausted` for why it is not `trigger`.
    """
    # Local import: dispatch imports this module for wave scheduling.
    from app.services import dispatch

    sos = await session.get(SOS, sos_id)
    if sos is None or sos.status is not SOSStatus.PENDING:
        return None

    upgraded = next_radius(sos.current_radius_m, ladder)

    if upgraded is None:
        await _mark_exhausted(session, sos, initial_trigger or trigger)
        return EscalationOutcome(
            wave_number=sos.wave_count,
            radius_m=sos.current_radius_m,
            trigger=trigger,
            newly_alerted=0,
            terminal=True,
        )

    sos.current_radius_m = upgraded
    result = await dispatch.dispatch_wave(session, sos, registry=registry)

    logger.info(
        "sos %s escalated to %sm on %s, %s newly alerted",
        sos_id, upgraded, trigger.value, result.alerted_count,
    )
    return EscalationOutcome(
        wave_number=result.sos.wave_count,
        radius_m=upgraded,
        trigger=trigger,
        newly_alerted=result.alerted_count,
        terminal=False,
    )


async def _mark_exhausted(
    session: AsyncSession, sos: SOS, trigger: EscalationTrigger
) -> None:
    """Ladder exhausted: an explicit terminal state, never a silent give-up.

    `trigger` is the condition that *started* this incident escalating, not the
    condition at the last rung. ADR-015 uses this field to separate a network
    that is too sparse from one that is merely unresponsive; recording the last
    trigger would file every incident as `empty_set`, since the final rung
    almost always finds nobody new -- including incidents where responders were
    alerted and ignored it, which is the opposite diagnosis.
    """
    sos.status = SOSStatus.NO_RESPONDER_FOUND

    existing = await session.scalar(
        select(IncidentHistory).where(IncidentHistory.sos_id == sos.id)
    )
    if existing is None:
        session.add(
            IncidentHistory(
                sos_id=sos.id,
                response_time_seconds=None,
                escalation_count=max(0, sos.wave_count - 1),
                final_radius_m=sos.current_radius_m,
                escalation_trigger=trigger,
            )
        )

    await session.commit()
    logger.info("sos %s reached no_responder_found at %sm", sos.id, sos.current_radius_m)


async def run_escalation(
    sos_id: int,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    registry: ConnectionRegistry,
    ladder: tuple[int, ...],
    accept_timeout_seconds: float,
    empty_first_wave: bool,
) -> None:
    """The per-incident background loop.

    Uses its own sessions rather than the request's: the request that created
    the incident returns long before this finishes, and its session is closed.

    Condition A skips the sleep entirely. That is the whole point of having two
    triggers -- an empty candidate set is already the answer, so waiting for a
    timeout to tell us again would be 30 wasted seconds.
    """
    trigger = EscalationTrigger.EMPTY_SET if empty_first_wave else EscalationTrigger.TIMEOUT
    # What made this incident start escalating, kept for Incident History.
    initial_trigger = trigger

    try:
        while True:
            if trigger is EscalationTrigger.TIMEOUT:
                await asyncio.sleep(accept_timeout_seconds)

            async with session_factory() as session:
                outcome = await escalate_once(
                    session,
                    sos_id=sos_id,
                    trigger=trigger,
                    ladder=ladder,
                    registry=registry,
                    initial_trigger=initial_trigger,
                )

            if outcome is None or outcome.terminal:
                return

            # After the first expansion, a wave that found nobody escalates
            # immediately again; a wave that alerted somebody waits for them.
            trigger = (
                EscalationTrigger.EMPTY_SET
                if outcome.newly_alerted == 0
                else EscalationTrigger.TIMEOUT
            )
    except asyncio.CancelledError:
        logger.info("escalation for sos %s cancelled (accepted)", sos_id)
        raise
