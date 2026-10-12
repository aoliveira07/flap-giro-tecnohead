from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable

from app.home_assistant import HomeAssistantClient, HomeAssistantError
from app.itach import ItachDriver, ItachError
from app.models import AppConfig
from app.mqtt import MqttBridge
from app.profile import load_profile
from app.storage import Database, utc_now

LOGGER = logging.getLogger("flap_giro_tecnohead.runtime")

DEFAULT_PRESETS = [
    {"name": "Cozinha", "position": 30},
    {"name": "Poltronas", "position": 65},
    {"name": "Piscina", "position": 100},
]

MOVEMENT_STATES = {"OPENING", "CLOSING", "MOVING"}
TV_ON_STATES = {"on", "playing", "idle", "paused", "buffering", "media_playing", "media_paused"}

def default_state() -> dict[str, Any]:
    return {
        "flap_state": "UNKNOWN",
        "rotation_state": "UNKNOWN",
        "calibration_state": "UNCERTAIN",
        "position": 0.0,
        "target_position": 0.0,
        "direction": None,
        "movement_in_progress": False,
        "movement_started_at": None,
        "movement_start_position": 0.0,
        "last_command_requested": None,
        "last_command_effective": None,
        "last_command_at": None,
        "last_command_source": None,
        "source": None,
        "sequence": "IDLE",
        "tv_entity_id": None,
        "tv_raw_state": "unknown",
        "tv_power_state": "unknown",
        "tv_last_confirmed_at": None,
        "tv_last_change_source": None,
        "tv_pending_action": None,
        "updated_at": utc_now(),
    }


