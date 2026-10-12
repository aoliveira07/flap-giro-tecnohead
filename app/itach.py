from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.models import AppConfig
from app.protocol import ProtocolError, parse_pronto, pronto_frequency_hz, pronto_to_itach

LOGGER = logging.getLogger("flap_giro_tecnohead.itach")

# The stored option may still be 1 from an earlier installation. Keep a
# protocol-level minimum so every sendir frame contains repeated IR pulses.
MIN_IR_PROTOCOL_REPEATS = 3
IR_SETTLE_MARGIN_SECONDS = 0.2
IR_READY_EPSILON_SECONDS = 0.05


class ItachError(RuntimeError):
    pass


Transport = Callable[[bytes], Awaitable[bytes | None]]


class ItachDriver:
    """Serialized TCP driver for a Global Caché iTach."""

    def __init__(self, config: AppConfig, profile: dict, transport: Transport | None = None):
        self.config = config
        self.profile = profile
        self.transport = transport
        self.lock = asyncio.Lock()
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None
        # The iTach can acknowledge sendir before the complete IR frame has
        # left the emitter. Keep a local reservation so a fast second request
        # cannot collide with the previous transmission.
        self.busy_until = 0.0
        self.command_active = False

    def update_config(self, config: AppConfig) -> None:
        self.config = config

    def build_command(
        self,
        action: str,
        *,
        repeat: int | None = None,
        minimum_protocol_repeats: int = MIN_IR_PROTOCOL_REPEATS,
    ) -> bytes:
        try:
            pronto = self.profile["commands"][action]["pronto"]
        except KeyError as exc:
            raise ProtocolError(f"Unknown IR action: {action}") from exc
        configured_repeat = self.config.ir_repeats if repeat is None else repeat
        effective_repeat = max(minimum_protocol_repeats, int(configured_repeat))
        return pronto_to_itach(
            pronto,
            connaddr=self.config.itach_connaddr,
            repeat=effective_repeat,
        )

    async def send_action(
        self,
        action: str,
        *,
        repeat: int | None = None,
        interval_seconds: float = 0,
        source: str = "SYSTEM",
        emissions: int = 1,
        minimum_protocol_repeats: int = MIN_IR_PROTOCOL_REPEATS,
    ) -> dict[str, Any]:
        # ``repeat`` is the repetition inside one iTach sendir command. By
        # default one TCP emission is used; the close compatibility path is
        # the only caller that explicitly requests two emissions.
        command = self.build_command(
            action,
            repeat=repeat,
            minimum_protocol_repeats=minimum_protocol_repeats,
        )
        protocol_repeat = int(command.decode("ascii").split(",", 5)[4])
        emission_count = max(1, int(emissions))
        async with self.lock:
            await self._wait_until_ready()
            started = time.monotonic()
            estimated_transmission_seconds = self._estimate_transmission_seconds(action, protocol_repeat)
            reservation_seconds = (
                estimated_transmission_seconds * emission_count
                + max(0.0, interval_seconds) * max(0, emission_count - 1)
                + IR_SETTLE_MARGIN_SECONDS * emission_count
            )
            self.command_active = True
            self.busy_until = time.monotonic() + reservation_seconds
            try:
                responses: list[dict[str, Any]] = []
                for index in range(emission_count):
                    response = await self._send_once(command)
                    responses.append({"index": index + 1, "response": response})
                    if index + 1 < emission_count and interval_seconds > 0:
                        await asyncio.sleep(interval_seconds)
                result = {
                    "ok": True,
                    "action": action,
                    "source": source,
                    "command": command.decode("ascii").strip(),
                    "repetitions": protocol_repeat,
                    "emissions": emission_count,
                    "estimated_transmission_seconds": round(estimated_transmission_seconds, 3),
                    "safety_margin_seconds": IR_SETTLE_MARGIN_SECONDS,
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                    "responses": responses,
                }
                self.last_result = result
                self.last_error = None
                return result
            except (OSError, asyncio.TimeoutError, ItachError) as exc:
                self.last_error = str(exc)
                self.last_result = {
                    "ok": False,
                    "action": action,
                    "source": source,
                    "error": str(exc),
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                }
                raise ItachError(str(exc)) from exc
            finally:
                self.command_active = False
                self.busy_until = max(self.busy_until, time.monotonic() + IR_SETTLE_MARGIN_SECONDS)

    def _estimate_transmission_seconds(self, action: str, protocol_repeat: int) -> float:
        try:
            pronto = self.profile["commands"][action]["pronto"]
        except KeyError as exc:
            raise ProtocolError(f"Unknown IR action: {action}") from exc
        code = parse_pronto(pronto)
        frame_seconds = sum(code.timings) / pronto_frequency_hz(code.frequency_word)
        return frame_seconds * protocol_repeat

    async def _wait_until_ready(self) -> None:
        remaining = self.busy_remaining_seconds()
        if remaining > 0:
            await asyncio.sleep(remaining)

    def busy_remaining_seconds(self) -> float:
        return max(0.0, self.busy_until - time.monotonic())

    def is_busy(self) -> bool:
        return self.command_active or self.busy_remaining_seconds() > IR_READY_EPSILON_SECONDS

    async def _send_once(self, command: bytes) -> str:
        if self.transport is not None:
            response = await self.transport(command)
            return self._validate_response(response)
        if not self.config.itach_host:
            raise ItachError("iTach host is not configured")
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.itach_host, self.config.itach_port),
                timeout=self.config.itach_timeout,
            )
            writer.write(command)
            await asyncio.wait_for(writer.drain(), timeout=self.config.itach_timeout)
            response = ""
            try:
                data = await asyncio.wait_for(reader.read(256), timeout=min(self.config.itach_timeout, 0.5))
                response = data.decode("utf-8", errors="replace")
            except asyncio.TimeoutError:
                # Some iTach firmware versions acknowledge only asynchronously.
                response = ""
            writer.close()
            await writer.wait_closed()
            return self._validate_response(response)
        except (OSError, asyncio.TimeoutError) as exc:
            raise ItachError(f"iTach connection failed: {exc}") from exc

    @staticmethod
    def _validate_response(response: bytes | str | None) -> str:
        normalized = response.decode("utf-8", errors="replace") if isinstance(response, bytes) else str(response or "")
        normalized = normalized.strip()
        if normalized.upper().startswith("ERR"):
            raise ItachError(normalized)
        if normalized.upper().startswith("BUSYIR"):
            raise ItachError(f"iTach ocupado: {normalized}")
        return normalized

    async def test_connection(self) -> dict[str, Any]:
        if self.transport is not None:
            response = await self.transport(b"getdevices\r")
            return {"ok": True, "response": (response or b"").decode("utf-8", errors="replace")}
        if not self.config.itach_host:
            return {"ok": False, "error": "iTach host is not configured"}
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.itach_host, self.config.itach_port),
                timeout=self.config.itach_timeout,
            )
            writer.write(b"getdevices\r")
            await asyncio.wait_for(writer.drain(), timeout=self.config.itach_timeout)
            data = b""
            try:
                data = await asyncio.wait_for(reader.read(512), timeout=min(self.config.itach_timeout, 1.0))
            except asyncio.TimeoutError:
                pass
            writer.close()
            await writer.wait_closed()
            response = data.decode("utf-8", errors="replace")
            return {"ok": not response.upper().startswith("ERR"), "response": response}
        except (OSError, asyncio.TimeoutError) as exc:
            return {"ok": False, "error": str(exc)}

    def status(self) -> dict[str, Any]:
        busy_remaining = self.busy_remaining_seconds()
        return {
            "configured": bool(self.config.itach_host),
            "host": self.config.itach_host,
            "port": self.config.itach_port,
            "connaddr": self.config.itach_connaddr,
            "last_result": self.last_result,
            "last_error": self.last_error,
            "busy": self.command_active or busy_remaining > IR_READY_EPSILON_SECONDS,
            "busy_remaining_seconds": round(busy_remaining, 2),
        }

