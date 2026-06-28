"""Settings schema and pure persistence logic.

Non-UI leaf module: must NOT import imagura2. Holds the shared SETTINGS_TABS
schema plus pure validation/coercion and a core save/apply implementation that
operates on ``imagura.config`` only. No ``globals()`` magic lives here -- the
mirror into ``imagura2``'s own module globals is performed by the imagura2 shim.
"""

from __future__ import annotations

from typing import Optional

from . import config as cfg
from .logging import log
from .user_settings import (
    load_user_settings,
    save_user_setting,
    user_settings_path,
)


# Settings window configuration - organized by tabs
# Format: (display_label, config_key, value_type, min_val, max_val)
# If config_key is None, it's a section header

# Labels are i18n keys resolved via imagura.i18n.tr() at render time.
# A value_type of "lang" marks the special language-selector row (handled by the
# settings modal, not the numeric editing pipeline). Tabs with "type": "info"
# render read-only content (Help/About) instead of editable fields.

SETTINGS_TABS = [
    {
        "name": "tab.general",
        "items": [
            ("hdr.language", None, None, None, None),
            ("fld.language", "LANGUAGE", "lang", None, None),
            ("hdr.performance", None, None, None, None),
            ("fld.target_fps", "TARGET_FPS", int, 30, 240),
            ("fld.async_workers", "ASYNC_WORKERS", int, 1, 32),
            ("hdr.scaling", None, None, None, None),
            ("fld.fit_default", "FIT_DEFAULT_SCALE", float, 0.5, 1.0),
            ("fld.fit_open", "FIT_OPEN_SCALE", float, 0.3, 1.0),
            ("fld.max_zoom", "MAX_ZOOM", float, 5.0, 50.0),
            ("fld.zoom_keys", "ZOOM_STEP_KEYS", float, 0.01, 0.2),
            ("fld.zoom_wheel", "ZOOM_STEP_WHEEL", float, 0.01, 0.5),
        ]
    },
    {
        "name": "tab.animation",
        "items": [
            ("hdr.anim_times", None, None, None, None),
            ("fld.anim_switch_keys", "ANIM_SWITCH_KEYS_MS", int, 1, 2000),
            ("fld.anim_switch_gallery", "ANIM_SWITCH_GALLERY_MS", int, 1, 500),
            ("fld.anim_open", "ANIM_OPEN_MS", int, 1, 2000),
            ("fld.anim_zoom", "ANIM_ZOOM_MS", int, 1, 500),
            ("fld.anim_toggle_zoom", "ANIM_TOGGLE_ZOOM_MS", int, 1, 500),
            ("fld.gallery_slide", "GALLERY_SLIDE_MS", int, 1, 500),
            ("fld.toolbar_slide", "TOOLBAR_SLIDE_MS", int, 1, 500),
        ]
    },
    {
        "name": "tab.interface",
        "items": [
            ("hdr.font", None, None, None, None),
            ("fld.font_size", "FONT_DISPLAY_SIZE", int, 12, 72),
            ("hdr.toolbar", None, None, None, None),
            ("fld.toolbar_height", "TOOLBAR_HEIGHT", int, 40, 100),
            ("fld.toolbar_btn_radius", "TOOLBAR_BTN_RADIUS", int, 16, 40),
            ("fld.toolbar_btn_spacing", "TOOLBAR_BTN_SPACING", int, 10, 40),
            ("fld.toolbar_bg_alpha", "TOOLBAR_BG_ALPHA", float, 0.3, 1.0),
            ("hdr.close_btn", None, None, None, None),
            ("fld.close_btn_radius", "CLOSE_BTN_RADIUS", int, 16, 50),
            ("fld.close_btn_margin", "CLOSE_BTN_MARGIN", int, 10, 50),
            ("hdr.overlays", None, None, None, None),
            ("fld.show_scale_overlay", "SHOW_SCALE_OVERLAY", bool, None, None),
            ("hdr.background", None, None, None, None),
            ("fld.blur", "BLUR_ENABLED", bool, None, None),
        ]
    },
    {
        "name": "tab.gallery",
        "items": [
            ("hdr.sizes", None, None, None, None),
            ("fld.gallery_height_frac", "GALLERY_HEIGHT_FRAC", float, 0.05, 0.3),
            ("fld.gallery_trigger_frac", "GALLERY_TRIGGER_FRAC", float, 0.02, 0.15),
            ("fld.gallery_thumb_spacing", "GALLERY_THUMB_SPACING", int, 5, 50),
            ("fld.gallery_min_scale", "GALLERY_MIN_SCALE", float, 0.3, 1.0),
            ("fld.gallery_min_alpha", "GALLERY_MIN_ALPHA", float, 0.1, 0.8),
            ("hdr.thumbnails", None, None, None, None),
            ("fld.thumb_cache_limit", "THUMB_CACHE_LIMIT", int, 50, 1000),
            ("fld.thumb_padding", "THUMB_PADDING", int, 2, 20),
            ("fld.thumb_preload", "THUMB_PRELOAD_SPAN", int, 10, 100),
        ]
    },
    {
        "name": "tab.input",
        "items": [
            ("hdr.mouse", None, None, None, None),
            ("fld.double_click_ms", "DOUBLE_CLICK_TIME_MS", int, 100, 600),
            ("fld.idle_threshold", "IDLE_THRESHOLD_SECONDS", float, 0.2, 2.0),
            ("hdr.keyboard", None, None, None, None),
            ("fld.key_repeat_delay", "KEY_REPEAT_DELAY", float, 0.1, 1.0),
            ("fld.key_repeat_interval", "KEY_REPEAT_INTERVAL", float, 0.02, 0.2),
            ("hdr.navigation", None, None, None, None),
            ("fld.nav_btn_radius", "NAV_BTN_RADIUS", int, 20, 80),
            ("fld.nav_edge_min", "NAV_EDGE_MIN_PX", int, 30, 150),
        ]
    },
    {
        "name": "tab.limits",
        "items": [
            ("hdr.images", None, None, None, None),
            ("fld.max_image_dim", "MAX_IMAGE_DIMENSION", int, 4096, 32768),
            ("fld.max_file_size", "MAX_FILE_SIZE_MB", int, 50, 1000),
            ("fld.heavy_file_size", "HEAVY_FILE_SIZE_MB", int, 5, 100),
            ("fld.heavy_min_side", "HEAVY_MIN_SHORT_SIDE", int, 1000, 10000),
            ("hdr.cache", None, None, None, None),
            ("fld.full_cache_mb", "FULL_IMAGE_CACHE_MAX_MB", int, 0, 4096),
            ("fld.full_cache_items", "FULL_IMAGE_CACHE_MAX_ITEMS", int, 0, 64),
            ("fld.anim_cache_mb", "ANIMATED_CONTENT_CACHE_MAX_MB", int, 0, 4096),
            ("fld.anim_cache_items", "ANIMATED_CONTENT_CACHE_MAX_ITEMS", int, 0, 64),
            ("fld.gif_max_frames", "MAX_ANIM_FRAMES", int, 1, 5000),
            ("fld.gif_decode_mb", "MAX_ANIM_MEMORY_MB", int, 16, 2048),
            ("hdr.window", None, None, None, None),
            ("fld.min_window_w", "MIN_WINDOW_WIDTH", int, 200, 800),
            ("fld.min_window_h", "MIN_WINDOW_HEIGHT", int, 150, 600),
            ("fld.gallery_min_h", "GALLERY_MIN_HEIGHT_PX", int, 40, 200),
        ]
    },
    {
        "name": "tab.help",
        "type": "info",
        "content": "help",
        "items": [],
    },
    {
        "name": "tab.about",
        "type": "info",
        "content": "about",
        "items": [],
    },
]


