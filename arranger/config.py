from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from arranger.models import SafetyMode


class AppConfig(BaseModel):
    name: str = "Arranger"
    dry_run: bool = True
    log_level: str = "info"
    database_path: str = "/data/arranger.db"
    bind_host: str = "0.0.0.0"
    bind_port: int = 8787
    manual_approval: bool = False
    download_temp_paths: list[str] = Field(
        default_factory=lambda: ["/downloads", "/download", "/tmp"]
    )


class ArrConfig(BaseModel):
    enabled: bool = True
    url: str
    api_key: str
    webhook_secret: str | None = None
    api_key_style: Literal["header", "query"] = "header"


class RuleConfig(BaseModel):
    name: str
    priority: int = 0
    target_root: str
    default: bool = False
    match_genres: list[str] = Field(default_factory=list)
    match_tags: list[str] = Field(default_factory=list)
    match_certifications: list[str] = Field(default_factory=list)
    title_regex: str | None = None
    monitored: bool | None = None
    path_contains: list[str] = Field(default_factory=list)
    match_fields: dict[str, Any] = Field(default_factory=dict)


class RulesConfig(BaseModel):
    radarr: list[RuleConfig] = Field(default_factory=list)
    sonarr: list[RuleConfig] = Field(default_factory=list)
    allow_first_equal_priority_match: bool = False


class SonarrMoveSafetyConfig(BaseModel):
    enabled: bool = True
    mode: SafetyMode = SafetyMode.ALL_AVAILABLE_EPISODES
    require_no_active_downloads: bool = True
    require_no_missing_monitored_episodes: bool = True
    require_series_refresh_before_check: bool = True
    delay_after_last_import_minutes: int = 30
    block_if_series_continuing: bool = False
    allow_move_if_continuing_but_all_available_complete: bool = True


class MoveQueueConfig(BaseModel):
    enabled: bool = True
    max_concurrent_moves: int = 1
    cooldown_seconds: int = 60
    retry_failed_after_minutes: int = 60
    max_attempts: int = 3


class SchedulerConfig(BaseModel):
    enabled: bool = True
    audit_interval_minutes: int = 60
    pending_move_check_minutes: int = 30


class LoggingConfig(BaseModel):
    file: str = "/logs/arranger.log"
    log_decisions: bool = True
    log_skipped_items: bool = True
    log_api_errors: bool = True


class WebhooksConfig(BaseModel):
    enabled: bool = True
    require_secret: bool = False


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app: AppConfig = Field(default_factory=AppConfig)
    radarr: ArrConfig | None = None
    sonarr: ArrConfig | None = None
    rules: RulesConfig = Field(default_factory=RulesConfig)
    sonarr_move_safety: SonarrMoveSafetyConfig = Field(default_factory=SonarrMoveSafetyConfig)
    move_queue: MoveQueueConfig = Field(default_factory=MoveQueueConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    webhooks: WebhooksConfig = Field(default_factory=WebhooksConfig)

    @field_validator("radarr", "sonarr")
    @classmethod
    def disabled_arr_can_be_missing_key(cls, value: ArrConfig | None) -> ArrConfig | None:
        if value and value.enabled and not value.api_key:
            raise ValueError("enabled Arr app requires api_key")
        return value


def load_settings(path: str | None = None) -> Settings:
    config_path = Path(path or os.getenv("ARRANGER_CONFIG", "config/arranger.example.yaml"))
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    data = yaml.safe_load(config_path.read_text()) or {}
    return Settings.model_validate(data)
