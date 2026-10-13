from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

try:
    from aiomqtt import Client, MqttError
except ImportError:  # pragma: no cover
    Client = None  # type: ignore[assignment,misc]

    class MqttError(Exception):
        pass

LOGGER = logging.getLogger("flap_giro_tecnohead.mqtt")


class MqttBridge:
    def __init__(
        self,
        discovery_prefix: str,
        state_snapshot: Callable[[], Awaitable[dict[str, Any]]],
        on_command: Callable[[str, str], Awaitable[None]],
    ):
        self.discovery_prefix = discovery_prefix.strip("/") or "homeassistant"
        self.state_snapshot = state_snapshot
        self.on_command = on_command
        self.host = os.getenv("MQTT_HOST")
        self.port = int(os.getenv("MQTT_PORT", "1883"))
        self.username = os.getenv("MQTT_USER") or None
        self.password = os.getenv("MQTT_PASSWORD") or None
        self.base = "flap_giro_tecnohead"
        self.task: asyncio.Task | None = None
        self.client: Any | None = None
        self.connected = False
        self.last_error: str | None = None
        self.last_connected: str | None = None

    @property
    def available(self) -> bool:
        return bool(self.host and Client)

    async def start(self) -> None:
        if self.available:
            self.task = asyncio.create_task(self._run(), name="flap-mqtt")

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
        self.connected = False

    async def _run(self) -> None:
        while True:
            try:
                async with Client(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    identifier="flap-giro-tecnohead",
                ) as client:
                    self.client = client
                    self.connected = True
                    self.last_connected = datetime.now(UTC).isoformat()
                    self.last_error = None
                    await self._publish_discovery(client)
                    await client.subscribe(f"{self.base}/media/set")
                    await client.subscribe(f"{self.base}/media/source")
                    await client.subscribe(f"{self.base}/control/+")
                    await client.subscribe(f"{self.base}/position/set")
                    await client.subscribe(f"{self.base}/preset/set")
                    await self._publish_state(client)
                    async for message in client.messages:
                        topic = str(message.topic)
                        payload = message.payload.decode("utf-8", errors="replace") if isinstance(message.payload, bytes) else str(message.payload)
                        if topic == f"{self.base}/media/set":
                            await self.on_command("media", payload)
                        elif topic == f"{self.base}/media/source":
                            await self.on_command("source", payload)
                        elif topic.startswith(f"{self.base}/control/"):
                            await self.on_command(topic.rsplit("/", 1)[1], payload)
                        elif topic == f"{self.base}/position/set":
                            await self.on_command("position", payload)
                        elif topic == f"{self.base}/preset/set":
                            await self.on_command("preset", payload)
                        await self._publish_state(client)
            except asyncio.CancelledError:
                raise
            except (MqttError, OSError, ValueError) as exc:
                self.last_error = str(exc)
                LOGGER.warning("MQTT disconnected: %s", exc)
            finally:
                self.connected = False
                self.client = None
            await asyncio.sleep(10)

    async def _publish(self, client: Any, topic: str, value: Any, *, retain: bool = True) -> None:
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        await client.publish(topic, value, qos=1, retain=retain)

    async def _publish_discovery(self, client: Any) -> None:
        base = self.base
        snapshot = await self.state_snapshot()
        config = snapshot.get("config", {})
        friendly_name = str(config.get("tv_friendly_name") or "Flap de Giro Tecnohead")
        device = {
            "identifiers": [base],
            "name": friendly_name,
            "manufacturer": "Tecnohead",
            "model": "Flap de Giro",
            "sw_version": os.getenv("APP_VERSION", "0.1.0-alpha.26"),
        }
        # The composite TV is managed by Home Assistant's Universal Media
        # Player YAML, which the app creates and reloads automatically. Clear
        # the old retained MQTT media_player discovery payload so it cannot
        # collide with the Universal entity or hide its native controls.
        await self._publish(client, f"{self.discovery_prefix}/media_player/{base}/config", "")
        sensors = {
            "position": ("sensor", "Posição do Flap", "%", "measurement"),
            "flap_state": ("sensor", "Estado do Flap", None, None),
            "calibration": ("sensor", "Calibração do Flap", None, None),
            "last_command": ("sensor", "Último comando do Flap", None, None),
            "itach": ("binary_sensor", "iTach do Flap", None, None),
        }
        for key, (domain, name, unit, state_class) in sensors.items():
            payload = {
                "name": name,
                "unique_id": f"{base}_{key}",
                "state_topic": f"{base}/state/{key}",
                "availability_topic": f"{base}/availability",
                "device": device,
            }
            if unit:
                payload["unit_of_measurement"] = unit
            if state_class:
                payload["state_class"] = state_class
            if domain == "binary_sensor":
                payload.update({"payload_on": "ON", "payload_off": "OFF", "device_class": "connectivity"})
            await self._publish(client, f"{self.discovery_prefix}/{domain}/{base}_{key}/config", payload)
        for action, name in {
            "open": "Abrir", "close": "Fechar", "left": "Esquerda", "stop": "Parar", "right": "Direita", "calibrate": "HOME / Calibrar"
        }.items():
            payload = {
                "name": name,
                "unique_id": f"{base}_{action}",
                "command_topic": f"{base}/control/{action}",
                "payload_press": "PRESS",
                "availability_topic": f"{base}/availability",
                "device": device,
            }
            await self._publish(client, f"{self.discovery_prefix}/button/{base}_{action}/config", payload)
        number = {
            "name": "Posição alvo do Flap",
            "unique_id": f"{base}_target_position",
            "command_topic": f"{base}/position/set",
            "state_topic": f"{base}/state/target_position",
            "min": 0,
            "max": 100,
            "step": 1,
            "unit_of_measurement": "%",
            "availability_topic": f"{base}/availability",
            "device": device,
        }
        await self._publish(client, f"{self.discovery_prefix}/number/{base}_target_position/config", number)
        select = {
            "name": "Preset do Flap",
            "unique_id": f"{base}_preset",
            "default_entity_id": f"select.{base}_preset",
            "command_topic": f"{base}/preset/set",
            "state_topic": f"{base}/state/source",
            "options": [item["name"] for item in snapshot.get("presets", [])],
            "availability_topic": f"{base}/availability",
            "device": device,
        }
        await self._publish(client, f"{self.discovery_prefix}/select/{base}_preset/config", select)

    async def _publish_state(self, client: Any) -> None:
        snapshot = await self.state_snapshot()
        state = snapshot.get("state", {})
        composite = state.get("tv_power_state", "unknown")
        await self._publish(client, f"{self.base}/availability", "online")
        await self._publish(client, f"{self.base}/media/state", {"on": "ON", "off": "OFF"}.get(composite, "UNKNOWN"))
        await self._publish(client, f"{self.base}/media/source", state.get("source") or "")
        await self._publish(client, f"{self.base}/attributes", {"device_class": "tv", **state, "source_list": [item["name"] for item in snapshot.get("presets", [])]})
        for key, value in {
            "position": state.get("position", 0),
            "target_position": state.get("target_position", 0),
            "flap_state": state.get("flap_state", "UNKNOWN"),
            "calibration": state.get("calibration_state", "UNCERTAIN"),
            "last_command": state.get("last_command_effective") or "",
            "itach": "ON" if snapshot.get("itach", {}).get("configured") else "OFF",
            "source": state.get("source") or "",
        }.items():
            await self._publish(client, f"{self.base}/state/{key}", value)

    async def publish_current_state(self) -> None:
        """Republish discovery and state after a preset/configuration change.

        Home Assistant keeps the media player's ``source_list`` in the retained
        discovery payload. Waiting for a reconnect leaves the entity showing
        stale sources, so publish both retained payloads immediately whenever
        the MQTT connection is alive.
        """
        client = self.client
        if not self.connected or client is None:
            return
        try:
            await self._publish_discovery(client)
            await self._publish_state(client)
        except (MqttError, OSError, ValueError) as exc:
            self.last_error = str(exc)
            LOGGER.warning("MQTT state refresh failed: %s", exc)

    def status(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "connected": self.connected,
            "host_configured": bool(self.host),
            "last_connected": self.last_connected,
            "last_error": self.last_error,
            "base_topic": self.base,
        }

