"""FIFO RAM cache for decoded animated content."""

from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional

from .. import config as cfg
from ..logging import log


@dataclass
class _CachedAnimatedContent:
    viewer: Any
    cpu_data: Any
    bytes_used: int


class AnimatedContentCache:
    """Owns a bounded FIFO cache of decoded animated frames.

    This cache is session-only and RAM-backed. It stores reusable CPU frame
    data, not raylib textures or live playback state. Cache hits still upload a
    fresh current texture, but avoid file I/O and GIF frame decoding.
    """

    def __init__(
        self,
        max_mb: int = cfg.ANIMATED_CONTENT_CACHE_MAX_MB,
        max_items: int = cfg.ANIMATED_CONTENT_CACHE_MAX_ITEMS,
    ):
        self.max_bytes = max(0, int(max_mb)) * 1024 * 1024
        self.max_items = max(0, int(max_items))
        self._entries: OrderedDict[str, _CachedAnimatedContent] = OrderedDict()
        self._bytes_used = 0

    @property
    def bytes_used(self) -> int:
        return self._bytes_used

    def configure(self, max_mb: int | None = None, max_items: int | None = None) -> None:
        if max_mb is not None:
            self.max_bytes = max(0, int(max_mb)) * 1024 * 1024
        if max_items is not None:
            self.max_items = max(0, int(max_items))
        self._evict_to_budget()

    def get(self, path: str) -> Optional[tuple[Any, Any]]:
        entry = self._entries.get(path)
        if not entry:
            return None

        clone = getattr(entry.viewer, "clone_cached_cpu_data", None)
        if clone is None:
            self.remove(path)
            return None

        try:
            cpu_data = clone(entry.cpu_data)
        except Exception as exc:
            log(f"[ANIM_CACHE][ERR] {os.path.basename(path)} clone failed: {exc!r}")
            self.remove(path)
            return None

        log(f"[ANIM_CACHE][HIT] {os.path.basename(path)}")
        return entry.viewer, cpu_data

    def put(self, path: str, viewer: Any, cpu_data: Any) -> None:
        if self.max_bytes <= 0 or self.max_items <= 0:
            return

        estimate = getattr(viewer, "estimate_cache_bytes", None)
        clone = getattr(viewer, "clone_cpu_data_for_cache", None)
        if estimate is None or clone is None:
            return

        try:
            bytes_used = max(1, int(estimate(cpu_data)))
        except Exception as exc:
            log(f"[ANIM_CACHE][ERR] {os.path.basename(path)} estimate failed: {exc!r}")
            return

        if bytes_used > self.max_bytes:
            log(
                f"[ANIM_CACHE][SKIP] {os.path.basename(path)} "
                f"{bytes_used / (1024 * 1024):.1f}MB exceeds cache budget "
                f"{self.max_bytes / (1024 * 1024):.1f}MB"
            )
            return

        try:
            cached_cpu_data = clone(cpu_data)
        except Exception as exc:
            log(f"[ANIM_CACHE][ERR] {os.path.basename(path)} cache clone failed: {exc!r}")
            return

        old = self._entries.pop(path, None)
        if old:
            self._bytes_used -= old.bytes_used
            self._cleanup_entry(path, old)

        self._entries[path] = _CachedAnimatedContent(viewer, cached_cpu_data, bytes_used)
        self._bytes_used += bytes_used
        log(
            f"[ANIM_CACHE][PUT] {os.path.basename(path)} "
            f"{bytes_used / (1024 * 1024):.1f}MB total={self._bytes_used / (1024 * 1024):.1f}MB"
        )

        self._evict_to_budget()

    def remove(self, path: str) -> bool:
        entry = self._entries.pop(path, None)
        if not entry:
            return False
        self._bytes_used -= entry.bytes_used
        self._cleanup_entry(path, entry)
        log(f"[ANIM_CACHE][DROP] {os.path.basename(path)}")
        return True

    def cached_paths(self) -> list[str]:
        return list(self._entries.keys())

    def clear(self) -> None:
        for path, entry in list(self._entries.items()):
            self._cleanup_entry(path, entry)
        self._entries.clear()
        self._bytes_used = 0

    def _evict_to_budget(self) -> None:
        while self._entries and (len(self._entries) > self.max_items or self._bytes_used > self.max_bytes):
            path, entry = self._entries.popitem(last=False)
            self._bytes_used -= entry.bytes_used
            self._cleanup_entry(path, entry)
            log(f"[ANIM_CACHE][EVICT] {os.path.basename(path)}")

    def _cleanup_entry(self, path: str, entry: _CachedAnimatedContent) -> None:
        cleanup = getattr(entry.viewer, "cleanup_cached_cpu_data", None)
        if cleanup is None:
            return
        try:
            cleanup(entry.cpu_data)
        except Exception as exc:
            log(f"[ANIM_CACHE][ERR] {os.path.basename(path)} cleanup failed: {exc!r}")
