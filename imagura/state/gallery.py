"""Gallery state - thumbnail strip at bottom."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from ..config import GALLERY_HEIGHT_FRAC


@dataclass
class GalleryState:
    """State for gallery/thumbnail strip."""
    center_index: float = 0.0
    y_position: float = 0.0  # Current Y position (animated)
    visible: bool = False
    target_index: Optional[int] = None
    last_wheel_time: float = 0.0

    def get_height(self, screen_h: int) -> int:
        """Get gallery height in pixels."""
        return int(screen_h * GALLERY_HEIGHT_FRAC)

    def get_y_visible(self, screen_h: int) -> int:
        """Get Y position when gallery is visible."""
        return screen_h - self.get_height(screen_h)

    def get_y_hidden(self, screen_h: int) -> int:
        """Get Y position when gallery is hidden."""
        return screen_h

    def is_fully_visible(self, screen_h: int) -> bool:
        """Check if gallery is fully visible."""
        return self.y_position <= self.get_y_visible(screen_h)

    def is_fully_hidden(self, screen_h: int) -> bool:
        """Check if gallery is fully hidden."""
        return self.y_position >= self.get_y_hidden(screen_h)

    @property
    def has_pending_target(self) -> bool:
        """Check if there's a pending target index."""
        return self.target_index is not None

    def clear_target(self) -> None:
        """Clear pending target index."""
        self.target_index = None
