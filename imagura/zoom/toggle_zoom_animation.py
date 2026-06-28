"""Toggle zoom cycle animation for 1:1, fit, and custom views."""

from __future__ import annotations

from typing import Callable

from ..logging import log
from ..math_utils import ease_in_out_cubic, lerp
from ..types import ViewParams
from ..view_math import clamp_pan as clamp_pan_pure
from ..view_math import view_for_1to1_centered as view_1to1_pure


_OVERLAY_MODES = {
    0: "real",
    1: "fit",
    2: "custom",
}


class ToggleZoomAnimationController:
    """Controls the F/double-click zoom cycle animation."""

    def __init__(self, now_fn: Callable[[], float]):
        self.now = now_fn

    def start(self, state, trigger_overlay: Callable[[object, str], None]) -> None:
        if state.toggle_zoom_active:
            return

        ti = state.cache.curr
        if not ti:
            return

        next_state = {2: 0, 0: 1, 1: 2}[state.zoom_state_cycle]
        target = self._target_view_for_state(state, next_state, ti)

        state.toggle_zoom_active = True
        state.toggle_zoom_t0 = self.now()
        state.toggle_zoom_from = ViewParams(state.view.scale, state.view.offx, state.view.offy)
        state.toggle_zoom_to = target
        state.toggle_zoom_target_state = next_state

        trigger_overlay(state, _OVERLAY_MODES[next_state])
        log(f"[TOGGLE_ZOOM] Started: {state.zoom_state_cycle} -> {next_state}")

    def update(self, state, duration_ms: int, save_view: Callable[[object, str, ViewParams], None]) -> None:
        if not state.toggle_zoom_active:
            return

        ti = state.cache.curr
        if not ti:
            state.toggle_zoom_active = False
            return

        duration_s = duration_ms / 1000.0
        t = 1.0 if duration_s <= 0.0 else (self.now() - state.toggle_zoom_t0) / duration_s

        if t >= 1.0:
            state.toggle_zoom_active = False
            state.view = clamp_pan_pure(state.toggle_zoom_to, ti.w, ti.h, state.screenW, state.screenH)
            state.zoom_state_cycle = state.toggle_zoom_target_state
            state.is_zoomed = state.view.scale > state.last_fit_view.scale
            self._save_finished_view(state, save_view)
            log(f"[TOGGLE_ZOOM] Finished: state={state.zoom_state_cycle} scale={state.view.scale:.3f}")
            return

        t_eased = ease_in_out_cubic(t)
        current = ViewParams(
            scale=lerp(state.toggle_zoom_from.scale, state.toggle_zoom_to.scale, t_eased),
            offx=lerp(state.toggle_zoom_from.offx, state.toggle_zoom_to.offx, t_eased),
            offy=lerp(state.toggle_zoom_from.offy, state.toggle_zoom_to.offy, t_eased),
        )
        state.view = clamp_pan_pure(current, ti.w, ti.h, state.screenW, state.screenH)

    def _target_view_for_state(self, state, next_state: int, ti) -> ViewParams:
        if next_state == 0:
            return view_1to1_pure(ti.w, ti.h, state.screenW, state.screenH)
        if next_state == 1:
            return state.last_fit_view

        current_path = state.current_dir_images[state.index] if state.index < len(state.current_dir_images) else None
        if current_path and current_path in state.user_zoom_memory:
            return state.user_zoom_memory[current_path]
        return state.last_fit_view

    def _save_finished_view(self, state, save_view: Callable[[object, str, ViewParams], None]) -> None:
        if state.index >= len(state.current_dir_images):
            return

        path = state.current_dir_images[state.index]
        save_view(state, path, state.view)
        if state.zoom_state_cycle == 2:
            state.user_zoom_memory[path] = ViewParams(state.view.scale, state.view.offx, state.view.offy)
            log(f"[TOGGLE_ZOOM] Saved USER view: scale={state.view.scale:.3f}")
