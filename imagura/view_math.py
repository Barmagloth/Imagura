"""Pure view calculation functions - no side effects, no state mutation."""

from __future__ import annotations
from typing import Tuple

from .types import ViewParams, TextureInfo
from .math_utils import clamp
from .logging import log


def compute_fit_scale(
    img_w: int,
    img_h: int,
    screen_w: int,
    screen_h: int,
    frac: float = 1.0
) -> float:
    """Compute scale to fit image within screen bounds.

    Args:
        img_w: Image width in pixels.
        img_h: Image height in pixels.
        screen_w: Screen width in pixels.
        screen_h: Screen height in pixels.
        frac: Fraction of screen to use (0.0-1.0).

    Returns:
        Scale factor to fit image.
    """
    if img_w == 0 or img_h == 0:
        return 1.0
    return min(screen_w * frac / img_w, screen_h * frac / img_h)


def center_view_for(
    scale: float,
    img_w: int,
    img_h: int,
    screen_w: int,
    screen_h: int
) -> ViewParams:
    """Create a centered ViewParams for given scale.

    Args:
        scale: Scale factor.
        img_w: Image width in pixels.
        img_h: Image height in pixels.
        screen_w: Screen width in pixels.
        screen_h: Screen height in pixels.

    Returns:
        ViewParams centered on screen.
    """
    return ViewParams(
        scale=scale,
        offx=(screen_w - img_w * scale) / 2.0,
        offy=(screen_h - img_h * scale) / 2.0
    )


def compute_fit_view(
    img_w: int,
    img_h: int,
    screen_w: int,
    screen_h: int,
    frac: float = 1.0
) -> ViewParams:
    """Compute a ViewParams that fits and centers the image.

    Args:
        img_w: Image width in pixels.
        img_h: Image height in pixels.
        screen_w: Screen width in pixels.
        screen_h: Screen height in pixels.
        frac: Fraction of screen to use.

    Returns:
        ViewParams with fit scale and centered offsets.
    """
    scale = compute_fit_scale(img_w, img_h, screen_w, screen_h, frac)
    return center_view_for(scale, img_w, img_h, screen_w, screen_h)


def clamp_pan(
    view: ViewParams,
    img_w: int,
    img_h: int,
    screen_w: int,
    screen_h: int
) -> ViewParams:
    """Clamp view offsets to keep image within screen bounds.

    Uses center-based clamping to ensure smooth transitions during zoom:
    - Tracks image center position relative to screen center
    - Clamps based on how far the center can move from screen center
    - For small images: center stays within screen bounds
    - For large images: center can move far enough to show edges

    Args:
        view: Current view parameters.
        img_w: Image width in pixels.
        img_h: Image height in pixels.
        screen_w: Screen width in pixels.
        screen_h: Screen height in pixels.

    Returns:
        New ViewParams with clamped offsets.
    """
    result = view.copy()
    vw = img_w * view.scale
    vh = img_h * view.scale

    # Calculate current image center
    img_center_x = view.offx + vw / 2
    img_center_y = view.offy + vh / 2
    screen_center_x = screen_w / 2
    screen_center_y = screen_h / 2

    # How far can image center deviate from screen center?
    # For small image: center must stay within [vw/2, screen_w - vw/2]
    #   => deviation from screen_center: [vw/2 - screen_w/2, screen_w/2 - vw/2]
    #   => max deviation = (screen_w - vw) / 2
    # For large image: center can go to [screen_w - vw/2, vw/2] to show edges
    #   => max deviation = (vw - screen_w) / 2

    # Unified: max deviation = abs(screen_w - vw) / 2
    max_dev_x = abs(screen_w - vw) / 2
    max_dev_y = abs(screen_h - vh) / 2

    # Clamp image center position
    clamped_center_x = clamp(img_center_x, screen_center_x - max_dev_x, screen_center_x + max_dev_x)
    clamped_center_y = clamp(img_center_y, screen_center_y - max_dev_y, screen_center_y + max_dev_y)

    # Convert back to offset
    result.offx = clamped_center_x - vw / 2
    result.offy = clamped_center_y - vh / 2

    return result


