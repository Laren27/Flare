"""Volunteer availability and position (Ch. 14, ADR-026).

The two are one operation here, deliberately. ADR-021 rejects a verified,
available volunteer with no `Locations` row as `no_location`, so availability
without a position produces a volunteer who believes they are on duty and is
never a candidate for anything. Keeping the write together means that state is
not reachable through this service at all.

Nothing in this module talks to the dispatch engine. A volunteer coming online
does not trigger a re-evaluation of incidents already in flight: the escalation
state machine re-queries every volunteer on each wave (ADR-012), so somebody who
comes online mid-incident is picked up by the next wave without being pushed at.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Location, Volunteer


class PositionRequired(Exception):
    """Raised when a volunteer tries to go online without coordinates."""


@dataclass(frozen=True, slots=True)
class VolunteerState:
    """What the volunteer record and its position say, together."""

    user_id: int
    verified: bool
    skills: str
    availability: bool
    lat: float | None
    lng: float | None
    location_updated_at: datetime | None


async def get_state(session: AsyncSession, *, user_id: int) -> VolunteerState | None:
    """The volunteer row joined to its latest position, or None if not a volunteer."""
    row = (
        await session.execute(
            select(
                Volunteer.user_id,
                Volunteer.verified,
                Volunteer.skills,
                Volunteer.availability,
                Location.lat,
                Location.lng,
                Location.updated_at,
            )
            # Outer join: a volunteer who has never been online has no Locations
            # row, and that is a state worth reporting rather than a reason to
            # return nothing.
            .outerjoin(Location, Location.user_id == Volunteer.user_id)
            .where(Volunteer.user_id == user_id)
        )
    ).first()

    if row is None:
        return None

    user_id_, verified, skills, availability, lat, lng, updated_at = row
    return VolunteerState(
        user_id=user_id_,
        verified=verified,
        skills=skills,
        availability=availability,
        lat=lat,
        lng=lng,
        location_updated_at=updated_at,
    )


async def set_availability(
    session: AsyncSession,
    *,
    user_id: int,
    available: bool,
    lat: float | None,
    lng: float | None,
) -> VolunteerState | None:
    """Toggle availability, publishing a position when going online (ADR-026).

    Going online without coordinates raises `PositionRequired`. That is the
    invariant this service exists to hold: the engine cannot dispatch to a
    volunteer it has no position for, so recording one as available without a
    position would be recording something the system cannot act on.

    Going offline deliberately does NOT clear the stored position. The row is
    the last place we knew the volunteer to be, and deleting it would make a
    volunteer who goes offline and back online briefly invisible; the dispatch
    engine already excludes them on `availability` alone, so keeping it costs
    nothing and removes a race.
    """
    volunteer = await session.get(Volunteer, user_id)
    if volunteer is None:
        return None

    if available and (lat is None or lng is None):
        raise PositionRequired

    if lat is not None and lng is not None:
        location = await session.get(Location, user_id)
        if location is None:
            session.add(Location(user_id=user_id, lat=lat, lng=lng))
        else:
            location.lat = lat
            location.lng = lng

    volunteer.availability = available
    await session.commit()

    return await get_state(session, user_id=user_id)
