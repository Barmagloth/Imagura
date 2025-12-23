"""Core data types for Imagura."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Tuple, Optional, Callable, Any
from enum import IntEnum

from .logging import now


class LoadPriority(IntEnum):
    """Priority levels for async image loading."""
    CURRENT = 0   # Currently viewed image - highest priority
    NEIGHBOR = 1  # Previous/next images for smooth navigation
    GALLERY = 2   # Thumbnail images - lowest priority


@dataclass
class LoadTask:
    """A task for the async image loader."""
    path: str
    priority: LoadPriority
    callback: Callable
    timestamp: float = 0.0

    def __lt__(self, other: LoadTask) -> bool:
        """Compare tasks for priority queue ordering."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp


@dataclass
class UIEvent:
    """An event to be processed on the main/UI thread."""
    callback: Callable
    args: tuple


@dataclass
class ViewParams:
    """View transformation parameters (scale and offset)."""
    scale: float = 1.0
    offx: float = 0.0
    offy: float = 0.0

    def copy(self) -> ViewParams:
        """Create a copy of this ViewParams."""
        return ViewParams(self.scale, self.offx, self.offy)


@dataclass
class TextureInfo:
    """Information about a loaded texture."""
    tex: Any  # rl.Texture2D - using Any to avoid raylib import
    w: int
    h: int
    path: str = ""

    def copy_ref(self) -> TextureInfo:
        """Create a copy that references the same texture."""
        return TextureInfo(tex=self.tex, w=self.w, h=self.h, path=self.path)


@dataclass
class ImageCache:
    """Cache for prev/curr/next images."""
    prev: Optional[TextureInfo] = None
    curr: Optional[TextureInfo] = None
    next: Optional[TextureInfo] = None


@dataclass
class BitmapThumb:
    """A thumbnail bitmap for the gallery."""
    texture: Optional[Any] = None  # rl.Texture2D
    size: Tuple[int, int] = (0, 0)
    src_path: str = ""
    ready: bool = False
