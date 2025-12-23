"""Clipboard operations for Imagura.

Provides cross-platform image copy to clipboard functionality.
On Windows uses win32clipboard, on other platforms uses PIL workarounds.
"""

from __future__ import annotations
import io
import sys
from typing import Optional
from PIL import Image

from .logging import log


def copy_image_to_clipboard(image_path: str) -> bool:
    """
    Copy an image file to the system clipboard.

    Args:
        image_path: Path to the image file.

    Returns:
        True if successful, False otherwise.
    """
    try:
        img = Image.open(image_path)
        # Convert to RGB if necessary (clipboard doesn't handle all modes well)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background for transparency
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        if sys.platform == 'win32':
            return _copy_to_clipboard_windows(img)
        else:
            log(f"[CLIPBOARD] Clipboard copy not supported on {sys.platform}")
            return False

    except Exception as e:
        log(f"[CLIPBOARD][ERR] Failed to copy image: {e!r}")
        return False


def _copy_to_clipboard_windows(img: Image.Image) -> bool:
    """Copy PIL Image to Windows clipboard using BMP format."""
    try:
        import win32clipboard
        import win32con

        # Convert to BMP format in memory
        output = io.BytesIO()
        img.save(output, format='BMP')
        bmp_data = output.getvalue()

        # BMP file header is 14 bytes, we skip it for clipboard
        # The clipboard expects DIB (device-independent bitmap) data
        dib_data = bmp_data[14:]  # Skip BITMAPFILEHEADER

        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32con.CF_DIB, dib_data)
        finally:
            win32clipboard.CloseClipboard()

        log(f"[CLIPBOARD] Image copied to clipboard ({img.width}x{img.height})")
        return True

    except ImportError:
        log("[CLIPBOARD][ERR] pywin32 not installed, trying alternative method")
        return _copy_to_clipboard_windows_alternative(img)
    except Exception as e:
        log(f"[CLIPBOARD][ERR] Windows clipboard error: {e!r}")
        return False


def _copy_to_clipboard_windows_alternative(img: Image.Image) -> bool:
    """Alternative Windows clipboard copy using ctypes."""
    try:
        import ctypes
        from ctypes import wintypes

        # Windows API constants
        CF_DIB = 8
        GMEM_MOVEABLE = 0x0002

        # Get DIB data
        output = io.BytesIO()
        img.save(output, format='BMP')
        bmp_data = output.getvalue()
        dib_data = bmp_data[14:]  # Skip BITMAPFILEHEADER

        # Windows API functions
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # Open clipboard
        if not user32.OpenClipboard(None):
            return False

        try:
            user32.EmptyClipboard()

            # Allocate global memory
            h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dib_data))
            if not h_mem:
                return False

            # Lock memory and copy data
            p_mem = kernel32.GlobalLock(h_mem)
            if not p_mem:
                kernel32.GlobalFree(h_mem)
                return False

            ctypes.memmove(p_mem, dib_data, len(dib_data))
            kernel32.GlobalUnlock(h_mem)

            # Set clipboard data
            user32.SetClipboardData(CF_DIB, h_mem)

        finally:
            user32.CloseClipboard()

        log(f"[CLIPBOARD] Image copied (alt method) ({img.width}x{img.height})")
        return True

    except Exception as e:
        log(f"[CLIPBOARD][ERR] Alternative clipboard method failed: {e!r}")
        return False
