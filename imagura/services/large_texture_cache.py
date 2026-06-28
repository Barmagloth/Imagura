"""FIFO cache for full-size heavy image textures."""

from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass
from typing import Iterable, List, Optional

from .. import config as cfg
from ..logging import log
from ..rl_compat import get_texture_id
from ..types import TextureInfo


@dataclass
class _CachedTexture:
    texture: TextureInfo
    bytes_used: int


class LargeTextureCache:
    """Owns a bounded FIFO cache of full-size GPU textures.

    This cache is intentionally session-only and VRAM-backed. It avoids decode
    and GPU upload when the user revisits a heavy static image before eviction.
    """

    def __init__(self, max_mb: int = cfg.FULL_IMAGE_CACHE_MAX_MB, max_items: int = cfg.FULL_IMAGE_CACHE_MAX_ITEMS):
        self.max_bytes = max(0, int(max_mb)) * 1024 * 1024
        self.max_items = max(0, int(max_items))
        self._entries: OrderedDict[str, _CachedTexture] = OrderedDict()
        self._bytes_used = 0

    @property
    def bytes_used(self) -> int:
        return self._bytes_used

    def configure(
        self,
        max_mb: Optional[int] = None,
        max_items: Optional[int] = None,
        protected_texture_ids: Iterable[int] = (),
    ) -> List[TextureInfo]:
        if max_mb is not None:
            self.max_bytes = max(0, int(max_mb)) * 1024 * 1024
        if max_items is not None:
            self.max_items = max(0, int(max_items))
        return self._evict_to_budget(set(protected_texture_ids))

    def get(self, path: str) -> Optional[TextureInfo]:
        entry = self._entries.get(path)
        if not entry:
            return None
        tex_id = get_texture_id(entry.texture.tex)
        if tex_id <= 0:
            self.remove(path)
            return None
        log(f"[FULL_CACHE][HIT] {os.path.basename(path)}")
        return entry.texture.copy_ref()

    def put(self, texture: TextureInfo, protected_texture_ids: Iterable[int] = ()) -> List[TextureInfo]:
        if self.max_bytes <= 0 or self.max_items <= 0:
            return []
        tex_id = get_texture_id(texture.tex)
        if tex_id <= 0:
            return []

        bytes_used = self._estimate_bytes(texture)
        if bytes_used > self.max_bytes:
            log(
                f"[FULL_CACHE][SKIP] {os.path.basename(texture.path)} "
                f"{bytes_used / (1024 * 1024):.1f}MB exceeds cache budget "
                f"{self.max_bytes / (1024 * 1024):.1f}MB"
            )
            return []

        protected_ids = set(protected_texture_ids)
        evicted = []
        old = self._entries.pop(texture.path, None)
        if old:
            self._bytes_used -= old.bytes_used
            old_tex_id = get_texture_id(old.texture.tex)
            if old_tex_id != tex_id and old_tex_id not in protected_ids:
                evicted.append(old.texture)

        self._entries[texture.path] = _CachedTexture(texture.copy_ref(), bytes_used)
        self._bytes_used += bytes_used
        log(
            f"[FULL_CACHE][PUT] {os.path.basename(texture.path)} "
            f"{bytes_used / (1024 * 1024):.1f}MB total={self._bytes_used / (1024 * 1024):.1f}MB"
        )

        evicted.extend(self._evict_to_budget(protected_ids))
        return evicted

    def remove(self, path: str) -> Optional[TextureInfo]:
        entry = self._entries.pop(path, None)
        if not entry:
            return None
        self._bytes_used -= entry.bytes_used
        log(f"[FULL_CACHE][DROP] {os.path.basename(path)}")
        return entry.texture

    def contains_path(self, path: str) -> bool:
        return path in self._entries

    def contains_texture(self, texture: Optional[TextureInfo]) -> bool:
        if not texture:
            return False
        tex_id = get_texture_id(texture.tex)
        if tex_id <= 0:
            return False
        return any(get_texture_id(entry.texture.tex) == tex_id for entry in self._entries.values())

    def cached_paths(self) -> List[str]:
        return list(self._entries.keys())

    def clear(self) -> List[TextureInfo]:
        textures = [entry.texture for entry in self._entries.values()]
        self._entries.clear()
        self._bytes_used = 0
        return textures

    def _evict_to_budget(self, protected_texture_ids: set[int]) -> List[TextureInfo]:
        evicted = []
        while self._entries and (len(self._entries) > self.max_items or self._bytes_used > self.max_bytes):
            victim_path = None
            victim = None
            for path, entry in self._entries.items():
                if get_texture_id(entry.texture.tex) not in protected_texture_ids:
                    victim_path = path
                    victim = entry
                    break

            if victim_path is None or victim is None:
                log("[FULL_CACHE][WARN] Cache is over budget but all entries are active")
                break

            self._entries.pop(victim_path)
            self._bytes_used -= victim.bytes_used
            evicted.append(victim.texture)
            log(f"[FULL_CACHE][EVICT] {os.path.basename(victim_path)}")
        return evicted

    def _estimate_bytes(self, texture: TextureInfo) -> int:
        return max(1, int(texture.w)) * max(1, int(texture.h)) * 4
