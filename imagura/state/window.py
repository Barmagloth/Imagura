"""Window state - screen dimensions, handle, font."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Any


@dataclass
class WindowState:
    """Window-related state."""
    screen_w: int = 0
    screen_h: int = 0
    hwnd: Optional[int] = None
    unicode_font: Optional[Any] = None

    @property
    def size(self) -> tuple[int, int]:
        """Get window size as tuple."""
        return (self.screen_w, self.screen_h)

    @property
    def center(self) -> tuple[int, int]:
        """Get window center point."""
        return (self.screen_w // 2, self.screen_h // 2)
