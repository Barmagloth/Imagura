"""Renderer - handles all drawing operations.

The Renderer is a pure drawing layer that only reads state and draws to screen.
It does not modify state - all state changes happen in update functions.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional
import os
import math

if TYPE_CHECKING:
    from .state import AppState

from .rl_compat import (
    rl, RL_WHITE,
    make_rect as RL_Rect, make_vec2 as RL_V2, make_color as RL_Color,
    draw_text as RL_DrawText,
)
from .types import ViewParams, TextureInfo
from .math_utils import clamp, lerp
from .config import (
    BG_MODES,
    CLOSE_BTN_RADIUS, CLOSE_BTN_MARGIN, CLOSE_BTN_BG_ALPHA_MAX,
    NAV_BTN_RADIUS, NAV_BTN_BG_ALPHA_MAX,
    GALLERY_HEIGHT_FRAC, GALLERY_THUMB_SPACING,
    GALLERY_MIN_SCALE, GALLERY_MIN_ALPHA,
)
from .logging import now


@dataclass
class Renderer:
    """
    Handles all drawing operations.

    Usage:
        renderer = Renderer()
        renderer.begin_frame(state)
        renderer.draw_background(state)
        renderer.draw_image(state)
        renderer.draw_gallery(state)
        renderer.draw_ui(state)
        renderer.end_frame()
    """

    def begin_frame(self) -> None:
        """Begin a new frame."""
        rl.BeginDrawing()

    def end_frame(self) -> None:
        """End the current frame."""
        rl.EndDrawing()

    # ═══════════════════════════════════════════════════════════════════════
    # Background
    # ═══════════════════════════════════════════════════════════════════════

    def draw_background(self, state: "AppState") -> None:
        """Draw background with current mode and opacity."""
        mode = BG_MODES[state.bg_mode_index]
        c = mode["color"]
        a = clamp(state.bg_current_opacity, 0.0, 1.0)

        if mode["blur"]:
            try:
                rl.ClearBackground(rl.BLANK)
            except Exception:
                rl.ClearBackground(RL_Color(0, 0, 0, 0))
            rl.DrawRectangle(0, 0, state.screenW, state.screenH,
                           RL_Color(c[0], c[1], c[2], int(255 * a)))
        else:
            col = RL_Color(c[0], c[1], c[2], int(255 * a))
            rl.ClearBackground(col)

    # ═══════════════════════════════════════════════════════════════════════
    # Image rendering
    # ═══════════════════════════════════════════════════════════════════════

    def draw_texture_at(self, ti: TextureInfo, v: ViewParams, alpha: float = 1.0) -> None:
        """Draw a texture at the specified view position."""
        if not ti:
            return
        tex_id = getattr(ti.tex, 'id', 0)
        if not tex_id or tex_id <= 0:
            return

        tint = RL_Color(255, 255, 255, int(255 * alpha))
        rl.DrawTexturePro(
            ti.tex,
            RL_Rect(0, 0, ti.w, ti.h),
            RL_Rect(v.offx, v.offy, ti.w * v.scale, ti.h * v.scale),
            RL_V2(0, 0), 0.0, tint
        )

    def draw_image(self, state: "AppState") -> None:
        """Draw the current image with animations."""
        ti = state.cache.curr
        if not ti:
            return

        # Open animation
        if state.open_anim_active:
            self._draw_open_animation(state, ti)
            return

        # Switch animation
        if state.switch_anim_active and state.switch_anim_prev_tex:
            self._draw_switch_animation(state, ti)
            return

        # Normal rendering
        self.draw_texture_at(ti, state.view)

    def _draw_open_animation(self, state: "AppState", ti: TextureInfo) -> None:
        """Draw open animation frame."""
        from .config import ANIM_OPEN_MS, FIT_OPEN_SCALE, OPEN_ALPHA_START

        if state.open_anim_t0 == 0.0:
            return

        t = (now() - state.open_anim_t0) / (ANIM_OPEN_MS / 1000.0)
        t = min(1.0, t)
        t_eased = self._ease_out_quad(t)

        # Calculate animated view
        fit_scale = min(
            state.screenW * FIT_OPEN_SCALE / ti.w,
            state.screenH * FIT_OPEN_SCALE / ti.h
        )
        from_view = ViewParams(
            scale=fit_scale,
            offx=(state.screenW - ti.w * fit_scale) / 2.0,
            offy=(state.screenH - ti.h * fit_scale) / 2.0,
        )

        v = ViewParams(
            scale=lerp(from_view.scale, state.last_fit_view.scale, t_eased),
            offx=lerp(from_view.offx, state.last_fit_view.offx, t_eased),
            offy=lerp(from_view.offy, state.last_fit_view.offy, t_eased),
        )
        alpha = lerp(OPEN_ALPHA_START, 1.0, t_eased)

        self.draw_texture_at(ti, v, alpha=alpha)

    def _draw_switch_animation(self, state: "AppState", ti: TextureInfo) -> None:
        """Draw switch animation frame."""
        t = (now() - state.switch_anim_t0) / (state.switch_anim_duration_ms / 1000.0)
        t = min(1.0, t)
        t_eased = self._ease_in_out_cubic(t)

        offset = state.screenW * state.switch_anim_direction
        prev_x = lerp(0, -offset, t_eased)
        curr_x = lerp(offset, 0, t_eased)

        # Draw previous image sliding out
        pv = ViewParams(
            scale=state.switch_anim_prev_view.scale,
            offx=state.switch_anim_prev_view.offx + prev_x,
            offy=state.switch_anim_prev_view.offy
        )
        self.draw_texture_at(state.switch_anim_prev_tex, pv, alpha=1.0 - t_eased)

        # Draw current image sliding in
        cv = ViewParams(
            scale=state.view.scale,
            offx=state.view.offx + curr_x,
            offy=state.view.offy
        )
        self.draw_texture_at(ti, cv, alpha=t_eased)

    # ═══════════════════════════════════════════════════════════════════════
    # Loading indicator
    # ═══════════════════════════════════════════════════════════════════════

    def draw_loading_indicator(self, state: "AppState") -> None:
        """Draw loading spinner when loading heavy image."""
        if not state.loading_current:
            return

        rl.DrawRectangle(0, 0, state.screenW, state.screenH, RL_Color(0, 0, 0, 120))

        cx = state.screenW // 2
        cy = state.screenH // 2
        radius = 50
        thickness = 6

        t = now() * 2.5
        angle = (t * 360.0) % 360.0

        rl.DrawRing(RL_V2(cx, cy), radius - thickness, radius,
                   angle, angle + 90, 32, RL_Color(255, 255, 255, 220))

        text = "Loading..."
        font_size = 28
        try:
            text_width = rl.MeasureText(text, font_size)
        except TypeError:
            text_width = rl.MeasureText(text.encode('utf-8'), font_size)

        RL_DrawText(text, cx - text_width // 2, cy + radius + 30,
                   font_size, RL_Color(255, 255, 255, 220))

    # ═══════════════════════════════════════════════════════════════════════
    # UI Elements
    # ═══════════════════════════════════════════════════════════════════════

    def draw_close_button(self, state: "AppState") -> None:
        """Draw close button in top-right corner."""
        if state.close_btn_alpha < 0.01:
            return

        dist = CLOSE_BTN_MARGIN + CLOSE_BTN_RADIUS
        cx = state.screenW - dist
        cy = dist

        btn_alpha = int(state.close_btn_alpha * 255)
        bg_alpha = int(state.close_btn_alpha * CLOSE_BTN_BG_ALPHA_MAX * 255)

        rl.DrawCircle(cx, cy, CLOSE_BTN_RADIUS, RL_Color(0, 0, 0, bg_alpha))
        rl.DrawCircleLines(cx, cy, CLOSE_BTN_RADIUS, RL_Color(255, 255, 255, btn_alpha))

        cross_size = CLOSE_BTN_RADIUS * 0.5
        rl.DrawLineEx(
            RL_V2(cx - cross_size, cy - cross_size),
            RL_V2(cx + cross_size, cy + cross_size),
            2.0, RL_Color(255, 255, 255, btn_alpha)
        )
        rl.DrawLineEx(
            RL_V2(cx + cross_size, cy - cross_size),
            RL_V2(cx - cross_size, cy + cross_size),
            2.0, RL_Color(255, 255, 255, btn_alpha)
        )

    def draw_nav_buttons(self, state: "AppState") -> None:
        """Draw navigation arrows when zoomed."""
        if state.nav_left_alpha <= 0.01 and state.nav_right_alpha <= 0.01:
            return

        cy = state.screenH // 2

        # Left arrow
        if state.nav_left_alpha > 0.01 and state.index > 0:
            cx = 60
            alpha = int(state.nav_left_alpha * 255)
            bg_alpha = int(state.nav_left_alpha * NAV_BTN_BG_ALPHA_MAX * 255)

            rl.DrawCircle(cx, cy, NAV_BTN_RADIUS, RL_Color(0, 0, 0, bg_alpha))
            rl.DrawCircleLines(cx, cy, NAV_BTN_RADIUS, RL_Color(255, 255, 255, alpha))
            self._draw_arrow_left(cx, cy, 18, RL_Color(255, 255, 255, alpha))

        # Right arrow
        if state.nav_right_alpha > 0.01 and state.index < len(state.current_dir_images) - 1:
            cx = state.screenW - 60
            alpha = int(state.nav_right_alpha * 255)
            bg_alpha = int(state.nav_right_alpha * NAV_BTN_BG_ALPHA_MAX * 255)

            rl.DrawCircle(cx, cy, NAV_BTN_RADIUS, RL_Color(0, 0, 0, bg_alpha))
            rl.DrawCircleLines(cx, cy, NAV_BTN_RADIUS, RL_Color(255, 255, 255, alpha))
            self._draw_arrow_right(cx, cy, 18, RL_Color(255, 255, 255, alpha))

    def _draw_arrow_left(self, cx: int, cy: int, size: float, color) -> None:
        """Draw left arrow icon."""
        points = [
            RL_V2(cx + size * 0.4, cy - size * 0.6),
            RL_V2(cx - size * 0.4, cy),
            RL_V2(cx + size * 0.4, cy + size * 0.6),
        ]
        rl.DrawLineEx(points[0], points[1], 2.5, color)
        rl.DrawLineEx(points[1], points[2], 2.5, color)

    def _draw_arrow_right(self, cx: int, cy: int, size: float, color) -> None:
        """Draw right arrow icon."""
        points = [
            RL_V2(cx - size * 0.4, cy - size * 0.6),
            RL_V2(cx + size * 0.4, cy),
            RL_V2(cx - size * 0.4, cy + size * 0.6),
        ]
        rl.DrawLineEx(points[0], points[1], 2.5, color)
        rl.DrawLineEx(points[1], points[2], 2.5, color)

    def draw_filename(self, state: "AppState") -> None:
        """Draw filename at top of screen."""
        if not state.show_filename or state.index >= len(state.current_dir_images):
            return

        filepath = state.current_dir_images[state.index]
        filename = os.path.basename(filepath)
        font_size = 24
        color = self._get_filename_color(state)

        if state.unicode_font:
            try:
                filename_bytes = filename.encode('utf-8')
                text_vec = rl.MeasureTextEx(state.unicode_font, filename_bytes, font_size, 1.0)
                text_width = int(text_vec.x)
                x = (state.screenW - text_width) // 2
                y = 40
                rl.DrawTextEx(state.unicode_font, filename_bytes, RL_V2(x, y),
                            font_size, 1.0, color)
                return
            except Exception:
                pass

        try:
            text_width = rl.MeasureText(filename, font_size)
        except TypeError:
            text_width = rl.MeasureText(filename.encode('utf-8'), font_size)

        x = (state.screenW - text_width) // 2
        y = 40
        RL_DrawText(filename, x, y, font_size, color)

    def _get_filename_color(self, state: "AppState"):
        """Get text color based on background."""
        mode = BG_MODES[state.bg_mode_index]
        bg_color = mode["color"]
        if bg_color == (0, 0, 0):
            return RL_Color(255, 255, 255, 255)
        else:
            return RL_Color(0, 0, 0, 255)

    def draw_hud(self, state: "AppState") -> None:
        """Draw debug HUD."""
        if not state.show_hud:
            return

        from .rl_compat import RL_VERSION

        hud_y = state.screenH - 180
        line_spacing = 24

        RL_DrawText(f"RL={RL_VERSION}", 12, hud_y, 16, rl.LIGHTGRAY)
        RL_DrawText(
            f"idx={state.index + 1}/{len(state.current_dir_images)} zoom={state.view.scale:.3f}",
            12, hud_y + line_spacing, 16, rl.LIGHTGRAY
        )
        RL_DrawText(
            f"loading={state.loading_current} idle={state.idle_detector.is_idle() if state.idle_detector else False}",
            12, hud_y + line_spacing * 2, 16, rl.LIGHTGRAY
        )

        if state.cache.curr:
            tid = getattr(state.cache.curr.tex, 'id', 0)
            RL_DrawText(
                f"curr_tex_id={tid} w={state.cache.curr.w} h={state.cache.curr.h}",
                12, hud_y + line_spacing * 3, 16, rl.LIGHTGRAY
            )
        else:
            RL_DrawText("curr_tex=None", 12, hud_y + line_spacing * 3, 16, rl.LIGHTGRAY)

    # ═══════════════════════════════════════════════════════════════════════
    # Gallery
    # ═══════════════════════════════════════════════════════════════════════

    def draw_gallery(self, state: "AppState") -> None:
        """Draw thumbnail gallery at bottom of screen."""
        n = len(state.current_dir_images)
        if n == 0:
            return

        sw, sh = state.screenW, state.screenH
        gh = int(sh * GALLERY_HEIGHT_FRAC)
        y_hidden = sh
        y_visible = sh - gh
        y = int(clamp(state.gallery_y, y_visible, y_hidden))

        # Panel background
        alpha_panel = 1.0 - ((state.gallery_y - y_visible) / (y_hidden - y_visible))
        rl.DrawRectangle(0, y, sw, gh, RL_Color(0, 0, 0, int(255 * 0.6 * alpha_panel)))

        # Get mouse position for hover effects
        mouse = rl.GetMousePosition()
        center_x = sw // 2
        base_thumb_h = int(gh * 0.8)
        visible_range = 10

        start_idx = max(0, int(state.gallery_center_index) - visible_range)
        end_idx = min(n - 1, int(state.gallery_center_index) + visible_range)

        # Calculate thumbnail positions
        thumb_positions = self._calculate_thumb_positions(
            state, start_idx, end_idx, visible_range, base_thumb_h
        )

        # Apply fractional offset
        center_frac = state.gallery_center_index - int(state.gallery_center_index)
        center_int = int(state.gallery_center_index)
        offset_adjust = 0.0
        if center_frac > 0 and center_int + 1 in thumb_positions and center_int in thumb_positions:
            offset_adjust = lerp(thumb_positions[center_int], thumb_positions[center_int + 1], center_frac)

        # Draw thumbnails
        for idx in range(start_idx, end_idx + 1):
            if idx not in thumb_positions:
                continue

            self._draw_gallery_thumb(
                state, idx, y, gh, center_x, base_thumb_h,
                visible_range, thumb_positions, offset_adjust,
                alpha_panel, mouse
            )

    def _calculate_thumb_positions(self, state: "AppState", start_idx: int, end_idx: int,
                                   visible_range: int, base_thumb_h: int) -> dict:
        """Calculate x-position for each thumbnail relative to center."""
        thumb_positions = {}
        center_idx = int(state.gallery_center_index)
        thumb_positions[center_idx] = 0.0

        # Left of center
        cumulative_offset = 0.0
        for idx in range(center_idx - 1, start_idx - 1, -1):
            w_curr, w_next = self._get_thumb_widths(state, idx, idx + 1, visible_range, base_thumb_h)
            cumulative_offset -= (w_curr / 2.0 + GALLERY_THUMB_SPACING + w_next / 2.0)
            thumb_positions[idx] = cumulative_offset

        # Right of center
        cumulative_offset = 0.0
        for idx in range(center_idx + 1, end_idx + 1):
            w_curr, w_prev = self._get_thumb_widths(state, idx, idx - 1, visible_range, base_thumb_h)
            cumulative_offset += (w_prev / 2.0 + GALLERY_THUMB_SPACING + w_curr / 2.0)
            thumb_positions[idx] = cumulative_offset

        return thumb_positions

    def _get_thumb_widths(self, state: "AppState", idx1: int, idx2: int,
                         visible_range: int, base_thumb_h: int) -> tuple:
        """Get widths of two thumbnails."""
        widths = []
        for idx in [idx1, idx2]:
            p = state.current_dir_images[idx]
            bt = state.thumb_cache.get(p)
            distance = abs(idx - state.gallery_center_index)
            scale_factor = lerp(1.0, GALLERY_MIN_SCALE, min(1.0, distance / visible_range))

            if bt and bt.ready and bt.texture:
                w = int(bt.size[0] * scale_factor)
            else:
                w = int(base_thumb_h * 1.4 * scale_factor)
            widths.append(w)
        return tuple(widths)

    def _draw_gallery_thumb(self, state: "AppState", idx: int, y: int, gh: int,
                           center_x: int, base_thumb_h: int, visible_range: int,
                           thumb_positions: dict, offset_adjust: float,
                           alpha_panel: float, mouse) -> None:
        """Draw a single gallery thumbnail."""
        p = state.current_dir_images[idx]
        bt = state.thumb_cache.get(p)

        distance = abs(idx - state.gallery_center_index)
        scale_factor = lerp(1.0, GALLERY_MIN_SCALE, min(1.0, distance / visible_range))
        alpha_factor = lerp(1.0, GALLERY_MIN_ALPHA, min(1.0, distance / visible_range))

        if bt and bt.ready and bt.texture and getattr(bt.texture, 'id', 0):
            scaled_w = int(bt.size[0] * scale_factor)
            scaled_h = int(bt.size[1] * scale_factor)

            thumb_center_x = center_x + int(thumb_positions[idx] - offset_adjust)
            thumb_x = thumb_center_x - scaled_w // 2
            thumb_y = y + (gh - scaled_h) // 2

            is_hover = (thumb_x <= mouse.x <= thumb_x + scaled_w and
                       thumb_y <= mouse.y <= thumb_y + scaled_h)
            final_alpha = 1.0 if is_hover else alpha_factor

            src_rect = RL_Rect(0, 0, bt.size[0], bt.size[1])
            dst_rect = RL_Rect(thumb_x, thumb_y, scaled_w, scaled_h)
            tint = RL_Color(255, 255, 255, int(255 * final_alpha * alpha_panel))
            rl.DrawTexturePro(bt.texture, src_rect, dst_rect, RL_V2(0, 0), 0.0, tint)

            # Selection border
            if idx == state.index:
                rl.DrawRectangleLines(
                    thumb_x - 2, thumb_y - 2, scaled_w + 4, scaled_h + 4,
                    RL_Color(255, 255, 255, int(255 * alpha_panel))
                )
        else:
            # Placeholder
            scaled_w = int(base_thumb_h * 1.4 * scale_factor)
            scaled_h = int(base_thumb_h * scale_factor)
            thumb_center_x = center_x + int(thumb_positions[idx] - offset_adjust)
            thumb_x = thumb_center_x - scaled_w // 2
            thumb_y = y + (gh - scaled_h) // 2

            rl.DrawRectangle(
                thumb_x, thumb_y, scaled_w, scaled_h,
                RL_Color(64, 64, 64, int(255 * alpha_factor * alpha_panel))
            )

    # ═══════════════════════════════════════════════════════════════════════
    # Convenience methods
    # ═══════════════════════════════════════════════════════════════════════

    def draw_all(self, state: "AppState") -> None:
        """Draw everything in correct order."""
        self.draw_background(state)
        self.draw_image(state)
        self.draw_nav_buttons(state)
        self.draw_close_button(state)
        self.draw_filename(state)
        self.draw_gallery(state)
        self.draw_loading_indicator(state)
        self.draw_hud(state)

    def draw_frame(self, state: "AppState") -> None:
        """Complete frame: begin, draw all, end."""
        self.begin_frame()
        self.draw_all(state)
        self.end_frame()

    # ═══════════════════════════════════════════════════════════════════════
    # Easing functions (duplicated here for independence)
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _ease_out_quad(t: float) -> float:
        return 1.0 - (1.0 - t) * (1.0 - t)

    @staticmethod
    def _ease_in_out_cubic(t: float) -> float:
        if t < 0.5:
            return 4.0 * t * t * t
        else:
            return 1.0 - pow(-2.0 * t + 2.0, 3) / 2.0


# Singleton instance
_default_renderer: Optional[Renderer] = None


def get_renderer() -> Renderer:
    """Get the default renderer instance."""
    global _default_renderer
    if _default_renderer is None:
        _default_renderer = Renderer()
    return _default_renderer
