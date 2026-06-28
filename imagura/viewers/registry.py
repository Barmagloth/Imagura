"""Viewer registry — maps file extensions to ContentViewer instances."""

from __future__ import annotations

import os
from typing import Optional, Dict

from .base import BaseViewer


class ViewerRegistry:
    """Maps file extensions to viewer instances."""

    def __init__(self):
        self._viewers: Dict[str, BaseViewer] = {}

    def register(self, viewer: BaseViewer) -> None:
        """Register a viewer for all its declared extensions."""
        for ext in viewer.extensions():
            self._viewers[ext] = viewer

    def get_viewer(self, path_or_ext: str) -> Optional[BaseViewer]:
        """Look up a viewer by file path or extension (e.g. '.png')."""
        if not path_or_ext.startswith('.'):
            ext = os.path.splitext(path_or_ext)[1].lower()
        else:
            ext = path_or_ext.lower()
        return self._viewers.get(ext)

    def supported_extensions(self) -> frozenset:
        """Return all registered extensions."""
        return frozenset(self._viewers.keys())


_registry: Optional[ViewerRegistry] = None


def get_registry() -> ViewerRegistry:
    """Module-level singleton. Registers built-in viewers on first call."""
    global _registry
    if _registry is None:
        from .image_viewer import ImageViewer
        _registry = ViewerRegistry()
        _registry.register(ImageViewer())

        try:
            from .webp_viewer import WebPViewer
            _registry.register(WebPViewer())
        except ImportError:
            pass  # Pillow not installed

        try:
            from .gif_viewer import GifViewer
            _registry.register(GifViewer())  # Overrides ImageViewer for .gif
        except ImportError:
            pass  # Pillow not installed
    return _registry
