"""Gallery behavior: visibility, scrolling, target reconciliation, and hit tests."""

from __future__ import annotations

from typing import Any, Callable

from .. import config as cfg
from ..math_utils import clamp


class GalleryBehavior:
    """Updates gallery state without drawing anything."""

    def update_scroll(self, state: Any, frame_dt: float) -> None:
        if state.gallery_target_index is not None:
            target = float(clamp(state.gallery_target_index, 0, max(0, len(state.current_dir_images) - 1)))
        else:
            target = float(state.index)

        current = state.gallery_center_index
        diff = target - current

        if abs(diff) < 0.01:
            state.gallery_center_index = target
            return

        factor = min(1.0, 15.0 * frame_dt)
        state.gallery_center_index += diff * factor

    def reconcile_target(
        self,
        state: Any,
        now_s: float,
        switch_callback: Callable[[int, bool, int], None],
    ) -> None:
        target = state.gallery_target_index
        if target is None:
            return

        if (now_s - state.gallery_last_wheel_time) < cfg.GALLERY_SETTLE_DEBOUNCE_S:
            return

        if state.switch_anim_active or state.waiting_for_switch or state.loading_current:
            return

        n = len(state.current_dir_images)
        if n == 0:
            state.gallery_target_index = None
            return

        target = clamp(int(target), 0, n - 1)

        if state.index == target:
            state.gallery_target_index = None
            return

        dist = abs(target - state.index)
        if dist >= cfg.RAPID_NAV_SKIP_THRESHOLD:
            state.gallery_target_index = None
            switch_callback(target, False, cfg.ANIM_SWITCH_KEYS_MS)
            return

        step = 1 if target > state.index else -1
        switch_callback(state.index + step, True, cfg.ANIM_SWITCH_GALLERY_MS)

    def update_visibility_and_slide(
        self,
        state: Any,
        mouse_y: float,
        frame_dt: float,
        gallery_height: int,
        force_visible: bool = False,
    ) -> None:
        y_hidden = state.screenH
        y_visible = state.screenH - gallery_height
        in_trigger = mouse_y >= state.screenH * (1.0 - cfg.GALLERY_TRIGGER_FRAC)
        in_panel = state.gallery_y < y_hidden and state.gallery_y <= mouse_y <= y_hidden
        want_show = force_visible or in_trigger or in_panel
        state.gallery_visible = want_show

        current_y = state.gallery_y
        target_y = y_visible if want_show else y_hidden
        slide_ms = cfg.GALLERY_SLIDE_MS

        if slide_ms <= 0:
            state.gallery_y = target_y
            return

        speed = gallery_height / (slide_ms / 1000.0)
        step = speed * frame_dt
        if abs(current_y - target_y) <= step:
            state.gallery_y = target_y
        else:
            state.gallery_y = current_y - step if current_y > target_y else current_y + step

    def is_mouse_over(self, state: Any, mouse_y: float, gallery_height: int) -> bool:
        y_visible = state.screenH - gallery_height
        return y_visible <= mouse_y <= state.screenH and state.gallery_y < state.screenH
