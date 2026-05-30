from __future__ import annotations

import copy
import hashlib
import hmac
import os
from pathlib import Path
from typing import Any

import yaml

from arranger.config import Settings

MASK = "********"
LIVE_CONFIRMATION = "ENABLE LIVE MOVES"


def config_path() -> Path:
    return Path(os.getenv("ARRANGER_CONFIG", "config/arranger.example.yaml"))


def mask_secret(value: str | None) -> str | None:
    if not value:
        return value
    if len(value) <= 8:
        return MASK
    return f"{value[:6]}{MASK}{value[-3:]}"


def is_masked(value: Any) -> bool:
    return isinstance(value, str) and MASK in value


def settings_to_safe_dict(settings: Settings) -> dict[str, Any]:
    data = settings.model_dump(mode="json")
    for section in ("radarr", "sonarr"):
        if data.get(section):
            data[section]["api_key"] = mask_secret(data[section].get("api_key"))
            data[section]["webhook_secret"] = mask_secret(data[section].get("webhook_secret"))
    if data.get("app", {}).get("ui_password_hash"):
        data["app"]["ui_password_hash"] = MASK
    return data


def load_raw_config(path: Path | None = None) -> dict[str, Any]:
    target = path or config_path()
    if not target.exists():
        return {}
    return yaml.safe_load(target.read_text()) or {}


def deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def merge_preserving_secrets(existing: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    cleaned = copy.deepcopy(updates)
    for section in ("radarr", "sonarr"):
        if section in cleaned and isinstance(cleaned[section], dict):
            for field in ("api_key", "webhook_secret"):
                if is_masked(cleaned[section].get(field)):
                    cleaned[section].pop(field)
    if isinstance(cleaned.get("app"), dict) and is_masked(cleaned["app"].get("ui_password_hash")):
        cleaned["app"].pop("ui_password_hash")
    return deep_merge(existing, cleaned)


def validate_live_mode_change(
    current: Settings, proposed: dict[str, Any], confirmation: str | None
) -> None:
    new_dry_run = proposed.get("app", {}).get("dry_run", current.app.dry_run)
    if current.app.dry_run and new_dry_run is False and confirmation != LIVE_CONFIRMATION:
        raise ValueError("Disabling dry-run requires typing ENABLE LIVE MOVES")


def save_config(
    updates: dict[str, Any], current: Settings, confirmation: str | None = None
) -> Settings:
    path = config_path()
    existing = load_raw_config(path)
    validate_live_mode_change(current, updates, confirmation)
    merged = merge_preserving_secrets(existing, updates)
    next_settings = Settings.model_validate(merged)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(next_settings.model_dump(mode="json"), sort_keys=False))
    return next_settings


def hash_password(password: str) -> str:
    digest = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return f"sha256${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash or stored_hash == "CHANGE_ME":
        return False
    if stored_hash.startswith("sha256$"):
        expected = hash_password(password)
        return hmac.compare_digest(expected, stored_hash)
    return False
