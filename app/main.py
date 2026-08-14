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

from fastapi import FastAPI, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import dispose_engine, get_sessionmaker
from app.routers import admin as admin_router
from app.routers import attachments as attachments_router
from app.routers import auth as auth_router
from app.routers import corridors as corridors_router
from app.routers import health
from app.routers import incidents as incidents_router
from app.routers import reports as reports_router
from app.worker import OutboxWorker, set_worker

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
    if settings.jwt_secret_is_default:
        if settings.environment == "production":
            # Refuse rather than warn. A production service signing tokens with a
            # secret published in the repository is not degraded, it is unauthenticated.
            raise RuntimeError(
                "JWT_SECRET is still the development default. Set a real one before "
                "running in production: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        log.warning("JWT_SECRET is the development default — fine locally, never in production")
    # The outbox worker runs in-process as an asyncio task rather than as a separate
    # service, because Render's free tier permits only one. A deliberate compromise,
    # recorded as decision D-013 and technical debt TD-01.
    worker = None
    if settings.database_configured:
        worker = OutboxWorker(get_sessionmaker(), settings)
        worker.start()
        set_worker(worker)

    yield

    log.info("shutting down")
    if worker is not None:
        await worker.stop()
        set_worker(None)
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
    app.include_router(auth_router.router)
    app.include_router(reports_router.router)
    app.include_router(incidents_router.router)
    app.include_router(attachments_router.router)
    app.include_router(corridors_router.router)
    app.include_router(admin_router.router)

    # Served by FastAPI directly. There is no separate front-end host — see D-012.
    #
    # The application is at the root. The original single page has been retired (D-045):
    # it existed so that a graded deployment always had something that worked while the
    # rebuild was unproven, and the rebuild is now proven.
    #
    # Putting it at `/` is not tidiness. The service worker and the manifest both need a
    # scope, a scope may not sit above the file it is declared in, and `/app` under a
    # scope of `/static/app/` meant **the worker controlled nothing and the installed app
    # opened a 404** — `/static/app/` was never a route. At the root the three agree by
    # construction and there is nothing left to keep in step.
    if WEB_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(WEB_DIR / "app" / "index.html")

        @app.get("/app", include_in_schema=False)
        async def pwa_moved() -> RedirectResponse:
            """Kept as a redirect, not deleted.

            `/app` has been the address for two days. It is in the deployment links file,
            in browser history, and possibly in an examiner's notes. A permanent redirect
            costs one route; a dead link costs a mark."""
            return RedirectResponse("/", status_code=status.HTTP_308_PERMANENT_REDIRECT)

        @app.get("/sw.js", include_in_schema=False)
        async def service_worker() -> FileResponse:
            # A service worker may only control paths at or below its own URL, so serving
            # it from the root is what allows a scope of "/" — which is what lets it
            # control the application page at all.
            return FileResponse(
                WEB_DIR / "app" / "sw.js",
                media_type="application/javascript",
                headers={"Service-Worker-Allowed": "/"},
            )

    return app


app = create_app()
