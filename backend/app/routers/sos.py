"""SOS router (Ch. 14). Thin by construction -- the dispatch decisions live in
`app.services.dispatch` (Ch. 20)."""

from fastapi import APIRouter, status

from app.config import get_settings
from app.dependencies import CurrentUser, DbSession
from app.schemas import CandidateOut, SOSCreateRequest, SOSCreateResponse
from app.services import dispatch

router = APIRouter(prefix="/sos", tags=["sos"])


@router.post("", response_model=SOSCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_sos(
    payload: SOSCreateRequest, user: CurrentUser, session: DbSession
) -> SOSCreateResponse:
    """Create an incident and run wave 1 candidate selection.

    Any authenticated user may trigger an SOS -- a volunteer can be the victim,
    and requiring the citizen role would refuse the emergency to prove a point.
    """
    sos = await dispatch.create_sos(
        session,
        victim_id=user.id,
        lat=payload.lat,
        lng=payload.lng,
        description=payload.description,
        radius_m=get_settings().base_radius_m,
    )

    result = await dispatch.dispatch_wave_one(session, sos)

    return SOSCreateResponse(
        id=result.sos.id,
        status=result.sos.status,
        current_radius_m=result.sos.current_radius_m,
        wave_count=result.sos.wave_count,
        created_at=result.sos.created_at,
        first_dispatch_at=result.sos.first_dispatch_at,
        candidates=[CandidateOut.model_validate(c) for c in result.candidates],
        evaluated_count=result.evaluated_count,
    )
