"""Analytics layer -- ADR-015, Ch. 18A.

Every figure the dashboard renders is the result of executing a named `.sql`
file from `analytics/queries/`. Chapter 18A's rule is explicit: if a number on
screen cannot be traced to a query file, it does not ship. So the SQL lives in
files rather than in Python string literals, and this module is only a loader
and a runner.

That has a second benefit worth stating: the queries are readable, runnable and
reviewable without the application. Someone can open a psql prompt, paste
`coverage_gap.sql`, and check the number themselves -- which is the difference
between a dashboard that reports and a dashboard that can be audited.

No separate BI tool, no pipeline, no warehouse. The operational tables are the
source (Ch. 18A).
"""

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

QUERY_DIR = Path(__file__).resolve().parents[3] / "analytics" / "queries"

DEFAULT_WINDOW_DAYS = 30
# ~500m of latitude in degrees. Named here rather than buried in the SQL so the
# grid resolution is one number, in one place, if it ever needs changing.
DEFAULT_BUCKET_DEG = 0.0045


@dataclass(frozen=True, slots=True)
class Metric:
    """One metric, with the file that produced it (Ch. 18A traceability)."""

    name: str
    query_file: str
    rows: list[dict[str, Any]] = field(default_factory=list)


@lru_cache
def load_query(name: str) -> str:
    """Read a query file. Cached -- the files do not change at runtime."""
    path = QUERY_DIR / f"{name}.sql"
    if not path.is_file():
        raise FileNotFoundError(f"no analytics query named {name!r} at {path}")
    return path.read_text(encoding="utf-8")


async def run_query(
    session: AsyncSession, name: str, **params: Any
) -> list[dict[str, Any]]:
    result = await session.execute(text(load_query(name)), params)
    return [dict(row) for row in result.mappings()]


async def metric(session: AsyncSession, name: str, **params: Any) -> Metric:
    """Run one metric, returning its rows alongside the file that produced them.

    A failing query degrades to an empty metric rather than a 500. A dashboard
    that renders six of seven panels and says so is more useful during a demo
    than one that shows nothing because a single query broke.
    """
    try:
        rows = await run_query(session, name, **params)
    except Exception as exc:
        logger.warning("analytics query %s failed: %s", name, exc)
        rows = []
    return Metric(name=name, query_file=f"analytics/queries/{name}.sql", rows=rows)


async def dashboard(
    session: AsyncSession,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    bucket_deg: float = DEFAULT_BUCKET_DEG,
) -> dict[str, Metric]:
    """Every metric the admin dashboard needs, in one round of queries."""
    window = {"window_days": window_days}

    return {
        "time_to_acceptance": await metric(session, "time_to_acceptance", **window),
        "time_to_acceptance_histogram": await metric(
            session, "time_to_acceptance_histogram", **window
        ),
        "time_to_first_dispatch": await metric(session, "time_to_first_dispatch", **window),
        "dispatch_funnel": await metric(session, "dispatch_funnel", **window),
        "coverage_gap": await metric(
            session, "coverage_gap", **window, bucket_deg=bucket_deg
        ),
        "acceptance_rate": await metric(session, "acceptance_rate", **window),
        "escalation_rate": await metric(session, "escalation_rate", **window),
        "ai_degradation_rate": await metric(session, "ai_degradation_rate", **window),
        "incidents_by_category": await metric(session, "incidents_by_category", **window),
    }


def available_queries() -> list[str]:
    return sorted(path.stem for path in QUERY_DIR.glob("*.sql"))
