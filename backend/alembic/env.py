"""Alembic environment -- ADR-017.

The database URL comes from the application settings (which read the process
environment, falling back to `backend/.env`), never from `alembic.ini`, so no
credential is committed.

Migrations run on a *sync* engine even though the application is async
(ADR-018): `postgresql+psycopg://` drives both, and an async migration runner
would add boilerplate to a one-shot command that has nothing to overlap with.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from sqlalchemy.engine import URL, make_url

from alembic import context
from app.config import get_settings
from app.database import Base

# Imported for its side effect: every model must be registered on Base.metadata
# before autogenerate compares it against the live schema.
import app.models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> URL:
    """A URL object, not a string: its repr masks the password, so a failed
    migration cannot print the credential into the traceback."""
    return make_url(get_settings().database_url.get_secret_value())


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing it (`alembic upgrade --sql`)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
