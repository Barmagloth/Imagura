"""Modular viewer architecture for Imagura.

Usage:
    from imagura.viewers import get_registry, ContentViewer, BaseViewer, Playback

    registry = get_registry()
    viewer = registry.get_viewer(".png")  # -> ImageViewer
    exts = registry.supported_extensions()
"""

from .base import ContentViewer, BaseViewer, Playback
from .registry import ViewerRegistry, get_registry

__all__ = [
    "ContentViewer",
    "BaseViewer",
    "Playback",
    "ViewerRegistry",
    "get_registry",
]
