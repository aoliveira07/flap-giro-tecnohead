from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from app.models import AppConfig
from app.protocol import ProtocolError, pronto_to_itach

LOGGER = logging.getLogger("flap_giro_tecnohead.itach")

# The stored option may still be 1 from an earlier installation. Keep a
# protocol-level minimum so every sendir frame contains repeated IR pulses.
MIN_IR_PROTOCOL_REPEATS = 3


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

    def update_config(self, config: AppConfig) -> None:
        self.config = config

    def build_command(self, action: str, *, repeat: int | None = None) -> bytes:
        try:
            pronto = self.profile["commands"][action]["pronto"]
        except KeyError as exc:
            raise ProtocolError(f"Unknown IR action: {action}") from exc
        configured_repeat = self.config.ir_repeats if repeat is None else repeat
        effective_repeat = max(MIN_IR_PROTOCOL_REPEATS, int(configured_repeat))
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
    ) -> dict[str, Any]:
        # ``repeat`` is the number of TCP emissions. The iTach repeat field
        # remains the installation-level protocol setting, so an action such
        # as Abrir twice really means two separate emissions with the
        # configured interval between them.
        command = self.build_command(action)
        async with self.lock:
            started = time.monotonic()
            records: list[dict[str, Any]] = []
            try:
                count = repeat or 1
                for index in range(count):
                    response = await self._send_once(command)
                    records.append({"index": index + 1, "response": response})
                    if index + 1 < count and interval_seconds:
                        await asyncio.sleep(interval_seconds)
                result = {
                    "ok": True,
                    "action": action,
                    "source": source,
                    "command": command.decode("ascii").strip(),
                    "repetitions": count,
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                    "responses": records,
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

    async def _send_once(self, command: bytes) -> str:
        if self.transport is not None:
            response = await self.transport(command)
            return response.decode("utf-8", errors="replace") if isinstance(response, bytes) else str(response or "")
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
            if response.upper().startswith("ERR"):
                raise ItachError(response.strip())
            return response.strip()
        except (OSError, asyncio.TimeoutError) as exc:
            raise ItachError(f"iTach connection failed: {exc}") from exc

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
        return {
            "configured": bool(self.config.itach_host),
            "host": self.config.itach_host,
            "port": self.config.itach_port,
            "connaddr": self.config.itach_connaddr,
            "last_result": self.last_result,
            "last_error": self.last_error,
        }

