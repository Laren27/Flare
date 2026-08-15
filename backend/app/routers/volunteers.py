"""Volunteer router (Ch. 14). Thin -- the coupling rule lives in the service.

Gated at the router on the volunteer role, so a new endpoint here is protected
by existing rather than by remembering a decorator, the same argument the admin
router makes.

`POST /volunteers/register` is listed in Chapter 14 and is not built: skills are
set at signup and editing them has no interface yet. It is absent rather than
stubbed, because a route that accepts a request and does nothing is worse than
one that is honestly missing.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import CurrentUser, DbSession, require_role
from app.models import UserRole
from app.schemas import AvailabilityRequest, VolunteerOut
from app.services import volunteers as volunteer_service

router = APIRouter(
    prefix="/volunteers",
    tags=["volunteers"],
    dependencies=[Depends(require_role(UserRole.VOLUNTEER))],
)


@router.get("/me", response_model=VolunteerOut)
async def get_me(user: CurrentUser, session: DbSession) -> VolunteerOut:
    """The caller's own volunteer record, including where the engine last had them."""
    state = await volunteer_service.get_state(session, user_id=user.id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No volunteer record"
        )
    return VolunteerOut.model_validate(state)


@router.patch("/availability", response_model=VolunteerOut)
async def set_availability(
    payload: AvailabilityRequest, user: CurrentUser, session: DbSession
) -> VolunteerOut:
    """Go on or off duty. Going online carries a position (ADR-026).

    A volunteer marked available with no position would be rejected at every
    dispatch as `no_location` while their own screen said they were visible to
    people nearby. Refusing the request is the only answer that keeps the
    record and the interface saying the same thing.
    """
    try:
        state = await volunteer_service.set_availability(
            session,
            user_id=user.id,
            available=payload.available,
            lat=payload.lat,
            lng=payload.lng,
        )
    except volunteer_service.PositionRequired:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Going online needs your location — the engine cannot dispatch without it",
        ) from None

    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No volunteer record"
        )

    return VolunteerOut.model_validate(state)
