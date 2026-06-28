"""Text overlay rendering for filename, scale, and HUD."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from .. import config as cfg
from ..image_metadata import get_image_metadata
from ..rl_compat import draw_text as RL_DrawText
from ..rl_compat import make_color as RL_Color
from ..rl_compat import make_vec2 as RL_V2
from ..rl_compat import rl
from ..zoom import scale_overlay_text, zoom_mode_label

if TYPE_CHECKING:
    from ..state import AppState


def draw_text_raw(state: "AppState", text: str, x: int, y: int, font_size: int, color) -> None:
    """Draw text using the app Unicode font when available."""
    if state.unicode_font:
        try:
            rl.DrawTextEx(state.unicode_font, text.encode("utf-8"), RL_V2(x, y), font_size, 1.0, color)
            return
        except Exception:
            pass
    RL_DrawText(text, x, y, font_size, color)


def measure_text_width(state: "AppState", text: str, font_size: int) -> int:
    """Measure text width using the active app font."""
    if state.unicode_font:
        try:
            return int(rl.MeasureTextEx(state.unicode_font, text.encode("utf-8"), font_size, 1.0).x)
        except Exception:
            pass
    try:
        return int(rl.MeasureText(text, font_size))
    except TypeError:
        return int(rl.MeasureText(text.encode("utf-8"), font_size))


def _build_shadow_passes() -> list[tuple[int, int, int]]:
    radius = 6
    y_bias = 1
    passes = []
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            dist_sq = dx * dx + dy * dy
            if dist_sq <= radius * radius:
                t = dist_sq ** 0.5 / radius
                alpha = int(40 * (1.0 - t))
                if alpha > 0:
                    passes.append((dx, dy + y_bias, alpha))
    return passes


_SHADOW_PASSES = _build_shadow_passes()


def draw_text_shadowed(state: "AppState", text: str, x: int, y: int, font_size: int, color) -> None:
    """Draw text with a soft drop shadow."""
    for dx, dy, alpha in _SHADOW_PASSES:
        draw_text_raw(state, text, x + dx, y + dy, font_size, RL_Color(0, 0, 0, alpha))
    draw_text_raw(state, text, x, y, font_size, color)


def draw_filename_overlay(state: "AppState") -> None:
    """Draw image index and filename at top center."""
    if not state.show_filename or state.index >= len(state.current_dir_images):
        return

    filepath = state.current_dir_images[state.index]
    total = len(state.current_dir_images)
    info_text = f"[{state.index + 1} / {total}] {os.path.basename(filepath)}"

    font_size = cfg.FONT_DISPLAY_SIZE
    x = (state.screenW - measure_text_width(state, info_text, font_size)) // 2
    draw_text_shadowed(state, info_text, x, 40, font_size, RL_Color(255, 255, 255, 255))


def draw_scale_overlay(state: "AppState") -> None:
    """Draw transient scale indicator at bottom center."""
    alpha = state.ui.scale_overlay_alpha
    if alpha <= 0.0:
        return

    text = scale_overlay_text(state.view.scale, state.ui.scale_overlay_mode)
    font_size = cfg.FONT_DISPLAY_SIZE
    text_width = measure_text_width(state, text, font_size)
    x = (state.screenW - text_width) // 2
    y = state.screenH - 60

    for dx, dy, sa in _SHADOW_PASSES:
        shadow_a = int(sa * alpha)
        if shadow_a > 0:
            draw_text_raw(state, text, x + dx, y + dy, font_size, RL_Color(0, 0, 0, shadow_a))

    draw_text_raw(state, text, x, y, font_size, RL_Color(255, 255, 255, int(255 * alpha)))


def draw_hud(state: "AppState") -> None:
    """Draw the optional diagnostic HUD."""
    if not state.show_hud:
        return

    hud_font_size = cfg.FONT_DISPLAY_SIZE
    line_spacing = hud_font_size + 4
    hud_color = RL_Color(255, 255, 255, 230)

    hud_lines = []
    total = len(state.current_dir_images)
    hud_lines.append(f"[{state.index + 1}/{total}]")
    hud_lines.append(f"{int(round(state.view.scale * 100))}% ({zoom_mode_label(state.zoom_state_cycle)})")

    if state.cache.curr:
        hud_lines.append(f"{state.cache.curr.w} x {state.cache.curr.h}")

    if state.index < len(state.current_dir_images):
        metadata = get_image_metadata(state.current_dir_images[state.index])
        if metadata:
            if "date" in metadata:
                hud_lines.append(metadata["date"])
            camera_info = []
            if "camera" in metadata:
                camera_info.append(metadata["camera"])
            if camera_info:
                hud_lines.append(" ".join(camera_info))
            exp_info = []
            if "focal" in metadata:
                exp_info.append(metadata["focal"])
            if "aperture" in metadata:
                exp_info.append(metadata["aperture"])
            if "exposure" in metadata:
                exp_info.append(metadata["exposure"])
            if "iso" in metadata:
                exp_info.append(metadata["iso"])
            if exp_info:
                hud_lines.append(" | ".join(exp_info))

    hud_y = state.screenH - (len(hud_lines) * line_spacing + 20)
    for i, line in enumerate(hud_lines):
        draw_text_shadowed(state, line, 12, hud_y + i * line_spacing, hud_font_size, hud_color)
