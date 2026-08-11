"""Escalation state machine -- ADR-012, invariant 3.

Both triggers are exercised independently, because the whole point of ADR-012 is
that there are two of them and each catches a failure the other misses:

  Condition A -- nobody is in range. Expanding immediately is right, because
  waiting for a timeout to confirm an emptiness we already measured burns
  seconds of an emergency.

  Condition B -- people were alerted and stayed silent. Expanding is right,
  because being alerted is not the same as responding, and assuming otherwise is
  the most unrealistic thing a dispatch system can do.

Timeouts are compressed to fractions of a second. The production value is 30s
(ADR-012); a test that actually waited 30 seconds would not get run.
"""

import asyncio

import pytest
from sqlalchemy import func, select

from app.models import SOS, DispatchEvent, EscalationTrigger, IncidentHistory, SOSStatus
from app.services import acceptance, escalation
from app.services.websocket_manager import ConnectionRegistry
from tests.factories import make_responder, make_sos, make_user

pytestmark = pytest.mark.asyncio

LADDER = (1000, 2000, 3000)
FAST_TIMEOUT = 0.25


class FakeSocket:
    """Accepts anything sent to it and remembers it."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000) -> None:
        pass


async def connected_registry(*user_ids: int) -> tuple[ConnectionRegistry, dict[int, FakeSocket]]:
    registry = ConnectionRegistry()
    sockets = {uid: FakeSocket() for uid in user_ids}
    for uid, socket in sockets.items():
        await registry.connect(uid, socket)  # type: ignore[arg-type]
    return registry, sockets


async def run_machine(session_factory, sos_id, registry, *, empty_first_wave, timeout=FAST_TIMEOUT):
    return asyncio.create_task(
        escalation.run_escalation(
            sos_id,
            session_factory=session_factory,
            registry=registry,
            ladder=LADDER,
            accept_timeout_seconds=timeout,
            empty_first_wave=empty_first_wave,
        )
    )


class TestConditionA:
    """Empty candidate set -> expand immediately, with no delay."""

    async def test_expands_without_waiting_for_the_timeout(self, session_factory):
        async with session_factory() as s:
            victim = await make_user(s, phone="+920000000000")
            # Only responder sits at 2.5km: outside 1km and 2km, inside 3km.
            far = await make_responder(s, phone="+921000000001", distance_m=2500.0)
            sos = await make_sos(s, victim_id=victim.id, wave_count=1)
            await s.commit()
            sos_id, far_id = sos.id, far.id

        registry, sockets = await connected_registry(far_id)

        started = asyncio.get_running_loop().time()
        task = await run_machine(session_factory, sos_id, registry, empty_first_wave=True,
                                 timeout=10.0)  # a timeout long enough to prove it is unused
        await asyncio.sleep(0.5)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        elapsed = asyncio.get_running_loop().time() - started

        async with session_factory() as s:
            stored = await s.get(SOS, sos_id)

        assert elapsed < 5.0, "condition A waited for the acceptance timeout"
        assert stored.current_radius_m == 3000, "should have walked past 2km to reach the responder"
        assert len(sockets[far_id].sent) == 1

    async def test_walks_the_whole_ladder_to_no_responder_found(self, session_factory):
        async with session_factory() as s:
            victim = await make_user(s, phone="+920000000001")
            # Far outside every rung.
            await make_responder(s, phone="+921000000002", distance_m=9000.0)
            sos = await make_sos(s, victim_id=victim.id, wave_count=1)
            await s.commit()
            sos_id = sos.id

        registry = ConnectionRegistry()
        task = await run_machine(session_factory, sos_id, registry, empty_first_wave=True)
        await asyncio.wait_for(task, timeout=10)

        async with session_factory() as s:
            stored = await s.get(SOS, sos_id)
            history = await s.scalar(
                select(IncidentHistory).where(IncidentHistory.sos_id == sos_id)
            )

        assert stored.status is SOSStatus.NO_RESPONDER_FOUND
        assert stored.current_radius_m == 3000
        assert history is not None, "terminal state must be recorded, not just reached"
        assert history.escalation_trigger is EscalationTrigger.EMPTY_SET
        assert history.response_time_seconds is None


class TestConditionB:
    """Alerted but silent -> expand after ACCEPT_TIMEOUT_SECONDS."""

    async def test_waits_for_the_timeout_before_expanding(self, session_factory):
        async with session_factory() as s:
            victim = await make_user(s, phone="+920000000002")
            near = await make_responder(s, phone="+922000000001", distance_m=500.0)
            sos = await make_sos(s, victim_id=victim.id, wave_count=1)
            await s.commit()
            sos_id, near_id = sos.id, near.id

        registry, _ = await connected_registry(near_id)
        task = await run_machine(session_factory, sos_id, registry, empty_first_wave=False,
                                 timeout=1.0)

        # Before the timeout elapses, nothing should have moved.
        await asyncio.sleep(0.4)
        async with session_factory() as s:
            mid = await s.get(SOS, sos_id)
        assert mid.current_radius_m == 1000, "expanded before the timeout"

        await asyncio.sleep(1.0)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        async with session_factory() as s:
            after = await s.get(SOS, sos_id)
        assert after.current_radius_m == 2000

    async def test_alerts_only_the_newly_included(self, session_factory):
        """Previously-alerted responders keep their open alert (ADR-012)."""
        async with session_factory() as s:
            victim = await make_user(s, phone="+920000000003")
            near = await make_responder(s, phone="+922000000002", distance_m=500.0)
            middle = await make_responder(s, phone="+922000000003", distance_m=1500.0)
            sos = await make_sos(s, victim_id=victim.id, wave_count=0)
            await s.commit()
            sos_id, near_id, middle_id = sos.id, near.id, middle.id

        registry, sockets = await connected_registry(near_id, middle_id)

        # Wave 1 at 1km reaches only the near responder.
        from app.services import dispatch

        async with session_factory() as s:
            sos = await s.get(SOS, sos_id)
            await dispatch.dispatch_wave(s, sos, registry=registry)

        assert len(sockets[near_id].sent) == 1
        assert len(sockets[middle_id].sent) == 0

        task = await run_machine(session_factory, sos_id, registry, empty_first_wave=False,
                                 timeout=FAST_TIMEOUT)
        await asyncio.sleep(0.6)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert len(sockets[middle_id].sent) == 1, "newly included responder was not alerted"
        assert len(sockets[near_id].sent) == 1, "already-alerted responder was alerted twice"

        async with session_factory() as s:
            already = await s.scalar(
                select(func.count())
                .select_from(DispatchEvent)
                .where(
                    DispatchEvent.sos_id == sos_id,
                    DispatchEvent.rejection_reason == "already_alerted",
                )
            )
        assert already >= 1, "re-inclusion must be recorded, not silently skipped"

    async def test_records_timeout_as_the_trigger(self, session_factory):
        async with session_factory() as s:
            victim = await make_user(s, phone="+920000000004")
            near = await make_responder(s, phone="+922000000004", distance_m=500.0)
            sos = await make_sos(s, victim_id=victim.id, wave_count=1)
            await s.commit()
            sos_id, near_id = sos.id, near.id

        registry, _ = await connected_registry(near_id)
        task = await run_machine(session_factory, sos_id, registry, empty_first_wave=False)
        await asyncio.wait_for(task, timeout=10)

        async with session_factory() as s:
            history = await s.scalar(
                select(IncidentHistory).where(IncidentHistory.sos_id == sos_id)
            )
        assert history.escalation_trigger is EscalationTrigger.TIMEOUT


class TestCancellationOnAcceptance:
    async def test_acceptance_stops_the_machine(self, session_factory):
        """An accepted incident must stop escalating (ADR-012).

        Otherwise the ladder keeps widening and alerts strangers to an emergency
        that already has help on the way.
        """
        async with session_factory() as s:
            victim = await make_user(s, phone="+920000000005")
            near = await make_responder(s, phone="+923000000001", distance_m=500.0)
            sos = await make_sos(s, victim_id=victim.id, wave_count=1)
            await s.commit()
            sos_id, near_id = sos.id, near.id

        registry, _ = await connected_registry(near_id)
        task = await run_machine(session_factory, sos_id, registry, empty_first_wave=False,
                                 timeout=1.0)
        escalation.tasks.register(sos_id, task)

        async with session_factory() as s:
            assert (await acceptance.accept(s, sos_id=sos_id, responder_id=near_id)).won

        assert escalation.tasks.cancel(sos_id) is True
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.sleep(1.2)  # past when the timeout would have fired

        async with session_factory() as s:
            stored = await s.get(SOS, sos_id)

        assert stored.status is SOSStatus.MATCHED
        assert stored.current_radius_m == 1000, "escalated after acceptance"

    async def test_machine_stops_on_its_own_if_status_moved(self, session_factory):
        """Belt and braces: even an uncancelled task refuses to escalate a
        non-pending incident, so a missed cancel cannot widen a matched one."""
        async with session_factory() as s:
            victim = await make_user(s, phone="+920000000006")
            near = await make_responder(s, phone="+923000000002", distance_m=500.0)
            sos = await make_sos(s, victim_id=victim.id, wave_count=1)
            await s.commit()
            sos_id, near_id = sos.id, near.id

        registry, _ = await connected_registry(near_id)
        async with session_factory() as s:
            await acceptance.accept(s, sos_id=sos_id, responder_id=near_id)

        task = await run_machine(session_factory, sos_id, registry, empty_first_wave=False)
        await asyncio.wait_for(task, timeout=10)

        async with session_factory() as s:
            stored = await s.get(SOS, sos_id)
        assert stored.current_radius_m == 1000


class TestLadder:
    async def test_next_radius_steps_upward(self):
        assert escalation.next_radius(1000, LADDER) == 2000
        assert escalation.next_radius(2000, LADDER) == 3000

    async def test_next_radius_is_none_at_the_top(self):
        assert escalation.next_radius(3000, LADDER) is None
