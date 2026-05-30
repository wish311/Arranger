from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class AppName(StrEnum):
    RADARR = "radarr"
    SONARR = "sonarr"


class MoveStatus(StrEnum):
    PENDING = "pending"
    BLOCKED = "blocked"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DRY_RUN = "dry_run"
    CANCELED = "canceled"


class SafetyMode(StrEnum):
    SERIES_COMPLETE_ONLY = "series_complete_only"
    SEASON_COMPLETE_ONLY = "season_complete_only"
    ALL_AVAILABLE_EPISODES = "all_available_episodes"


@dataclass(slots=True)
class MediaItem:
    app: AppName
    id: int
    title: str
    path: str
    root_folder_path: str | None = None
    genres: list[str] = field(default_factory=list)
    tags: list[str | int] = field(default_factory=list)
    monitored: bool | None = None
    downloaded: bool | None = None
    certification: str | None = None
    status: str | None = None
    tmdb_id: int | None = None
    tvdb_id: int | None = None
    imdb_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RuleMatch:
    matched: bool
    rule_name: str | None = None
    target_root: str | None = None
    reason: str | None = None
    conflict: bool = False


@dataclass(slots=True)
class SafetyResult:
    allowed: bool
    reason: str


@dataclass(slots=True)
class MoveResult:
    success: bool
    status: MoveStatus
    reason: str
    target_path: str | None = None
    api_response: dict[str, Any] | None = None


@dataclass(slots=True)
class MoveRecord:
    app: AppName
    media_id: int
    title: str
    current_path: str
    target_root: str
    matched_rule: str
    status: MoveStatus
    reason: str
    target_path: str | None = None
    attempts: int = 0
    last_error: str | None = None
    id: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
