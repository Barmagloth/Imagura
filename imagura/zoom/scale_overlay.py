"""Scale overlay state and text helpers."""

from __future__ import annotations

from typing import Callable

from .. import config as cfg
from ..i18n import tr


def zoom_mode_label(zoom_state_cycle: int) -> str:
    """Return the short HUD label for the current zoom cycle state."""
    if zoom_state_cycle == 0:
        return "1:1"
    if zoom_state_cycle == 1:
        return tr("zoom.fit")
    return tr("zoom.custom")


def scale_overlay_text(scale: float, mode: str = "") -> str:
    """Return the text shown by the transient scale overlay."""
    pct = int(round(scale * 100))
    if mode == "real":
        return f"{tr('zoom.real')} ({pct}%)"
    if mode == "fit":
        return f"{tr('zoom.fit')} ({pct}%)"
    if mode == "custom":
        return f"{tr('zoom.custom')} ({pct}%)"
    return f"{pct}%"


class ScaleOverlayController:
    """Controls scale overlay visibility and fade timing."""

    def __init__(
        self,
        now_fn: Callable[[], float],
        enabled_fn: Callable[[], bool] | None = None,
        hold_seconds: float = 1.0,
        fade_per_second: float = 2.0,
    ):
        self.now = now_fn
        self.enabled = enabled_fn or (lambda: cfg.SHOW_SCALE_OVERLAY)
        self.hold_seconds = hold_seconds
        self.fade_per_second = fade_per_second

    def trigger(self, state, mode: str = "") -> bool:
        """Show the overlay. Returns True if it was enabled and triggered."""
        if not self.enabled():
            return False
        state.ui.scale_overlay_mode = mode
        state.ui.scale_overlay_alpha = 1.0
        state.ui.scale_last_change_time = self.now()
        return True

    def update(self, state, frame_dt: float) -> None:
        """Fade the overlay after the hold period."""
        if state.ui.scale_overlay_alpha <= 0.0:
            return
        elapsed = self.now() - state.ui.scale_last_change_time
        if elapsed > self.hold_seconds:
            state.ui.scale_overlay_alpha = max(
                0.0,
                state.ui.scale_overlay_alpha - frame_dt * self.fade_per_second,
            )
