from __future__ import annotations

from typing import Any

from arranger.config import AppConfig
from arranger.models import MediaItem, SafetyResult
from arranger.safety.common import queue_has_media, validate_common_move


class RadarrSafetyGate:
    def __init__(self, app_config: AppConfig) -> None:
        self.app_config = app_config

    def evaluate(
        self,
        movie: MediaItem,
        target_root: str,
        rootfolders: list[dict[str, Any]],
        queue: dict[str, Any] | list[dict[str, Any]],
    ) -> SafetyResult:
        common = validate_common_move(
            target_root=target_root,
            rootfolders=rootfolders,
            current_path=movie.path,
            download_temp_paths=self.app_config.download_temp_paths,
        )
        if not common.allowed:
            return common
        if not movie.downloaded:
            return SafetyResult(False, "Movie is not downloaded/imported")
        if queue_has_media(queue, "radarr", movie.id):
            return SafetyResult(False, "Radarr queue has active item for movie")
        return SafetyResult(True, "Radarr movie is safe to move")
