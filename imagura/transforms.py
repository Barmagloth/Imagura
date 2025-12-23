"""Image transformation operations for Imagura.

Provides rotate and flip operations that modify image files in-place
or create transformed textures.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Optional, Tuple
from PIL import Image
import os

from .logging import log

if TYPE_CHECKING:
    from .rl_compat import rl


def rotate_image_file(image_path: str, clockwise: bool = True) -> bool:
    """
    Rotate an image file 90 degrees and save it.

    Args:
        image_path: Path to the image file.
        clockwise: If True, rotate clockwise; otherwise counter-clockwise.

    Returns:
        True if successful, False otherwise.
    """
    try:
        img = Image.open(image_path)

        # PIL uses counter-clockwise angles
        angle = -90 if clockwise else 90
        rotated = img.rotate(angle, expand=True)

        # Preserve format and EXIF if possible
        fmt = img.format or 'PNG'
        exif = img.info.get('exif')

        save_kwargs = {}
        if exif and fmt.upper() in ('JPEG', 'JPG', 'WEBP', 'TIFF'):
            save_kwargs['exif'] = exif
        if fmt.upper() in ('JPEG', 'JPG'):
            save_kwargs['quality'] = 95
            save_kwargs['optimize'] = True
        if fmt.upper() == 'PNG':
            save_kwargs['optimize'] = True

        rotated.save(image_path, format=fmt, **save_kwargs)

        direction = "clockwise" if clockwise else "counter-clockwise"
        log(f"[TRANSFORM] Rotated {direction}: {os.path.basename(image_path)}")
        return True

    except Exception as e:
        log(f"[TRANSFORM][ERR] Rotate failed: {e!r}")
        return False


def flip_image_file(image_path: str, horizontal: bool = True) -> bool:
    """
    Flip an image file horizontally or vertically and save it.

    Args:
        image_path: Path to the image file.
        horizontal: If True, flip horizontally; otherwise vertically.

    Returns:
        True if successful, False otherwise.
    """
    try:
        img = Image.open(image_path)

        if horizontal:
            flipped = img.transpose(Image.FLIP_LEFT_RIGHT)
        else:
            flipped = img.transpose(Image.FLIP_TOP_BOTTOM)

        # Preserve format and EXIF if possible
        fmt = img.format or 'PNG'
        exif = img.info.get('exif')

        save_kwargs = {}
        if exif and fmt.upper() in ('JPEG', 'JPG', 'WEBP', 'TIFF'):
            save_kwargs['exif'] = exif
        if fmt.upper() in ('JPEG', 'JPG'):
            save_kwargs['quality'] = 95
            save_kwargs['optimize'] = True
        if fmt.upper() == 'PNG':
            save_kwargs['optimize'] = True

        flipped.save(image_path, format=fmt, **save_kwargs)

        direction = "horizontally" if horizontal else "vertically"
        log(f"[TRANSFORM] Flipped {direction}: {os.path.basename(image_path)}")
        return True

    except Exception as e:
        log(f"[TRANSFORM][ERR] Flip failed: {e!r}")
        return False


def get_rotated_dimensions(width: int, height: int, clockwise: bool = True) -> Tuple[int, int]:
    """Get dimensions after 90-degree rotation (they swap)."""
    return (height, width)


def get_flipped_dimensions(width: int, height: int) -> Tuple[int, int]:
    """Get dimensions after flip (unchanged)."""
    return (width, height)
