"""Thumbnail scheduling and cache maintenance."""

from __future__ import annotations

import os
from typing import Any, Optional

from .. import config as cfg
from ..logging import log
from ..types import BitmapThumb, LoadPriority


class ThumbnailService:
    """Coordinates gallery thumbnail queueing, loading, and cache eviction."""

    def __init__(self, texture_manager: Any):
        self.texture_manager = texture_manager

    def schedule_around(self, state: Any, around_index: int) -> None:
        n = len(state.current_dir_images)
        if n == 0:
            return

        span = int(cfg.THUMB_PRELOAD_SPAN)
        lo = max(0, around_index - span)
        hi = min(n - 1, around_index + span)
        in_queue = set(state.thumb_queue)

        for idx in range(lo, hi + 1):
            path = state.current_dir_images[idx]
            if path not in state.thumb_cache and path not in in_queue:
                state.thumb_queue.append(path)
                in_queue.add(path)

    def gallery_height(self, screen_h: int) -> int:
        return max(int(screen_h * cfg.GALLERY_HEIGHT_FRAC), int(cfg.GALLERY_MIN_HEIGHT_PX))

    def process_queue(self, state: Any) -> None:
        target_h = int(self.gallery_height(state.screenH) * 0.8)
        budget = int(cfg.THUMB_BUILD_BUDGET_PER_FRAME)

        while budget > 0 and state.thumb_queue:
            path = state.thumb_queue.popleft()
            if path in state.thumb_cache:
                continue

            state.thumb_cache[path] = BitmapThumb(None, (0, 0), path, False)
            state.async_loader.submit(
                path,
                LoadPriority.GALLERY,
                self._make_loaded_callback(state, target_h),
            )
            budget -= 1

        self.enforce_cache_limit(state)

    def enforce_cache_limit(self, state: Any) -> None:
        limit = int(cfg.THUMB_CACHE_LIMIT)
        while len(state.thumb_cache) > limit:
            _, thumb = state.thumb_cache.popitem(last=False)
            if thumb and thumb.texture:
                self.texture_manager.unload_texture(thumb.texture)

    def _make_loaded_callback(self, state: Any, target_h: int):
        def on_thumb_loaded(path: str, loaded, error: Optional[Exception]) -> None:
            if error:
                log(f"[THUMB][ERR] {os.path.basename(path)}: {error!r}")
                state.thumb_cache[path] = BitmapThumb(None, (0, 0), path, False)
                return

            try:
                thumb = self.texture_manager.build_thumbnail(loaded, target_h, path)
                state.thumb_cache[path] = thumb
            except Exception as exc:
                log(f"[THUMB][ERR] Failed to create texture: {exc!r}")
                state.thumb_cache[path] = BitmapThumb(None, (0, 0), path, False)

        return on_thumb_loaded
