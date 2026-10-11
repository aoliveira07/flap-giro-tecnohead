"""Pronto Hex and Global Caché iTach protocol helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class ProntoCode:
    frequency_word: int
    intro_pairs: int
    repeat_pairs: int
    timings: tuple[int, ...]


def parse_pronto(value: str) -> ProntoCode:
    if not isinstance(value, str):
        raise ProtocolError("Pronto Hex must be text")
    normalized = re.sub(r"[\s,_:-]", " ", value).strip()
    try:
        words = [int(item, 16) for item in normalized.split()]
    except ValueError as exc:
        raise ProtocolError("Pronto Hex contains invalid hexadecimal words") from exc
    if len(words) < 4 or any(word < 0 or word > 0xFFFF for word in words):
        raise ProtocolError("Pronto Hex must contain a complete header")
    if words[0] != 0x0000:
        raise ProtocolError("Only raw learned Pronto codes (0000) are supported")
    expected = 4 + 2 * (words[2] + words[3])
    if len(words) != expected:
        raise ProtocolError(f"Pronto Hex expected {expected} words, received {len(words)}")
    timings = tuple(words[4:])
    if len(timings) % 2:
        raise ProtocolError("Pronto Hex timing data must contain on/off pairs")
    return ProntoCode(words[1], words[2], words[3], timings)


def pronto_frequency_hz(frequency_word: int) -> int:
    if frequency_word <= 0:
        raise ProtocolError("Pronto frequency word must be positive")
    # Pronto uses a 0.241246 MHz time base for the carrier word.
    return max(1, round(1_000_000 / (frequency_word * 0.241246)))


def pronto_to_itach(
    value: str,
    *,
    connaddr: str,
    repeat: int = 1,
    command_id: int = 1,
    offset: int = 1,
) -> bytes:
    """Convert raw Pronto Hex to an iTach ``sendir`` command.

    iTach accepts the Pronto timing words as decimal carrier-cycle values.
    Keeping the conversion deterministic makes the profile portable and easy
    to test without hardware.
    """

    code = parse_pronto(value)
    if not connaddr or any(char in connaddr for char in ",\r\n"):
        raise ProtocolError("connaddr must be a non-empty iTach address")
    if repeat < 1 or repeat > 255:
        raise ProtocolError("repeat must be between 1 and 255")
    if command_id < 0 or command_id > 255 or offset < 0 or offset > 255:
        raise ProtocolError("command_id and offset must be between 0 and 255")
    frequency = pronto_frequency_hz(code.frequency_word)
    timing_text = ",".join(str(value) for value in code.timings)
    return (
        f"sendir,{connaddr},{command_id},{frequency},{repeat},{offset},{timing_text}\r"
    ).encode("ascii")

