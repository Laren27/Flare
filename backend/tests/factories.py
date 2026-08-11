"""Minimal object builders for the database-backed tests."""

import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SOS, Location, SkillClass, SOSStatus, User, UserRole, Volunteer

EARTH_RADIUS_M = 6_371_008.8
INCIDENT_LAT, INCIDENT_LNG = 12.9716, 77.5946


def north_of(metres: float, lat: float = INCIDENT_LAT, lng: float = INCIDENT_LNG):
    """Exact on a sphere along a meridian, so the distance is precisely `metres`."""
    return lat + math.degrees(metres / EARTH_RADIUS_M), lng


async def make_user(
    session: AsyncSession, *, phone: str, role: UserRole = UserRole.VOLUNTEER, name: str = "T"
) -> User:
    user = User(name=name, phone=phone, role=role, password_hash="x" * 60)
    session.add(user)
    await session.flush()
    return user


async def make_responder(
    session: AsyncSession,
    *,
    phone: str,
    distance_m: float | None = 500.0,
    skill: SkillClass = SkillClass.CPR,
    verified: bool = True,
    available: bool = True,
) -> User:
    user = await make_user(session, phone=phone, name=f"R{phone[-4:]}")
    session.add(
        Volunteer(user_id=user.id, verified=verified, skills=skill, availability=available)
    )
    if distance_m is not None:
        lat, lng = north_of(distance_m)
        session.add(Location(user_id=user.id, lat=lat, lng=lng))
    await session.flush()
    return user


async def make_sos(
    session: AsyncSession, *, victim_id: int, radius_m: int = 1000, wave_count: int = 0
) -> SOS:
    sos = SOS(
        victim_id=victim_id,
        lat=INCIDENT_LAT,
        lng=INCIDENT_LNG,
        description="test incident",
        status=SOSStatus.PENDING,
        current_radius_m=radius_m,
        wave_count=wave_count,
    )
    session.add(sos)
    await session.flush()
    return sos
