"""Animated content playback lifecycle for the current image."""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..types import TextureInfo


class AnimatedContentPlayback:
    """Starts, advances, and stops playback attached to AppState."""

    def stop(self, state: Any) -> None:
        playback = state.playback
        if not playback:
            return
        playback.cleanup()
        state.playback = None

    def start_if_animated(self, state: Any, viewer: Any, cpu_data: Any) -> None:
        if viewer.is_animated(cpu_data):
            state.playback = viewer.create_playback(cpu_data)

    def replace_for_loaded_content(self, state: Any, viewer: Any, cpu_data: Any) -> None:
        self.stop(state)
        self.start_if_animated(state, viewer, cpu_data)

    def advance(
        self,
        state: Any,
        dt_ms: float,
        on_replace_current_texture: Optional[Callable[[TextureInfo], None]] = None,
    ) -> Optional[TextureInfo]:
        playback = state.playback
        if not playback or not playback.playing:
            return None

        new_texture = playback.advance(dt_ms)
        if new_texture is None:
            return None

        old_texture = state.cache.curr
        if old_texture and on_replace_current_texture:
            on_replace_current_texture(old_texture)
        state.cache.curr = new_texture
        return new_texture