class Runtime:
    def __init__(
        self,
        data_path: str,
        version: str,
        *,
        ha_client: HomeAssistantClient | None = None,
        initial_config: dict[str, Any] | None = None,
    ):
        self.version = version
        self.initial_config = initial_config or {}
        self.database = Database(data_path)
        self.profile = load_profile()
        self.config = AppConfig()
        self.state = default_state()
        self.driver = ItachDriver(self.config, self.profile)
        self.ha = ha_client or HomeAssistantClient()
        self.mqtt = MqttBridge(self.config.discovery_prefix, self.snapshot, self.handle_mqtt_command)
        self.started_at = time.monotonic()
        self.control_lock = asyncio.Lock()
        self.operation_task: asyncio.Task | None = None
        self.tv_task: asyncio.Task | None = None
        self.stop_event = asyncio.Event()
        self.errors: deque[dict[str, str]] = deque(maxlen=100)
        self.initial_tv_sync_done = False

    async def start(self) -> None:
        await self.database.initialize(DEFAULT_PRESETS)
        saved_config = await self.database.get_json("config", {})
        self.config = AppConfig.model_validate(
            {
                **AppConfig().model_dump(),
                **self.initial_config,
                **(saved_config or {}),
            }
        )
        saved_state = await self.database.get_json("state", {})
        self.state = {**default_state(), **(saved_state or {})}
        if self.state.get("movement_in_progress"):
            self.state.update(
                {
                    "movement_in_progress": False,
                    "rotation_state": "IDLE",
                    "calibration_state": "UNCERTAIN",
                    "sequence": "IDLE",
                }
            )
            await self.persist_state()
        self.state["tv_entity_id"] = self.config.tv_entity_id
        self.driver.update_config(self.config)
        self.mqtt.discovery_prefix = self.config.discovery_prefix
        await self.mqtt.start()
        if self.config.tv_enabled and self.config.tv_entity_id and self.ha.enabled:
            self.tv_task = asyncio.create_task(self._tv_reconcile_loop(), name="flap-tv-reconcile")
            await self.reconcile_tv(run_policy=False)

    async def stop(self) -> None:
        self.stop_event.set()
        if self.operation_task and not self.operation_task.done():
            self.operation_task.cancel()
            await asyncio.gather(self.operation_task, return_exceptions=True)
        if self.tv_task:
            self.tv_task.cancel()
            await asyncio.gather(self.tv_task, return_exceptions=True)
        await self.mqtt.stop()

    def record_error(self, message: str) -> None:
        LOGGER.error(message)
        self.errors.append({"timestamp": datetime.now(UTC).isoformat(), "message": message})

    async def persist_state(self) -> None:
        self.state["updated_at"] = utc_now()
        await self.database.set_json("state", self.state)

    async def log(self, source: str, event: str, **payload: Any) -> None:
        await self.database.add_log(source, event, payload)

    async def snapshot(self) -> dict[str, Any]:
        return {
            "app_version": self.version,
            "state": dict(self.state),
            "presets": await self.database.list_presets(),
            "itach": self.driver.status(),
            "mqtt": self.mqtt.status(),
        }

    async def list_presets(self) -> list[dict[str, Any]]:
        return await self.database.list_presets()

    async def save_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        values = self.config.model_dump()
        values.update({key: value for key, value in patch.items() if value is not None})
        if values.get("tv_entity_id") == "":
            values["tv_entity_id"] = None
        self.config = AppConfig.model_validate(values)
        await self.database.set_json("config", self.config.model_dump())
        self.driver.update_config(self.config)
        self.mqtt.discovery_prefix = self.config.discovery_prefix
        self.state["tv_entity_id"] = self.config.tv_entity_id
        await self.persist_state()
        return self.config.model_dump()

    async def _send_ir(
        self,
        action: str,
        *,
        source: str,
        repeat: int | None = None,
        interval: float = 0,
        emissions: int = 1,
        minimum_protocol_repeats: int = 3,
    ) -> dict[str, Any]:
        requested_at = utc_now()
        self.state.update(
            {
                "last_command_requested": action,
                "last_command_at": requested_at,
                "last_command_source": source,
            }
        )
        await self.persist_state()
        try:
            result = await self.driver.send_action(
                action,
                repeat=repeat,
                interval_seconds=interval,
                source=source,
                emissions=emissions,
                minimum_protocol_repeats=minimum_protocol_repeats,
            )
            self.state["last_command_effective"] = action
            await self.persist_state()
            await self.log(source, "ir_command", action=action, result=result)
            return result
        except ItachError as exc:
            self.state["flap_state"] = "ERROR"
            await self.persist_state()
            await self.log(source, "ir_error", action=action, error=str(exc))
            self.record_error(str(exc))
            raise

    async def _cancel_active(self, *, send_stop: bool = True) -> None:
        task = self.operation_task
        if task and not task.done() and task is not asyncio.current_task():
            was_calibrating = self.state.get("calibration_state") == "CALIBRATING" or self.state.get("sequence") == "CALIBRATING"
            self._update_position_from_clock()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.operation_task = None
            if was_calibrating:
                self.state.update(
                    {
                        "calibration_state": "UNCERTAIN",
                        "movement_in_progress": False,
                        "direction": None,
                        "rotation_state": "IDLE",
                    }
                )
                await self.persist_state()
            if send_stop:
                try:
                    await self._send_ir("stop", source="SYSTEM")
                except ItachError:
                    pass

    def ensure_ir_ready(self) -> None:
        if not self.driver.is_busy():
            return
        remaining = max(0.1, self.driver.busy_remaining_seconds())
        raise ValueError(f"Aguarde {remaining:.1f} s antes de enviar outro comando ao iTach.")

    async def _start_operation(self, name: str, operation: Callable[[], Awaitable[None]], *, cancel_active: bool = True) -> dict[str, Any]:
        async with self.control_lock:
            if self.state.get("sequence") == "TURNING_OFF" and name != "TURNING_OFF":
                raise ValueError("O desligamento do Flap está em andamento; aguarde a conclusão.")
            self.ensure_ir_ready()
            if cancel_active:
                await self._cancel_active()
            self.state["sequence"] = name
            await self.persist_state()
            task = asyncio.create_task(self._run_operation(name, operation), name=f"flap-{name.lower()}")
            self.operation_task = task
        return dict(self.state)

    async def _run_operation(self, name: str, operation: Callable[[], Awaitable[None]]) -> None:
        try:
            await operation()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - surfaced in status and diagnostics
            self.record_error(f"{name} failed: {exc}")
            self.state["sequence"] = "ERROR"
            if name == "CALIBRATING":
                self.state.update(
                    {
                        "calibration_state": "UNCERTAIN",
                        "movement_in_progress": False,
                        "direction": None,
                        "rotation_state": "IDLE",
                    }
                )
            await self.persist_state()
        finally:
            if self.operation_task is asyncio.current_task():
                self.operation_task = None

    async def open(self, source: str = "UI") -> dict[str, Any]:
        return await self._start_operation("TURNING_ON_MECHANISM", lambda: self._open_sequence(source))

    async def _open_sequence(self, source: str) -> None:
        # Opening the mechanism does not change the calibrated rotation
        # reference. Preserve CALIBRATED after HOME so a later OPEN does not
        # incorrectly ask the user to calibrate again.
        self.state.update({"flap_state": "OPENING", "rotation_state": "IDLE"})
        await self.persist_state()
        await self._send_ir("open", source=source, repeat=self.config.open_repeats, interval=self.config.open_interval_seconds)
        await asyncio.sleep(self.config.opening_seconds)
        self.state.update({"flap_state": "OPEN", "sequence": "IDLE"})
        await self.persist_state()

    async def close(self, source: str = "UI", *, automatic: bool = False) -> dict[str, Any]:
        if automatic and self.state.get("calibration_state") == "UNCERTAIN":
            raise ValueError("A posição está incerta. Execute HOME / Calibrar antes do fechamento automático.")
        return await self._start_operation("TURNING_OFF", lambda: self._close_sequence(source, automatic=automatic))

    async def _close_sequence(self, source: str, *, automatic: bool = False) -> None:
        if self.state.get("calibration_state") == "UNCERTAIN" and automatic:
            raise ValueError("A posição está incerta; o fechamento automático exige calibração HOME.")
        if self.state.get("position", 0) > 0.01:
            await self._move_to_now(0, source=source)
        else:
            self.state.update({"position": 0.0, "target_position": 0.0, "rotation_state": "IDLE"})
            await self.persist_state()
        await self._send_ir("stop", source=source)
        await self._wait_for_ir_settle()
        await self._send_close_ir(source)
        await asyncio.sleep(self.config.closing_seconds)
        self.state.update({"flap_state": "CLOSED", "rotation_state": "IDLE", "position": 0.0, "target_position": 0.0, "sequence": "IDLE"})
        await self.persist_state()
        await self.log(source, "closed", position=0)

    async def _wait_for_ir_settle(self) -> None:
        # iTach can answer busyIR for a new action immediately after STOP,
        # while the previous repeated frame is still being emitted. The
        # pause prevents CLOSE from being rejected without sending duplicates.
        delay = min(2.0, max(0.25, float(self.config.close_interval_seconds)))
        await asyncio.sleep(delay)

    async def _send_close_ir(self, source: str) -> dict[str, Any]:
        # The close command is the original learned frame: one protocol
        # repeat, emitted twice with the configured gap. Other actions use
        # one sendir command with the stronger protocol-level repetition.
        return await self._send_ir(
            "close",
            source=source,
            repeat=1,
            interval=self.config.close_interval_seconds,
            emissions=2,
            minimum_protocol_repeats=1,
        )

    async def stop(self, source: str = "UI") -> dict[str, Any]:
        async with self.control_lock:
            self.ensure_ir_ready()
            await self._cancel_active(send_stop=False)
            self._update_position_from_clock()
            try:
                await self._send_ir("stop", source=source)
            except ItachError:
                self.state.update(
                    {
                        "flap_state": "ERROR",
                        "rotation_state": "UNKNOWN",
                        "sequence": "ERROR",
                        "movement_in_progress": False,
                    }
                )
                await self.persist_state()
                raise
            # Stopping mid-course makes the current estimated position the new
            # target. The UI slider is driven by target_position, so leaving
            # the previous endpoint here would show a stale command target.
            current_position = float(self.state.get("position", 0.0))
            self.state.update(
                {
                    "movement_in_progress": False,
                    "rotation_state": "IDLE",
                    "sequence": "IDLE",
                    "target_position": current_position,
                }
            )
            await self.persist_state()
        return dict(self.state)

    def _update_position_from_clock(self) -> None:
        if not self.state.get("movement_in_progress") or not self.state.get("movement_started_monotonic"):
            return
        elapsed = max(0.0, time.monotonic() - float(self.state["movement_started_monotonic"]))
        start = float(self.state.get("movement_start_position", self.state.get("position", 0)))
        direction = self.state.get("direction")
        seconds = self.config.full_travel_right_seconds if direction == "right" else self.config.full_travel_left_seconds
        delta = elapsed * 100 / seconds
        self.state["position"] = max(0.0, min(100.0, start + delta if direction == "right" else start - delta))

    async def _move_to_now(self, target: float, *, source: str) -> None:
        target = max(0.0, min(100.0, float(target)))
        current = float(self.state.get("position", 0))
        self.state.update(
            {
                "target_position": target,
                "movement_in_progress": False,
                "movement_started_at": utc_now(),
                "movement_start_position": current,
            }
        )
        if abs(target - current) < 0.05:
            self.state.update({"position": target, "rotation_state": "IDLE", "direction": None})
            await self.persist_state()
            return
        direction = "right" if target > current else "left"
        seconds = self.config.full_travel_right_seconds if direction == "right" else self.config.full_travel_left_seconds
        duration = abs(target - current) / 100 * seconds
        self.state.update(
            {
                "direction": direction,
                "rotation_state": "MOVING_RIGHT" if direction == "right" else "MOVING_LEFT",
                "movement_in_progress": True,
                "movement_started_monotonic": time.monotonic(),
            }
        )
        await self.persist_state()
        await self._send_ir(direction, source=source)
        try:
            deadline = time.monotonic() + duration
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(0.5, remaining))
                self._update_position_from_clock()
                await self.persist_state()
            self.state["position"] = target
        finally:
            self.state["movement_in_progress"] = False
            self.state["direction"] = None
            await self.persist_state()
        await self._send_ir("stop", source=source)
        self.state.update({"rotation_state": "IDLE", "position": target, "target_position": target})
        await self.persist_state()

    async def position(self, target: float, source: str = "UI") -> dict[str, Any]:
        if self.state.get("calibration_state") == "CALIBRATING" or self.state.get("sequence") == "CALIBRATING":
            raise ValueError("A calibração HOME ainda está em andamento. Aguarde a conclusão antes de mover o Flap.")
        if self.state.get("calibration_state") == "UNCERTAIN" and target == 0:
            raise ValueError("A posição está incerta. Execute HOME / Calibrar antes de fechar para 0%.")

        async def operation() -> None:
            if self.state.get("flap_state") in {"CLOSED", "UNKNOWN"}:
                await self._open_sequence(source)
            await self._move_to_now(target, source=source)
            self.state["sequence"] = "IDLE"
            await self.persist_state()

        return await self._start_operation("MOVING", operation)

    async def preset(self, preset_id: int, source: str = "UI") -> dict[str, Any]:
        presets = await self.list_presets()
        item = next((item for item in presets if int(item["id"]) == preset_id), None)
        if not item:
            raise ValueError("Preset não encontrado")

        async def operation() -> None:
            if self.state.get("flap_state") in {"CLOSED", "UNKNOWN"}:
                await self._open_sequence(source)
            await self._move_to_now(float(item["position"]), source=source)
            self.state.update({"source": item["name"], "sequence": "IDLE"})
            await self.persist_state()

        return await self._start_operation("SELECTING_PRESET", operation)

    async def calibrate(self, source: str = "UI") -> dict[str, Any]:
        async def operation() -> None:
            self.state.update({"calibration_state": "CALIBRATING", "sequence": "CALIBRATING", "flap_state": "OPENING"})
            await self.persist_state()
            await self._open_sequence(source)
            direction = self.config.home_direction
            self.state.update({"direction": direction, "rotation_state": "MOVING_LEFT" if direction == "left" else "MOVING_RIGHT", "movement_in_progress": True, "movement_started_monotonic": time.monotonic(), "movement_start_position": float(self.state.get("position", 0)), "target_position": 0.0})
            await self.persist_state()
            await self._send_ir(direction, source=source)
            await asyncio.sleep((self.config.full_travel_left_seconds if direction == "left" else self.config.full_travel_right_seconds) + self.config.homing_margin_seconds)
            await self._send_ir("stop", source=source)
            self.state.update({"position": 0.0, "target_position": 0.0, "movement_in_progress": False, "direction": None, "rotation_state": "IDLE", "calibration_state": "CALIBRATED"})
            await self.persist_state()
            await self._wait_for_ir_settle()
            await self._send_close_ir(source)
            await asyncio.sleep(self.config.closing_seconds)
            self.state.update({"flap_state": "CLOSED", "sequence": "IDLE"})
            await self.persist_state()
            await self.log(source, "calibrated_home", position=0, margin_seconds=self.config.homing_margin_seconds)

        return await self._start_operation("CALIBRATING", operation)

    async def turn_on(self, source: str = "HA") -> dict[str, Any]:
        async def operation() -> None:
            self.state.update({"sequence": "TURNING_ON", "tv_pending_action": "on"})
            await self.persist_state()
            await self._open_sequence(source)
            if self.config.tv_enabled and self.config.tv_entity_id and self.ha.enabled:
                await self.ha.call_service("media_player", "turn_on", self.config.tv_entity_id)
            if self.config.tv_start_delay_seconds:
                await asyncio.sleep(self.config.tv_start_delay_seconds)
            preset_id = self.config.tv_initial_preset_id
            if preset_id is None:
                presets = await self.list_presets()
                current_name = self.state.get("source")
                item = next((row for row in presets if row["name"] == current_name), None) or (presets[0] if presets else None)
                preset_id = int(item["id"]) if item else None
            if preset_id is not None:
                presets = await self.list_presets()
                item = next((row for row in presets if int(row["id"]) == preset_id), None)
                if item:
                    await self._move_to_now(float(item["position"]), source=source)
                    self.state["source"] = item["name"]
            self.state["sequence"] = "IDLE"
            await self.persist_state()

        return await self._start_operation("TURNING_ON", operation)

    async def turn_off(self, source: str = "HA") -> dict[str, Any]:
        async def operation() -> None:
            self.state.update({"sequence": "TURNING_OFF", "tv_pending_action": "off"})
            await self.persist_state()
            if self.config.tv_enabled and self.config.tv_entity_id and self.ha.enabled and self.state.get("tv_power_state") != "off":
                await self.ha.call_service("media_player", "turn_off", self.config.tv_entity_id)
            await self._move_to_now(0, source=source) if self.state.get("position", 0) > 0.01 else None
            await self._send_ir("stop", source=source)
            await self._wait_for_ir_settle()
            await self._send_close_ir(source)
            await asyncio.sleep(self.config.closing_seconds)
            self.state.update({"position": 0.0, "target_position": 0.0, "flap_state": "CLOSED", "rotation_state": "IDLE", "sequence": "IDLE"})
            await self.persist_state()

        return await self._start_operation("TURNING_OFF", operation)

    def tv_power_from_raw(self, raw: str) -> str:
        value = str(raw or "").lower()
        if value == "off":
            return "off"
        if value in TV_ON_STATES:
            return "on"
        return "unavailable" if value in {"unknown", "unavailable", "none", ""} else "on"

    async def observe_tv_state(self, raw_state: str, attributes: dict[str, Any] | None = None, *, source: str = "TV_LINKED") -> None:
        new_power = self.tv_power_from_raw(raw_state)
        previous = self.state.get("tv_power_state", "unknown")
        self.state.update(
            {
                "tv_raw_state": raw_state,
                "tv_power_state": new_power,
                "tv_last_confirmed_at": utc_now(),
                "tv_last_change_source": source,
            }
        )
        pending = self.state.get("tv_pending_action")
        if pending and ((pending == "on" and new_power == "on") or (pending == "off" and new_power == "off")):
            self.state["tv_pending_action"] = None
        await self.persist_state()
        if not self.initial_tv_sync_done:
            self.initial_tv_sync_done = True
            return
        if new_power == "off" and previous == "on" and not pending and self.config.external_tv_off_behavior == "home_close":
            try:
                await self.close(source="TV_LINKED", automatic=True)
            except ValueError as exc:
                self.record_error(str(exc))
        elif new_power == "on" and previous == "off" and not pending and self.config.external_tv_on_behavior == "open_restore":
            await self.turn_on(source="TV_LINKED")

    async def reconcile_tv(self, *, run_policy: bool = True) -> dict[str, Any]:
        if not (self.config.tv_enabled and self.config.tv_entity_id):
            return {"configured": False}
        try:
            data = await self.ha.get_state(self.config.tv_entity_id)
            await self.observe_tv_state(str(data.get("state", "unknown")), data.get("attributes", {}), source="HA")
            return {"configured": True, "ok": True, "entity": data}
        except HomeAssistantError as exc:
            self.state.update({"tv_power_state": "unavailable", "tv_raw_state": "unavailable", "tv_last_confirmed_at": utc_now()})
            await self.persist_state()
            if run_policy:
                self.record_error(str(exc))
            return {"configured": True, "ok": False, "error": str(exc)}

    async def _tv_reconcile_loop(self) -> None:
        while not self.stop_event.is_set():
            await self.reconcile_tv()
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=self.config.tv_reconcile_interval_seconds)
            except asyncio.TimeoutError:
                pass

    async def linked_tv_entities(self) -> list[dict[str, Any]]:
        if not self.ha.enabled:
            return []
        try:
            return await self.ha.list_media_players()
        except HomeAssistantError as exc:
            self.record_error(str(exc))
            return []

    async def handle_mqtt_command(self, kind: str, payload: str) -> None:
        source = "MQTT"
        value = payload.strip()
        if kind == "media":
            if value.upper() in {"ON", "TURN_ON"}:
                await self.turn_on(source)
            elif value.upper() in {"OFF", "TURN_OFF"}:
                await self.turn_off(source)
        elif kind == "source":
            presets = await self.list_presets()
            item = next((item for item in presets if item["name"].casefold() == value.casefold()), None)
            if item:
                await self.preset(int(item["id"]), source)
        elif kind == "position":
            await self.position(float(value), source)
        elif kind == "preset":
            presets = await self.list_presets()
            item = next((item for item in presets if str(item["id"]) == value or item["name"].casefold() == value.casefold()), None)
            if item:
                await self.preset(int(item["id"]), source)
        elif value.upper() in {"PRESS", "ON", "1"}:
            actions = {"open": self.open, "close": self.close, "left": lambda s: self.position(0, s), "right": lambda s: self.position(100, s), "stop": self.stop, "calibrate": self.calibrate}
            action = actions.get(kind)
            if action:
                await action(source)

    def status(self) -> dict[str, Any]:
        return {
            "app_version": self.version,
            "uptime_seconds": round(time.monotonic() - self.started_at, 1),
            "state": dict(self.state),
            "config": self.config.model_dump(),
            "profile": {"id": self.profile["profile_id"], "name": self.profile["name"], "version": self.profile["version"]},
            "itach": self.driver.status(),
            "mqtt": self.mqtt.status(),
            "errors": list(self.errors)[-20:],
            "operation_active": bool(self.operation_task and not self.operation_task.done()),
        }

