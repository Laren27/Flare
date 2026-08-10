"""Application configuration, sourced entirely from the environment (Ch. 20).

`database_url` and `jwt_secret` deliberately have no defaults. A deployment
missing either fails loudly at startup rather than falling back to a guessable
signing key -- a silent default here would be the exact kind of quiet failure
Chapter 22 forbids.

Both are `SecretStr`, so neither renders in a repr, a log line, or a traceback.
This is not hypothetical tidiness: a failing test printed the full DSN,
password and all, into pytest output before this change. A credential only has
to be written somewhere readable once.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr

# pydantic-settings: typed, validated parsing of environment variables,
# consistent with the Ch. 20 convention of a Pydantic model for structured input.
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Runtime configuration. Values come from the process environment, falling
    back to `backend/.env` for local development (never committed)."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SecretStr: reading the value is an explicit .get_secret_value() call, so a
    # credential can never reach output by accident -- only on purpose.
    database_url: SecretStr
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60

    # Wave 1 dispatch radius, and the ladder the escalation state machine walks
    # outward along before giving up (ADR-012).
    base_radius_m: int = 1000
    radius_ladder_m: tuple[int, ...] = (1000, 2000, 3000)

    # How long a wave may sit un-accepted before condition B fires (ADR-012).
    accept_timeout_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    """Cached accessor -- the environment is read once per process."""
    return Settings()  # type: ignore[call-arg]  # values supplied by env/.env
