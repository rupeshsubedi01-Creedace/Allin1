"""Thread-safe SQLite-backed history store."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT,
    platform_key TEXT,
    platform_label TEXT,
    thumbnail TEXT,
    format_id TEXT,
    media_type TEXT,
    ext TEXT,
    filepath TEXT,
    filesize INTEGER,
    status TEXT NOT NULL,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_history_created_at ON history (created_at DESC);
"""


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class HistoryStore:
    """A minimal, thread-safe wrapper around a SQLite history table."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def create(
        self,
        *,
        url: str,
        title: str | None,
        platform_key: str | None,
        platform_label: str | None,
        thumbnail: str | None,
        format_id: str | None,
        media_type: str | None,
        ext: str | None,
        status: str = "queued",
        job_id: str | None = None,
    ) -> dict[str, Any]:
        record_id = job_id or str(uuid.uuid4())
        ts = now_iso()
        row = {
            "id": record_id,
            "url": url,
            "title": title,
            "platform_key": platform_key,
            "platform_label": platform_label,
            "thumbnail": thumbnail,
            "format_id": format_id,
            "media_type": media_type,
            "ext": ext,
            "filepath": None,
            "filesize": None,
            "status": status,
            "error_message": None,
            "created_at": ts,
            "updated_at": ts,
        }
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO history (
                    id, url, title, platform_key, platform_label, thumbnail,
                    format_id, media_type, ext, filepath, filesize, status,
                    error_message, created_at, updated_at
                ) VALUES (
                    :id, :url, :title, :platform_key, :platform_label, :thumbnail,
                    :format_id, :media_type, :ext, :filepath, :filesize, :status,
                    :error_message, :created_at, :updated_at
                )
                """,
                row,
            )
            self._conn.commit()
        return row

    def update(self, record_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = now_iso()
        set_clause = ", ".join(f"{k} = :{k}" for k in fields)
        fields["id"] = record_id
        with self._lock:
            self._conn.execute(f"UPDATE history SET {set_clause} WHERE id = :id", fields)
            self._conn.commit()

    def get(self, record_id: str) -> dict[str, Any] | None:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM history WHERE id = ?", (record_id,))
            row = cur.fetchone()
        return dict(row) if row else None

    def list_all(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM history ORDER BY created_at DESC LIMIT ?", (limit,)
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def delete(self, record_id: str) -> dict[str, Any] | None:
        row = self.get(record_id)
        if row is None:
            return None
        with self._lock:
            self._conn.execute("DELETE FROM history WHERE id = ?", (record_id,))
            self._conn.commit()
        return row

    def delete_all(self) -> list[dict[str, Any]]:
        rows = self.list_all(limit=10_000)
        with self._lock:
            self._conn.execute("DELETE FROM history")
            self._conn.commit()
        return rows
