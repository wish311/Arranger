from __future__ import annotations

from typing import Any

from arranger.clients.base import ArrClient
from arranger.config import ArrConfig
from arranger.models import AppName, MediaItem, MoveResult, MoveStatus


class SonarrClient(ArrClient):
    def __init__(self, config: ArrConfig) -> None:
        super().__init__(config, "sonarr")

    async def list_series(self) -> list[dict[str, Any]]:
        data = await self.request("GET", "/api/v3/series")
        if not isinstance(data, list):
            raise TypeError("Sonarr series schema mismatch")
        return data

    async def get_series(self, series_id: int) -> dict[str, Any]:
        data = await self.request("GET", f"/api/v3/series/{series_id}")
        if not isinstance(data, dict):
            raise TypeError("Sonarr series schema mismatch")
        return data

    async def get_episodes(self, series_id: int) -> list[dict[str, Any]]:
        data = await self.request("GET", "/api/v3/episode", params={"seriesId": series_id})
        if not isinstance(data, list):
            raise TypeError("Sonarr episode schema mismatch")
        return data

    async def get_episode_files(self, series_id: int) -> list[dict[str, Any]]:
        data = await self.request("GET", "/api/v3/episodefile", params={"seriesId": series_id})
        if not isinstance(data, list):
            raise TypeError("Sonarr episode file schema mismatch")
        return data

    def to_media_item(self, series: dict[str, Any]) -> MediaItem:
        return MediaItem(
            app=AppName.SONARR,
            id=int(series["id"]),
            title=str(series.get("title") or series["id"]),
            path=str(series.get("path") or ""),
            root_folder_path=series.get("rootFolderPath"),
            genres=list(series.get("genres") or []),
            tags=list(series.get("tags") or []),
            monitored=series.get("monitored"),
            downloaded=bool(series.get("statistics", {}).get("episodeFileCount", 0)),
            certification=series.get("certification") or series.get("contentRating"),
            status=series.get("status"),
            tvdb_id=series.get("tvdbId"),
            imdb_id=series.get("imdbId"),
            raw=series,
        )

    async def move_series_to_root(self, series_id: int, target_root: str) -> MoveResult:
        series = await self.get_series(series_id)
        rootfolders = await self.get_rootfolders()
        failed = await self.validate_move_prereqs(series, rootfolders, target_root)
        if failed:
            return failed
        target_path = self.compute_target_path(str(series["path"]), target_root)
        updated = dict(series)
        updated["rootFolderPath"] = target_root
        updated["path"] = target_path
        response = await self.request(
            "PUT", f"/api/v3/series/{series_id}", params={"moveFiles": "true"}, json=updated
        )
        if not self.verify_move_response(response, target_path):
            return MoveResult(
                False, MoveStatus.FAILED, "Sonarr move response schema mismatch", target_path
            )
        await self.trigger_command("RefreshSeries", seriesId=series_id)
        return MoveResult(
            True, MoveStatus.COMPLETED, "Sonarr series moved through API", target_path, response
        )
