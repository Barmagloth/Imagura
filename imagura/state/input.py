"""Input state - mouse, panning, clicks."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple

from ..config import DOUBLE_CLICK_TIME_MS
from ..logging import now


@dataclass
class InputState:
    """State for input handling."""
    is_panning: bool = False
    pan_start_mouse: Tuple[float, float] = (0.0, 0.0)
    pan_start_offset: Tuple[float, float] = (0.0, 0.0)
    last_click_time: float = 0.0
    last_click_pos: Tuple[int, int] = (0, 0)

    def start_pan(self, mouse_x: float, mouse_y: float,
                  offset_x: float, offset_y: float) -> None:
        """Start panning operation."""
        self.is_panning = True
        self.pan_start_mouse = (mouse_x, mouse_y)
        self.pan_start_offset = (offset_x, offset_y)

    def end_pan(self) -> bool:
        """End panning operation. Returns True if was panning."""
        was_panning = self.is_panning
        self.is_panning = False
        return was_panning

    def get_pan_delta(self, mouse_x: float, mouse_y: float) -> Tuple[float, float]:
        """Get delta from pan start position."""
        dx = mouse_x - self.pan_start_mouse[0]
        dy = mouse_y - self.pan_start_mouse[1]
        return (dx, dy)

    def get_panned_offset(self, mouse_x: float, mouse_y: float) -> Tuple[float, float]:
        """Get new offset based on current mouse position."""
        dx, dy = self.get_pan_delta(mouse_x, mouse_y)
        return (self.pan_start_offset[0] + dx, self.pan_start_offset[1] + dy)

    def check_double_click(self, x: int, y: int, max_distance: int = 10) -> bool:
        """Check if this click is a double-click. Updates state."""
        t = now()
        is_double = False

        if (t - self.last_click_time) < (DOUBLE_CLICK_TIME_MS / 1000.0):
            dx = abs(x - self.last_click_pos[0])
            dy = abs(y - self.last_click_pos[1])
            if dx < max_distance and dy < max_distance:
                is_double = True
                self.last_click_time = 0.0  # Reset to prevent triple-click
                return True

        self.last_click_time = t
        self.last_click_pos = (x, y)
        return False
