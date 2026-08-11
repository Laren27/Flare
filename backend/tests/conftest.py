"""Test fixtures for the database-backed tests (weeks 4+).

Runs against a **separate** `flare_test` database, created on demand and
migrated with Alembic. Alembic rather than `create_all` on purpose: the
accept-lock claim is a claim about the real schema, so the schema under test
has to be the one the migrations actually produce.

`test_haversine.py` deliberately touches none of this -- it needs no database
and no environment, and that stays true.
"""

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_SUFFIX = "_test"


def _test_database_url() -> str:
    """Derive the test URL from DATABASE_URL by suffixing the database name."""
    from app.config import get_settings

    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}{TEST_DB_SUFFIX}").render_as_string(
        hide_password=False
    )


def _ensure_database(url: str) -> None:
    """CREATE DATABASE if absent, connecting via the server's default database."""
    target = make_url(url)
    admin = target.set(database="postgres")

    # AUTOCOMMIT: CREATE DATABASE cannot run inside a transaction block.
    engine = create_engine(admin, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    engine.dispose()


def _migrate() -> None:
    """Run Alembic against whatever DATABASE_URL currently says.

    The URL is deliberately *not* passed via `config.set_main_option`: Alembic's
    config is a configparser, which treats `%` as interpolation syntax, so any
    percent-encoded character in the password (and reserved characters must be
    percent-encoded there) raises before a migration runs. env.py already reads
    the environment, so the environment is the channel used.
    """
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def test_database_url() -> str:
    from app.config import get_settings

    url = _test_database_url()
    _ensure_database(url)

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()  # settings are cached; the override must win
    try:
        _migrate()
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()

    return url


@pytest.fixture(scope="session")
def _asyncio_loop_factory():
    """Give pytest-asyncio a loop psycopg can actually use (ADR-020).

    Same constraint as the application: Windows' default ProactorEventLoop
    cannot drive psycopg in async mode, and pytest-asyncio builds the loop
    before any test code runs. It passes this fixture straight to
    `asyncio.Runner(loop_factory=...)`, which is the same mechanism `run.py`
    uses -- not the deprecated event loop policy.

    The name is private to pytest-asyncio; overriding it by name is how the
    plugin intends the factory to be supplied.
    """
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop
    return None


@pytest.fixture
async def engine(test_database_url):
    engine = create_async_engine(test_database_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def clean_tables(engine) -> AsyncIterator[None]:
    """Empty every table before each test.

    TRUNCATE ... CASCADE rather than DELETE: dispatch_events holds foreign keys
    into users that deliberately do not cascade (the decision log should not be
    erasable by deleting a user), so an ordered DELETE would be fragile here.
    """
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE users, volunteers, locations, sos, notifications, "
                "dispatch_events, incident_history RESTART IDENTITY CASCADE"
            )
        )
    yield
