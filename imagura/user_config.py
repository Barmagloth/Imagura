"""User configuration persistence via TOML file.

Stores user overrides in a platform-appropriate directory:
- Windows: %APPDATA%/Imagura/config.toml
- Linux: ~/.config/imagura/config.toml
- macOS: ~/Library/Application Support/Imagura/config.toml

Falls back gracefully if the directory is not writable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from imagura import logging as imagura_logging

# Try to import tomllib (Python 3.11+), fall back to manual parsing for 3.10
if sys.version_info >= (3, 11):
    import tomllib
    HAS_TOMLLIB = True
else:
    HAS_TOMLLIB = False


def get_config_dir() -> Path:
    """Get the platform-appropriate config directory.

    Returns:
        Path to config directory (~/.config/imagura on Linux, etc.)

    Raises:
        RuntimeError: If unable to determine config directory.
    """
    if sys.platform == "win32":
        # Windows: %APPDATA%/Imagura
        appdata = Path.home() / "AppData" / "Roaming"
        return appdata / "Imagura"
    elif sys.platform == "darwin":
        # macOS: ~/Library/Application Support/Imagura
        return Path.home() / "Library" / "Application Support" / "Imagura"
    else:
        # Linux and other Unix-like: ~/.config/imagura
        xdg_config = Path.home() / ".config"
        return xdg_config / "imagura"


def get_config_path() -> Path:
    """Get the full path to the config.toml file.

    Returns:
        Path to config.toml file.
    """
    return get_config_dir() / "config.toml"


def _parse_toml_simple(content: str) -> dict[str, Any]:
    """Parse simple flat TOML file (key = value pairs only).

    This is a minimal TOML parser for simple key = value pairs.
    Handles int, float, and string values with basic comments.

    Args:
        content: TOML file content as string.

    Returns:
        Dictionary of parsed values.
    """
    config: dict[str, Any] = {}

    for line in content.split("\n"):
        # Remove comments and strip whitespace
        line = line.split("#")[0].strip()

        if not line or line.startswith("["):
            # Skip empty lines and section headers
            continue

        if "=" not in line:
            continue

        key, _, value_str = line.partition("=")
        key = key.strip()
        value_str = value_str.strip()

        if not key:
            continue

        # Parse value
        try:
            # Try int
            if "." not in value_str:
                config[key] = int(value_str)
            else:
                # Try float
                config[key] = float(value_str)
        except ValueError:
            # String value (remove quotes if present)
            value_str = value_str.strip('"\'')
            config[key] = value_str

    return config


def load_user_config() -> dict[str, Any]:
    """Load user configuration from TOML file.

    Returns empty dict if file doesn't exist or can't be read.

    Returns:
        Dictionary of user configuration overrides.
    """
    config_path = get_config_path()

    if not config_path.exists():
        return {}

    try:
        content = config_path.read_text(encoding="utf-8")
        imagura_logging.log(f"[CONFIG] Loading user config from {config_path}")

        if HAS_TOMLLIB:
            # Python 3.11+ - use native tomllib
            return tomllib.loads(content)
        else:
            # Python 3.10 - use simple parser
            return _parse_toml_simple(content)

    except Exception as e:
        imagura_logging.log(f"Error loading config from {config_path}: {e}")
        return {}


def save_value(key: str, value: int | float, val_type: type) -> bool:
    """Save a single configuration value to the TOML file.

    Reads existing file, updates the key, and writes back.
    Falls back silently if directory is not writable.

    Args:
        key: Configuration key to save.
        value: Value to save (int or float).
        val_type: Expected type (int or float) - for validation.

    Returns:
        True if saved successfully, False otherwise.
    """
    # Validate type
    if val_type not in (int, float):
        imagura_logging.log(f"Invalid type for config save: {val_type}")
        return False

    if not isinstance(value, val_type):
        imagura_logging.log(
            f"Type mismatch: expected {val_type.__name__}, got {type(value).__name__}"
        )
        return False

    config_path = get_config_path()

    try:
        # Ensure config directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing config
        if config_path.exists():
            try:
                existing_content = config_path.read_text(encoding="utf-8")
                config = _parse_toml_simple(existing_content)
            except Exception as e:
                imagura_logging.log(f"Error reading existing config: {e}")
                config = {}
        else:
            config = {}

        # Update value
        config[key] = value

        # Write back as simple TOML
        lines = [
            "# Imagura user configuration",
            "# Auto-generated - manual edits may be lost",
            "",
        ]

        for config_key, config_value in sorted(config.items()):
            lines.append(f"{config_key} = {config_value}")

        new_content = "\n".join(lines) + "\n"
        config_path.write_text(new_content, encoding="utf-8")

        imagura_logging.log(f"Saved config: {key} = {value}")
        return True

    except Exception as e:
        imagura_logging.log(f"Error saving config to {config_path}: {e}")
        return False


def apply_user_config() -> None:
    """Load user config and apply overrides to imagura.config module.

    This function:
    1. Loads user config from TOML file
    2. Applies each value to the imagura.config module via setattr
    3. Logs all applied overrides
    4. Handles errors gracefully (logs but doesn't crash)

    Should be called at app startup, after config module is imported.
    """
    user_config = load_user_config()

    if not user_config:
        return

    try:
        # Import config module to apply overrides
        from imagura import config

        for key, value in user_config.items():
            try:
                setattr(config, key, value)
                imagura_logging.log(f"Applied user config: {key} = {value}")
            except Exception as e:
                imagura_logging.log(f"Error applying config {key}: {e}")

    except Exception as e:
        imagura_logging.log(f"Error in apply_user_config: {e}")
