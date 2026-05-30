from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from arranger.api.webhooks import extract_media_id, verify_webhook_secret
from arranger.database import Database
from arranger.models import MoveStatus
from arranger.services.audit import AuditService
from arranger.services.health import HealthService
from arranger.services.moves import MoveExecutor

LOG = logging.getLogger(__name__)


def create_router() -> APIRouter:
    router = APIRouter()

    def get_audit(request: Request) -> AuditService:
        return request.app.state.audit_service

    def get_db(request: Request) -> Database:
        return request.app.state.db

    def get_health(request: Request) -> HealthService:
        return request.app.state.health_service

    def get_moves(request: Request) -> MoveExecutor:
        return request.app.state.move_executor

    @router.get("/health")
    async def health(health_service: HealthService = Depends(get_health)) -> dict[str, Any]:
        return await health_service.startup_check()

    @router.get("/status")
    async def status(db: Database = Depends(get_db)) -> dict[str, Any]:
        return {
            "queue": len(
                db.list_records([MoveStatus.PENDING, MoveStatus.APPROVED, MoveStatus.BLOCKED])
            ),
            "history": len(db.list_records()),
        }

    @router.post("/audit/radarr")
    async def audit_radarr(audit: AuditService = Depends(get_audit)) -> dict[str, Any]:
        return await audit.audit_radarr()

    @router.post("/audit/sonarr")
    async def audit_sonarr(audit: AuditService = Depends(get_audit)) -> dict[str, Any]:
        return await audit.audit_sonarr()

    @router.post("/audit/all")
    async def audit_all(
        audit: AuditService = Depends(get_audit), moves: MoveExecutor = Depends(get_moves)
    ) -> dict[str, Any]:
        result = {"radarr": await audit.audit_radarr(), "sonarr": await audit.audit_sonarr()}
        result["moves"] = await moves.process_approved_once()
        return result

    @router.get("/queue")
    async def queue(db: Database = Depends(get_db)) -> list[dict[str, Any]]:
        return db.list_records(
            [MoveStatus.PENDING, MoveStatus.BLOCKED, MoveStatus.APPROVED, MoveStatus.RUNNING]
        )

    @router.get("/history")
    async def history(db: Database = Depends(get_db)) -> list[dict[str, Any]]:
        return db.list_records()

    @router.post("/queue/{record_id}/approve")
    async def approve(
        record_id: int, request: Request, db: Database = Depends(get_db)
    ) -> dict[str, Any]:
        if request.app.state.settings.app.dry_run:
            raise HTTPException(409, "Dry-run is enabled; approval for real moves is blocked")
        if not db.get_record(record_id):
            raise HTTPException(404, "Queue record not found")
        db.update_status(record_id, MoveStatus.APPROVED, "Manually approved")
        return {"id": record_id, "status": MoveStatus.APPROVED.value}

    @router.post("/queue/{record_id}/cancel")
    async def cancel(record_id: int, db: Database = Depends(get_db)) -> dict[str, Any]:
        if not db.get_record(record_id):
            raise HTTPException(404, "Queue record not found")
        db.update_status(record_id, MoveStatus.CANCELED, "Manually canceled")
        return {"id": record_id, "status": MoveStatus.CANCELED.value}

    @router.post("/queue/{record_id}/recheck")
    async def recheck(
        record_id: int, request: Request, db: Database = Depends(get_db)
    ) -> dict[str, Any]:
        record = db.get_record(record_id)
        if not record:
            raise HTTPException(404, "Queue record not found")
        audit: AuditService = request.app.state.audit_service
        if record["app"] == "radarr":
            return await audit.audit_radarr(int(record["media_id"]))
        return await audit.audit_sonarr(int(record["media_id"]))

    @router.post("/webhook/radarr")
    async def webhook_radarr(
        request: Request, background: BackgroundTasks, audit: AuditService = Depends(get_audit)
    ) -> dict[str, Any]:
        await verify_webhook_secret(
            request,
            request.app.state.settings.radarr.webhook_secret
            if request.app.state.settings.radarr
            else None,
            request.app.state.settings.webhooks.require_secret,
        )
        payload = await request.json()
        media_id = extract_media_id(payload, "radarr")
        if media_id:
            background.add_task(audit.audit_radarr, media_id)
        else:
            LOG.info("Unknown Radarr webhook payload; scheduling full audit: %s", payload)
            background.add_task(audit.audit_radarr)
        return {"accepted": True, "media_id": media_id}

    @router.post("/webhook/sonarr")
    async def webhook_sonarr(
        request: Request, background: BackgroundTasks, audit: AuditService = Depends(get_audit)
    ) -> dict[str, Any]:
        await verify_webhook_secret(
            request,
            request.app.state.settings.sonarr.webhook_secret
            if request.app.state.settings.sonarr
            else None,
            request.app.state.settings.webhooks.require_secret,
        )
        payload = await request.json()
        media_id = extract_media_id(payload, "sonarr")
        if media_id:
            background.add_task(audit.audit_sonarr, media_id)
        else:
            LOG.info("Unknown Sonarr webhook payload; scheduling full audit: %s", payload)
            background.add_task(audit.audit_sonarr)
        return {"accepted": True, "media_id": media_id}

    return router
