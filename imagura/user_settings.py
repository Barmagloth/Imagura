"""User-writable settings persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


APP_NAME = "Imagura"
ENV_SETTINGS_PATH = "IMAGURA_USER_SETTINGS_PATH"


def user_settings_path() -> Path:
    override = os.environ.get(ENV_SETTINGS_PATH)
    if override:
        return Path(override)

    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME / "settings.json"
        return Path.home() / "AppData" / "Roaming" / APP_NAME / "settings.json"

    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / APP_NAME.lower() / "settings.json"
    return Path.home() / ".config" / APP_NAME.lower() / "settings.json"


def load_user_settings() -> dict[str, Any]:
    path = user_settings_path()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}
    return data


def save_user_setting(key: str, value: Any) -> Path:
    path = user_settings_path()
    data = load_user_settings()
    data[key] = value
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            f.write(text)
        tmp_path.replace(path)
    except PermissionError:
        path.write_text(text, encoding="utf-8")
        try:
            tmp_path.unlink()
        except OSError:
            pass
    return path
