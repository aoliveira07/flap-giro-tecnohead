from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _normalize_choice(value: object, choices: dict[str, str]) -> object:
    """Accept the Portuguese UI labels and the previous internal values."""
    if value is None:
        return None
    normalized = str(value).strip().casefold()
    return choices.get(normalized, value)


class AppConfig(BaseModel):
    itach_host: str = ""
    itach_port: int = Field(default=4998, ge=1, le=65535)
    itach_connaddr: str = "1:3"
    itach_timeout: float = Field(default=3.0, gt=0, le=30)
    ir_repeats: int = Field(default=3, ge=1, le=10)
    full_travel_left_seconds: float = Field(default=37.0, gt=0, le=600)
    full_travel_right_seconds: float = Field(default=37.0, gt=0, le=600)
    opening_seconds: float = Field(default=5.0, gt=0, le=120)
    closing_seconds: float = Field(default=5.0, gt=0, le=120)
    open_repeats: int = Field(default=2, ge=1, le=10)
    open_interval_seconds: float = Field(default=1.0, ge=0, le=30)
    close_repeats: int = Field(default=2, ge=1, le=10)
    close_interval_seconds: float = Field(default=1.0, ge=0, le=30)
    homing_margin_seconds: float = Field(default=2.0, ge=0, le=120)
    home_direction: Literal["left", "right"] = "left"
    tv_enabled: bool = False
    tv_entity_id: str | None = None
    tv_composed_entity_id: str = "media_player.flap_giro_tecnohead"
    tv_friendly_name: str = "Flap de Giro Tecnohead"
    tv_initial_preset_id: int | None = None
    tv_start_delay_seconds: float = Field(default=0.0, ge=0, le=120)
    external_tv_on_behavior: Literal["open_restore", "ignore"] = "open_restore"
    external_tv_off_behavior: Literal["home_close", "ignore"] = "home_close"
    tv_reconcile_interval_seconds: float = Field(default=5.0, ge=1, le=300)
    discovery_prefix: str = "homeassistant"

    @field_validator("itach_host", "itach_connaddr", "tv_friendly_name", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("itach_connaddr", mode="after")
    @classmethod
    def normalize_itach_connaddr(cls, value: str) -> str:
        """Use the Global Caché module:connector address format.

        Older versions exposed only the connector number (for example ``3``).
        A classic iTach identifies the same output as module 1, connector 3:
        ``1:3``.
        """
        normalized = value.strip()
        if normalized.isdigit():
            normalized = f"1:{normalized}"
        if not re.fullmatch(r"[1-9][0-9]*:[1-3]", normalized):
            raise ValueError("connaddr deve usar o formato módulo:conector, por exemplo 1:3")
        return normalized

    @field_validator("discovery_prefix", mode="before")
    @classmethod
    def normalize_prefix(cls, value: object) -> str:
        return str(value or "homeassistant").strip("/") or "homeassistant"

    @field_validator("home_direction", mode="before")
    @classmethod
    def normalize_home_direction(cls, value: object) -> object:
        return _normalize_choice(
            value,
            {
                "esquerda": "left",
                "direita": "right",
                "left": "left",
                "right": "right",
            },
        )

    @field_validator("external_tv_on_behavior", mode="before")
    @classmethod
    def normalize_tv_on_behavior(cls, value: object) -> object:
        return _normalize_choice(
            value,
            {
                "abrir e restaurar": "open_restore",
                "ignorar": "ignore",
                "open_restore": "open_restore",
                "ignore": "ignore",
            },
        )

    @field_validator("external_tv_off_behavior", mode="before")
    @classmethod
    def normalize_tv_off_behavior(cls, value: object) -> object:
        return _normalize_choice(
            value,
            {
                "fechar no home": "home_close",
                "home e fechar": "home_close",
                "ignorar": "ignore",
                "home_close": "home_close",
                "ignore": "ignore",
            },
        )


class ConfigPatch(BaseModel):
    itach_host: str | None = None
    itach_port: int | None = Field(default=None, ge=1, le=65535)
    itach_connaddr: str | None = None
    itach_timeout: float | None = Field(default=None, gt=0, le=30)
    ir_repeats: int | None = Field(default=None, ge=1, le=10)
    full_travel_left_seconds: float | None = Field(default=None, gt=0, le=600)
    full_travel_right_seconds: float | None = Field(default=None, gt=0, le=600)
    opening_seconds: float | None = Field(default=None, gt=0, le=120)
    closing_seconds: float | None = Field(default=None, gt=0, le=120)
    open_repeats: int | None = Field(default=None, ge=1, le=10)
    open_interval_seconds: float | None = Field(default=None, ge=0, le=30)
    close_repeats: int | None = Field(default=None, ge=1, le=10)
    close_interval_seconds: float | None = Field(default=None, ge=0, le=30)
    homing_margin_seconds: float | None = Field(default=None, ge=0, le=120)
    home_direction: Literal["left", "right"] | None = None
    tv_enabled: bool | None = None
    tv_entity_id: str | None = None
    tv_composed_entity_id: str | None = None
    tv_friendly_name: str | None = None
    tv_initial_preset_id: int | None = None
    tv_start_delay_seconds: float | None = Field(default=None, ge=0, le=120)
    external_tv_on_behavior: Literal["open_restore", "ignore"] | None = None
    external_tv_off_behavior: Literal["home_close", "ignore"] | None = None
    tv_reconcile_interval_seconds: float | None = Field(default=None, ge=1, le=300)
    discovery_prefix: str | None = None

    @field_validator("itach_connaddr", mode="before")
    @classmethod
    def normalize_itach_connaddr(cls, value: object) -> object:
        if value is None:
            return None
        normalized = str(value).strip()
        if normalized.isdigit():
            normalized = f"1:{normalized}"
        if not re.fullmatch(r"[1-9][0-9]*:[1-3]", normalized):
            raise ValueError("connaddr deve usar o formato módulo:conector, por exemplo 1:3")
        return normalized

    @field_validator("home_direction", mode="before")
    @classmethod
    def normalize_home_direction(cls, value: object) -> object:
        return _normalize_choice(
            value,
            {
                "esquerda": "left",
                "direita": "right",
                "left": "left",
                "right": "right",
            },
        )

    @field_validator("external_tv_on_behavior", mode="before")
    @classmethod
    def normalize_tv_on_behavior(cls, value: object) -> object:
        return _normalize_choice(
            value,
            {
                "abrir e restaurar": "open_restore",
                "ignorar": "ignore",
                "open_restore": "open_restore",
                "ignore": "ignore",
            },
        )

    @field_validator("external_tv_off_behavior", mode="before")
    @classmethod
    def normalize_tv_off_behavior(cls, value: object) -> object:
        return _normalize_choice(
            value,
            {
                "fechar no home": "home_close",
                "home e fechar": "home_close",
                "ignorar": "ignore",
                "home_close": "home_close",
                "ignore": "ignore",
            },
        )


class PositionRequest(BaseModel):
    position: float = Field(ge=0, le=100)


class PresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    position: float = Field(ge=0, le=100)


class PresetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    position: float | None = Field(default=None, ge=0, le=100)
    sort_order: int | None = Field(default=None, ge=0, le=10000)


class TvStateEvent(BaseModel):
    entity_id: str
    state: str
    attributes: dict = Field(default_factory=dict)

