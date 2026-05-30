from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from arranger.config import AppConfig, SonarrMoveSafetyConfig
from arranger.models import MediaItem, SafetyMode, SafetyResult
from arranger.safety.common import queue_has_media, validate_common_move


class SonarrSafetyGate:
    def __init__(self, safety_config: SonarrMoveSafetyConfig, app_config: AppConfig) -> None:
        self.safety_config = safety_config
        self.app_config = app_config

    def evaluate(
        self,
        series: MediaItem,
        target_root: str,
        rootfolders: list[dict[str, Any]],
        queue: dict[str, Any] | list[dict[str, Any]],
        episodes: list[dict[str, Any]],
        episode_files: list[dict[str, Any]] | None = None,
    ) -> SafetyResult:
        if not self.safety_config.enabled:
            return SafetyResult(True, "Sonarr safety gate disabled")
        common = validate_common_move(
            target_root=target_root,
            rootfolders=rootfolders,
            current_path=series.path,
            download_temp_paths=self.app_config.download_temp_paths,
        )
        if not common.allowed:
            return common
        if self.safety_config.require_no_active_downloads and queue_has_media(
            queue, "sonarr", series.id
        ):
            return SafetyResult(False, "Sonarr queue has active item for series")
        if (
            self.safety_config.block_if_series_continuing
            and str(series.status).casefold() == "continuing"
        ):
            return SafetyResult(False, "Series is continuing and continuing moves are blocked")
        recent = self._recent_import_block(episode_files or [])
        if recent:
            return recent
        if self.safety_config.mode == SafetyMode.SERIES_COMPLETE_ONLY:
            if str(series.status).casefold() not in {"ended", "complete"}:
                return SafetyResult(False, "Series is not ended/complete")
            return self._all_monitored_have_files(episodes)
        if self.safety_config.mode == SafetyMode.SEASON_COMPLETE_ONLY:
            return self._season_complete(episodes)
        return self._all_available_have_files(episodes)

    def _recent_import_block(self, episode_files: list[dict[str, Any]]) -> SafetyResult | None:
        if self.safety_config.delay_after_last_import_minutes <= 0:
            return None
        cutoff = datetime.now(UTC) - timedelta(
            minutes=self.safety_config.delay_after_last_import_minutes
        )
        for episode_file in episode_files:
            date_str = episode_file.get("dateAdded") or episode_file.get("dateAddedUtc")
            if not date_str:
                continue
            try:
                parsed = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
            except ValueError:
                continue
            if parsed > cutoff:
                return SafetyResult(
                    False, "Recently imported files are inside the safety delay window"
                )
        return None

    def _all_monitored_have_files(self, episodes: list[dict[str, Any]]) -> SafetyResult:
        missing = [e for e in episodes if e.get("monitored") and not e.get("hasFile")]
        if missing and self.safety_config.require_no_missing_monitored_episodes:
            return SafetyResult(False, "Missing monitored episodes")
        return SafetyResult(True, "All monitored episodes have files")

    def _season_complete(self, episodes: list[dict[str, Any]]) -> SafetyResult:
        monitored = [e for e in episodes if e.get("monitored")]
        if not monitored:
            return SafetyResult(True, "No monitored episodes in relevant season")
        current_season = max(int(e.get("seasonNumber") or 0) for e in monitored)
        season_eps = [e for e in monitored if int(e.get("seasonNumber") or 0) == current_season]
        missing = [e for e in season_eps if not e.get("hasFile")]
        if missing:
            return SafetyResult(False, "Missing monitored episodes in current season")
        return SafetyResult(True, "Current season monitored episodes have files")

    def _all_available_have_files(self, episodes: list[dict[str, Any]]) -> SafetyResult:
        now = datetime.now(UTC)
        missing: list[dict[str, Any]] = []
        for episode in episodes:
            if not episode.get("monitored"):
                continue
            air_date = episode.get("airDateUtc") or episode.get("airDate")
            if air_date:
                try:
                    parsed = datetime.fromisoformat(str(air_date).replace("Z", "+00:00"))
                    if parsed > now:
                        continue
                except ValueError:
                    pass
            if not episode.get("hasFile"):
                missing.append(episode)
        if missing and self.safety_config.require_no_missing_monitored_episodes:
            return SafetyResult(False, "Missing monitored available episodes")
        return SafetyResult(True, "All available monitored episodes have files")
