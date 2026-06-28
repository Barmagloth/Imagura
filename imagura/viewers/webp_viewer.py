"""WebPViewer — handles WebP images via Pillow + raylib."""

from __future__ import annotations

import io
import os
from typing import Any, Optional, Tuple

from ..config import MAX_FILE_SIZE_MB, MAX_IMAGE_DIMENSION, HEAVY_FILE_SIZE_MB, HEAVY_MIN_SHORT_SIDE
from ..logging import log

from .base import BaseViewer, load_image_from_memory


class WebPViewer(BaseViewer):
    """Viewer for WebP images decoded via Pillow, rendered via raylib."""

    @staticmethod
    def extensions() -> frozenset:
        return frozenset({".webp"})

    @staticmethod
    def name() -> str:
        return "WebP"

    # --- Loading (background thread) ---

    def load_cpu(self, path: str) -> Any:
        from PIL import Image as PILImage

        file_size_mb = os.path.getsize(path) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            raise RuntimeError(f"file too large: {file_size_mb:.1f}MB")

        pil_img = PILImage.open(path)
        pil_img.load()  # Force decode
        pil_img = pil_img.convert("RGBA")

        w, h = pil_img.size
        if w <= 0 or h <= 0:
            pil_img.close()
            raise RuntimeError("empty image")

        if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
            scale = min(MAX_IMAGE_DIMENSION / w, MAX_IMAGE_DIMENSION / h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            log(f"[WEBP][RESIZE] {os.path.basename(path)}: {w}x{h} -> {new_w}x{new_h}")
            pil_img = pil_img.resize((new_w, new_h), PILImage.LANCZOS)

        # Encode as PNG in memory for raylib
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG", compress_level=1)
        pil_img.close()
        png_bytes = buf.getvalue()

        return load_image_from_memory(".png", png_bytes)

    # --- Metadata ---

    def probe_dimensions(self, path: str) -> Optional[Tuple[int, int]]:
        try:
            from PIL import Image as PILImage
            with PILImage.open(path) as img:
                return img.size
        except Exception:
            return None

    def is_heavy(self, path: str) -> bool:
        try:
            file_size_mb = os.path.getsize(path) / (1024 * 1024)
            if file_size_mb >= HEAVY_FILE_SIZE_MB:
                return True
        except Exception:
            pass

        dims = self.probe_dimensions(path)
        if dims:
            w, h = dims
            if min(w, h) >= HEAVY_MIN_SHORT_SIDE:
                return True
        return False

    # to_texture and make_thumbnail inherited from BaseViewer
    # (they work with raylib Image, which is what load_cpu returns)
