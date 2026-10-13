"""Small Home Assistant Core API client used by the linked-TV adapter."""

from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urlunsplit
from typing import Any

try:
    import websockets
except ImportError:  # pragma: no cover
    websockets = None  # type: ignore[assignment]


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

    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Any:
        payload = dict(data or {})
        if entity_id:
            payload["entity_id"] = entity_id
        return await asyncio.to_thread(
            self._request_sync,
            f"/core/api/services/{domain}/{service}",
            "POST",
            payload,
        )

    async def reload_universal_media_players(self) -> Any:
        """Apply the app-managed Universal Media Player YAML immediately."""

        return await self.call_service("universal", "reload")

    def _websocket_url(self) -> str:
        parsed = urlsplit(self.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        path = f"{parsed.path.rstrip('/')}/core/api/websocket"
        return urlunsplit((scheme, parsed.netloc, path, "", ""))

    async def _websocket_command(self, payload: dict[str, Any]) -> Any:
        if not self.token:
            raise HomeAssistantError("Home Assistant Supervisor token is not available")
        if websockets is None:
            raise HomeAssistantError("A dependência WebSocket do Home Assistant não está disponível")

        async def receive(socket: Any) -> dict[str, Any]:
            raw = await asyncio.wait_for(socket.recv(), timeout=self.timeout)
            try:
                value = json.loads(raw)
            except (TypeError, json.JSONDecodeError) as exc:
                raise HomeAssistantError("Resposta inválida do WebSocket do Home Assistant") from exc
            if not isinstance(value, dict):
                raise HomeAssistantError("Resposta inválida do WebSocket do Home Assistant")
            return value

        try:
            async with websockets.connect(
                self._websocket_url(),
                open_timeout=self.timeout,
                close_timeout=self.timeout,
            ) as socket:
                hello = await receive(socket)
                if hello.get("type") != "auth_required":
                    raise HomeAssistantError("Home Assistant não iniciou a autenticação WebSocket")
                await socket.send(json.dumps({"type": "auth", "access_token": self.token}))
                auth = await receive(socket)
                if auth.get("type") != "auth_ok":
                    error = auth.get("message") or "autenticação recusada"
                    raise HomeAssistantError(f"Autenticação WebSocket recusada: {error}")

                command = {"id": 1, **payload}
                await socket.send(json.dumps(command))
                while True:
                    response = await receive(socket)
                    if response.get("id") != 1:
                        continue
                    if not response.get("success"):
                        error = response.get("error") or {}
                        raise HomeAssistantError(str(error.get("message") or "Comando WebSocket recusado"))
                    return response.get("result")
        except HomeAssistantError:
            raise
        except Exception as exc:
            raise HomeAssistantError(str(exc)) from exc

    async def update_entity_registry(
        self,
        entity_id: str,
        *,
        name: str | None = None,
        new_entity_id: str | None = None,
        area_id: str | None = None,
        hidden_by: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": "config/entity_registry/update",
            "entity_id": entity_id,
        }
        if name is not None:
            payload["name"] = name
        if new_entity_id is not None:
            payload["new_entity_id"] = new_entity_id
        if area_id is not None:
            payload["area_id"] = area_id
        if hidden_by is not None:
            payload["hidden_by"] = hidden_by
        result = await self._websocket_command(payload)
        return result if isinstance(result, dict) else {}

    async def remove_entity_registry(self, entity_id: str) -> None:
        await self._websocket_command(
            {"type": "config/entity_registry/remove", "entity_id": entity_id}
        )

    async def get_entity_registry(self, entity_id: str) -> dict[str, Any]:
        result = await self._websocket_command(
            {"type": "config/entity_registry/get", "entity_id": entity_id}
        )
        return result if isinstance(result, dict) else {}