def is_editable_item(item) -> bool:
    """True for rows that are standard editable numeric/bool fields.

    Excludes section headers (config_key None) and special rows like the language
    selector (value_type "lang"), so they are skipped by the editing pipeline.
    """
    return item[1] is not None and item[2] in (int, float, bool)

# Backward compatibility: flat list for legacy code
SETTINGS_ITEMS = []
for tab in SETTINGS_TABS:
    SETTINGS_ITEMS.extend(tab["items"])


def get_settings_item_index(item_idx: int) -> int:
    """Convert visual item index to editable item index (skip headers)."""
    editable_idx = 0
    for i, item in enumerate(SETTINGS_ITEMS):
        if is_editable_item(item):  # Not a header / special row
            if i == item_idx:
                return editable_idx
            editable_idx += 1
    return -1


def settings_definitions() -> dict[str, tuple[type, object, object]]:
    definitions = {}
    for tab in SETTINGS_TABS:
        for _label, config_key, val_type, min_val, max_val in tab["items"]:
            if config_key is not None and val_type in (int, float, bool):
                definitions[config_key] = (val_type, min_val, max_val)
    return definitions


def validate_settings_value(value_str: str, val_type: type, min_val, max_val) -> tuple:
    """Validate a settings value. Returns (is_valid, parsed_value, error_msg)."""
    if not value_str.strip():
        return False, None, "Empty value"

    try:
        if val_type == bool:
            return True, value_str if isinstance(value_str, bool) else value_str.strip().lower() == "true", None
        if val_type == int:
            val = int(value_str)
        elif val_type == float:
            val = float(value_str)
        else:
            return False, None, "Unknown type"

        if min_val is not None and val < min_val:
            return False, None, f"Min: {min_val}"
        if max_val is not None and val > max_val:
            return False, None, f"Max: {max_val}"

        return True, val, None

    except ValueError:
        return False, None, "Invalid number"


