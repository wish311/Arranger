from __future__ import annotations

from typing import Any

from arranger.clients.base import ArrClient
from arranger.config import ArrConfig
from arranger.models import AppName, MediaItem, MoveResult, MoveStatus


class RadarrClient(ArrClient):
    def __init__(self, config: ArrConfig) -> None:
        super().__init__(config, "radarr")

    async def list_movies(self) -> list[dict[str, Any]]:
        data = await self.request("GET", "/api/v3/movie")
        if not isinstance(data, list):
            raise TypeError("Radarr movie schema mismatch")
        return data

    async def get_movie(self, movie_id: int) -> dict[str, Any]:
        data = await self.request("GET", f"/api/v3/movie/{movie_id}")
        if not isinstance(data, dict):
            raise TypeError("Radarr movie schema mismatch")
        return data

    def to_media_item(self, movie: dict[str, Any]) -> MediaItem:
        movie_file = movie.get("movieFile") or {}
        return MediaItem(
            app=AppName.RADARR,
            id=int(movie["id"]),
            title=str(movie.get("title") or movie.get("sortTitle") or movie["id"]),
            path=str(movie.get("path") or ""),
            root_folder_path=movie.get("rootFolderPath"),
            genres=list(movie.get("genres") or []),
            tags=list(movie.get("tags") or []),
            monitored=movie.get("monitored"),
            downloaded=bool(movie.get("hasFile") or movie_file),
            certification=movie.get("certification")
            or movie.get("ratings", {}).get("mpaa", {}).get("value"),
            tmdb_id=movie.get("tmdbId"),
            imdb_id=movie.get("imdbId"),
            raw=movie,
        )

    async def move_movie_to_root(self, movie_id: int, target_root: str) -> MoveResult:
        movie = await self.get_movie(movie_id)
        rootfolders = await self.get_rootfolders()
        failed = await self.validate_move_prereqs(movie, rootfolders, target_root)
        if failed:
            return failed
        target_path = self.compute_target_path(str(movie["path"]), target_root)
        updated = dict(movie)
        updated["rootFolderPath"] = target_root
        updated["path"] = target_path
        response = await self.request(
            "PUT", f"/api/v3/movie/{movie_id}", params={"moveFiles": "true"}, json=updated
        )
        if not self.verify_move_response(response, target_path):
            return MoveResult(
                False, MoveStatus.FAILED, "Radarr move response schema mismatch", target_path
            )
        await self.trigger_command("RefreshMovie", movieIds=[movie_id])
        return MoveResult(
            True, MoveStatus.COMPLETED, "Radarr movie moved through API", target_path, response
        )
