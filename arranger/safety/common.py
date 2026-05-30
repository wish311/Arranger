from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from arranger.models import SafetyResult

ACTIVE_QUEUE_STATES = {"downloading", "downloadclientunavailable", "importing", "queued", "paused"}


def path_is_inside_any(path: str, roots: list[str]) -> bool:
    normalized = PurePosixPath(path)
    for root in roots:
        try:
            normalized.relative_to(PurePosixPath(root))
            return True
        except ValueError:
            continue
    return False


def root_exists(target_root: str, rootfolders: list[dict[str, Any]]) -> bool:
    return any(
        str(folder.get("path", "")).rstrip("/") == target_root.rstrip("/") for folder in rootfolders
    )


def queue_has_media(queue: dict[str, Any] | list[dict[str, Any]], app: str, media_id: int) -> bool:
    records = queue.get("records", []) if isinstance(queue, dict) else queue
    for record in records:
        status = str(record.get("status") or record.get("trackedDownloadStatus") or "").casefold()
        if status and status not in ACTIVE_QUEUE_STATES:
            continue
        if app == "radarr" and (
            record.get("movieId") == media_id or record.get("movie", {}).get("id") == media_id
        ):
            return True
        if app == "sonarr" and (
            record.get("seriesId") == media_id or record.get("series", {}).get("id") == media_id
        ):
            return True
    return False


def validate_common_move(
    *,
    target_root: str,
    rootfolders: list[dict[str, Any]],
    current_path: str,
    download_temp_paths: list[str],
) -> SafetyResult:
    if not root_exists(target_root, rootfolders):
        return SafetyResult(False, f"Target root not found in Arr root folders: {target_root}")
    if path_is_inside_any(current_path, download_temp_paths):
        return SafetyResult(False, "Current path is inside a configured download/temp folder")
    return SafetyResult(True, "Common safety checks passed")
