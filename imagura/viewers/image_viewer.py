"""ImageViewer — handles static raster images (PNG, JPG, BMP, TGA, GIF, QOI)."""

from __future__ import annotations

import os
from typing import Any, Optional, Tuple

from ..config import IMG_EXTS, MAX_FILE_SIZE_MB, MAX_IMAGE_DIMENSION, HEAVY_FILE_SIZE_MB, HEAVY_MIN_SHORT_SIDE
from ..logging import log
from ..image_utils import probe_image_dimensions

from .base import BaseViewer, _image_resize_mut, load_image_from_memory


class ImageViewer(BaseViewer):
    """Viewer for static raster images loaded via raylib."""

    @staticmethod
    def extensions() -> frozenset:
        return IMG_EXTS

    @staticmethod
    def name() -> str:
        return "Image"

    # --- Loading (background thread) ---

    def load_cpu(self, path: str) -> Any:
        file_size_mb = os.path.getsize(path) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            raise RuntimeError(f"file too large: {file_size_mb:.1f}MB")

        ext = os.path.splitext(path)[1].lower()
        with open(path, "rb") as file:
            img = load_image_from_memory(ext, file.read())

        w, h = img.width, img.height
        if w <= 0 or h <= 0:
            raise RuntimeError("empty image")

        if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
            scale = min(MAX_IMAGE_DIMENSION / w, MAX_IMAGE_DIMENSION / h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            log(f"[LOAD_CPU][RESIZE] {os.path.basename(path)}: {w}x{h} -> {new_w}x{new_h}")
            img = _image_resize_mut(img, new_w, new_h)

        return img

    # --- Metadata ---

    def probe_dimensions(self, path: str) -> Optional[Tuple[int, int]]:
        return probe_image_dimensions(path)

    def is_heavy(self, path: str) -> bool:
        """Heavy if large file or high resolution."""
        try:
            file_size_mb = os.path.getsize(path) / (1024 * 1024)
            if file_size_mb >= HEAVY_FILE_SIZE_MB:
                return True
        except Exception:
            pass

        dims = probe_image_dimensions(path)
        if dims:
            w, h = dims
            if min(w, h) >= HEAVY_MIN_SHORT_SIDE:
                return True
        return False

    # to_texture and make_thumbnail are inherited from BaseViewer
    # (they work with raylib Image, which is exactly what load_cpu returns)
