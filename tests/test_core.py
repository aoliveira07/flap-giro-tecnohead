from __future__ import annotations

import json
import asyncio
import time
from pathlib import Path

import pytest

from app.home_assistant import HomeAssistantClient
from app.itach import ItachDriver, ItachError
from app.models import AppConfig
from app.mqtt import MqttBridge
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
    message = pronto_to_itach(code, connaddr="1:3", repeat=2, command_id=7, offset=1)

    assert message.startswith(b"sendir,1:3,7,38029,2,1,")
    assert message.endswith(b"\r")
    assert message.count(b",") == 81
    assert pronto_frequency_hz(0x006D) == 38029


def test_itach_repetition_stays_inside_one_command() -> None:
    sent: list[bytes] = []

    async def transport(command: bytes) -> bytes:
        sent.append(command)
        return b"completeir,1\r"

    driver = ItachDriver(AppConfig(itach_connaddr="3", ir_repeats=1), load_profile(), transport=transport)
    result = asyncio.run(driver.send_action("open", repeat=3, interval_seconds=0))

    assert result["repetitions"] == 3
    assert result["emissions"] == 1
    assert len(sent) == 1
    assert all(b"sendir,1:3,1,38029,3,1," in command for command in sent)


def test_defaults_capture_installation_constraints() -> None:
    config = AppConfig()

    assert config.itach_port == 4998
    assert config.itach_connaddr == "1:3"
    assert config.full_travel_left_seconds == 37
    assert config.full_travel_right_seconds == 37
    assert config.open_repeats == 2
    assert config.open_interval_seconds == 1
    assert config.close_repeats == 2
    assert config.close_interval_seconds == 1
    assert config.home_direction == "left"
    assert config.ir_repeats == 3


def test_itach_protocol_repeat_has_safe_minimum_for_legacy_config() -> None:
    sent: list[bytes] = []

    async def transport(command: bytes) -> bytes:
        sent.append(command)
        return b"completeir,1\r"

    driver = ItachDriver(AppConfig(ir_repeats=1), load_profile(), transport=transport)
    result = asyncio.run(driver.send_action("right", repeat=3, interval_seconds=0))

    assert result["emissions"] == 1
    assert len(sent) == 1
    assert all(b"sendir,1:3,1,38029,3,1," in command for command in sent)


def test_close_uses_original_protocol_frame_with_two_emissions() -> None:
    sent: list[bytes] = []

    async def transport(command: bytes) -> bytes:
        sent.append(command)
        return b"completeir,1\r"

    driver = ItachDriver(AppConfig(ir_repeats=3), load_profile(), transport=transport)
    result = asyncio.run(
        driver.send_action(
            "close",
            repeat=1,
            interval_seconds=0,
            emissions=2,
            minimum_protocol_repeats=1,
        )
    )

    assert result["repetitions"] == 1
    assert result["emissions"] == 2
    assert len(sent) == 2
    assert all(b"sendir,1:3,1,38029,1,1," in command for command in sent)


def test_itach_busy_response_is_not_reported_as_success() -> None:
    async def transport(command: bytes) -> bytes:
        return b"busyIR,1:3,1"

    driver = ItachDriver(AppConfig(), load_profile(), transport=transport)
    with pytest.raises(ItachError, match="iTach ocupado"):
        asyncio.run(driver.send_action("close", repeat=3, interval_seconds=0))


def test_itach_missing_ack_is_not_reported_as_success() -> None:
    async def transport(command: bytes) -> bytes:
        return b""

    driver = ItachDriver(AppConfig(), load_profile(), transport=transport)
    with pytest.raises(ItachError, match="não confirmou"):
        asyncio.run(driver.send_action("right", repeat=3, interval_seconds=0))


