"""Image utilities - probing, listing, loading helpers."""

from __future__ import annotations
import os
import struct
import hashlib
from typing import Optional, Tuple, List

from .config import (
    IMG_EXTS,
    MAX_FILE_SIZE_MB,
    HEAVY_FILE_SIZE_MB,
    HEAVY_MIN_SHORT_SIDE,
    THUMB_CACHE_DIR,
)


def probe_image_dimensions(filepath: str) -> Optional[Tuple[int, int]]:
    """Quickly read image dimensions from file header without loading the full image.

    Args:
        filepath: Path to image file.

    Returns:
        Tuple of (width, height) or None if unable to determine.
    """
    ext = os.path.splitext(filepath)[1].lower()
    try:
        with open(filepath, 'rb') as f:
            header = f.read(64 * 1024)

        if ext in ('.jpg', '.jpeg'):
            return _probe_jpeg(header)
        elif ext == '.png':
            return _probe_png(header)
    except Exception:
        pass
    return None


def _probe_jpeg(data: bytes) -> Optional[Tuple[int, int]]:
    """Extract dimensions from JPEG header."""
    i = 0
    while i + 9 < len(data):
        if data[i] == 0xFF:
            marker = data[i + 1]
            # SOF markers contain dimensions
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                height = struct.unpack('>H', data[i + 5:i + 7])[0]
                width = struct.unpack('>H', data[i + 7:i + 9])[0]
                return (width, height)
            elif marker not in (0x00, 0xFF) and i + 3 < len(data):
                seg_len = struct.unpack('>H', data[i + 2:i + 4])[0]
                i += 2 + seg_len
            else:
                i += 1
        else:
            i += 1
    return None


def _probe_png(data: bytes) -> Optional[Tuple[int, int]]:
    """Extract dimensions from PNG header."""
    if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    width = struct.unpack('>I', data[16:20])[0]
    height = struct.unpack('>I', data[20:24])[0]
    return (width, height)


def is_heavy_image(filepath: str) -> bool:
    """Check if image is 'heavy' (large file or high resolution).

    Heavy images show a loading indicator during async load.

    Args:
        filepath: Path to image file.

    Returns:
        True if image is considered heavy.
    """
    try:
        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        if file_size_mb >= HEAVY_FILE_SIZE_MB:
            return True
    except Exception:
        pass

    dims = probe_image_dimensions(filepath)
    if dims:
        w, h = dims
        if min(w, h) >= HEAVY_MIN_SHORT_SIDE:
            return True
    return False


def get_file_size_mb(filepath: str) -> float:
    """Get file size in megabytes."""
    try:
        return os.path.getsize(filepath) / (1024 * 1024)
    except Exception:
        return 0.0


def is_file_too_large(filepath: str) -> bool:
    """Check if file exceeds maximum allowed size."""
    return get_file_size_mb(filepath) > MAX_FILE_SIZE_MB


def list_images(dirpath: str) -> List[str]:
    """List all supported image files in directory, sorted by name.

    Args:
        dirpath: Directory path to scan.

    Returns:
        List of full paths to image files.
    """
    try:
        names = sorted(os.listdir(dirpath))
    except Exception:
        return []

    result = []
    for name in names:
        path = os.path.join(dirpath, name)
        ext = os.path.splitext(name)[1].lower()
        if os.path.isfile(path) and ext in IMG_EXTS:
            result.append(path)
    return result


def get_thumb_cache_path(filepath: str) -> str:
    """Generate cache path for thumbnail based on file path and modification time.

    Args:
        filepath: Path to original image.

    Returns:
        Path where thumbnail should be cached.
    """
    try:
        stat = os.stat(filepath)
        key_data = f"{filepath}|{stat.st_mtime_ns}|{stat.st_size}".encode('utf-8')
    except Exception:
        key_data = filepath.encode('utf-8')

    cache_key = hashlib.sha1(key_data).hexdigest()
    os.makedirs(THUMB_CACHE_DIR, exist_ok=True)
    return os.path.join(THUMB_CACHE_DIR, f"{cache_key}_thumb.qoi")


def is_supported_image(filepath: str) -> bool:
    """Check if file has a supported image extension."""
    ext = os.path.splitext(filepath)[1].lower()
    return ext in IMG_EXTS
