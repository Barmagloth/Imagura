"""Pure math utilities - no external dependencies."""

from __future__ import annotations


def clamp(v: float, a: float, b: float) -> float:
    """Clamp value v to range [a, b]."""
    return a if v < a else b if v > b else v


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation from a to b by factor t (clamped to [0, 1])."""
    t = clamp(t, 0.0, 1.0)
    return a + (b - a) * t


def ease_out_quad(t: float) -> float:
    """Quadratic ease-out: decelerating to zero velocity."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return 1.0 - (1.0 - t) * (1.0 - t)


def ease_in_out_cubic(t: float) -> float:
    """Cubic ease-in-out: acceleration until halfway, then deceleration."""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    if t < 0.5:
        return 4.0 * t * t * t
    else:
        p = 2.0 * t - 2.0
        return 1.0 + 0.5 * p * p * p


def distance_squared(x1: float, y1: float, x2: float, y2: float) -> float:
    """Squared distance between two points (avoids sqrt for comparisons)."""
    dx = x2 - x1
    dy = y2 - y1
    return dx * dx + dy * dy
