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

from app.config import get_settings
from app.routers import auth


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


def create_app() -> FastAPI:
    get_settings()  # fail fast on missing configuration

    app = FastAPI(
        title="FLARE",
        summary="Fast Local Alert & Response Engine",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)

    return app


app = create_app()
