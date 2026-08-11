"""AI summary degradation -- ADR-013, ADR-024, invariant 2.

Chapter 21 says to test where correctness is hard. The hard part here is not the
happy path -- it is the promise that this call can fail in any way at all and
dispatch still works. That promise is load-bearing (the AI provider is the
project's weakest dependency by its own admission) and it is invisible: nothing
about the code looks wrong if the fallback quietly stops working.

Every test here runs without a network and without an API key.
"""

import asyncio
import json
import socket
import threading
import time

import pytest

from app.config import Settings
from app.models import AIPriority, AIStatus
from app.services import ai_summary

# No module-level asyncio mark: pytest.ini runs asyncio_mode=auto, so async
# tests are collected automatically and the sync ones stay unmarked.


def settings_with(**overrides) -> Settings:
    """Hermetic settings: `_env_file=None` stops pydantic reading backend/.env.

    Without it these tests inherit whatever key the developer happens to have
    configured, and "no key configured" quietly becomes a live API call -- which
    is exactly how this helper was wrong the first time it was written.
    """
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:p@h/d",
        jwt_secret="test-secret",
        **overrides,
    )


def gemini_payload(text: str) -> str:
    return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]})


def groq_payload(text: str) -> str:
    return json.dumps({"choices": [{"message": {"content": text}}]})


class TestFallback:
    async def test_no_description_is_skipped_not_called(self):
        result = await ai_summary.summarise(None)
        assert result.status is AIStatus.SKIPPED
        assert result.category == ai_summary.FALLBACK_CATEGORY
        assert result.priority is AIPriority.MEDIUM

    async def test_whitespace_description_is_skipped(self):
        assert (await ai_summary.summarise("   \n ")).status is AIStatus.SKIPPED

    async def test_missing_key_is_skipped_not_error(self, monkeypatch):
        """No key configured is a configuration state, not a failure."""
        monkeypatch.setattr(ai_summary, "get_settings", lambda: settings_with())
        result = await ai_summary.summarise("someone collapsed")
        assert result.status is AIStatus.SKIPPED

    async def test_placeholder_key_is_treated_as_missing(self, monkeypatch):
        """A CHANGE_ME left in .env must not become a confusing 401."""
        monkeypatch.setattr(
            ai_summary, "get_settings", lambda: settings_with(gemini_api_key="CHANGE_ME")
        )
        assert (await ai_summary.summarise("someone collapsed")).status is AIStatus.SKIPPED


class TestTimeoutIsHard:
    async def test_a_silent_server_does_not_outlast_the_budget(self, monkeypatch):
        """The case a plain socket timeout can miss: the connection is accepted
        and then nothing is ever sent. `wait_for` is what actually binds."""
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(5)
        port = server.getsockname()[1]
        threading.Thread(target=lambda: [server.accept() for _ in range(10)], daemon=True).start()

        monkeypatch.setattr(
            ai_summary,
            "GEMINI_ENDPOINT",
            f"http://127.0.0.1:{port}/v1beta/models/{{model}}:generateContent",
        )
        monkeypatch.setattr(
            ai_summary,
            "get_settings",
            lambda: settings_with(gemini_api_key="test-key", ai_timeout_seconds=1.0),
        )

        started = time.perf_counter()
        result = await ai_summary.summarise("someone collapsed and is not breathing")
        elapsed = time.perf_counter() - started

        server.close()

        assert result.status in {AIStatus.TIMEOUT, AIStatus.ERROR}
        assert result.category == ai_summary.FALLBACK_CATEGORY
        assert result.priority is AIPriority.MEDIUM
        assert elapsed < 2.5, f"blew the budget: {elapsed:.2f}s"

    async def test_an_unreachable_host_degrades_to_error(self, monkeypatch):
        monkeypatch.setattr(
            ai_summary,
            "GEMINI_ENDPOINT",
            "http://127.0.0.1:1/v1beta/models/{model}:generateContent",
        )
        monkeypatch.setattr(
            ai_summary,
            "get_settings",
            lambda: settings_with(gemini_api_key="test-key", ai_timeout_seconds=1.0),
        )
        result = await ai_summary.summarise("someone collapsed")
        assert result.status is AIStatus.ERROR
        assert result.category == ai_summary.FALLBACK_CATEGORY


class TestParsing:
    def test_valid_gemini_response(self):
        result = ai_summary.parse_response(
            "gemini", gemini_payload('{"category":"cardiac_arrest","priority":"high"}')
        )
        assert result.category == "cardiac_arrest"
        assert result.priority is AIPriority.HIGH
        assert result.status is AIStatus.OK

    def test_valid_groq_response(self):
        result = ai_summary.parse_response(
            "groq", groq_payload('{"category":"choking","priority":"medium"}')
        )
        assert result.category == "choking"
        assert result.priority is AIPriority.MEDIUM

    def test_category_outside_the_vocabulary_is_rejected(self):
        """Accepting an unknown category would let model drift silently change
        wave-2 dispatch ranking. It is an error, not something to coerce."""
        with pytest.raises(ValueError, match="outside the allowed set"):
            ai_summary.parse_response(
                "gemini", gemini_payload('{"category":"vibes","priority":"high"}')
            )

    def test_invalid_priority_is_rejected(self):
        with pytest.raises(ValueError):
            ai_summary.parse_response(
                "gemini", gemini_payload('{"category":"choking","priority":"URGENT"}')
            )

    def test_malformed_json_is_rejected(self):
        with pytest.raises(Exception):
            ai_summary.parse_response("gemini", gemini_payload("not json at all"))

    async def test_a_malformed_response_becomes_a_logged_fallback(self, monkeypatch):
        """Whatever parse_response raises, summarise() must never propagate it --
        a dispatch in flight cannot be interrupted by a bad LLM reply."""
        def explode(*_args, **_kwargs):
            raise ValueError("category outside the allowed set: 'vibes'")

        monkeypatch.setattr(ai_summary, "_call_blocking", explode)
        monkeypatch.setattr(
            ai_summary, "get_settings", lambda: settings_with(gemini_api_key="test-key")
        )
        result = await ai_summary.summarise("someone collapsed")
        assert result.status is AIStatus.ERROR
        assert result.degraded is True


class TestProviderSwitch:
    def test_gemini_selected_by_default(self):
        s = settings_with(gemini_api_key="g-key", groq_api_key="q-key")
        assert s.ai_provider == "gemini"
        assert s.ai_api_key.get_secret_value() == "g-key"

    def test_groq_selected_by_config(self):
        s = settings_with(ai_provider="groq", gemini_api_key="g-key", groq_api_key="q-key")
        assert s.ai_api_key.get_secret_value() == "q-key"
        assert s.ai_model == s.groq_model

    def test_the_key_never_lands_in_the_url(self):
        """ADR-022's reasoning applied here: a credential in a URL is written to
        every log the request passes through."""
        s = settings_with(gemini_api_key="super-secret-key")
        request = ai_summary._build_request(s, "someone collapsed")
        assert "super-secret-key" not in request.full_url
        assert request.headers["X-goog-api-key"] == "super-secret-key"