def recompute_view_anchor_zoom(
    view: ViewParams,
    new_scale: float,
    anchor: Tuple[int, int],
    img_w: int,
    img_h: int
) -> ViewParams:
    """Recompute view for new scale, keeping anchor point fixed.

    This allows zooming "towards" the mouse cursor position.

    Args:
        view: Current view parameters.
        new_scale: Target scale factor.
        anchor: Screen position (x, y) to keep fixed.
        img_w: Image width in pixels.
        img_h: Image height in pixels.

    Returns:
        New ViewParams with adjusted offsets.
    """
    ax, ay = anchor
    old_scale = view.scale if view.scale and view.scale > 1e-6 else 1e-6

    # Convert anchor to image coordinates
    wx = (ax - view.offx) / old_scale
    wy = (ay - view.offy) / old_scale

    # Create new view with adjusted offsets
    result = ViewParams(scale=max(0.01, float(new_scale)))
    result.offx = ax - wx * result.scale
    result.offy = ay - wy * result.scale

    return result


def view_for_1to1_centered(
    img_w: int,
    img_h: int,
    screen_w: int,
    screen_h: int
) -> ViewParams:
    """Create a 1:1 (100%) scale centered view.

    Args:
        img_w: Image width in pixels.
        img_h: Image height in pixels.
        screen_w: Screen width in pixels.
        screen_h: Screen height in pixels.

    Returns:
        ViewParams at 1:1 scale, centered.
    """
    return center_view_for(1.0, img_w, img_h, screen_w, screen_h)


def sanitize_view(
    view: ViewParams,
    img_w: int,
    img_h: int,
    screen_w: int,
    screen_h: int,
    verbose: bool = True
) -> ViewParams:
    """Sanitize view parameters to fix common issues.

    Fixes:
    - Near-zero offsets that should be centered
    - Asymmetric offsets that indicate corruption
    - 1:1 views with bad offsets

    Args:
        view: View to sanitize.
        img_w: Image width in pixels.
        img_h: Image height in pixels.
        screen_w: Screen width in pixels.
        screen_h: Screen height in pixels.
        verbose: Whether to log corrections.

    Returns:
        Sanitized ViewParams.
    """
    v = view.copy()
    centered = center_view_for(v.scale, img_w, img_h, screen_w, screen_h)

    # Fix near-zero offsets
    if abs(v.offx) < 5.0 and abs(v.offy) < 5.0:
        if verbose:
            log(f"[SANITIZE] Near-zero offsets ({v.offx:.1f},{v.offy:.1f}) "
                f"at scale={v.scale:.3f} -> centering to "
                f"({centered.offx:.1f},{centered.offy:.1f})")
        return centered

    # Fix asymmetric offsets (one near zero, one large)
    if (abs(v.offx) < 5.0 and abs(v.offy) > 50.0) or \
       (abs(v.offy) < 5.0 and abs(v.offx) > 50.0):
        if verbose:
            log(f"[SANITIZE] Asymmetric offsets ({v.offx:.1f},{v.offy:.1f}) "
                f"at scale={v.scale:.3f} -> centering to "
                f"({centered.offx:.1f},{centered.offy:.1f})")
        return centered

    # Fix 1:1 views with bad offsets
    if abs(v.scale - 1.0) < 0.01:
        centered_1to1 = view_for_1to1_centered(img_w, img_h, screen_w, screen_h)
        if abs(v.offx - centered_1to1.offx) > 50 or \
           abs(v.offy - centered_1to1.offy) > 50:
            if verbose:
                log(f"[SANITIZE] 1:1 with bad offsets ({v.offx:.1f},{v.offy:.1f}) "
                    f"vs centered ({centered_1to1.offx:.1f},{centered_1to1.offy:.1f}) "
                    f"-> fixing")
            return centered_1to1

    # Apply pan clamping
    return clamp_pan(v, img_w, img_h, screen_w, screen_h)
