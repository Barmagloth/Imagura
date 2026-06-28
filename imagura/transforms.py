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
        with Image.open(image_path) as img:
            if getattr(img, "is_animated", False):
                log(f"[TRANSFORM][SKIP] Animated files are not rotated in-place yet: {os.path.basename(image_path)}")
                return False

            # PIL uses counter-clockwise angles
            angle = -90 if clockwise else 90
            rotated = img.rotate(angle, expand=True)

            # Preserve format and EXIF if possible, but reset orientation tag
            fmt = img.format or 'PNG'
            exif_bytes = img.info.get('exif')

        save_kwargs = {}
        if exif_bytes and fmt.upper() in ('JPEG', 'JPG', 'WEBP', 'TIFF'):
            try:
                import piexif
                exif_dict = piexif.load(exif_bytes)
                # Reset orientation to normal (1) since we physically rotated
                if piexif.ImageIFD.Orientation in exif_dict.get("0th", {}):
                    exif_dict["0th"][piexif.ImageIFD.Orientation] = 1
                save_kwargs['exif'] = piexif.dump(exif_dict)
            except Exception:
                # piexif not available — strip exif to avoid double-rotation
                pass
        if fmt.upper() in ('JPEG', 'JPG'):
            save_kwargs['quality'] = 95
            save_kwargs['optimize'] = True
        if fmt.upper() == 'PNG':
            save_kwargs['optimize'] = True

        try:
            rotated.save(image_path, format=fmt, **save_kwargs)
        finally:
            rotated.close()

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
        with Image.open(image_path) as img:
            if getattr(img, "is_animated", False):
                log(f"[TRANSFORM][SKIP] Animated files are not flipped in-place yet: {os.path.basename(image_path)}")
                return False

            if horizontal:
                flipped = img.transpose(Image.FLIP_LEFT_RIGHT)
            else:
                flipped = img.transpose(Image.FLIP_TOP_BOTTOM)

            # Preserve format and EXIF if possible, but reset orientation tag
            fmt = img.format or 'PNG'
            exif_bytes = img.info.get('exif')

        save_kwargs = {}
        if exif_bytes and fmt.upper() in ('JPEG', 'JPG', 'WEBP', 'TIFF'):
            try:
                import piexif
                exif_dict = piexif.load(exif_bytes)
                if piexif.ImageIFD.Orientation in exif_dict.get("0th", {}):
                    exif_dict["0th"][piexif.ImageIFD.Orientation] = 1
                save_kwargs['exif'] = piexif.dump(exif_dict)
            except Exception:
                pass
        if fmt.upper() in ('JPEG', 'JPG'):
            save_kwargs['quality'] = 95
            save_kwargs['optimize'] = True
        if fmt.upper() == 'PNG':
            save_kwargs['optimize'] = True

        try:
            flipped.save(image_path, format=fmt, **save_kwargs)
        finally:
            flipped.close()

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