def _coerce_setting_value(config_key: str, value, val_type: type, min_val, max_val):
    if val_type == bool:
        if isinstance(value, bool):
            parsed = value
        elif isinstance(value, str):
            parsed = value.strip().lower() == "true"
        else:
            parsed = bool(value)
    else:
        is_valid, parsed, error = validate_settings_value(str(value), val_type, min_val, max_val)
        if not is_valid:
            raise ValueError(f"{config_key}: {error}")
    return parsed


def _set_config_value(config_key: str, value, val_type: type) -> None:
    """Set the typed value on ``imagura.config`` only.

    The mirror into imagura2's own module globals is handled by the imagura2 shim.
    """
    typed_value = val_type(value)
    setattr(cfg, config_key, typed_value)


def apply_saved_settings_impl(state=None, *, on_applied=None) -> None:
    """Load persisted user settings into ``imagura.config``.

    ``on_applied`` is an optional callback ``(config_key, state) -> None`` invoked
    after each setting is applied, used by the imagura2 shim to trigger cache
    reconfiguration (apply_runtime_config_change).
    """
    saved = load_user_settings()
    if not saved:
        return

    definitions = settings_definitions()
    applied = 0
    for config_key, raw_value in saved.items():
        definition = definitions.get(config_key)
        if definition is None:
            continue
        val_type, min_val, max_val = definition
        try:
            value = _coerce_setting_value(config_key, raw_value, val_type, min_val, max_val)
        except ValueError as exc:
            log(f"[SETTINGS][WARN] Ignoring saved value: {exc}")
            continue
        _set_config_value(config_key, value, val_type)
        if on_applied is not None:
            on_applied(config_key, state)
        applied += 1

    if applied:
        log(f"[SETTINGS] Loaded {applied} user settings from {user_settings_path()}")


def save_config_value_impl(config_key: str, value, val_type: type, state=None, *, on_applied=None) -> bool:
    """Save a single config value to the user settings file and ``imagura.config``.

    ``on_applied`` is an optional callback ``(config_key, state) -> None`` invoked
    after a successful save, used by the imagura2 shim to trigger cache
    reconfiguration (apply_runtime_config_change).
    """
    definitions = settings_definitions()
    definition = definitions.get(config_key)
    if definition is None:
        log(f"[SETTINGS][ERR] Unknown setting {config_key}")
        return False

    expected_type, min_val, max_val = definition
    if expected_type is not val_type:
        val_type = expected_type

    try:
        typed_value = _coerce_setting_value(config_key, value, val_type, min_val, max_val)
        _set_config_value(config_key, typed_value, val_type)
        save_user_setting(config_key, typed_value)
        if on_applied is not None:
            on_applied(config_key, state)
        log(f"[SETTINGS] Saved {config_key} = {typed_value} to {user_settings_path()}")
        return True

    except Exception as e:
        log(f"[SETTINGS][ERR] Failed to save {config_key}: {e!r}")
        return False
