from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from arranger.config import Settings
from arranger.database import Database
from arranger.models import MoveStatus
from arranger.services.config_store import verify_password

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
security = HTTPBasic(auto_error=False)


def ui_auth(request: Request, credentials: HTTPBasicCredentials | None = Depends(security)) -> None:
    settings: Settings = request.app.state.settings
    if not settings.app.ui_auth_enabled:
        return
    if not credentials or credentials.username != settings.app.ui_username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    if not verify_password(credentials.password, settings.app.ui_password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )


def create_ui_router() -> APIRouter:
    router = APIRouter(prefix="/ui", dependencies=[Depends(ui_auth)])

    def context(request: Request, page: str, **extra: Any) -> dict[str, Any]:
        settings: Settings = request.app.state.settings
        db: Database = request.app.state.db
        records = db.list_records()
        counts = Counter(row["status"] for row in records)
        base = {
            "request": request,
            "settings": settings,
            "page": page,
            "counts": counts,
            "auth_warning": not settings.app.ui_auth_enabled,
            "recent_records": records[:6],
        }
        base.update(extra)
        return base

    @router.get("", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        db: Database = request.app.state.db
        return templates.TemplateResponse(
            request,
            "ui/dashboard.html",
            context(request, "dashboard", records=db.list_records()),
        )

    @router.get("/onboarding", response_class=HTMLResponse)
    async def onboarding(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "ui/onboarding.html", context(request, "onboarding")
        )

    @router.get("/queue", response_class=HTMLResponse)
    async def queue(request: Request) -> HTMLResponse:
        db: Database = request.app.state.db
        records = db.list_records(
            [MoveStatus.PENDING, MoveStatus.BLOCKED, MoveStatus.APPROVED, MoveStatus.RUNNING]
        )
        return templates.TemplateResponse(
            request, "ui/queue.html", context(request, "queue", records=records)
        )

    @router.get("/history", response_class=HTMLResponse)
    async def history(request: Request) -> HTMLResponse:
        db: Database = request.app.state.db
        return templates.TemplateResponse(
            request, "ui/history.html", context(request, "history", records=db.list_records())
        )

    @router.get("/rules", response_class=HTMLResponse)
    async def rules(request: Request) -> HTMLResponse:
        settings: Settings = request.app.state.settings
        return templates.TemplateResponse(
            request,
            "ui/rules.html",
            context(
                request,
                "rules",
                radarr_rules=settings.rules.radarr,
                sonarr_rules=settings.rules.sonarr,
            ),
        )

    @router.get("/settings", response_class=HTMLResponse)
    async def settings(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "ui/settings.html", context(request, "settings"))

    @router.get("/logs", response_class=HTMLResponse)
    async def logs(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "ui/logs.html", context(request, "logs"))

    @router.get("/help", response_class=HTMLResponse)
    async def help_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request, "ui/help.html", context(request, "help"))

    @router.get("/partials/logs", response_class=PlainTextResponse)
    async def log_partial(
        request: Request, level: str | None = None, app: str | None = None
    ) -> str:
        settings: Settings = request.app.state.settings
        path = Path(settings.logging.file)
        if not path.exists():
            return "No logs found"
        lines = path.read_text(errors="replace").splitlines()[-300:]
        if level:
            lines = [line for line in lines if level.upper() in line.upper()]
        if app:
            lines = [line for line in lines if app.casefold() in line.casefold()]
        return "\n".join(lines[-120:]) or "No logs found"

    return router
