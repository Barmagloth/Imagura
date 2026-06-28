"""Base viewer protocol and classes for the modular viewer architecture."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple, Protocol, runtime_checkable

from ..types import TextureInfo, BitmapThumb
from ..config import HEAVY_FILE_SIZE_MB
from ..rl_compat import rl
from ..logging import log


@dataclass
class Playback:
    """State for animated content playback.

    Stored alongside TextureInfo for the current image.
    The main loop calls advance() each frame — if it's time for a new
    frame, a new TextureInfo is returned to replace the current one.
    """
    viewer: Any  # ContentViewer that manages this playback
    data: Any  # Decoder / frame list / video handle
    playing: bool = True
    looping: bool = True
    duration_ms: float = 0  # Total duration (0 = unknown)
    position_ms: float = 0  # Current position

    def advance(self, dt_ms: float) -> Optional[TextureInfo]:
        """Advance playback by dt_ms milliseconds.

        Returns new TextureInfo if the frame changed, else None.
        Called from the main thread every frame.
        """
        return self.viewer.advance_frame(self, dt_ms)

    def seek(self, position_ms: float) -> TextureInfo:
        """Seek to the given position."""
        return self.viewer.seek_frame(self, position_ms)

    def toggle_play(self):
        self.playing = not self.playing

    def cleanup(self):
        """Release decoder resources."""
        self.viewer.cleanup_playback(self)


@runtime_checkable
class ContentViewer(Protocol):
    """Protocol that every viewer must implement."""

    # === Identification ===
    @staticmethod
    def extensions() -> frozenset: ...

    @staticmethod
    def name() -> str: ...

    # === Loading (background thread, no GPU) ===
    def load_cpu(self, path: str) -> Any: ...

    # === Texture (main thread) ===
    def to_texture(self, cpu_data: Any, path: str) -> TextureInfo: ...
    def make_thumbnail(self, cpu_data: Any, target_h: int, path: str) -> BitmapThumb: ...

    # === Metadata ===
    def probe_dimensions(self, path: str) -> Optional[Tuple[int, int]]: ...
    def is_heavy(self, path: str) -> bool: ...

    # === Animation (optional) ===
    def is_animated(self, cpu_data: Any) -> bool: ...
    def create_playback(self, cpu_data: Any) -> Playback: ...


class BaseViewer:
    """Base class with sensible defaults for all viewer methods."""

    @staticmethod
    def extensions() -> frozenset:
        return frozenset()

    @staticmethod
    def name() -> str:
        return "Base"

    # --- Loading ---

    def load_cpu(self, path: str) -> Any:
        raise NotImplementedError

    # --- Texture ---

    def to_texture(self, cpu_data: Any, path: str) -> TextureInfo:
        """Default: treat cpu_data as a raylib Image, upload to GPU."""
        img = cpu_data
        tex = rl.LoadTextureFromImage(img)
        rl.SetTextureFilter(tex, 1)  # TEXTURE_FILTER_BILINEAR
        w, h = img.width, img.height
        try:
            rl.UnloadImage(img)
        except Exception:
            pass
        return TextureInfo(tex=tex, w=w, h=h, path=path)

    def make_thumbnail(self, cpu_data: Any, target_h: int, path: str) -> BitmapThumb:
        """Default: resize raylib Image to target_h, upload to GPU."""
        img = cpu_data
        try:
            w, h = img.width, img.height
            if w <= 0 or h <= 0:
                return BitmapThumb(None, (0, 0), path, False)

            scale = target_h / h
            tw, th = max(1, int(w * scale)), target_h
            rimg = _image_resize_mut(img, tw, th)

            tex = rl.LoadTextureFromImage(rimg)
            rl.SetTextureFilter(tex, 1)
            try:
                rl.UnloadImage(rimg)
            except Exception:
                pass

            return BitmapThumb(tex, (tw, th), path, True)
        except Exception as e:
            log(f"[THUMB][ERR] {os.path.basename(path)}: {e!r}")
            return BitmapThumb(None, (0, 0), path, False)

    # --- Metadata ---

    def probe_dimensions(self, path: str) -> Optional[Tuple[int, int]]:
        return None

    def is_heavy(self, path: str) -> bool:
        """Default: heavy if file > HEAVY_FILE_SIZE_MB."""
        try:
            return os.path.getsize(path) / (1024 * 1024) >= HEAVY_FILE_SIZE_MB
        except Exception:
            return False

    # --- Animation ---

    def is_animated(self, cpu_data: Any) -> bool:
        return False

    def create_playback(self, cpu_data: Any) -> Playback:
        raise NotImplementedError("This viewer does not support animation")

    def advance_frame(self, playback: Playback, dt_ms: float) -> Optional[TextureInfo]:
        return None

    def seek_frame(self, playback: Playback, position_ms: float) -> TextureInfo:
        raise NotImplementedError("This viewer does not support seeking")

    def cleanup_playback(self, playback: Playback) -> None:
        pass

    def cleanup_cpu_data(self, cpu_data: Any) -> None:
        """Release CPU-side data (e.g. raylib Image). Called for stale results."""
        try:
            rl.UnloadImage(cpu_data)
        except Exception:
            pass


def _image_resize_mut(img, w: int, h: int):
    """Resize a raylib Image in-place. Handles both CFFI and ctypes bindings."""
    import ctypes
    if hasattr(rl, 'ffi'):
        try:
            p = rl.ffi.new("Image *", img)
            try:
                rl.ImageResize(p, int(w), int(h))
            except Exception:
                rl.ImageResizeNN(p, int(w), int(h))
            return p[0]
        except Exception:
            pass
    for fn in (
            lambda im: rl.ImageResize(ctypes.byref(im), int(w), int(h)),
            lambda im: rl.ImageResize(im, int(w), int(h)),
            lambda im: rl.ImageResizeNN(ctypes.byref(im), int(w), int(h)),
            lambda im: rl.ImageResizeNN(im, int(w), int(h)),
    ):
        try:
            fn(img)
            return img
        except Exception:
            continue
    return img


def load_image_from_memory(file_type: str, data: bytes) -> Any:
    """Load raylib Image from in-memory bytes. Handles CFFI and ctypes bindings."""
    ft = file_type.encode("utf-8") if isinstance(file_type, str) else file_type

    if hasattr(rl, "ffi"):
        c_data = rl.ffi.new("unsigned char[]", data)
        return rl.LoadImageFromMemory(ft, c_data, len(data))

    c_data = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    try:
        return rl.LoadImageFromMemory(ft, c_data, len(data))
    except TypeError:
        return rl.LoadImageFromMemory(file_type, c_data, ctypes.c_int(len(data)))


def update_texture_rgba(tex: Any, rgba_bytes: bytes) -> None:
    """Update existing GPU texture with new RGBA pixel data."""
    if hasattr(rl, "ffi"):
        c_data = rl.ffi.from_buffer(bytearray(rgba_bytes))
        rl.UpdateTexture(tex, c_data)
    else:
        c_data = (ctypes.c_ubyte * len(rgba_bytes)).from_buffer_copy(rgba_bytes)
        rl.UpdateTexture(tex, c_data)
