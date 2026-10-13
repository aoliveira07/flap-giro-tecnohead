"""Keep the Home Assistant Universal Media Player managed by the app.

The app is installed on different Home Assistant instances, so the composite
player cannot depend on a user manually copying YAML into an editor.  This
module owns only the small include and platform entry required by the app and
leaves unrelated Home Assistant configuration untouched.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


MANAGED_UNIQUE_PREFIX = "flap_giro_tecnohead_"
PRESET_INPUT_SELECT_ENTITY_ID = "input_select.flap_giro_tecnohead_preset"
MANAGED_INPUT_SELECT_KEY = "flap_giro_tecnohead_preset"
MANAGED_INPUT_SELECT_BEGIN = "# BEGIN flap-giro-tecnohead managed input select"
MANAGED_INPUT_SELECT_END = "# END flap-giro-tecnohead managed input select"


@dataclass(frozen=True)
class CompositionUpdate:
    changed: bool = False
    include_changed: bool = False
    media_player_changed: bool = False
    input_select_changed: bool = False
    media_include_changed: bool = False
    input_select_include_changed: bool = False
    disabled: bool = False


def _yaml_string(value: str) -> str:
    """Return a YAML-safe double-quoted scalar without a YAML dependency."""

    return json.dumps(str(value), ensure_ascii=False)


def _object_id(entity_id: str) -> str:
    return entity_id.split(".", 1)[1] if "." in entity_id else entity_id


def render_universal_media_player(
    *,
    composed_entity_id: str,
    base_entity_id: str,
    friendly_name: str,
    preset_select_entity_id: str = PRESET_INPUT_SELECT_ENTITY_ID,
) -> str:
    """Render the complete TV control surface for a Universal Media Player."""

    base = _yaml_string(base_entity_id)
    preset_select = _yaml_string(preset_select_entity_id)
    object_id = _object_id(composed_entity_id)
    unique_id = f"{MANAGED_UNIQUE_PREFIX}{object_id}"

    return f'''- platform: universal
  name: {_yaml_string(friendly_name)}
  unique_id: {_yaml_string(unique_id)}
  device_class: tv
  children:
    - {base}
  commands:
    turn_on:
      action: media_player.turn_on
      target:
        entity_id: {base}
    turn_off:
      action: media_player.turn_off
      target:
        entity_id: {base}
    volume_set:
      action: media_player.volume_set
      target:
        entity_id: {base}
      data:
        volume_level: "{{{{ volume_level }}}}"
    volume_up:
      action: media_player.volume_up
      target:
        entity_id: {base}
    volume_down:
      action: media_player.volume_down
      target:
        entity_id: {base}
    volume_mute:
      action: media_player.volume_mute
      target:
        entity_id: {base}
      data:
        is_volume_muted: "{{{{ is_volume_muted }}}}"
    media_play:
      action: media_player.media_play
      target:
        entity_id: {base}
    media_pause:
      action: media_player.media_pause
      target:
        entity_id: {base}
    media_stop:
      action: media_player.media_stop
      target:
        entity_id: {base}
    media_previous_track:
      action: media_player.media_previous_track
      target:
        entity_id: {base}
    media_next_track:
      action: media_player.media_next_track
      target:
        entity_id: {base}
    play_media:
      action: media_player.play_media
      target:
        entity_id: {base}
      data:
        media_content_id: "{{{{ media_content_id }}}}"
        media_content_type: "{{{{ media_content_type }}}}"
    select_source:
      action: input_select.select_option
      target:
        entity_id: {preset_select}
      data:
        option: "{{{{ source }}}}"
  attributes:
    state: {base}
    volume_level: {_yaml_string(f"{base_entity_id}|volume_level")}
    is_volume_muted: {_yaml_string(f"{base_entity_id}|is_volume_muted")}
    source: {preset_select}
    source_list: {_yaml_string(f"{preset_select_entity_id}|options")}
    media_title: {_yaml_string(f"{base_entity_id}|media_title")}
    media_artist: {_yaml_string(f"{base_entity_id}|media_artist")}
    media_album_name: {_yaml_string(f"{base_entity_id}|media_album_name")}
    media_content_id: {_yaml_string(f"{base_entity_id}|media_content_id")}
    media_content_type: {_yaml_string(f"{base_entity_id}|media_content_type")}
    media_duration: {_yaml_string(f"{base_entity_id}|media_duration")}
    media_position: {_yaml_string(f"{base_entity_id}|media_position")}
    media_position_updated_at: {_yaml_string(f"{base_entity_id}|media_position_updated_at")}
    entity_picture: {_yaml_string(f"{base_entity_id}|entity_picture")}
'''


class HomeAssistantCompositionFiles:
    """Idempotently maintain the app-owned Home Assistant YAML entry."""

    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or self._default_config_dir()

    @staticmethod
    def _default_config_dir() -> Path:
        configured = os.getenv("HA_CONFIG_DIR")
        if configured:
            return Path(configured)
        # Newer Home Assistant apps expose homeassistant_config as /homeassistant.
        # Keep /config as a compatibility fallback for older installations.
        for candidate in (Path("/homeassistant"), Path("/config")):
            if candidate.exists():
                return candidate
        return Path("/homeassistant")

    @property
    def available(self) -> bool:
        return self.config_dir.is_dir()

    def ensure(
        self,
        *,
        composed_entity_id: str,
        base_entity_id: str,
        friendly_name: str,
        presets: list[dict[str, object]] | None = None,
        source_options: list[str] | None = None,
        preset_select_entity_id: str = PRESET_INPUT_SELECT_ENTITY_ID,
    ) -> CompositionUpdate:
        """Write the managed entries and includes, returning the required reload."""

        if not self.available:
            return CompositionUpdate()

        media_path = self.config_dir / "media_players.yaml"
        input_select_path = self.config_dir / "input_select.yaml"
        configuration_path = self.config_dir / "configuration.yaml"
        preset_names = [str(item["name"]).strip() for item in (presets or []) if str(item.get("name", "")).strip()]
        rendered = render_universal_media_player(
            composed_entity_id=composed_entity_id,
            base_entity_id=base_entity_id,
            friendly_name=friendly_name,
            preset_select_entity_id=preset_select_entity_id,
        )
        media_changed = self._upsert_media_player(media_path, rendered)
        options = self._merge_source_options(source_options or [], preset_names)
        input_select_changed = self._upsert_input_select(input_select_path, options)
        media_include_changed = self._ensure_include(configuration_path, "media_player", "media_players.yaml")
        input_select_include_changed = self._ensure_include(configuration_path, "input_select", "input_select.yaml")
        include_changed = media_include_changed or input_select_include_changed
        return CompositionUpdate(
            changed=media_changed or input_select_changed or include_changed,
            include_changed=include_changed,
            media_player_changed=media_changed,
            input_select_changed=input_select_changed,
            media_include_changed=media_include_changed,
            input_select_include_changed=input_select_include_changed,
        )

    @staticmethod
    def _merge_source_options(original_sources: list[str], preset_names: list[str]) -> list[str]:
        options: list[str] = []
        for value in [*original_sources, *preset_names]:
            normalized = str(value).strip()
            if normalized and normalized not in options:
                options.append(normalized)
        return options

    @staticmethod
    def _write_if_changed(path: Path, content: str) -> bool:
        try:
            current = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = ""
        if current == content:
            return False
        path.write_text(content, encoding="utf-8")
        return True

    @classmethod
    def _upsert_media_player(cls, path: Path, rendered: str) -> bool:
        try:
            current = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = ""

        lines = current.splitlines(keepends=True)
        starts = [index for index, line in enumerate(lines) if line.startswith("- ")]
        blocks: list[str] = []
        prefix = ""
        if starts:
            prefix = "".join(lines[: starts[0]])
            for position, start in enumerate(starts):
                end = starts[position + 1] if position + 1 < len(starts) else len(lines)
                block = "".join(lines[start:end])
                if MANAGED_UNIQUE_PREFIX in block:
                    continue
                blocks.append(block.rstrip("\n"))
        elif current.strip():
            # A malformed/unsupported shape should not be silently overwritten.
            # The app can still report the error to the user during setup.
            raise RuntimeError(f"O arquivo {path} não contém uma lista de media players válida")

        body = "\n\n".join([*blocks, rendered.rstrip("\n")]).rstrip() + "\n"
        content = f"{prefix}{body}" if prefix else body
        return cls._write_if_changed(path, content)

    @classmethod
    def _upsert_input_select(cls, path: Path, preset_names: list[str]) -> bool:
        rendered = "\n".join(
            [
                MANAGED_INPUT_SELECT_BEGIN,
                f"{MANAGED_INPUT_SELECT_KEY}:",
                '  name: "Preset do Flap Tecnohead"',
                "  options:",
                *[f"    - {_yaml_string(name)}" for name in preset_names],
                "  icon: mdi:bookmark-multiple",
                MANAGED_INPUT_SELECT_END,
                "",
            ]
        )
        try:
            current = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = ""

        if MANAGED_INPUT_SELECT_BEGIN in current and MANAGED_INPUT_SELECT_END in current:
            start = current.index(MANAGED_INPUT_SELECT_BEGIN)
            end = current.index(MANAGED_INPUT_SELECT_END, start) + len(MANAGED_INPUT_SELECT_END)
            content = f"{current[:start]}{rendered.rstrip()}\n{current[end:].lstrip(chr(10))}"
            return cls._write_if_changed(path, content)

        for line in current.splitlines():
            if line.strip().startswith(f"{MANAGED_INPUT_SELECT_KEY}:"):
                raise RuntimeError(
                    f"O arquivo {path} já possui uma configuração manual para {MANAGED_INPUT_SELECT_KEY}"
                )
        prefix = current.rstrip()
        content = f"{prefix}\n\n{rendered}" if prefix else rendered
        return cls._write_if_changed(path, content)

    def disable(
        self,
        *,
        remove_media_include: bool = False,
        remove_input_select_include: bool = False,
    ) -> CompositionUpdate:
        """Remove only the entries owned by this app and optionally its includes."""

        if not self.available:
            return CompositionUpdate(disabled=True)

        media_path = self.config_dir / "media_players.yaml"
        input_select_path = self.config_dir / "input_select.yaml"
        configuration_path = self.config_dir / "configuration.yaml"
        media_changed = self._remove_managed_media_player(media_path)
        input_select_changed = self._remove_managed_input_select(input_select_path)
        media_include_changed = (
            self._remove_include(configuration_path, "media_player", "media_players.yaml")
            if remove_media_include and self._file_has_no_meaningful_content(media_path)
            else False
        )
        input_select_include_changed = (
            self._remove_include(configuration_path, "input_select", "input_select.yaml")
            if remove_input_select_include and self._file_has_no_meaningful_content(input_select_path)
            else False
        )
        include_changed = media_include_changed or input_select_include_changed
        return CompositionUpdate(
            changed=media_changed or input_select_changed or include_changed,
            include_changed=include_changed,
            media_player_changed=media_changed,
            input_select_changed=input_select_changed,
            media_include_changed=media_include_changed,
            input_select_include_changed=input_select_include_changed,
            disabled=True,
        )

    def managed_include_present(self, domain: str, filename: str) -> bool:
        """Tell the runtime whether an app-owned entry is currently included."""

        configuration_path = self.config_dir / "configuration.yaml"
        try:
            configuration = configuration_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return False
        if f"{domain}: !include {filename}" not in configuration:
            return False
        if domain == "media_player":
            try:
                return MANAGED_UNIQUE_PREFIX in (self.config_dir / "media_players.yaml").read_text(encoding="utf-8")
            except FileNotFoundError:
                return False
        if domain == "input_select":
            try:
                content = (self.config_dir / "input_select.yaml").read_text(encoding="utf-8")
            except FileNotFoundError:
                return False
            return MANAGED_INPUT_SELECT_BEGIN in content and MANAGED_INPUT_SELECT_END in content
        return False

    @classmethod
    def _remove_managed_media_player(cls, path: Path) -> bool:
        try:
            current = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return False
        lines = current.splitlines(keepends=True)
        starts = [index for index, line in enumerate(lines) if line.startswith("- ")]
        if not starts:
            return False
        prefix = "".join(lines[: starts[0]])
        blocks: list[str] = []
        for position, start in enumerate(starts):
            end = starts[position + 1] if position + 1 < len(starts) else len(lines)
            block = "".join(lines[start:end])
            if MANAGED_UNIQUE_PREFIX not in block:
                blocks.append(block.rstrip("\n"))
        body = "\n\n".join(blocks).rstrip()
        content = f"{prefix}{body}\n" if body else prefix.rstrip() + ("\n" if prefix.strip() else "")
        return cls._write_if_changed(path, content)

    @classmethod
    def _remove_managed_input_select(cls, path: Path) -> bool:
        try:
            current = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return False
        if MANAGED_INPUT_SELECT_BEGIN not in current or MANAGED_INPUT_SELECT_END not in current:
            return False
        start = current.index(MANAGED_INPUT_SELECT_BEGIN)
        end = current.index(MANAGED_INPUT_SELECT_END, start) + len(MANAGED_INPUT_SELECT_END)
        before = current[:start].rstrip()
        after = current[end:].lstrip("\n")
        content = f"{before}\n\n{after}" if before and after else f"{before or after}\n"
        return cls._write_if_changed(path, content)

    @classmethod
    def _remove_include(cls, path: Path, domain: str, filename: str) -> bool:
        try:
            current = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return False
        expected = f"{domain}: !include {filename}"
        lines = current.splitlines(keepends=True)
        kept = [line for line in lines if line.strip() != expected]
        if len(kept) == len(lines):
            return False
        return cls._write_if_changed(path, "".join(kept))

    @staticmethod
    def _file_has_no_meaningful_content(path: Path) -> bool:
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return True
        return not any(
            line.strip() and not line.lstrip().startswith("#")
            for line in content.splitlines()
        )

    @classmethod
    def _ensure_include(cls, path: Path, domain: str, filename: str) -> bool:
        try:
            current = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = ""
        expected = f"{domain}: !include {filename}"
        if expected in current:
            return False
        lines = current.splitlines()
        for line in lines:
            if line.strip().startswith(f"{domain}:"):
                raise RuntimeError(
                    f"{path} já possui uma configuração manual para {domain}; "
                    "o App não a substituiu automaticamente"
                )
        suffix = "\n" if current and not current.endswith("\n") else ""
        return cls._write_if_changed(path, f"{current}{suffix}\n{expected}\n")
