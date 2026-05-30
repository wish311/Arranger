from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from arranger.clients.radarr import RadarrClient
from arranger.clients.sonarr import SonarrClient
from arranger.config import Settings
from arranger.database import Database

LOG = logging.getLogger(__name__)


class HealthService:
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

    async def startup_check(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "database": False,
            "log_file": False,
            "radarr": None,
            "sonarr": None,
        }
        result["database"] = self.db.healthcheck()
        log_path = Path(self.settings.logging.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as handle:
            handle.write("")
        result["log_file"] = True
        if self.radarr:
            try:
                result["radarr"] = await self.radarr.healthcheck()
            except Exception as exc:  # noqa: BLE001
                LOG.error("Radarr startup check failed: %s", exc)
                result["radarr"] = {"ok": False, "error": str(exc)}
        if self.sonarr:
            try:
                result["sonarr"] = await self.sonarr.healthcheck()
            except Exception as exc:  # noqa: BLE001
                LOG.error("Sonarr startup check failed: %s", exc)
                result["sonarr"] = {"ok": False, "error": str(exc)}
        LOG.info("Startup status: %s", result)
        return result
