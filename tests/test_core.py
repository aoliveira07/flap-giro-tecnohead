from __future__ import annotations

import json
import asyncio
from pathlib import Path

import pytest

from app.home_assistant import HomeAssistantClient
from app.itach import ItachDriver
from app.models import AppConfig
from app.protocol import parse_pronto, pronto_frequency_hz, pronto_to_itach
from app.profile import load_profile
from app.runtime import Runtime


PROFILE_PATH = Path(__file__).parents[1] / "app" / "profile.json"


def test_profile_contains_all_valid_pronto_commands() -> None:
    profile = load_profile()

    assert set(profile["commands"]) == {"open", "close", "stop", "left", "right"}
    for command in profile["commands"].values():
        parsed = parse_pronto(command["pronto"])
        assert parsed.frequency_word == 0x006D
        assert len(parsed.timings) == 76


def test_profile_matches_handoff_source() -> None:
    source_path = Path(r"C:\Users\PDV\Desktop\HANDOFF_FLAP_DE_GIRO_TECNOHEAD.md")
    if not source_path.exists():
        pytest.skip("handoff local não disponível neste ambiente")
    profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    handoff = source_path.read_text(encoding="utf-8")
    expected = {
        "close": handoff.split("### Fechar", 1)[1].split("### Abrir", 1)[0].strip().splitlines()[1].strip(),
        "open": handoff.split("### Abrir", 1)[1].split("### Parar", 1)[0].strip().splitlines()[1].strip(),
        "stop": handoff.split("### Parar", 1)[1].split("### Esquerda", 1)[0].strip().splitlines()[1].strip(),
        "left": handoff.split("### Esquerda", 1)[1].split("### Direita", 1)[0].strip().splitlines()[1].strip(),
        "right": handoff.split("### Direita", 1)[1].split("## ", 1)[0].strip().splitlines()[1].strip(),
    }
    assert {key: value["pronto"] for key, value in profile["commands"].items()} == expected


def test_itach_conversion_is_deterministic() -> None:
    code = load_profile()["commands"]["open"]["pronto"]
    message = pronto_to_itach(code, connaddr="3", repeat=2, command_id=7, offset=1)

    assert message.startswith(b"sendir,3,7,38029,2,1,")
    assert message.endswith(b"\r")
    assert message.count(b",") == 81
    assert pronto_frequency_hz(0x006D) == 38029


def test_itach_repetition_emits_separate_commands() -> None:
    sent: list[bytes] = []

    async def transport(command: bytes) -> bytes:
        sent.append(command)
        return b"completeir,1\r"

    driver = ItachDriver(AppConfig(itach_connaddr="3"), load_profile(), transport=transport)
    result = asyncio.run(driver.send_action("open", repeat=2, interval_seconds=0))

    assert result["repetitions"] == 2
    assert len(sent) == 2
    assert all(b"sendir,3,1,38029,1,1," in command for command in sent)


def test_defaults_capture_installation_constraints() -> None:
    config = AppConfig()

    assert config.itach_port == 4998
    assert config.itach_connaddr == "3"
    assert config.full_travel_left_seconds == 37
    assert config.full_travel_right_seconds == 37
    assert config.open_repeats == 2
    assert config.open_interval_seconds == 1
    assert config.close_repeats == 2
    assert config.close_interval_seconds == 1
    assert config.home_direction == "left"


def test_portuguese_app_labels_normalize_to_internal_values() -> None:
    config = AppConfig(
        home_direction="Direita",
        external_tv_on_behavior="Abrir e restaurar",
        external_tv_off_behavior="Fechar no HOME",
    )

    assert config.home_direction == "right"
    assert config.external_tv_on_behavior == "open_restore"
    assert config.external_tv_off_behavior == "home_close"


def test_previous_tv_values_remain_supported() -> None:
    config = AppConfig(
        home_direction="left",
        external_tv_on_behavior="open_restore",
        external_tv_off_behavior="home_close",
    )

    assert config.home_direction == "left"
    assert config.external_tv_on_behavior == "open_restore"
    assert config.external_tv_off_behavior == "home_close"


def test_runtime_loads_initial_options_and_exposes_profile(tmp_path: Path) -> None:
    async def exercise() -> dict:
        runtime = Runtime(
            tmp_path,
            "0.1.0-test",
            initial_config={"itach_host": "192.168.0.46", "tv_entity_id": "media_player.tv"},
        )
        await runtime.start()
        try:
            return runtime.status()
        finally:
            await runtime.stop()

    status = asyncio.run(exercise())
    assert status["config"]["itach_host"] == "192.168.0.46"
    assert status["state"]["tv_entity_id"] == "media_player.tv"
    assert status["profile"] == {
        "id": "tecnohead_flap_giro_v1",
        "name": "Tecnohead Flap de Giro",
        "version": "1.0.0",
    }


def test_home_assistant_client_requires_supervisor_token() -> None:
    client = HomeAssistantClient(token=None)
    assert client.enabled is False
