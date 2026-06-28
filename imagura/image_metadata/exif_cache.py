"""Bounded EXIF metadata cache for HUD display."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from typing import Dict, List

from ..logging import log

try:
    from PIL import Image
    from PIL.ExifTags import TAGS

    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class ExifMetadataCache:
    """Reads a small normalized EXIF subset and keeps a bounded LRU cache."""

    def __init__(self, limit: int = 500):
        self.limit = max(1, int(limit))
        self._cache: OrderedDict[str, Dict[str, str]] = OrderedDict()

    def get(self, filepath: str) -> Dict[str, str]:
        if filepath in self._cache:
            self._cache.move_to_end(filepath)
            return self._cache[filepath]

        metadata = self._read_uncached(filepath)
        self._cache[filepath] = metadata
        while len(self._cache) > self.limit:
            self._cache.popitem(last=False)
        return metadata

    def cached_paths(self) -> List[str]:
        return list(self._cache.keys())

    def _read_uncached(self, filepath: str) -> Dict[str, str]:
        metadata: Dict[str, str] = {}
        if not HAS_PIL:
            return metadata

        try:
            with Image.open(filepath) as img:
                exif_data = img._getexif()
                if not exif_data:
                    return metadata

                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, str(tag_id))
                    self._apply_metadata_value(metadata, tag_name, value)
        except Exception as exc:
            log(f"[METADATA] Error reading EXIF from {filepath}: {exc}")

        return metadata

    def _apply_metadata_value(self, metadata: Dict[str, str], tag_name: str, value) -> None:
        if tag_name == "DateTimeOriginal":
            try:
                dt = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                metadata["date"] = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                metadata["date"] = str(value)
        elif tag_name == "Model":
            metadata["camera"] = str(value).strip()
        elif tag_name == "FocalLength":
            metadata["focal"] = f"{_ratio_to_float(value):.0f}mm" if _is_ratio(value) else f"{value}mm"
        elif tag_name == "FNumber":
            metadata["aperture"] = f"f/{_ratio_to_float(value):.1f}" if _is_ratio(value) else f"f/{value}"
        elif tag_name == "ISOSpeedRatings":
            metadata["iso"] = f"ISO {value}"
        elif tag_name == "ExposureTime":
            exposure = _format_exposure(value)
            if exposure:
                metadata["exposure"] = exposure


def _is_ratio(value) -> bool:
    return hasattr(value, "numerator") and hasattr(value, "denominator")


def _ratio_to_float(value) -> float:
    return value.numerator / value.denominator if value.denominator else 0.0


def _format_exposure(value) -> str:
    if _is_ratio(value):
        if not value.denominator or not value.numerator:
            return ""
        if value.numerator < value.denominator:
            return f"1/{value.denominator // value.numerator}s"
        return f"{_ratio_to_float(value):.1f}s"
    return f"{value}s"


_DEFAULT_CACHE = ExifMetadataCache()


def get_image_metadata(filepath: str) -> Dict[str, str]:
    return _DEFAULT_CACHE.get(filepath)
