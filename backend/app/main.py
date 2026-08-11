"""FLARE application entry point.

Routers are mounted here and nowhere else. Route handlers stay thin and call
into `app.services`; no business logic lives in this module or in any router
(Ch. 20).
"""

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import admin, auth, sos, ws


def assert_usable_event_loop() -> None:
    """Fail at startup, not at the first query, on an incompatible loop (ADR-020).

    psycopg's async mode cannot run on Windows' default ProactorEventLoop. Left
    unchecked this surfaces as an opaque InterfaceError the first time any
    endpoint touches the database, which is exactly the kind of silent-until-late
    failure the project refuses elsewhere.
    """
    if sys.platform != "win32":
        return

    if isinstance(asyncio.get_running_loop(), asyncio.ProactorEventLoop):
        raise RuntimeError(
            "psycopg cannot run on Windows' ProactorEventLoop (ADR-020). "
            "Start the server with `python run.py` from backend/, which selects "
            "a SelectorEventLoop, rather than invoking uvicorn directly."
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    assert_usable_event_loop()
    yield


# Sent on every response (Ch. 22). None of these are exotic; their absence is
# simply something nobody had checked until the week 7 security pass.
#
# The CSP allows the two CDNs the frontend actually uses -- unpkg for Leaflet
# and Google Fonts -- plus OpenStreetMap tiles. It is deliberately written as an
# allowlist of things that exist rather than a permissive default: when Leaflet
# is vendored locally, the unpkg entries come out and the policy tightens by
# subtraction. 'unsafe-inline' for styles is required by Leaflet's own inline
# marker styling and is noted as the one concession.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(self), camera=(), microphone=(), payment=()",
    "Content-Security-Policy": "; ".join(
        [
            "default-src 'self'",
            "script-src 'self' https://unpkg.com",
            "style-src 'self' 'unsafe-inline' https://unpkg.com https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com",
            "img-src 'self' data: https://*.tile.openstreetmap.org https://unpkg.com",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
    ),
}


def create_app() -> FastAPI:
    settings = get_settings()  # fail fast on missing configuration

    app = FastAPI(
        title="FLARE",
        summary="Fast Local Alert & Response Engine",
        version="0.1.0",
        lifespan=lifespan,
        # Off in production: /docs and /openapi.json enumerate every endpoint
        # and schema in the system (Ch. 22).
        docs_url=settings.docs_url,
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if settings.is_production:
            # Only over TLS, and only in production -- setting HSTS on a plain
            # http:// dev server would make localhost unreachable in that
            # browser until the max-age expired.
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(sos.router)
    app.include_router(ws.router)
    app.include_router(admin.router)

    # Mounted last so it cannot shadow an API route. html=True serves
    # directory index.html, which is what makes /app/citizen/ work.
    frontend = get_settings().frontend_dir
    if frontend.is_dir():
        app.mount("/app", StaticFiles(directory=frontend, html=True), name="frontend")

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/app/")

    return app


app = create_app()
