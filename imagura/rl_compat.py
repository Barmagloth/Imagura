"""Raylib compatibility layer - abstracts differences between raylibpy and python-raylib."""

from __future__ import annotations
import ctypes
from typing import Any, Tuple

# Try to import raylib
try:
    import raylibpy as rl
    RL_VERSION = "raylibpy"
except Exception:
    import raylib as rl
    RL_VERSION = "python-raylib"

# Get common colors
RL_WHITE = getattr(rl, "RAYWHITE", rl.WHITE)


class _CTypesRect(ctypes.Structure):
    """Fallback Rectangle structure for ctypes."""
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
        ("width", ctypes.c_float),
        ("height", ctypes.c_float),
    ]


class _CTypesVec2(ctypes.Structure):
    """Fallback Vector2 structure for ctypes."""
    _fields_ = [
        ("x", ctypes.c_float),
        ("y", ctypes.c_float),
    ]


def make_rect(x: float, y: float, w: float, h: float) -> Any:
    """Create a raylib Rectangle compatible with the current binding."""
    if hasattr(rl, 'Rectangle'):
        try:
            return rl.Rectangle(x, y, w, h)
        except Exception:
            pass
    if hasattr(rl, 'ffi'):
        r = rl.ffi.new("Rectangle *")
        r[0].x = float(x)
        r[0].y = float(y)
        r[0].width = float(w)
        r[0].height = float(h)
        return r[0]
    return _CTypesRect(float(x), float(y), float(w), float(h))


def make_vec2(x: float, y: float) -> Any:
    """Create a raylib Vector2 compatible with the current binding."""
    if hasattr(rl, 'Vector2'):
        try:
            return rl.Vector2(x, y)
        except Exception:
            pass
    if hasattr(rl, 'ffi'):
        v = rl.ffi.new("Vector2 *")
        v[0].x = float(x)
        v[0].y = float(y)
        return v[0]
    return _CTypesVec2(float(x), float(y))


def make_color(r: int, g: int, b: int, a: int) -> Any:
    """Create a raylib Color compatible with the current binding."""
    ctor = getattr(rl, "Color", None)
    if ctor:
        try:
            return ctor(int(r), int(g), int(b), int(a))
        except Exception:
            pass
    # Fallback: use Fade on a base color
    base = rl.WHITE if (int(r) + int(g) + int(b)) >= 384 else rl.BLACK
    alpha = max(0.0, min(1.0, int(a) / 255.0))
    try:
        return rl.Fade(base, float(alpha))
    except Exception:
        return base


def draw_text(text: str, x: int, y: int, size: int, color: Any) -> None:
    """Draw text with encoding fallback."""
    try:
        rl.DrawText(text, x, y, size, color)
    except TypeError:
        rl.DrawText(text.encode('utf-8'), x, y, size, color)


def measure_text(text: str, size: int) -> int:
    """Measure text width with encoding fallback."""
    try:
        return rl.MeasureText(text, size)
    except TypeError:
        return rl.MeasureText(text.encode('utf-8'), size)


def load_image(path: str) -> Any:
    """Load image with encoding fallback."""
    try:
        return rl.LoadImage(path)
    except Exception:
        return rl.LoadImage(path.encode('utf-8'))


def get_texture_id(tex: Any) -> int:
    """Safely get texture ID."""
    return getattr(tex, 'id', 0) or 0


def is_texture_valid(tex: Any) -> bool:
    """Check if texture is valid and loaded."""
    return get_texture_id(tex) > 0


# Re-export commonly used raylib items
__all__ = [
    'rl',
    'RL_VERSION',
    'RL_WHITE',
    'make_rect',
    'make_vec2',
    'make_color',
    'draw_text',
    'measure_text',
    'load_image',
    'get_texture_id',
    'is_texture_valid',
]
