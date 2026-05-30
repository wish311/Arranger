from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException, Request


def extract_media_id(payload: dict[str, Any], app: str) -> int | None:
    candidates: list[Any] = []
    if app == "radarr":
        candidates.extend([payload.get("movieId"), payload.get("movie", {}).get("id")])
    else:
        candidates.extend([payload.get("seriesId"), payload.get("series", {}).get("id")])
    for value in candidates:
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None


async def verify_webhook_secret(
    request: Request,
    expected: str | None,
    require_secret: bool,
    header_secret: str | None = Header(default=None, alias="X-Arranger-Secret"),
) -> None:
    if not require_secret:
        return
    query_secret = request.query_params.get("secret")
    if not expected or (header_secret != expected and query_secret != expected):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")
