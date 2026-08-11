"""SOS router (Ch. 14). Thin by construction -- the dispatch decisions live in
`app.services.dispatch`, `acceptance` and `escalation` (Ch. 20)."""

from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession
from app.models import SOS, UserRole
from app.schemas import (
    AcceptResponse,
    CandidateOut,
    SOSCreateRequest,
    SOSCreateResponse,
    SOSStatusResponse,
)
from app.services import acceptance, dispatch, escalation

router = APIRouter(prefix="/sos", tags=["sos"])


@router.post("", response_model=SOSCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_sos(
    payload: SOSCreateRequest, user: CurrentUser, session: DbSession
) -> SOSCreateResponse:
    """Create an incident, run wave 1, and arm its escalation task.

    Any authenticated user may trigger an SOS -- a volunteer can be the victim,
    and requiring the citizen role would refuse the emergency to prove a point.
    """
    result = await dispatch.start_incident(
        session,
        victim_id=user.id,
        lat=payload.lat,
        lng=payload.lng,
        description=payload.description,
    )

    return SOSCreateResponse(
        id=result.sos.id,
        status=result.sos.status,
        current_radius_m=result.sos.current_radius_m,
        wave_count=result.sos.wave_count,
        created_at=result.sos.created_at,
        first_dispatch_at=result.sos.first_dispatch_at,
        candidates=[CandidateOut.model_validate(c) for c in result.candidates],
        evaluated_count=result.evaluated_count,
        alerted_count=result.alerted_count,
    )


@router.get("/{sos_id}", response_model=SOSStatusResponse)
async def get_sos(sos_id: int, user: CurrentUser, session: DbSession) -> SOSStatusResponse:
    sos = await session.get(SOS, sos_id)
    if sos is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such incident")

    # The victim, the assigned responder, and admins. A responder still deciding
    # whether to accept already has what they need from the alert payload.
    permitted = {sos.victim_id, sos.accepted_by}
    if user.id not in permitted and user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your incident")

    return SOSStatusResponse.model_validate(sos)


@router.post("/{sos_id}/accept", response_model=AcceptResponse)
async def accept_sos(sos_id: int, user: CurrentUser, session: DbSession) -> AcceptResponse:
    """Claim an incident. Exactly one responder can win (ADR-011).

    Losing returns 200, not an error status: being second is a normal outcome of
    a race, not a client mistake, and the volunteer UI shows it as its own
    "already handled" state.
    """
    result = await acceptance.accept(session, sos_id=sos_id, responder_id=user.id)

    if result.outcome is acceptance.AcceptOutcome.NOT_FOUND:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such incident")

    if result.won:
        # Cancel before returning: an accepted incident that keeps escalating
        # would alert strangers to an emergency that already has help (ADR-012).
        escalation.tasks.cancel(sos_id)

    assert result.sos is not None
    return AcceptResponse(
        accepted=result.won,
        sos_id=sos_id,
        status=result.sos.status,
        detail="Assigned to you" if result.won else "Another responder already accepted",
    )


@router.post("/{sos_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
async def decline_sos(sos_id: int, user: CurrentUser, session: DbSession) -> None:
    """Record a decline. Does not change incident status -- one responder
    declining is not the incident being declined."""
    await acceptance.decline(session, sos_id=sos_id, responder_id=user.id)


@router.post("/{sos_id}/resolve", response_model=SOSStatusResponse)
async def resolve_sos(sos_id: int, user: CurrentUser, session: DbSession) -> SOSStatusResponse:
    sos = await session.get(SOS, sos_id)
    if sos is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such incident")

    if user.id not in {sos.victim_id, sos.accepted_by} and user.role is not UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your incident")

    resolved = await acceptance.resolve(session, sos_id=sos_id)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a matched incident can be resolved",
        )

    return SOSStatusResponse.model_validate(resolved)
