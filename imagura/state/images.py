"""Image list state - current directory images, index, caching."""

from __future__ import annotations
from dataclasses import dataclass, field
from collections import OrderedDict, deque
from typing import List, Deque, Optional, Any

from ..types import ImageCache, BitmapThumb, ViewParams


@dataclass
class ImageListState:
    """State for image list and caching."""
    images: List[str] = field(default_factory=list)
    index: int = 0
    cache: ImageCache = field(default_factory=ImageCache)
    thumb_cache: "OrderedDict[str, BitmapThumb]" = field(default_factory=OrderedDict)
    thumb_queue: Deque[str] = field(default_factory=deque)
    to_unload: List[Any] = field(default_factory=list)  # List[rl.Texture2D]
    view_memory: dict = field(default_factory=dict)
    user_zoom_memory: dict = field(default_factory=dict)

    @property
    def count(self) -> int:
        """Total number of images."""
        return len(self.images)

    @property
    def current_path(self) -> Optional[str]:
        """Get current image path or None."""
        if 0 <= self.index < len(self.images):
            return self.images[self.index]
        return None

    @property
    def has_prev(self) -> bool:
        """Check if there's a previous image."""
        return self.index > 0

    @property
    def has_next(self) -> bool:
        """Check if there's a next image."""
        return self.index < len(self.images) - 1

    def get_path(self, idx: int) -> Optional[str]:
        """Get image path at index or None."""
        if 0 <= idx < len(self.images):
            return self.images[idx]
        return None

    def clamp_index(self, idx: int) -> int:
        """Clamp index to valid range."""
        if len(self.images) == 0:
            return 0
        return max(0, min(idx, len(self.images) - 1))

    def save_view(self, path: str, view: ViewParams) -> None:
        """Save view parameters for a path."""
        self.view_memory[path] = ViewParams(view.scale, view.offx, view.offy)

    def get_saved_view(self, path: str) -> Optional[ViewParams]:
        """Get saved view parameters for a path."""
        return self.view_memory.get(path)

    def save_user_zoom(self, path: str, view: ViewParams) -> None:
        """Save user zoom parameters for a path."""
        self.user_zoom_memory[path] = ViewParams(view.scale, view.offx, view.offy)

    def get_user_zoom(self, path: str) -> Optional[ViewParams]:
        """Get saved user zoom parameters for a path."""
        return self.user_zoom_memory.get(path)
