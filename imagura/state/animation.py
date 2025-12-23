"""Animation state - all animation-related state."""

from __future__ import annotations
from dataclasses import dataclass, field
from collections import deque
from typing import Deque, Tuple, Optional, Any

from ..types import ViewParams, TextureInfo


@dataclass
class AnimationState:
    """State for all animations."""
    # Open animation
    open_active: bool = False
    open_t0: float = 0.0

    # Switch animation
    switch_active: bool = False
    switch_t0: float = 0.0
    switch_duration_ms: int = 0
    switch_direction: int = 0
    switch_prev_tex: Optional[TextureInfo] = None
    switch_prev_view: ViewParams = field(default_factory=ViewParams)
    switch_queue: Deque[Tuple[int, int]] = field(default_factory=deque)

    # Zoom animation (wheel/keys)
    zoom_active: bool = False
    zoom_t0: float = 0.0
    zoom_from: ViewParams = field(default_factory=ViewParams)
    zoom_to: ViewParams = field(default_factory=ViewParams)

    # Toggle zoom animation (F key / double-click)
    toggle_zoom_active: bool = False
    toggle_zoom_t0: float = 0.0
    toggle_zoom_from: ViewParams = field(default_factory=ViewParams)
    toggle_zoom_to: ViewParams = field(default_factory=ViewParams)
    toggle_zoom_target_state: int = 0

    @property
    def any_zoom_animating(self) -> bool:
        """Check if any zoom animation is running."""
        return self.zoom_active or self.toggle_zoom_active

    @property
    def any_animating(self) -> bool:
        """Check if any animation is running."""
        return (self.open_active or self.switch_active or
                self.zoom_active or self.toggle_zoom_active)

    @property
    def has_queued_switches(self) -> bool:
        """Check if there are queued switch animations."""
        return len(self.switch_queue) > 0

    def queue_switch(self, direction: int, duration_ms: int) -> bool:
        """Queue a switch animation. Returns True if queued."""
        if len(self.switch_queue) < 20:
            self.switch_queue.append((direction, duration_ms))
            return True
        return False

    def pop_switch(self) -> Optional[Tuple[int, int]]:
        """Pop next switch from queue."""
        if self.switch_queue:
            return self.switch_queue.popleft()
        return None

    def clear_switch_prev(self) -> Optional[TextureInfo]:
        """Clear and return previous texture for unloading."""
        tex = self.switch_prev_tex
        self.switch_prev_tex = None
        return tex
