"""Regression guard: credentials must not be renderable (Ch. 22).

Chapter 21 says to test where correctness is hard and skip where it is obvious,
and this looks like the obvious kind. It is here anyway, because it is not
guarding a computation -- it is guarding an accident. A failing test in week 4
printed the full database DSN, password included, into pytest output. Nothing
about the code looked wrong; the credential was simply a `str`, and `str` is
what tracebacks print.

These tests fail the moment someone changes a SecretStr field back to a plain
string, which is exactly when the accident would silently become possible again.
"""

from sqlalchemy.engine import make_url

from app.config import Settings, get_settings

SENTINEL_PASSWORD = "sentinel-password-do-not-log"
SENTINEL_SECRET = "sentinel-jwt-secret-do-not-log"


def _settings_with_sentinels() -> Settings:
    return Settings(
        database_url=f"postgresql+psycopg://user:{SENTINEL_PASSWORD}@localhost:5432/db",
        jwt_secret=SENTINEL_SECRET,
    )


class TestSettingsDoNotRenderSecrets:
    def test_repr_hides_the_database_password(self):
        assert SENTINEL_PASSWORD not in repr(_settings_with_sentinels())

    def test_str_hides_the_database_password(self):
        assert SENTINEL_PASSWORD not in str(_settings_with_sentinels())

    def test_repr_hides_the_jwt_secret(self):
        assert SENTINEL_SECRET not in repr(_settings_with_sentinels())

    def test_model_dump_hides_secrets(self):
        """Guards the path a structured logger would take."""
        dumped = str(_settings_with_sentinels().model_dump())
        assert SENTINEL_PASSWORD not in dumped
        assert SENTINEL_SECRET not in dumped

    def test_the_value_is_still_reachable_on_purpose(self):
        """Masking must not mean unusable -- only that reading is explicit."""
        settings = _settings_with_sentinels()
        assert SENTINEL_PASSWORD in settings.database_url.get_secret_value()
        assert settings.jwt_secret.get_secret_value() == SENTINEL_SECRET


class TestUrlObjectsMaskPasswords:
    """The engine is built from a URL object rather than a DSN string, so a
    connection failure renders `***` instead of the credential."""

    def test_url_repr_masks_the_password(self):
        url = make_url(f"postgresql+psycopg://user:{SENTINEL_PASSWORD}@localhost:5432/db")
        assert SENTINEL_PASSWORD not in repr(url)
        assert "***" in repr(url)

    def test_url_still_carries_the_password_for_connecting(self):
        url = make_url(f"postgresql+psycopg://user:{SENTINEL_PASSWORD}@localhost:5432/db")
        assert url.password == SENTINEL_PASSWORD


class TestRealSettings:
    def test_the_configured_password_does_not_appear_in_a_repr(self):
        """The actual running configuration, not a synthetic one."""
        settings = get_settings()
        password = make_url(settings.database_url.get_secret_value()).password
        if not password:
            return  # nothing to leak on a passwordless local socket
        assert password not in repr(settings)
        assert password not in str(settings.database_url)
