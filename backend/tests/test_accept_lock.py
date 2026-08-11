"""The accept-lock under concurrency -- ADR-010, ADR-011, invariant 1.

This is the project's headline correctness claim, and Chapter 21 is blunt about
why the test exists: a concurrency claim asserted without a test is not a claim,
it is a hope.

Each responder gets its **own session on its own connection**, because that is
the only way the race is real. Sharing one session would serialise the accepts
inside SQLAlchemy and the test would pass without proving anything about the
database at all -- the most dangerous kind of green test.
"""

import asyncio

import pytest
from sqlalchemy import select, text

from app.models import SOS, Notification, NotificationStatus, SOSStatus
from app.services import acceptance
from tests.factories import make_responder, make_sos, make_user

pytestmark = pytest.mark.asyncio

CONCURRENCY_LEVELS = [2, 10, 50]


async def _race(session_factory, sos_id: int, responder_ids: list[int]):
    """Fire every accept at once, each on its own connection."""

    async def attempt(responder_id: int):
        async with session_factory() as session:
            return await acceptance.accept(
                session, sos_id=sos_id, responder_id=responder_id
            )

    # A barrier would be tighter still, but gather already dispatches all N
    # coroutines before any of them completes its UPDATE round trip.
    return await asyncio.gather(*(attempt(rid) for rid in responder_ids))


@pytest.mark.parametrize("n", CONCURRENCY_LEVELS)
async def test_exactly_one_responder_wins(session_factory, n):
    """N concurrent accepts -> exactly 1 success, exactly N-1 already-handled."""
    async with session_factory() as setup:
        victim = await make_user(setup, phone="+910000000000")
        responders = [
            await make_responder(setup, phone=f"+9110000{i:05d}") for i in range(n)
        ]
        sos = await make_sos(setup, victim_id=victim.id)
        await setup.commit()
        sos_id, responder_ids = sos.id, [r.id for r in responders]

    results = await _race(session_factory, sos_id, responder_ids)

    winners = [r for r in results if r.won]
    losers = [r for r in results if not r.won]

    assert len(winners) == 1, f"expected exactly 1 winner at N={n}, got {len(winners)}"
    assert len(losers) == n - 1
    assert all(r.outcome is acceptance.AcceptOutcome.ALREADY_HANDLED for r in losers)


@pytest.mark.parametrize("n", CONCURRENCY_LEVELS)
async def test_database_agrees_with_the_winner(session_factory, n):
    """The row records one assignee, and it is the responder who was told they won."""
    async with session_factory() as setup:
        victim = await make_user(setup, phone="+910000000001")
        responders = [
            await make_responder(setup, phone=f"+9120000{i:05d}") for i in range(n)
        ]
        sos = await make_sos(setup, victim_id=victim.id)
        await setup.commit()
        sos_id, responder_ids = sos.id, [r.id for r in responders]

    results = await _race(session_factory, sos_id, responder_ids)
    winner = next(r for r in results if r.won)

    async with session_factory() as session:
        stored = await session.get(SOS, sos_id)
        assert stored.status is SOSStatus.MATCHED
        assert stored.accepted_by == winner.sos.accepted_by
        assert stored.accepted_by in responder_ids
        assert stored.matched_at is not None


async def test_second_accept_after_the_fact_is_refused(session_factory):
    """The lock holds across time, not only under simultaneous load."""
    async with session_factory() as setup:
        victim = await make_user(setup, phone="+910000000002")
        first = await make_responder(setup, phone="+911300000001")
        second = await make_responder(setup, phone="+911300000002")
        sos = await make_sos(setup, victim_id=victim.id)
        await setup.commit()
        sos_id, first_id, second_id = sos.id, first.id, second.id

    async with session_factory() as s:
        assert (await acceptance.accept(s, sos_id=sos_id, responder_id=first_id)).won

    async with session_factory() as s:
        later = await acceptance.accept(s, sos_id=sos_id, responder_id=second_id)

    assert later.outcome is acceptance.AcceptOutcome.ALREADY_HANDLED


async def test_losers_are_dismissed_not_left_pending(session_factory):
    """Every alerted responder ends in a terminal notification state.

    A loser left as `sent` would sit in the volunteer's UI as a live alert for
    an incident that already has help, and would count as un-actioned in the
    ADR-015 acceptance-rate metric.
    """
    n = 10
    async with session_factory() as setup:
        victim = await make_user(setup, phone="+910000000003")
        responders = [
            await make_responder(setup, phone=f"+9140000{i:05d}") for i in range(n)
        ]
        sos = await make_sos(setup, victim_id=victim.id)
        for responder in responders:
            setup.add(
                Notification(sos_id=sos.id, volunteer_id=responder.id, wave_number=1)
            )
        await setup.commit()
        sos_id, responder_ids = sos.id, [r.id for r in responders]

    await _race(session_factory, sos_id, responder_ids)

    async with session_factory() as session:
        rows = (
            await session.execute(
                select(Notification.status).where(Notification.sos_id == sos_id)
            )
        ).scalars().all()

    assert sum(s is NotificationStatus.ACCEPTED for s in rows) == 1
    assert sum(s is NotificationStatus.DISMISSED for s in rows) == n - 1
    assert NotificationStatus.SENT not in rows


async def test_accepting_a_missing_incident_is_not_found(session_factory):
    async with session_factory() as setup:
        responder = await make_responder(setup, phone="+911500000001")
        await setup.commit()
        responder_id = responder.id

    async with session_factory() as session:
        result = await acceptance.accept(session, sos_id=999_999, responder_id=responder_id)

    assert result.outcome is acceptance.AcceptOutcome.NOT_FOUND


async def test_the_lock_is_a_conditional_update_not_a_read(session_factory):
    """Guards the mechanism, not just the outcome (ADR-011).

    If someone later 'simplifies' accept() into a read-then-write, the race
    tests above might still pass on a fast machine. This one fails immediately,
    because it moves the status behind the caller's back after the row is read
    and before the accept is issued -- exactly the TOCTOU window a Python-level
    check would open.
    """
    async with session_factory() as setup:
        victim = await make_user(setup, phone="+910000000004")
        responder = await make_responder(setup, phone="+911600000001")
        sos = await make_sos(setup, victim_id=victim.id)
        await setup.commit()
        sos_id, responder_id = sos.id, responder.id

    async with session_factory() as observer:
        # Someone reads the incident and sees 'pending'.
        observed = await observer.get(SOS, sos_id)
        assert observed.status is SOSStatus.PENDING

        # It is claimed by another party on another connection.
        async with session_factory() as other:
            await other.execute(
                text("UPDATE sos SET status='matched', accepted_by=:r WHERE id=:i"),
                {"r": responder_id, "i": sos_id},
            )
            await other.commit()

        # The stale read must not authorise the write.
        result = await acceptance.accept(observer, sos_id=sos_id, responder_id=responder_id)

    assert result.outcome is acceptance.AcceptOutcome.ALREADY_HANDLED
