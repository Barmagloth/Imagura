"""GifViewer — animated GIF support via Pillow + raylib."""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from ..config import (
    MAX_ANIM_FRAMES,
    MAX_ANIM_MEMORY_MB,
    MAX_FILE_SIZE_MB,
    MAX_IMAGE_DIMENSION,
    HEAVY_FILE_SIZE_MB,
    HEAVY_MIN_SHORT_SIDE,
)
from ..rl_compat import rl
from ..logging import log
from ..types import TextureInfo, BitmapThumb

from .base import BaseViewer, Playback, load_image_from_memory, update_texture_rgba, _image_resize_mut


@dataclass
class GifCpuData:
    """CPU-side data from a decoded GIF."""
    first_frame_img: Any  # raylib Image for to_texture / make_thumbnail
    frames_rgba: List[bytes] = field(default_factory=list)
    durations: List[float] = field(default_factory=list)  # ms per frame
    width: int = 0
    height: int = 0
    first_frame_png: Optional[bytes] = None


class GifViewer(BaseViewer):
    """Viewer for animated GIFs decoded via Pillow, rendered via raylib."""

    @staticmethod
    def extensions() -> frozenset:
        return frozenset({".gif"})

    @staticmethod
    def name() -> str:
        return "GIF"

    # --- Loading (background thread) ---

    def load_cpu(self, path: str) -> Any:
        from PIL import Image as PILImage

        file_size_mb = os.path.getsize(path) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            raise RuntimeError(f"file too large: {file_size_mb:.1f}MB")

        pil_img = PILImage.open(path)
        n_frames = getattr(pil_img, "n_frames", 1)

        # Determine output size
        w, h = pil_img.size
        if w <= 0 or h <= 0:
            pil_img.close()
            raise RuntimeError("empty image")

        out_w, out_h = w, h
        if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
            scale = min(MAX_IMAGE_DIMENSION / w, MAX_IMAGE_DIMENSION / h)
            out_w = max(1, int(w * scale))
            out_h = max(1, int(h * scale))
            log(f"[GIF][RESIZE] {os.path.basename(path)}: {w}x{h} -> {out_w}x{out_h}")

        need_resize = (out_w != w or out_h != h)
        frames_rgba = []
        durations = []
        bytes_per_frame = max(1, out_w * out_h * 4)
        max_frames_by_memory = max(
            1,
            int((MAX_ANIM_MEMORY_MB * 1024 * 1024) // bytes_per_frame),
        )
        frame_limit = min(n_frames, MAX_ANIM_FRAMES, max_frames_by_memory)

        if frame_limit < n_frames:
            kept_mb = (frame_limit * bytes_per_frame) / (1024 * 1024)
            full_mb = (n_frames * bytes_per_frame) / (1024 * 1024)
            log(
                f"[GIF][LIMIT] {os.path.basename(path)}: "
                f"keeping {frame_limit}/{n_frames} frames "
                f"({kept_mb:.1f}MB of {full_mb:.1f}MB decoded RGBA)"
            )

        # Decode all frames
        for i in range(frame_limit):
            try:
                pil_img.seek(i)
            except EOFError:
                break

            frame = pil_img.convert("RGBA")
            if need_resize:
                frame = frame.resize((out_w, out_h), PILImage.LANCZOS)

            frames_rgba.append(frame.tobytes())
            dur = pil_img.info.get("duration", 100)
            if dur <= 0:
                dur = 100  # Default 10 fps for broken durations
            durations.append(float(dur))

        pil_img.close()

        if not frames_rgba:
            raise RuntimeError("no frames decoded")

        # Build first frame as raylib Image for to_texture / make_thumbnail
        first_frame_png = _rgba_to_png(frames_rgba[0], out_w, out_h)
        first_img = load_image_from_memory(".png", first_frame_png)

        return GifCpuData(
            first_frame_img=first_img,
            frames_rgba=frames_rgba,
            durations=durations,
            width=out_w,
            height=out_h,
            first_frame_png=first_frame_png,
        )

    # --- Texture ---

    def to_texture(self, cpu_data: Any, path: str) -> TextureInfo:
        img = cpu_data.first_frame_img
        if img is None and cpu_data.frames_rgba:
            png = cpu_data.first_frame_png or _rgba_to_png(cpu_data.frames_rgba[0], cpu_data.width, cpu_data.height)
            img = load_image_from_memory(".png", png)
            cpu_data.first_frame_img = img
        if img is None:
            raise RuntimeError("no GIF frame available for texture upload")

        tex = rl.LoadTextureFromImage(img)
        rl.SetTextureFilter(tex, 1)
        w, h = img.width, img.height
        try:
            rl.UnloadImage(img)
        except Exception:
            pass
        cpu_data.first_frame_img = None

        # Store texture ref for playback's UpdateTexture
        cpu_data._tex_ref = tex
        return TextureInfo(tex=tex, w=w, h=h, path=path)

    def make_thumbnail(self, cpu_data: Any, target_h: int, path: str) -> BitmapThumb:
        img = cpu_data.first_frame_img
        if img is None:
            # first_frame_img already consumed by to_texture — rebuild from RGBA
            if cpu_data.frames_rgba:
                png = cpu_data.first_frame_png or _rgba_to_png(cpu_data.frames_rgba[0], cpu_data.width, cpu_data.height)
                img = load_image_from_memory(".png", png)
            else:
                return BitmapThumb(None, (0, 0), path, False)

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
            log(f"[GIF][THUMB][ERR] {os.path.basename(path)}: {e!r}")
            return BitmapThumb(None, (0, 0), path, False)

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
            if os.path.getsize(path) / (1024 * 1024) >= HEAVY_FILE_SIZE_MB:
                return True
        except Exception:
            pass
        dims = self.probe_dimensions(path)
        if dims and min(dims) >= HEAVY_MIN_SHORT_SIDE:
            return True
        return False

    # --- Animation ---

    def is_animated(self, cpu_data: Any) -> bool:
        return isinstance(cpu_data, GifCpuData) and len(cpu_data.frames_rgba) > 1

    # --- Decoded frame cache ---

    def estimate_cache_bytes(self, cpu_data: Any) -> int:
        if not isinstance(cpu_data, GifCpuData):
            return 0
        return (
            sum(len(frame) for frame in cpu_data.frames_rgba)
            + (len(cpu_data.durations) * 8)
            + len(cpu_data.first_frame_png or b"")
        )

    def clone_cpu_data_for_cache(self, cpu_data: Any) -> GifCpuData:
        if not isinstance(cpu_data, GifCpuData):
            raise TypeError("expected GifCpuData")
        return GifCpuData(
            first_frame_img=None,
            frames_rgba=list(cpu_data.frames_rgba),
            durations=list(cpu_data.durations),
            width=cpu_data.width,
            height=cpu_data.height,
            first_frame_png=cpu_data.first_frame_png,
        )

    def clone_cached_cpu_data(self, cpu_data: Any) -> GifCpuData:
        if not isinstance(cpu_data, GifCpuData):
            raise TypeError("expected cached GifCpuData")
        if not cpu_data.frames_rgba:
            raise RuntimeError("cached GIF has no frames")
        first_png = cpu_data.first_frame_png or _rgba_to_png(cpu_data.frames_rgba[0], cpu_data.width, cpu_data.height)
        first_img = load_image_from_memory(".png", first_png)
        return GifCpuData(
            first_frame_img=first_img,
            frames_rgba=list(cpu_data.frames_rgba),
            durations=list(cpu_data.durations),
            width=cpu_data.width,
            height=cpu_data.height,
            first_frame_png=first_png,
        )

    def cleanup_cached_cpu_data(self, cpu_data: Any) -> None:
        if isinstance(cpu_data, GifCpuData):
            if cpu_data.first_frame_img is not None:
                try:
                    rl.UnloadImage(cpu_data.first_frame_img)
                except Exception:
                    pass
            cpu_data.first_frame_img = None
            cpu_data.frames_rgba = []
            cpu_data.durations = []
            cpu_data.first_frame_png = None

    def create_playback(self, cpu_data: Any) -> Playback:
        total_ms = sum(cpu_data.durations)
        return Playback(
            viewer=self,
            data={
                "frames_rgba": cpu_data.frames_rgba,
                "durations": cpu_data.durations,
                "texture": cpu_data._tex_ref,
                "width": cpu_data.width,
                "height": cpu_data.height,
                "current_frame": 0,
                "elapsed": 0.0,
            },
            playing=True,
            looping=True,
            duration_ms=total_ms,
        )

    def advance_frame(self, playback: Playback, dt_ms: float) -> Optional[TextureInfo]:
        d = playback.data
        d["elapsed"] += dt_ms

        dur = d["durations"][d["current_frame"]]
        if d["elapsed"] < dur:
            return None

        # Advance to next frame (handle skipping if lag)
        while d["elapsed"] >= dur:
            d["elapsed"] -= dur
            d["current_frame"] = (d["current_frame"] + 1) % len(d["frames_rgba"])
            dur = d["durations"][d["current_frame"]]

        # Update texture in-place — no new TextureInfo needed
        update_texture_rgba(d["texture"], d["frames_rgba"][d["current_frame"]])
        playback.position_ms = (playback.position_ms + dt_ms) % playback.duration_ms
        return None  # Same texture, updated in place

    def cleanup_playback(self, playback: Playback) -> None:
        playback.data["frames_rgba"] = []
        playback.data["durations"] = []

    def cleanup_cpu_data(self, cpu_data: Any) -> None:
        if isinstance(cpu_data, GifCpuData):
            if cpu_data.first_frame_img is not None:
                try:
                    rl.UnloadImage(cpu_data.first_frame_img)
                except Exception:
                    pass
                cpu_data.first_frame_img = None
            cpu_data.frames_rgba = []
            cpu_data.durations = []
            cpu_data.first_frame_png = None
        else:
            super().cleanup_cpu_data(cpu_data)


def _rgba_to_png(rgba_bytes: bytes, w: int, h: int) -> bytes:
    """Convert raw RGBA bytes to PNG in memory."""
    from PIL import Image as PILImage
    img = PILImage.frombytes("RGBA", (w, h), rgba_bytes)
    buf = io.BytesIO()
    img.save(buf, format="PNG", compress_level=1)
    img.close()
    return buf.getvalue()
