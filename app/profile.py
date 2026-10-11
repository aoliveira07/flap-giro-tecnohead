from __future__ import annotations

import json
from pathlib import Path


PROFILE_PATH = Path(__file__).with_name("profile.json")


def load_profile() -> dict:
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))

