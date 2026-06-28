"""CPU-side content loader dispatch through the viewer registry."""

from __future__ import annotations

import os

from ..viewers import get_registry


def load_content_cpu(path: str):
    """Load file via the appropriate viewer. Returns (viewer, cpu_data)."""
    viewer = get_registry().get_viewer(path)
    if viewer is None:
        raise RuntimeError(f"No viewer for {os.path.splitext(path)[1]}")
    return (viewer, viewer.load_cpu(path))
