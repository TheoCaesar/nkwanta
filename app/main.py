"""Nkwanta — road incident reporting and dispatch for urban Ghana.

Entry point. Deliberately thin: it wires routers, mounts the single static page and
manages startup/shutdown. All logic lives in the modules it imports.

Run locally:
    uvicorn app.main:app --reload

The application starts successfully with no database attached. See app/db.py for why.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import dispose_engine
from app.routers import health

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)s  %(message)s",
)
log = logging.getLogger("nkwanta")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info("starting %s v%s (%s)", settings.app_name, settings.app_version, settings.environment)
    if not settings.database_configured:
        log.warning("DATABASE_URL is not set — running without a database")
    # The outbox worker is started here from B09 onward. It runs in-process rather
    # than as a separate service because Render's free tier permits only one. This
    # is a deliberate, recorded compromise — see decision D-013.
    yield
    log.info("shutting down")
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Road users report what is blocking traffic. Nkwanta works out which "
            "reports describe the same event, scores how believable it is, warns "
            "commuters heading that way, and queues a job for the authorities."
        ),
        lifespan=lifespan,
    )

    app.include_router(health.router)

    # One static page, served by FastAPI. There is no separate front-end host —
    # see decision D-012.
    if WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(WEB_DIR / "index.html")

    return app


app = create_app()
