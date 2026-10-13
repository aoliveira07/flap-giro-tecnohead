from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_options() -> dict[str, Any]:
    path = Path(os.getenv("OPTIONS_PATH", "/data/options.json"))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def data_dir() -> Path:
    return Path(os.getenv("APP_DATA_DIR", "/data"))


def app_version() -> str:
    return os.getenv("APP_VERSION", "0.1.0-alpha.24")

