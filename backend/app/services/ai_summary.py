"""The single AI touchpoint -- ADR-005, ADR-013, ADR-024.

Free-text description in, `{category, priority}` out. That is the entire AI
surface of this project, deliberately: one bounded call is defensible under
questioning, where several invite questions about model accuracy and clinical
validation that this project cannot answer.

Three properties matter more than the output itself:

  1. It never blocks dispatch. Wave 1 goes out on radius and declared skills
     alone; this runs concurrently and refines wave 2 (ADR-013).
  2. It has a hard ceiling. Past `ai_timeout_seconds` the incident keeps
     {unspecified, medium} and the degradation is recorded, not swallowed.
  3. Every way it can fail is separable. `timeout`, `error` and `skipped` are
     distinct `ai_status` values, so quota exhaustion, a network failure and a
     missing key do not collapse into one number in the ADR-015 metric.

A plain HTTPS POST rather than a vendor SDK, per ADR-024 -- the whole request is
readable in one screen, and the timeout is ours rather than a library's.
"""

import asyncio
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.models import AIPriority, AIStatus

logger = logging.getLogger(__name__)

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"

FALLBACK_CATEGORY = "unspecified"
FALLBACK_PRIORITY = AIPriority.MEDIUM

# A closed vocabulary, not free text. The category feeds wave-2 ranking, so an
# open-ended answer would make dispatch behaviour depend on model phrasing --
# "cardiac arrest" versus "Possible Cardiac Arrest" must not rank differently.
CATEGORIES = (
    "cardiac_arrest",
    "choking",
    "severe_bleeding",
    "trauma",
    "breathing_difficulty",
    "allergic_reaction",
    "burn",
    "seizure",
    "unconscious",
    "other",
    FALLBACK_CATEGORY,
)

PROMPT = (
    "You are triaging a civilian emergency report for a dispatch system.\n"
    "Classify the report into exactly one category and one priority.\n\n"
    f"category must be one of: {', '.join(CATEGORIES)}\n"
    "priority must be one of: low, medium, high\n\n"
    "Answer with a single JSON object and nothing else, in the form:\n"
    '{"category": "...", "priority": "..."}\n\n'
    "If the report is too vague to classify, use category 'unspecified' and "
    "priority 'medium'. Do not guess a specific medical condition from an "
    "ambiguous report.\n\n"
    "Report: "
)


@dataclass(frozen=True, slots=True)
class AISummary:
    category: str
    priority: AIPriority
    status: AIStatus

    @property
    def degraded(self) -> bool:
        return self.status is not AIStatus.OK


def fallback(status: AIStatus) -> AISummary:
    return AISummary(category=FALLBACK_CATEGORY, priority=FALLBACK_PRIORITY, status=status)


def _build_request(settings: Settings, description: str) -> urllib.request.Request:
    """One request per provider. The key rides in a header, never the URL."""
    key = settings.ai_api_key
    assert key is not None  # guarded by the caller
    prompt = PROMPT + description

    if settings.ai_provider == "gemini":
        url = GEMINI_ENDPOINT.format(model=settings.ai_model)
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": key.get_secret_value(),
        }
    else:
        url = GROQ_ENDPOINT
        body = {
            "model": settings.ai_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key.get_secret_value()}",
        }

    return urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )


def _extract_text(provider: str, payload: dict) -> str:
    if provider == "gemini":
        return payload["candidates"][0]["content"]["parts"][0]["text"]
    return payload["choices"][0]["message"]["content"]


def parse_response(provider: str, raw: str) -> AISummary:
    """Parse and *validate* against the closed vocabulary.

    A model returning something outside the enum is an error, not something to
    coerce -- silently accepting an unknown category would let model drift
    change dispatch ranking without anyone noticing.
    """
    payload = json.loads(raw)
    answer = json.loads(_extract_text(provider, payload))

    category = str(answer.get("category", "")).strip().lower()
    priority = str(answer.get("priority", "")).strip().lower()

    if category not in CATEGORIES:
        raise ValueError(f"category outside the allowed set: {category!r}")

    return AISummary(
        category=category,
        priority=AIPriority(priority),
        status=AIStatus.OK,
    )


def _call_blocking(settings: Settings, description: str) -> AISummary:
    request = _build_request(settings, description)
    timeout = settings.ai_timeout_seconds
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return parse_response(settings.ai_provider, response.read().decode("utf-8"))


async def summarise(description: str | None) -> AISummary:
    """Classify a report. Never raises -- every failure is a logged fallback.

    This function is the reason ADR-013 exists: it is allowed to be slow, wrong
    or absent, and the dispatch engine must not care.
    """
    settings = get_settings()

    if not description or not description.strip():
        return fallback(AIStatus.SKIPPED)

    if settings.ai_api_key is None:
        # No key configured. Honest and expected -- not an error.
        return fallback(AIStatus.SKIPPED)

    try:
        # Two ceilings on purpose: urllib's own socket timeout, and wait_for as
        # the one that actually binds. A socket that connects but never sends a
        # byte would otherwise sit past the budget.
        return await asyncio.wait_for(
            asyncio.to_thread(_call_blocking, settings, description),
            timeout=settings.ai_timeout_seconds + 0.5,
        )
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning("ai summary timed out after %ss", settings.ai_timeout_seconds)
        return fallback(AIStatus.TIMEOUT)
    except urllib.error.HTTPError as exc:
        # 429 lands here: quota exhaustion degrades exactly like any other
        # upstream failure, which is the whole point of having a fallback.
        logger.warning("ai summary failed: HTTP %s", exc.code)
        return fallback(AIStatus.ERROR)
    except Exception as exc:
        logger.warning("ai summary failed: %s", type(exc).__name__)
        return fallback(AIStatus.ERROR)
