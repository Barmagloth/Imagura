"""Gallery renderer: draws the thumbnail strip and reports thumbnail clicks."""

from __future__ import annotations

import os
from typing import Any, Optional

from .. import config as cfg
from ..logging import log
from ..math_utils import clamp, lerp
from ..rl_compat import rl, make_color as RL_Color, make_rect as RL_Rect, make_vec2 as RL_V2


class GalleryRenderer:
    """Draws gallery state. It does not navigate by itself."""

    def render(
        self,
        state: Any,
        mouse_x: float,
        mouse_y: float,
        left_clicked: bool,
        gallery_height: int,
    ) -> Optional[int]:
        n = len(state.current_dir_images)
        if n == 0:
            return None
        if state.gallery_y >= state.screenH:
            return None

        screen_w, screen_h = state.screenW, state.screenH
        y_hidden = screen_h
        y_visible = screen_h - gallery_height
        y = int(clamp(state.gallery_y, y_visible, y_hidden))

        denom = y_hidden - y_visible
        alpha_panel = 1.0 - ((state.gallery_y - y_visible) / denom) if denom > 0 else 1.0
        rl.DrawRectangle(0, y, screen_w, gallery_height, RL_Color(0, 0, 0, int(255 * 0.6 * alpha_panel)))

        center_x = screen_w // 2
        base_thumb_h = int(gallery_height * 0.8)
        visible_range = 10
        start_idx = max(0, int(state.gallery_center_index) - visible_range)
        end_idx = min(n - 1, int(state.gallery_center_index) + visible_range)

        thumb_positions = self._compute_thumb_positions(state, start_idx, end_idx, base_thumb_h, visible_range)
        center_frac = state.gallery_center_index - int(state.gallery_center_index)
        center_int = int(state.gallery_center_index)
        offset_adjust = 0.0
        if center_frac > 0 and center_int + 1 in thumb_positions and center_int in thumb_positions:
            offset_adjust = lerp(thumb_positions[center_int], thumb_positions[center_int + 1], center_frac)

        clicked_index = None
        for idx in range(start_idx, end_idx + 1):
            if idx not in thumb_positions:
                continue

            path = state.current_dir_images[idx]
            thumb = state.thumb_cache.get(path)
            distance = abs(idx - state.gallery_center_index)
            scale_factor = lerp(1.0, cfg.GALLERY_MIN_SCALE, min(1.0, distance / visible_range))
            alpha_factor = lerp(1.0, cfg.GALLERY_MIN_ALPHA, min(1.0, distance / visible_range))

            thumb_center_x = center_x + int(thumb_positions[idx] - offset_adjust)
            if thumb and thumb.ready and thumb.texture and getattr(thumb.texture, "id", 0) and thumb.size[1] > 0:
                fit_scale = base_thumb_h / thumb.size[1]
                total_scale = fit_scale * scale_factor
                scaled_w = int(thumb.size[0] * total_scale)
                scaled_h = int(thumb.size[1] * total_scale)
                thumb_x = thumb_center_x - scaled_w // 2
                thumb_y = y + (gallery_height - scaled_h) // 2
                is_hover = thumb_x <= mouse_x <= thumb_x + scaled_w and thumb_y <= mouse_y <= thumb_y + scaled_h
                final_alpha = 1.0 if is_hover else alpha_factor

                try:
                    src_rect = RL_Rect(0, 0, thumb.size[0], thumb.size[1])
                    dst_rect = RL_Rect(thumb_x, thumb_y, scaled_w, scaled_h)
                    tint = RL_Color(255, 255, 255, int(255 * final_alpha * alpha_panel))
                    rl.DrawTexturePro(thumb.texture, src_rect, dst_rect, RL_V2(0, 0), 0.0, tint)
                except Exception as exc:
                    log(f"[DRAW][THUMB][ERR] {os.path.basename(path)}: {exc!r}")

                if idx == state.index:
                    rl.DrawRectangleLines(
                        thumb_x - 2,
                        thumb_y - 2,
                        scaled_w + 4,
                        scaled_h + 4,
                        RL_Color(255, 255, 255, int(255 * alpha_panel)),
                    )

                if is_hover and left_clicked:
                    clicked_index = idx
            else:
                scaled_w = int(base_thumb_h * 1.4 * scale_factor)
                scaled_h = int(base_thumb_h * scale_factor)
                thumb_x = thumb_center_x - scaled_w // 2
                thumb_y = y + (gallery_height - scaled_h) // 2
                rl.DrawRectangle(
                    thumb_x,
                    thumb_y,
                    scaled_w,
                    scaled_h,
                    RL_Color(64, 64, 64, int(255 * alpha_factor * alpha_panel)),
                )

        return clicked_index

    def _compute_thumb_positions(self, state: Any, start_idx: int, end_idx: int, base_thumb_h: int, visible_range: int):
        thumb_positions = {}
        center_idx = int(state.gallery_center_index)
        thumb_positions[center_idx] = 0.0

        cumulative_offset = 0.0
        for idx in range(center_idx - 1, start_idx - 1, -1):
            current_w = self._thumb_width(state, idx, base_thumb_h, visible_range)
            next_w = self._thumb_width(state, idx + 1, base_thumb_h, visible_range)
            cumulative_offset -= current_w / 2.0 + cfg.GALLERY_THUMB_SPACING + next_w / 2.0
            thumb_positions[idx] = cumulative_offset

        cumulative_offset = 0.0
        for idx in range(center_idx + 1, end_idx + 1):
            prev_w = self._thumb_width(state, idx - 1, base_thumb_h, visible_range)
            current_w = self._thumb_width(state, idx, base_thumb_h, visible_range)
            cumulative_offset += prev_w / 2.0 + cfg.GALLERY_THUMB_SPACING + current_w / 2.0
            thumb_positions[idx] = cumulative_offset

        return thumb_positions

    def _thumb_width(self, state: Any, idx: int, base_thumb_h: int, visible_range: int) -> int:
        path = state.current_dir_images[idx]
        thumb = state.thumb_cache.get(path)
        distance = abs(idx - state.gallery_center_index)
        scale_factor = lerp(1.0, cfg.GALLERY_MIN_SCALE, min(1.0, distance / visible_range))
        if thumb and thumb.ready and thumb.texture and thumb.size[1] > 0:
            fit_scale = base_thumb_h / thumb.size[1]
            return int(thumb.size[0] * fit_scale * scale_factor)
        return int(base_thumb_h * 1.4 * scale_factor)
