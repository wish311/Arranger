from __future__ import annotations

import logging
from typing import Any

from arranger.clients.radarr import RadarrClient
from arranger.clients.sonarr import SonarrClient
from arranger.config import Settings
from arranger.database import Database
from arranger.models import MediaItem, MoveRecord, MoveStatus
from arranger.rules.engine import RuleEngine
from arranger.safety.radarr import RadarrSafetyGate
from arranger.safety.sonarr import SonarrSafetyGate

LOG = logging.getLogger(__name__)


class AuditService:
    def __init__(
        self,
        settings: Settings,
        db: Database,
        rule_engine: RuleEngine,
        radarr: RadarrClient | None = None,
        sonarr: SonarrClient | None = None,
    ) -> None:
        self.settings = settings
        self.db = db
        self.rule_engine = rule_engine
        self.radarr = radarr
        self.sonarr = sonarr
        self.radarr_gate = RadarrSafetyGate(settings.app)
        self.sonarr_gate = SonarrSafetyGate(settings.sonarr_move_safety, settings.app)

    async def audit_radarr(self, media_id: int | None = None) -> dict[str, Any]:
        if not self.radarr:
            return {"enabled": False, "processed": 0}
        movies = (
            [await self.radarr.get_movie(media_id)] if media_id else await self.radarr.list_movies()
        )
        rootfolders = await self.radarr.get_rootfolders()
        queue = await self.radarr.get_queue()
        results = []
        for raw in movies:
            try:
                results.append(
                    await self._process_radarr_movie(
                        self.radarr.to_media_item(raw), rootfolders, queue
                    )
                )
            except Exception as exc:  # noqa: BLE001 - isolate one bad media item
                LOG.exception("Radarr audit failed for item")
                results.append({"status": "failed", "reason": str(exc)})
        return {"enabled": True, "processed": len(results), "results": results}

    async def audit_sonarr(self, media_id: int | None = None) -> dict[str, Any]:
        if not self.sonarr:
            return {"enabled": False, "processed": 0}
        series_items = (
            [await self.sonarr.get_series(media_id)]
            if media_id
            else await self.sonarr.list_series()
        )
        rootfolders = await self.sonarr.get_rootfolders()
        queue = await self.sonarr.get_queue()
        results = []
        for raw in series_items:
            try:
                item = self.sonarr.to_media_item(raw)
                episodes = await self.sonarr.get_episodes(item.id)
                episode_files = await self.sonarr.get_episode_files(item.id)
                results.append(
                    await self._process_sonarr_series(
                        item, rootfolders, queue, episodes, episode_files
                    )
                )
            except Exception as exc:  # noqa: BLE001
                LOG.exception("Sonarr audit failed for item")
                results.append({"status": "failed", "reason": str(exc)})
        return {"enabled": True, "processed": len(results), "results": results}

    async def _process_radarr_movie(
        self,
        item: MediaItem,
        rootfolders: list[dict[str, Any]],
        queue: dict[str, Any] | list[dict[str, Any]],
    ) -> dict[str, Any]:
        match = self.rule_engine.match("radarr", item)
        if not match.matched or not match.target_root:
            return self._skip(item, match.reason or "No rule")
        if self._already_correct(item, match.target_root):
            return self._skip(item, "Already in target root")
        if self.settings.app.dry_run:
            return self._record_dry_run(item, match.rule_name or "unknown", match.target_root)
        safety = self.radarr_gate.evaluate(item, match.target_root, rootfolders, queue)
        if not safety.allowed:
            return self._record_blocked(
                item, match.rule_name or "unknown", match.target_root, safety.reason
            )
        return self._record_pending_or_approved(
            item, match.rule_name or "unknown", match.target_root, safety.reason
        )

    async def _process_sonarr_series(
        self,
        item: MediaItem,
        rootfolders: list[dict[str, Any]],
        queue: dict[str, Any] | list[dict[str, Any]],
        episodes: list[dict[str, Any]],
        episode_files: list[dict[str, Any]],
    ) -> dict[str, Any]:
        match = self.rule_engine.match("sonarr", item)
        if not match.matched or not match.target_root:
            return self._skip(item, match.reason or "No rule")
        if self._already_correct(item, match.target_root):
            return self._skip(item, "Already in target root")
        if self.settings.app.dry_run:
            return self._record_dry_run(item, match.rule_name or "unknown", match.target_root)
        safety = self.sonarr_gate.evaluate(
            item, match.target_root, rootfolders, queue, episodes, episode_files
        )
        if not safety.allowed:
            return self._record_blocked(
                item, match.rule_name or "unknown", match.target_root, safety.reason
            )
        return self._record_pending_or_approved(
            item, match.rule_name or "unknown", match.target_root, safety.reason
        )

    def _already_correct(self, item: MediaItem, target_root: str) -> bool:
        root = item.root_folder_path or ""
        return root.rstrip("/") == target_root.rstrip("/") or item.path.rstrip("/").startswith(
            target_root.rstrip("/") + "/"
        )

    def _skip(self, item: MediaItem, reason: str) -> dict[str, Any]:
        LOG.info("[SKIP] %s %s: %s", item.app.value, item.title, reason)
        return {"media_id": item.id, "title": item.title, "status": "skipped", "reason": reason}

    def _record_dry_run(self, item: MediaItem, rule_name: str, target_root: str) -> dict[str, Any]:
        LOG.info(
            "[DRY RUN] %s would be moved: Title=%s From=%s To root=%s Matched Rule=%s",
            item.app.value.title(),
            item.title,
            item.path,
            target_root,
            rule_name,
        )
        record_id = self.db.add_move(
            self._record(
                item, rule_name, target_root, MoveStatus.DRY_RUN, "Dry-run blocks real move"
            )
        )
        return {
            "id": record_id,
            "media_id": item.id,
            "status": MoveStatus.DRY_RUN.value,
            "reason": "Dry-run blocks real move",
        }

    def _record_blocked(
        self, item: MediaItem, rule_name: str, target_root: str, reason: str
    ) -> dict[str, Any]:
        LOG.warning(
            "[BLOCKED] %s not safe to move: Title=%s Matched Rule=%s Reason=%s",
            item.app.value.title(),
            item.title,
            rule_name,
            reason,
        )
        record_id = self.db.add_move(
            self._record(item, rule_name, target_root, MoveStatus.BLOCKED, reason)
        )
        return {
            "id": record_id,
            "media_id": item.id,
            "status": MoveStatus.BLOCKED.value,
            "reason": reason,
        }

    def _record_pending_or_approved(
        self, item: MediaItem, rule_name: str, target_root: str, reason: str
    ) -> dict[str, Any]:
        status = MoveStatus.PENDING if self.settings.app.manual_approval else MoveStatus.APPROVED
        record_id = self.db.add_move(self._record(item, rule_name, target_root, status, reason))
        LOG.info(
            "[QUEUED] %s %s status=%s reason=%s", item.app.value, item.title, status.value, reason
        )
        return {"id": record_id, "media_id": item.id, "status": status.value, "reason": reason}

    def _record(
        self, item: MediaItem, rule_name: str, target_root: str, status: MoveStatus, reason: str
    ) -> MoveRecord:
        return MoveRecord(
            app=item.app,
            media_id=item.id,
            title=item.title,
            current_path=item.path,
            target_root=target_root,
            matched_rule=rule_name,
            status=status,
            reason=reason,
        )
