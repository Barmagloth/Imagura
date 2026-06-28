"""Image list sorting helpers."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, Sequence

from .image_metadata import get_image_metadata


@dataclass(frozen=True)
class SortOption:
    key: str
    label: str


SORT_OPTIONS: tuple[SortOption, ...] = (
    SortOption("name", "Name"),
    SortOption("modified", "Modified"),
    SortOption("created", "Created"),
    SortOption("size", "Size"),
    SortOption("type", "Type"),
    SortOption("date_taken", "Taken"),
)

VALID_SORT_KEYS = frozenset(option.key for option in SORT_OPTIONS)


def sort_label(sort_key: str) -> str:
    for option in SORT_OPTIONS:
        if option.key == sort_key:
            return option.label
    return SORT_OPTIONS[0].label


def normalize_sort_key(sort_key: str) -> str:
    return sort_key if sort_key in VALID_SORT_KEYS else "name"


def sort_image_paths(paths: Sequence[str], sort_key: str = "name", descending: bool = False) -> list[str]:
    """Return paths sorted by a user-facing key.

    Name sorting is natural and case-insensitive. Other sorts use filename as a
    stable tie-breaker, so repeated sorting is deterministic.
    """
    normalized_key = normalize_sort_key(sort_key)
    if normalized_key == "name":
        return sorted(paths, key=_natural_name_key, reverse=descending)

    by_name = sorted(paths, key=_natural_name_key)
    key_fn = _key_function(normalized_key)
    return sorted(by_name, key=key_fn, reverse=descending)


def resort_preserving_current(
    paths: Sequence[str],
    current_path: str | None,
    sort_key: str,
    descending: bool,
) -> tuple[list[str], int]:
    sorted_paths = sort_image_paths(paths, sort_key, descending)
    if not current_path:
        return sorted_paths, 0
    try:
        return sorted_paths, sorted_paths.index(current_path)
    except ValueError:
        return sorted_paths, 0


def _key_function(sort_key: str) -> Callable[[str], object]:
    if sort_key == "modified":
        return _mtime_key
    if sort_key == "created":
        return _ctime_key
    if sort_key == "size":
        return _size_key
    if sort_key == "type":
        return _type_key
    if sort_key == "date_taken":
        return _date_taken_key
    return _natural_name_key


def _natural_name_key(path: str) -> tuple[object, ...]:
    name = os.path.basename(path).casefold()
    parts = re.split(r"(\d+)", name)
    return tuple(int(part) if part.isdigit() else part for part in parts)


def _stat_value(path: str, attr: str) -> int:
    try:
        return int(getattr(os.stat(path), attr))
    except Exception:
        return 0


def _mtime_key(path: str) -> int:
    return _stat_value(path, "st_mtime_ns")


def _ctime_key(path: str) -> int:
    return _stat_value(path, "st_ctime_ns")


def _size_key(path: str) -> int:
    try:
        return os.path.getsize(path)
    except Exception:
        return 0


def _type_key(path: str) -> str:
    return os.path.splitext(path)[1].casefold()


def _date_taken_key(path: str) -> str:
    metadata = get_image_metadata(path)
    return metadata.get("date", "")
