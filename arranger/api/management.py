from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from arranger.clients.base import ArrApiError
from arranger.clients.radarr import RadarrClient
from arranger.clients.sonarr import SonarrClient
from arranger.config import ArrConfig, RuleConfig, Settings
from arranger.services.config_store import save_config, settings_to_safe_dict

LOG = logging.getLogger(__name__)


class ConfigUpdate(BaseModel):
    config: dict[str, Any]
    confirmation: str | None = None


class ConnectionTestPayload(BaseModel):
    enabled: bool = True
    url: str
    api_key: str
    api_key_style: Literal["header", "query"] = "header"


class RulePayload(BaseModel):
    app: Literal["radarr", "sonarr"]
    rule: RuleConfig


class RuleUpdatePayload(BaseModel):
    rule: RuleConfig


class RuleValidationPayload(BaseModel):
    app: Literal["radarr", "sonarr"]
    rules: list[RuleConfig] = Field(default_factory=list)
    rootfolders: list[str] = Field(default_factory=list)


def validate_rules(rules: list[RuleConfig], rootfolders: list[str] | None = None) -> list[str]:
    warnings: list[str] = []
    explicit = [rule for rule in rules if not rule.default]
    for index, first in enumerate(explicit):
        for second in explicit[index + 1 :]:
            if first.priority != second.priority:
                continue
            if set(map(str.casefold, first.match_genres)) & set(
                map(str.casefold, second.match_genres)
            ):
                warnings.append(
                    f"Rules '{first.name}' and '{second.name}' can both match at "
                    f"priority {first.priority}"
                )
    if not any(rule.default for rule in rules):
        warnings.append("No default rule is configured")
    if rootfolders:
        known = {root.rstrip("/") for root in rootfolders}
        for rule in rules:
            if rule.target_root.rstrip("/") not in known:
                warnings.append(f"Target root for '{rule.name}' is not in discovered root folders")
    return warnings


def create_management_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/config")
    async def get_config(request: Request) -> dict[str, Any]:
        return settings_to_safe_dict(request.app.state.settings)

    @router.post("/config")
    async def post_config(payload: ConfigUpdate, request: Request) -> dict[str, Any]:
        try:
            new_settings = save_config(
                payload.config, request.app.state.settings, payload.confirmation
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        request.app.state.settings = new_settings
        return settings_to_safe_dict(new_settings)

    @router.post("/test/radarr")
    async def test_radarr(payload: ConnectionTestPayload) -> dict[str, Any]:
        client = RadarrClient(ArrConfig(**payload.model_dump()))
        try:
            return {"ok": True, "result": await client.healthcheck()}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"Radarr connection failed: {exc}"}
        finally:
            await client.close()

    @router.post("/test/sonarr")
    async def test_sonarr(payload: ConnectionTestPayload) -> dict[str, Any]:
        client = SonarrClient(ArrConfig(**payload.model_dump()))
        try:
            return {"ok": True, "result": await client.healthcheck()}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"Sonarr connection failed: {exc}"}
        finally:
            await client.close()

    @router.get("/rootfolders/radarr")
    async def radarr_roots(request: Request) -> dict[str, Any]:
        client = getattr(request.app.state, "radarr", None)
        if not client:
            return {"ok": False, "rootfolders": [], "error": "Radarr disabled"}
        try:
            return {"ok": True, "rootfolders": await client.get_rootfolders()}
        except ArrApiError as exc:
            return {"ok": False, "rootfolders": [], "error": str(exc)}

    @router.get("/rootfolders/sonarr")
    async def sonarr_roots(request: Request) -> dict[str, Any]:
        client = getattr(request.app.state, "sonarr", None)
        if not client:
            return {"ok": False, "rootfolders": [], "error": "Sonarr disabled"}
        try:
            return {"ok": True, "rootfolders": await client.get_rootfolders()}
        except ArrApiError as exc:
            return {"ok": False, "rootfolders": [], "error": str(exc)}

    @router.get("/logs")
    async def logs(
        request: Request, level: str | None = None, app: str | None = None
    ) -> dict[str, Any]:
        settings: Settings = request.app.state.settings
        path = Path(settings.logging.file)
        if not path.exists():
            return {"lines": []}
        lines = path.read_text(errors="replace").splitlines()[-500:]
        if level:
            lines = [line for line in lines if level.upper() in line.upper()]
        if app:
            lines = [line for line in lines if app.casefold() in line.casefold()]
        return {"lines": lines[-200:]}

    @router.get("/rules")
    async def get_rules(request: Request) -> dict[str, Any]:
        settings: Settings = request.app.state.settings
        return {
            "radarr": [r.model_dump(mode="json") for r in settings.rules.radarr],
            "sonarr": [r.model_dump(mode="json") for r in settings.rules.sonarr],
            "warnings": {
                "radarr": validate_rules(settings.rules.radarr),
                "sonarr": validate_rules(settings.rules.sonarr),
            },
        }

    @router.post("/rules/validate")
    async def validate_rule_payload(payload: RuleValidationPayload) -> dict[str, Any]:
        return {"warnings": validate_rules(payload.rules, payload.rootfolders)}

    @router.post("/rules")
    async def add_rule(payload: RulePayload, request: Request) -> dict[str, Any]:
        settings: Settings = request.app.state.settings
        data = settings.model_dump(mode="json")
        data["rules"][payload.app].append(payload.rule.model_dump(mode="json"))
        request.app.state.settings = save_config(data, settings)
        return {
            "ok": True,
            "warnings": validate_rules(getattr(request.app.state.settings.rules, payload.app)),
        }

    @router.put("/rules/{app}/{rule_id}")
    async def update_rule(
        app: Literal["radarr", "sonarr"], rule_id: int, payload: RuleUpdatePayload, request: Request
    ) -> dict[str, Any]:
        settings: Settings = request.app.state.settings
        data = settings.model_dump(mode="json")
        rules = data["rules"][app]
        if rule_id < 0 or rule_id >= len(rules):
            raise HTTPException(404, "Rule not found")
        rules[rule_id] = payload.rule.model_dump(mode="json")
        request.app.state.settings = save_config(data, settings)
        return {
            "ok": True,
            "warnings": validate_rules(getattr(request.app.state.settings.rules, app)),
        }

    @router.put("/rules/{rule_id}")
    async def update_rule_default_app(
        rule_id: int,
        payload: RuleUpdatePayload,
        request: Request,
        app: Literal["radarr", "sonarr"] = "radarr",
    ) -> dict[str, Any]:
        return await update_rule(app, rule_id, payload, request)

    @router.delete("/rules/{rule_id}")
    async def delete_rule_default_app(
        rule_id: int, request: Request, app: Literal["radarr", "sonarr"] = "radarr"
    ) -> dict[str, Any]:
        return await delete_rule(app, rule_id, request)

    @router.delete("/rules/{app}/{rule_id}")
    async def delete_rule(
        app: Literal["radarr", "sonarr"], rule_id: int, request: Request
    ) -> dict[str, Any]:
        settings: Settings = request.app.state.settings
        data = settings.model_dump(mode="json")
        rules = data["rules"][app]
        if rule_id < 0 or rule_id >= len(rules):
            raise HTTPException(404, "Rule not found")
        rules.pop(rule_id)
        request.app.state.settings = save_config(data, settings)
        return {
            "ok": True,
            "warnings": validate_rules(getattr(request.app.state.settings.rules, app)),
        }

    return router