def test_itach_reports_safe_cooldown_after_transmission() -> None:
    async def transport(command: bytes) -> bytes:
        return b"completeir,1\r"

    driver = ItachDriver(AppConfig(ir_repeats=3), load_profile(), transport=transport)
    result = asyncio.run(driver.send_action("right"))
    status = driver.status()

    assert result["estimated_transmission_seconds"] == pytest.approx(0.978, abs=0.01)
    assert status["busy"] is True
    assert status["busy_remaining_seconds"] > 0


def test_runtime_rejects_commands_during_ir_cooldown(tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime = Runtime(tmp_path, "0.1.0-test")
        await runtime.start()
        runtime.driver.busy_until = time.monotonic() + 1
        try:
            with pytest.raises(ValueError, match="Aguarde"):
                await runtime.open()
        finally:
            await runtime.mqtt.stop()

    asyncio.run(exercise())


def test_mqtt_refresh_publishes_current_preset_sources() -> None:
    async def exercise() -> dict[str, object]:
        published: list[tuple[str, str]] = []

        class FakeClient:
            async def publish(self, topic, payload, qos=0, retain=False):
                published.append((str(topic), payload.decode() if isinstance(payload, bytes) else str(payload)))

        async def snapshot() -> dict[str, object]:
            return {
                "state": {"tv_power_state": "off", "source": "Piscina"},
                "presets": [{"name": "Cozinha", "position": 30}, {"name": "Piscina", "position": 100}],
                "itach": {"configured": True},
            }

        async def on_command(kind: str, payload: str) -> None:
            return None

        bridge = MqttBridge("homeassistant", snapshot, on_command)
        bridge.client = FakeClient()
        bridge.connected = True
        await bridge.publish_current_state()

        discovery = next(payload for topic, payload in published if topic.endswith("/media_player/flap_giro_tecnohead/config"))
        attributes = next(payload for topic, payload in published if topic == "flap_giro_tecnohead/attributes")
        return {"discovery": json.loads(discovery), "attributes": json.loads(attributes)}

    result = asyncio.run(exercise())
    assert result["discovery"]["source_list"] == ["Cozinha", "Piscina"]
    assert result["attributes"]["source_list"] == ["Cozinha", "Piscina"]


def test_legacy_itach_connector_number_is_upgraded_to_module_address() -> None:
    assert AppConfig(itach_connaddr="3").itach_connaddr == "1:3"


def test_config_patch_normalizes_itach_connector_number() -> None:
    from app.models import ConfigPatch

    assert ConfigPatch(itach_connaddr="3").itach_connaddr == "1:3"


def test_stop_synchronizes_target_with_estimated_position(tmp_path: Path) -> None:
    async def exercise() -> dict:
        runtime = Runtime(tmp_path, "0.1.0-test")
        await runtime.start()

        async def fake_send_ir(*args, **kwargs):
            return {"ok": True}

        runtime._send_ir = fake_send_ir
        runtime.state.update(
            {
                "position": 43.7,
                "target_position": 100.0,
                "movement_in_progress": True,
                "rotation_state": "MOVING_RIGHT",
            }
        )
        try:
            return await runtime.stop()
        finally:
            await runtime.stop()

    state = asyncio.run(exercise())
    assert state["position"] == 43.7
    assert state["target_position"] == 43.7
    assert state["movement_in_progress"] is False
    assert state["rotation_state"] == "IDLE"


def test_position_clock_starts_only_after_itach_ack(tmp_path: Path) -> None:
    async def exercise() -> tuple[list[tuple[str, bool, object]], dict]:
        runtime = Runtime(
            tmp_path,
            "0.1.0-test",
            initial_config={"full_travel_right_seconds": 0.01},
        )
        await runtime.start()
        observations: list[tuple[str, bool, object]] = []

        async def fake_send_ir(action, *args, **kwargs):
            observations.append(
                (
                    action,
                    bool(runtime.state.get("movement_in_progress")),
                    runtime.state.get("movement_started_monotonic"),
                )
            )
            return {"ok": True}

        runtime._send_ir = fake_send_ir
        try:
            await runtime._move_to_now(100, source="TEST")
            return observations, dict(runtime.state)
        finally:
            await runtime.stop()

    observations, state = asyncio.run(exercise())
    assert observations[0][0] == "right"
    assert observations[0][1] is False
    assert observations[0][2] is None
    assert observations[1][0] == "stop"
    assert observations[1][1] is True
    assert observations[1][2] is not None
    assert state["movement_in_progress"] is False


def test_recent_command_history_keeps_three_confirmed_commands(tmp_path: Path) -> None:
    async def exercise() -> list[dict]:
        runtime = Runtime(tmp_path, "0.1.0-test")
        await runtime.start()

        async def fake_send_action(action, **kwargs):
            return {"ok": True, "action": action}

        runtime.driver.send_action = fake_send_action
        try:
            for action in ("left", "right", "stop", "close"):
                await runtime._send_ir(action, source="TEST")
            return list(runtime.state["recent_commands"])
        finally:
            await runtime.stop()

    history = asyncio.run(exercise())
    assert [item["action"] for item in history] == ["close", "stop", "right"]
    assert all(item["source"] == "TEST" for item in history)


def test_stop_surfaces_ir_failure_and_marks_error(tmp_path: Path) -> None:
    async def exercise() -> dict:
        runtime = Runtime(tmp_path, "0.1.0-test")
        await runtime.start()

        async def failed_send_ir(*args, **kwargs):
            raise ItachError("iTach ocupado: busyIR,1:3,1")

        runtime._send_ir = failed_send_ir
        try:
            with pytest.raises(ItachError, match="iTach ocupado"):
                await runtime.stop()
            return runtime.state
        finally:
            await runtime.mqtt.stop()

    state = asyncio.run(exercise())
    assert state["flap_state"] == "ERROR"
    assert state["sequence"] == "ERROR"


def test_runtime_sends_one_command_to_driver(tmp_path: Path) -> None:
    async def exercise() -> tuple[int | None, float]:
        runtime = Runtime(tmp_path, "0.1.0-test")
        await runtime.start()
        calls: list[tuple[int | None, float]] = []

        async def fake_send_action(
            action,
            *,
            repeat=None,
            interval_seconds=0,
            source="SYSTEM",
            emissions=1,
            minimum_protocol_repeats=3,
        ):
            calls.append((repeat, interval_seconds))
            return {"ok": True}

        runtime.driver.send_action = fake_send_action
        try:
            await runtime._send_ir("stop", source="TEST")
            return calls[0]
        finally:
            await runtime.stop()

    repeat, interval = asyncio.run(exercise())
    assert repeat is None
    assert interval == 0


def test_position_is_rejected_while_home_calibration_is_running(tmp_path: Path) -> None:
    async def exercise() -> None:
        runtime = Runtime(tmp_path, "0.1.0-test")
        await runtime.start()
        runtime.state.update({"calibration_state": "CALIBRATING", "sequence": "CALIBRATING"})
        try:
            with pytest.raises(ValueError, match="calibração HOME ainda está em andamento"):
                await runtime.position(100)
        finally:
            await runtime.stop()

    asyncio.run(exercise())


def test_open_preserves_completed_home_calibration(tmp_path: Path) -> None:
    async def exercise() -> str:
        runtime = Runtime(tmp_path, "0.1.0-test", initial_config={"opening_seconds": 0.1})
        await runtime.start()
        runtime.state.update({"calibration_state": "CALIBRATED", "flap_state": "CLOSED"})

        async def fake_send_ir(*args, **kwargs):
            return {"ok": True}

        runtime._send_ir = fake_send_ir
        try:
            await runtime._open_sequence("TEST")
            return runtime.state["calibration_state"]
        finally:
            await runtime.stop()

    assert asyncio.run(exercise()) == "CALIBRATED"


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
