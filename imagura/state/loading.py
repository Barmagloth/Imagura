"""Loading state - async loading coordination."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any

from ..types import ViewParams, TextureInfo
from ..config import ANIM_SWITCH_KEYS_MS


@dataclass
class LoadingState:
    """State for async loading coordination."""
    async_loader: Optional[Any] = None  # AsyncImageLoader
    idle_detector: Optional[Any] = None  # IdleDetector
    loading_current: bool = False
    waiting_for_switch: bool = False
    waiting_prev_snapshot: Optional[TextureInfo] = None
    waiting_prev_view: ViewParams = field(default_factory=ViewParams)
    pending_target_index: Optional[int] = None
    pending_neighbors_load: bool = False
    pending_switch_duration_ms: int = field(default=ANIM_SWITCH_KEYS_MS)

    @property
    def is_busy(self) -> bool:
        """Check if currently loading or waiting."""
        return self.loading_current or self.waiting_for_switch

    @property
    def has_pending_switch(self) -> bool:
        """Check if there's a pending switch target."""
        return self.pending_target_index is not None

    def prepare_switch(self, target_index: int, duration_ms: int,
                       prev_tex: Optional[TextureInfo],
                       prev_view: ViewParams) -> None:
        """Prepare for an animated switch."""
        self.waiting_for_switch = True
        self.pending_target_index = target_index
        self.pending_switch_duration_ms = duration_ms
        self.waiting_prev_snapshot = prev_tex
        self.waiting_prev_view = ViewParams(prev_view.scale, prev_view.offx, prev_view.offy)

    def complete_switch(self) -> tuple:
        """Complete switch and return (prev_snapshot, prev_view, direction, duration).
        Returns (None, None, 0, 0) if no pending switch."""
        if not self.waiting_for_switch or self.pending_target_index is None:
            return (None, None, 0, 0)

        result = (
            self.waiting_prev_snapshot,
            self.waiting_prev_view,
            self.pending_target_index,
            self.pending_switch_duration_ms,
        )

        self.waiting_for_switch = False
        self.waiting_prev_snapshot = None
        self.pending_target_index = None
        self.pending_switch_duration_ms = ANIM_SWITCH_KEYS_MS

        return result

    def reset_pending(self) -> None:
        """Reset all pending state."""
        self.waiting_for_switch = False
        self.waiting_prev_snapshot = None
        self.pending_target_index = None
        self.pending_neighbors_load = False
        self.pending_switch_duration_ms = ANIM_SWITCH_KEYS_MS
