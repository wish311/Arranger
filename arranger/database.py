from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from arranger.models import MoveRecord, MoveStatus


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS move_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    app TEXT NOT NULL,
                    media_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    current_path TEXT NOT NULL,
                    target_root TEXT NOT NULL,
                    target_path TEXT,
                    matched_rule TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_error TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_move_records_status ON move_records(status)"
            )
            conn.commit()

    def add_move(self, record: MoveRecord) -> int:
        now = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO move_records
                (app, media_id, title, current_path, target_root, target_path, matched_rule,
                 status, reason, attempts, created_at, updated_at, last_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.app.value,
                    record.media_id,
                    record.title,
                    record.current_path,
                    record.target_root,
                    record.target_path,
                    record.matched_rule,
                    record.status.value,
                    record.reason,
                    record.attempts,
                    now,
                    now,
                    record.last_error,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def update_status(
        self,
        record_id: int,
        status: MoveStatus,
        reason: str | None = None,
        last_error: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE move_records
                SET status = ?, reason = COALESCE(?, reason), last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status.value,
                    reason,
                    last_error,
                    datetime.now(UTC).isoformat(),
                    record_id,
                ),
            )
            conn.commit()

    def increment_attempts(self, record_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE move_records SET attempts = attempts + 1, updated_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), record_id),
            )
            conn.commit()

    def list_records(self, statuses: Iterable[MoveStatus] | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if statuses:
                values = [s.value for s in statuses]
                placeholders = ",".join("?" for _ in values)
                rows = conn.execute(
                    f"SELECT * FROM move_records WHERE status IN ({placeholders}) ORDER BY id DESC",
                    values,
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM move_records ORDER BY id DESC").fetchall()
            return [dict(row) for row in rows]

    def get_record(self, record_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM move_records WHERE id = ?", (record_id,)).fetchone()
            return dict(row) if row else None

    def healthcheck(self) -> bool:
        with self.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
