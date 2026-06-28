"""View zoom tween for wheel and keyboard zoom."""

from __future__ import annotations

from typing import Callable

from ..math_utils import ease_out_quad, lerp
from ..types import ViewParams
from ..view_math import clamp_pan as clamp_pan_pure


class ZoomAnimationController:
    """Controls the short zoom tween used by wheel and key zoom."""

    def __init__(self, now_fn: Callable[[], float]):
        self.now = now_fn

    def start(self, state, target_view: ViewParams) -> None:
        state.zoom_anim_active = True
        state.zoom_anim_t0 = self.now()
        state.zoom_anim_from = ViewParams(state.view.scale, state.view.offx, state.view.offy)
        state.zoom_anim_to = target_view

    def update(self, state, duration_ms: int) -> None:
        if not state.zoom_anim_active:
            return

        duration_s = duration_ms / 1000.0
        t = 1.0 if duration_s <= 0.0 else (self.now() - state.zoom_anim_t0) / duration_s
        if t >= 1.0:
            state.zoom_anim_active = False
            if state.cache.curr:
                ti = state.cache.curr
                state.view = clamp_pan_pure(state.zoom_anim_to, ti.w, ti.h, state.screenW, state.screenH)
            else:
                state.view = state.zoom_anim_to
            return

        t_eased = ease_out_quad(t)
        state.view = ViewParams(
            scale=lerp(state.zoom_anim_from.scale, state.zoom_anim_to.scale, t_eased),
            offx=lerp(state.zoom_anim_from.offx, state.zoom_anim_to.offx, t_eased),
            offy=lerp(state.zoom_anim_from.offy, state.zoom_anim_to.offy, t_eased),
        )
