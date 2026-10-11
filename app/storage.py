"""SQLite persistence for installation configuration and durable state."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "flap_giro_tecnohead.db"

    def _connect(self) -> sqlite3.Connection:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        return db

    async def _run(self, function: Callable[..., T], *args: Any) -> T:
        return await asyncio.to_thread(function, *args)

    async def initialize(self, default_presets: list[dict[str, Any]]) -> None:
        await self._run(self._initialize_sync, default_presets)

    def _initialize_sync(self, default_presets: list[dict[str, Any]]) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS presets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    position REAL NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS event_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    source TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )
            count = db.execute("SELECT COUNT(*) FROM presets").fetchone()[0]
            if count == 0:
                now = utc_now()
                for order, item in enumerate(default_presets):
                    db.execute(
                        "INSERT INTO presets(name, position, sort_order, created_at, updated_at) VALUES(?,?,?,?,?)",
                        (item["name"], float(item["position"]), order, now, now),
                    )

    def _set_json_sync(self, key: str, value: Any) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False, separators=(",", ":"))),
            )

    async def set_json(self, key: str, value: Any) -> None:
        await self._run(self._set_json_sync, key, value)

    def _get_json_sync(self, key: str, default: Any) -> Any:
        with self._connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            if not row:
                return default
            try:
                return json.loads(row["value"])
            except json.JSONDecodeError:
                return default

    async def get_json(self, key: str, default: Any) -> Any:
        return await self._run(self._get_json_sync, key, default)

    def _list_presets_sync(self) -> list[dict[str, Any]]:
        with self._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM presets ORDER BY sort_order, id").fetchall()]

    async def list_presets(self) -> list[dict[str, Any]]:
        return await self._run(self._list_presets_sync)

    def _create_preset_sync(self, name: str, position: float) -> dict[str, Any]:
        with self._connect() as db:
            now = utc_now()
            order = db.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM presets").fetchone()[0]
            cursor = db.execute(
                "INSERT INTO presets(name,position,sort_order,created_at,updated_at) VALUES(?,?,?,?,?)",
                (name, position, order, now, now),
            )
            return dict(db.execute("SELECT * FROM presets WHERE id=?", (cursor.lastrowid,)).fetchone())

    async def create_preset(self, name: str, position: float) -> dict[str, Any]:
        return await self._run(self._create_preset_sync, name, position)

    def _update_preset_sync(self, preset_id: int, values: dict[str, Any]) -> dict[str, Any] | None:
        allowed = {"name", "position", "sort_order"}
        values = {key: value for key, value in values.items() if key in allowed}
        if not values:
            with self._connect() as db:
                row = db.execute("SELECT * FROM presets WHERE id=?", (preset_id,)).fetchone()
                return dict(row) if row else None
        values["updated_at"] = utc_now()
        assignments = ",".join(f"{key}=?" for key in values)
        with self._connect() as db:
            cursor = db.execute(
                f"UPDATE presets SET {assignments} WHERE id=?",
                [*values.values(), preset_id],
            )
            if cursor.rowcount == 0:
                return None
            return dict(db.execute("SELECT * FROM presets WHERE id=?", (preset_id,)).fetchone())

    async def update_preset(self, preset_id: int, values: dict[str, Any]) -> dict[str, Any] | None:
        return await self._run(self._update_preset_sync, preset_id, values)

    def _delete_preset_sync(self, preset_id: int) -> bool:
        with self._connect() as db:
            return db.execute("DELETE FROM presets WHERE id=?", (preset_id,)).rowcount > 0

    async def delete_preset(self, preset_id: int) -> bool:
        return await self._run(self._delete_preset_sync, preset_id)

    def _add_log_sync(self, source: str, event: str, payload: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO event_log(timestamp,source,event,payload) VALUES(?,?,?,?)",
                (utc_now(), source, event, json.dumps(payload, ensure_ascii=False, default=str)),
            )

    async def add_log(self, source: str, event: str, payload: dict[str, Any]) -> None:
        await self._run(self._add_log_sync, source, event, payload)

    def _recent_logs_sync(self, limit: int) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT timestamp,source,event,payload FROM event_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item["payload"])
            except json.JSONDecodeError:
                pass
            result.append(item)
        return result

    async def recent_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        return await self._run(self._recent_logs_sync, max(1, min(limit, 500)))

