"""Async SQLAlchemy engine, session factory, and declarative base (ADR-018).

Sessions are async because the escalation state machine of ADR-012 runs inside
`asyncio.create_task`; a blocking query in one of those background tasks would
stall the same event loop that delivers WebSocket alerts.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for every model in `app.models`."""


_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    # Hosted Postgres drops idle connections; without pre-ping the first query
    # after an idle period fails on a stale connection. Reliability, not tuning.
    pool_pre_ping=True,
)

SessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    # Attributes stay loaded after commit. Under asyncio the alternative is an
    # implicit lazy refresh on attribute access, which raises outside a session.
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one session per request.

    Commits are explicit and belong to the service layer -- this only guarantees
    the session is closed, and that uncommitted work is discarded on error.
    """
    async with SessionFactory() as session:
        yield session
