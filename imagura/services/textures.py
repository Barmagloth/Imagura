"""Main-thread GPU texture ownership helpers."""

from __future__ import annotations

import os
from typing import Any, Optional

from ..logging import log
from ..rl_compat import rl
from ..types import BitmapThumb, TextureInfo


class TextureManager:
    """Owns conversion to GPU textures and deferred unload bookkeeping.

    Worker threads should not touch GPU resources. They return viewer CPU data;
    this service is used from the main thread to upload textures and release
    old ones at predictable points in the frame.
    """

    def content_to_texture(self, loaded: tuple, path: str) -> TextureInfo:
        viewer, cpu_data = loaded
        return viewer.to_texture(cpu_data, path)

    def build_thumbnail(self, loaded: tuple, target_h: int, path: str) -> BitmapThumb:
        viewer, cpu_data = loaded
        return viewer.make_thumbnail(cpu_data, target_h, path)

    def cleanup_cpu_data(self, loaded: Optional[tuple]) -> None:
        if loaded is None:
            return
        viewer, cpu_data = loaded
        viewer.cleanup_cpu_data(cpu_data)

    def defer_unload(self, state: Any, ti: Optional[TextureInfo]) -> None:
        if not ti:
            return
        tex = getattr(ti, "tex", None)
        if not tex:
            return
        tex_id = getattr(tex, "id", 0)
        if tex_id and tex_id > 0:
            state.to_unload.append(tex)
            log(f"[DEFER_UNLOAD] Queued: {os.path.basename(ti.path)} (id={tex_id})")

    def process_deferred_unloads(self, state: Any) -> None:
        while state.to_unload:
            self.unload_texture(state.to_unload.pop())

    def unload_texture(self, tex: Any) -> None:
        try:
            tex_id = getattr(tex, "id", 0)
            if tex_id and tex_id > 0:
                rl.UnloadTexture(tex)
                log(f"[UNLOAD] Texture id={tex_id}")
        except Exception as exc:
            log(f"[UNLOAD][ERR] {exc!r}")
