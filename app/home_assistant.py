"""Small Home Assistant Core API client used by the linked-TV adapter."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any


class HomeAssistantError(RuntimeError):
    pass


class HomeAssistantClient:
    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: float = 5.0):
        self.base_url = (base_url or os.getenv("SUPERVISOR_URL", "http://supervisor")).rstrip("/")
        self.token = token or os.getenv("SUPERVISOR_TOKEN") or os.getenv("HASSIO_TOKEN")
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _request_sync(self, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> Any:
        if not self.token:
            raise HomeAssistantError("Home Assistant Supervisor token is not available")
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8")) if raw else None
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            raise HomeAssistantError(str(exc)) from exc

    async def get_state(self, entity_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._request_sync, f"/core/api/states/{entity_id}")

    async def list_states(self) -> list[dict[str, Any]]:
        value = await asyncio.to_thread(self._request_sync, "/core/api/states")
        return value if isinstance(value, list) else []

    async def list_media_players(self) -> list[dict[str, Any]]:
        return [item for item in await self.list_states() if str(item.get("entity_id", "")).startswith("media_player.")]

    async def call_service(self, domain: str, service: str, entity_id: str) -> Any:
        return await asyncio.to_thread(
            self._request_sync,
            f"/core/api/services/{domain}/{service}",
            "POST",
            {"entity_id": entity_id},
        )

