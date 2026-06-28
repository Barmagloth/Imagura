"""Manual wheel/key zoom calculation and state persistence."""

from __future__ import annotations

from typing import Callable, Tuple

from ..types import ViewParams
from ..view_math import clamp_pan as clamp_pan_pure
from ..view_math import recompute_view_anchor_zoom as anchor_zoom_pure


def apply_manual_zoom(
    state,
    scale_multiplier: float,
    anchor: Tuple[int, int],
    max_zoom: float,
    start_zoom_animation: Callable[[object, ViewParams], None],
    trigger_scale_overlay: Callable[[object], None],
    save_view_for_path: Callable[[object, str, ViewParams], None],
) -> bool:
    """Apply anchored manual zoom and persist it as a custom user view.

    Returns True when a zoom target was applied.
    """
    texture = state.cache.curr
    if not texture:
        return False

    # Lower zoom bound = half the fit scale, but never above half real-size:
    # tiny images have a huge fit scale (they're scaled way up to fit the
    # screen), so a plain fit*0.5 floor would be > 1.0 and snap every zoom
    # attempt up to that floor. Capping the fit at 1.0 lets small images zoom
    # down to 50% of real size instead of jumping.
    min_scale = min(state.last_fit_view.scale, 1.0) * 0.5
    new_scale = max(min_scale, min(state.view.scale * scale_multiplier, max_zoom))
    target = anchor_zoom_pure(state.view, new_scale, anchor, texture.w, texture.h)
    target = clamp_pan_pure(target, texture.w, texture.h, state.screenW, state.screenH)

    start_zoom_animation(state, target)
    trigger_scale_overlay(state)
    state.is_zoomed = target.scale > state.last_fit_view.scale
    state.zoom_state_cycle = 2

    if state.index < len(state.current_dir_images):
        path = state.current_dir_images[state.index]
        save_view_for_path(state, path, target)
        state.user_zoom_memory[path] = ViewParams(target.scale, target.offx, target.offy)

    return True
