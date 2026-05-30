from __future__ import annotations

import logging
from pathlib import PurePosixPath
from typing import Any

import httpx

from arranger.config import ArrConfig
from arranger.models import MoveResult, MoveStatus
from arranger.safety.common import root_exists

LOG = logging.getLogger(__name__)

REQUIRED_ITEM_FIELDS = {"id", "title", "path"}


class ArrApiError(RuntimeError):
    pass


class ArrClient:
    def __init__(self, config: ArrConfig, name: str) -> None:
        self.config = config
        self.name = name
        self.base_url = config.url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=30)

    async def close(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.config.api_key} if self.config.api_key_style == "header" else {}

    def _params(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = dict(params or {})
        if self.config.api_key_style == "query":
            merged["apikey"] = self.config.api_key
        return merged

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(
                method,
                path,
                headers=self._headers(),
                params=self._params(kwargs.pop("params", None)),
                **kwargs,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            LOG.exception("%s API request failed: %s %s", self.name, method, path)
            raise ArrApiError(str(exc)) from exc
        if not response.content:
            return None
        return response.json()

    async def healthcheck(self) -> dict[str, Any]:
        status = await self.request("GET", "/api/v3/system/status")
        roots = await self.request("GET", "/api/v3/rootfolder")
        queue = await self.request("GET", "/api/v3/queue")
        if (
            not isinstance(status, dict)
            or not isinstance(roots, list)
            or not isinstance(queue, dict | list)
        ):
            raise ArrApiError(f"{self.name} health schema mismatch")
        return {"status": status, "rootfolders": len(roots), "queue_ok": True}

    async def get_rootfolders(self) -> list[dict[str, Any]]:
        roots = await self.request("GET", "/api/v3/rootfolder")
        if not isinstance(roots, list):
            raise ArrApiError("Rootfolder schema mismatch")
        return roots

    async def get_queue(self) -> dict[str, Any] | list[dict[str, Any]]:
        queue = await self.request("GET", "/api/v3/queue")
        if not isinstance(queue, dict | list):
            raise ArrApiError("Queue schema mismatch")
        return queue

    def verify_item_schema(self, item: dict[str, Any]) -> bool:
        return isinstance(item, dict) and REQUIRED_ITEM_FIELDS.issubset(item)

    def compute_target_path(self, current_path: str, target_root: str) -> str:
        leaf = PurePosixPath(current_path).name
        return str(PurePosixPath(target_root) / leaf)

    def verify_move_response(self, response: dict[str, Any], expected_path: str) -> bool:
        return (
            isinstance(response, dict)
            and response.get("path") == expected_path
            and "id" in response
        )

    async def trigger_command(self, name: str, **body: Any) -> None:
        await self.request("POST", "/api/v3/command", json={"name": name, **body})

    async def validate_move_prereqs(
        self, item: dict[str, Any], rootfolders: list[dict[str, Any]], target_root: str
    ) -> MoveResult | None:
        if not self.verify_item_schema(item):
            return MoveResult(
                False, MoveStatus.FAILED, "API schema validation failed for current item"
            )
        if not root_exists(target_root, rootfolders):
            return MoveResult(False, MoveStatus.FAILED, f"Target root not found: {target_root}")
        return None
