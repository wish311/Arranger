from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from arranger.api.management import create_management_router
from arranger.api.routes import create_router
from arranger.api.ui import create_ui_router
from arranger.clients.radarr import RadarrClient
from arranger.clients.sonarr import SonarrClient
from arranger.config import load_settings
from arranger.database import Database
from arranger.logging_config import setup_logging
from arranger.rules.engine import RuleEngine
from arranger.services.audit import AuditService
from arranger.services.health import HealthService
from arranger.services.moves import MoveExecutor
from arranger.workers.scheduler import AsyncScheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    setup_logging(settings)
    db = Database(settings.app.database_path)
    radarr = RadarrClient(settings.radarr) if settings.radarr and settings.radarr.enabled else None
    sonarr = SonarrClient(settings.sonarr) if settings.sonarr and settings.sonarr.enabled else None
    rules = RuleEngine(settings.rules)
    audit = AuditService(settings, db, rules, radarr, sonarr)
    moves = MoveExecutor(settings, db, radarr, sonarr)
    health = HealthService(settings, db, radarr, sonarr)
    scheduler = AsyncScheduler(settings, audit, moves)
    app.state.settings = settings
    app.state.db = db
    app.state.radarr = radarr
    app.state.sonarr = sonarr
    app.state.audit_service = audit
    app.state.move_executor = moves
    app.state.health_service = health
    app.state.scheduler = scheduler
    await health.startup_check()
    scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()
        if radarr:
            await radarr.close()
        if sonarr:
            await sonarr.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Arranger", version="0.1.0", lifespan=lifespan)
    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(create_router())
    app.include_router(create_management_router())
    app.include_router(create_ui_router())
    return app


app = create_app()
