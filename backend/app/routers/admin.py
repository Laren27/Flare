"""Admin router (Ch. 14). Admin-only, enforced by the role dependency."""

from typing import Any

from fastapi import APIRouter, Depends, Query, status

from fastapi import HTTPException

from app.dependencies import DbSession, require_role
from app.models import SOS, UserRole
from app.services import analytics, incidents as incident_service

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    # Applied at the router, not per-route: a new admin endpoint should be
    # protected by existing, not by remembering to add a decorator.
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)


@router.get("/analytics")
async def get_analytics(
    session: DbSession,
    window_days: int = Query(default=analytics.DEFAULT_WINDOW_DAYS, ge=1, le=365),
) -> dict[str, Any]:
    """Every Chapter 18A metric, each labelled with the query file behind it.

    The `query_file` on each metric is not decoration. Ch. 18A requires every
    figure on screen to be traceable to a named query, and shipping the filename
    with the data is what makes that checkable from the dashboard itself.
    """
    metrics = await analytics.dashboard(session, window_days=window_days)

    return {
        "window_days": window_days,
        "metrics": {
            name: {"query_file": m.query_file, "rows": m.rows}
            for name, m in metrics.items()
        },
    }


@router.get("/incidents")
async def list_incidents(
    session: DbSession,
    limit: int = Query(default=25, ge=1, le=200),
) -> list[dict[str, Any]]:
    """Recent incidents, newest first, for the active-incidents panel."""
    from sqlalchemy import select

    rows = await session.execute(
        select(SOS).order_by(SOS.created_at.desc()).limit(limit)
    )

    return [
        {
            "id": sos.id,
            "status": sos.status.value,
            "lat": sos.lat,
            "lng": sos.lng,
            "current_radius_m": sos.current_radius_m,
            "wave_count": sos.wave_count,
            "ai_category": sos.ai_category,
            "ai_status": sos.ai_status.value,
            "created_at": sos.created_at.isoformat(),
            "matched_at": sos.matched_at.isoformat() if sos.matched_at else None,
        }
        for sos in rows.scalars()
    ]


@router.get("/incidents/{sos_id}")
async def get_incident(sos_id: int, session: DbSession) -> dict[str, Any]:
    """One incident and every dispatch decision made about it (ADR-014).

    This is the endpoint behind the answer to "why wasn't responder X alerted?".
    Every candidate the engine evaluated appears, selected or rejected, with the
    reason — invariant 4 says nothing is filtered silently, and this is where
    that promise becomes visible rather than merely kept.
    """
    detail = await incident_service.get_detail(session, sos_id=sos_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such incident"
        )
    return detail


@router.get("/queries", status_code=status.HTTP_200_OK)
async def list_queries() -> dict[str, list[str]]:
    """The traceability index: every query file the analytics layer can run."""
    return {"queries": analytics.available_queries()}
