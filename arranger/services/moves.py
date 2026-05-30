from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from arranger.clients.radarr import RadarrClient
from arranger.clients.sonarr import SonarrClient
from arranger.config import Settings
from arranger.database import Database
from arranger.models import MoveStatus

LOG = logging.getLogger(__name__)


class MoveExecutor:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        radarr: RadarrClient | None,
        sonarr: SonarrClient | None,
    ) -> None:
        self.settings = settings
        self.db = db
        self.radarr = radarr
        self.sonarr = sonarr
        self._lock = asyncio.Semaphore(settings.move_queue.max_concurrent_moves)
        self._last_move: datetime | None = None

    async def process_approved_once(self) -> list[dict[str, Any]]:
        if self.settings.app.dry_run:
            LOG.info("Dry-run enabled; approved moves will not execute")
            return []
        records = self.db.list_records([MoveStatus.APPROVED])
        results = []
        for record in records:
            async with self._lock:
                await self._cooldown()
                results.append(await self._execute(record))
        return results

    async def _cooldown(self) -> None:
        if not self._last_move:
            return
        elapsed = (datetime.now(UTC) - self._last_move).total_seconds()
        wait = self.settings.move_queue.cooldown_seconds - elapsed
        if wait > 0:
            await asyncio.sleep(wait)

    async def _execute(self, record: dict[str, Any]) -> dict[str, Any]:
        record_id = int(record["id"])
        self.db.update_status(record_id, MoveStatus.RUNNING, "Move running")
        self.db.increment_attempts(record_id)
        try:
            if record["app"] == "radarr" and self.radarr:
                result = await self.radarr.move_movie_to_root(
                    int(record["media_id"]), str(record["target_root"])
                )
            elif record["app"] == "sonarr" and self.sonarr:
                result = await self.sonarr.move_series_to_root(
                    int(record["media_id"]), str(record["target_root"])
                )
            else:
                raise RuntimeError("No client configured for move")
            self.db.update_status(
                record_id, result.status, result.reason, None if result.success else result.reason
            )
            self._last_move = datetime.now(UTC)
            return {"id": record_id, "success": result.success, "reason": result.reason}
        except Exception as exc:  # noqa: BLE001
            LOG.exception("Move execution failed for record %s", record_id)
            self.db.update_status(record_id, MoveStatus.FAILED, "Move failed", str(exc))
            return {"id": record_id, "success": False, "reason": str(exc)}

    def retryable_cutoff(self) -> datetime:
        return datetime.now(UTC) - timedelta(
            minutes=self.settings.move_queue.retry_failed_after_minutes
        )
