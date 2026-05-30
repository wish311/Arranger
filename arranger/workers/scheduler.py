from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from arranger.config import Settings
from arranger.services.audit import AuditService
from arranger.services.moves import MoveExecutor

LOG = logging.getLogger(__name__)


class AsyncScheduler:
    def __init__(self, settings: Settings, audit: AuditService, moves: MoveExecutor) -> None:
        self.settings = settings
        self.audit = audit
        self.moves = moves
        self._tasks: list[asyncio.Task[None]] = []
        self._stopped = asyncio.Event()

    def start(self) -> None:
        if not self.settings.scheduler.enabled:
            return
        self._tasks = [
            asyncio.create_task(self._audit_loop(), name="audit-loop"),
            asyncio.create_task(self._move_loop(), name="move-loop"),
        ]

    async def stop(self) -> None:
        self._stopped.set()
        for task in self._tasks:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def _audit_loop(self) -> None:
        interval = self.settings.scheduler.audit_interval_minutes * 60
        while not self._stopped.is_set():
            try:
                await self.audit.audit_radarr()
                await self.audit.audit_sonarr()
            except Exception:  # noqa: BLE001
                LOG.exception("Scheduled audit failed")
            await asyncio.sleep(interval)

    async def _move_loop(self) -> None:
        interval = self.settings.scheduler.pending_move_check_minutes * 60
        while not self._stopped.is_set():
            try:
                await self.moves.process_approved_once()
            except Exception:  # noqa: BLE001
                LOG.exception("Scheduled move processing failed")
            await asyncio.sleep(interval)
