"""Async SQLAlchemy engine, session factory, and declarative base (ADR-018).

Sessions are async because the escalation state machine of ADR-012 runs inside
`asyncio.create_task`; a blocking query in one of those background tasks would
stall the same event loop that delivers WebSocket alerts.

The engine is built on first use rather than at import. Importing this module --
which `app.models` does, and therefore so does anything touching the domain
vocabulary -- must not require a configured database. `tests/test_haversine.py`
is the case that matters: Chapter 24 proves the dispatch core as a pure function
before any transport or storage is involved, and a test that needs DATABASE_URL
to import a distance function is not a pure-function test. Startup still fails
fast on missing configuration, in `app.main.create_app`.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for every model in `app.models`."""


@lru_cache
def get_engine() -> AsyncEngine:
    # make_url turns the DSN into a URL object whose repr masks the password, so
    # a connection failure cannot print the credential into a traceback.
    return create_async_engine(
        make_url(get_settings().database_url.get_secret_value()),
        # Hosted Postgres drops idle connections; without pre-ping the first query
        # after an idle period fails on a stale connection. Reliability, not tuning.
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_engine(),
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
    async with get_session_factory()() as session:
        yield session
