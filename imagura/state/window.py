"""Window state - screen dimensions, handle, font."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Any, Tuple


@dataclass
class WindowState:
    """Window-related state."""
    screen_w: int = 0
    screen_h: int = 0
    hwnd: Optional[int] = None
    unicode_font: Optional[Any] = None
    # Windowed mode support
    windowed_mode: bool = False
    fullscreen_x: int = 0
    fullscreen_y: int = 0
    fullscreen_w: int = 0
    fullscreen_h: int = 0

    @property
    def size(self) -> Tuple[int, int]:
        """Get window size as tuple."""
        return (self.screen_w, self.screen_h)

    @property
    def center(self) -> Tuple[int, int]:
        """Get window center point."""
        return (self.screen_w // 2, self.screen_h // 2)
