"""Load the current image plus previous/next neighbor textures."""

from __future__ import annotations

import os
from typing import Any, Callable, Optional

from .. import config as cfg
from ..image_utils import is_heavy_image
from ..logging import log
from ..math_utils import clamp
from ..types import LoadPriority, TextureInfo
from ..view_math import compute_fit_view as compute_fit_view_pure
from ..view_math import sanitize_view as sanitize_view_pure
from ..viewers import get_registry


class CurrentAndNeighborLoader:
    """Coordinates async loading callbacks for current, previous, and next images."""

    def __init__(
        self,
        texture_manager: Any,
        thumbnail_service: Any,
        animated_playback: Any,
        placeholder_factory: Callable[[str], Optional[TextureInfo]],
        now_fn: Callable[[], float],
        large_texture_cache: Any = None,
        animated_content_cache: Any = None,
    ):
        self.texture_manager = texture_manager
        self.thumbnail_service = thumbnail_service
        self.animated_playback = animated_playback
        self.placeholder_factory = placeholder_factory
        self.now = now_fn
        self.large_texture_cache = large_texture_cache
        self.animated_content_cache = animated_content_cache

    def preload(self, state: Any, new_index: int, skip_neighbors: bool = False) -> None:
        n = len(state.current_dir_images)
        if n == 0:
            return

        new_index = clamp(new_index, 0, n - 1)
        current_path = state.current_dir_images[new_index]
        old_index = state.index
        state.index = new_index

        viewer = get_registry().get_viewer(current_path)
        is_heavy = viewer.is_heavy(current_path) if viewer else is_heavy_image(current_path)

        state.load_generation += 1
        generation = state.load_generation

        log(
            f"[PRELOAD] Starting async load for index={new_index} "
            f"path={os.path.basename(current_path)} heavy={is_heavy} "
            f"skip_neighbors={skip_neighbors} gen={generation}"
        )

        current_applied = self._try_apply_animated_cache_hit(state, current_path, new_index, old_index)
        if not current_applied:
            cache_hit = self.large_texture_cache.get(current_path) if is_heavy and self.large_texture_cache else None
            if cache_hit:
                state.loading_current = False
                self._apply_current_texture(
                    state,
                    current_path,
                    cache_hit,
                    None,
                    None,
                    new_index,
                    old_index,
                    source="cache",
                )
                current_applied = True

        if not current_applied:
            state.loading_current = is_heavy
            state.async_loader.submit(
                current_path,
                LoadPriority.CURRENT,
                self._current_loaded_callback(state, new_index, old_index, generation, is_heavy),
            )

        if skip_neighbors:
            log("[PRELOAD] Skipping neighbors/thumbs during animation")
            return

        expected_prev_path = state.current_dir_images[new_index - 1] if new_index - 1 >= 0 else None
        expected_next_path = state.current_dir_images[new_index + 1] if new_index + 1 < n else None
        neighbor_callback = self._neighbor_loaded_callback(state, generation, expected_prev_path, expected_next_path)

        if expected_prev_path:
            state.async_loader.submit(expected_prev_path, LoadPriority.NEIGHBOR, neighbor_callback)
        if expected_next_path:
            state.async_loader.submit(expected_next_path, LoadPriority.NEIGHBOR, neighbor_callback)

        self.thumbnail_service.schedule_around(state, new_index)

    def _current_loaded_callback(self, state: Any, new_index: int, old_index: int, generation: int, is_heavy: bool):
        def on_current_loaded(path: str, loaded, error: Optional[Exception]) -> None:
            if state.load_generation != generation:
                self.texture_manager.cleanup_cpu_data(loaded)
                log(
                    f"[ASYNC][CURRENT] Stale gen={generation} current={state.load_generation}, "
                    f"discarding {os.path.basename(path)}"
                )
                return

            if error:
                self._handle_current_error(state, path, error)
                return

            try:
                viewer, cpu_data = loaded
                is_animated = bool(getattr(viewer, "is_animated", lambda _: False)(cpu_data))
                texture = self.texture_manager.content_to_texture(loaded, path)
                self._apply_current_texture(
                    state,
                    path,
                    texture,
                    viewer,
                    cpu_data,
                    new_index,
                    old_index,
                    source="async",
                )

                if is_animated:
                    if self.animated_content_cache:
                        self.animated_content_cache.put(path, viewer, cpu_data)
                elif is_heavy and self.large_texture_cache:
                    evicted = self.large_texture_cache.put(texture, self._active_texture_ids(state))
                    for evicted_texture in evicted:
                        self.texture_manager.defer_unload(state, evicted_texture)
            except Exception as exc:
                log(f"[ASYNC][CURRENT][ERR] Failed to create texture: {exc!r}")
                state.loading_current = False

        return on_current_loaded

    def _neighbor_loaded_callback(
        self,
        state: Any,
        generation: int,
        expected_prev_path: Optional[str],
        expected_next_path: Optional[str],
    ):
        def on_neighbor_loaded(path: str, loaded, error: Optional[Exception]) -> None:
            if state.load_generation != generation:
                self.texture_manager.cleanup_cpu_data(loaded)
                log(
                    f"[ASYNC][NEIGHBOR] Stale gen={generation} current={state.load_generation}, "
                    f"discarding {os.path.basename(path)}"
                )
                return

            if error:
                log(f"[ASYNC][NEIGHBOR][ERR] {os.path.basename(path)}: {error!r}")
                return

            try:
                tex_info = self.texture_manager.content_to_texture(loaded, path)
                if path == expected_prev_path:
                    if state.cache.prev:
                        self.texture_manager.defer_unload(state, state.cache.prev)
                    state.cache.prev = tex_info
                    log(f"[ASYNC][PREV] Loaded: {os.path.basename(path)}")
                elif path == expected_next_path:
                    if state.cache.next:
                        self.texture_manager.defer_unload(state, state.cache.next)
                    state.cache.next = tex_info
                    log(f"[ASYNC][NEXT] Loaded: {os.path.basename(path)}")
            except Exception as exc:
                log(f"[ASYNC][NEIGHBOR][ERR] Failed to create texture: {exc!r}")

        return on_neighbor_loaded

    def _try_apply_animated_cache_hit(self, state: Any, path: str, new_index: int, old_index: int) -> bool:
        if not self.animated_content_cache:
            return False

        loaded = self.animated_content_cache.get(path)
        if not loaded:
            return False

        try:
            viewer, cpu_data = loaded
            texture = self.texture_manager.content_to_texture(loaded, path)
            state.loading_current = False
            self._apply_current_texture(
                state,
                path,
                texture,
                viewer,
                cpu_data,
                new_index,
                old_index,
                source="animated-cache",
            )
            return True
        except Exception as exc:
            self.texture_manager.cleanup_cpu_data(loaded)
            self.animated_content_cache.remove(path)
            log(f"[ANIM_CACHE][ERR] {os.path.basename(path)} load failed: {exc!r}")
            return False

    def _handle_current_error(self, state: Any, path: str, error: Exception) -> None:
        log(f"[ASYNC][CURRENT][ERR] {os.path.basename(path)}: {error!r}")
        state.loading_current = False
        try:
            if state.cache.curr and not self._is_texture_in_use(state, state.cache.curr):
                self._release_current_texture(state, state.cache.curr)
            placeholder = self.placeholder_factory(path)
            if placeholder:
                state.cache.curr = placeholder
        except Exception:
            pass

    def _apply_current_texture(
        self,
        state: Any,
        path: str,
        texture: TextureInfo,
        viewer: Any,
        cpu_data: Any,
        new_index: int,
        old_index: int,
        source: str,
    ) -> None:
        self.animated_playback.stop(state)
        if state.cache.curr and not self._is_texture_in_use(state, state.cache.curr):
            self._release_current_texture(state, state.cache.curr)

        state.cache.curr = texture.copy_ref()
        if viewer is not None and cpu_data is not None:
            self.animated_playback.start_if_animated(state, viewer, cpu_data)
        state.loading_current = False
        state.last_fit_view = self._compute_fit_view(state, cfg.FIT_DEFAULT_SCALE)

        if path in state.view_memory:
            restored_view = state.view_memory[path]
            state.view = self._sanitize_view(state, restored_view, state.cache.curr)
            log(
                f"[ASYNC][CURRENT] Restored view: scale={state.view.scale:.3f} "
                f"off=({state.view.offx:.1f},{state.view.offy:.1f})"
            )
            self._sync_zoom_state(state)
        else:
            state.view = state.last_fit_view
            state.is_zoomed = False
            state.zoom_state_cycle = 1
            log(
                f"[ASYNC][CURRENT] New view (FIT): scale={state.view.scale:.3f} "
                f"off=({state.view.offx:.1f},{state.view.offy:.1f})"
            )

        tex_id = getattr(state.cache.curr.tex, "id", 0)
        log(f"[ASYNC][CURRENT] Loaded from {source}: {os.path.basename(path)} tex_id={tex_id}")
        self._finish_pending_switch_if_needed(state, new_index, old_index)
        self._start_open_animation_if_needed(state)

    def _release_current_texture(self, state: Any, texture: TextureInfo) -> None:
        if self.large_texture_cache and self.large_texture_cache.contains_texture(texture):
            log(f"[FULL_CACHE][KEEP] {os.path.basename(texture.path)}")
            return
        self.texture_manager.defer_unload(state, texture)

    def _finish_pending_switch_if_needed(self, state: Any, new_index: int, old_index: int) -> None:
        if not state.waiting_for_switch or state.pending_target_index is None:
            return

        log(
            f"[SWITCH_ANIM] About to start: pending_duration={state.pending_switch_duration_ms}ms "
            f"waiting={state.waiting_for_switch} target={state.pending_target_index}"
        )
        direction = 1 if new_index > old_index else -1
        if state.waiting_prev_snapshot:
            state.switch_anim_prev_tex = state.waiting_prev_snapshot
            state.switch_anim_prev_view = state.waiting_prev_view
            state.switch_anim_active = True
            state.switch_anim_t0 = self.now()
            state.switch_anim_direction = direction
            state.switch_anim_duration_ms = state.pending_switch_duration_ms
            log(f"[SWITCH_ANIM] Started after load: actual_duration={state.switch_anim_duration_ms}ms")

        state.waiting_for_switch = False
        state.waiting_prev_snapshot = None
        state.pending_target_index = None
        state.pending_switch_duration_ms = cfg.ANIM_SWITCH_KEYS_MS
        log(f"[SWITCH_ANIM] Reset pending_duration to default: {cfg.ANIM_SWITCH_KEYS_MS}ms")

    def _start_open_animation_if_needed(self, state: Any) -> None:
        if not state.open_anim_active or state.open_anim_t0 != 0.0:
            return

        state.open_anim_t0 = self.now()
        state.bg_current_opacity = 0.0
        state.pending_neighbors_load = True
        state.anim.open_from_view = self._compute_fit_view(state, cfg.FIT_OPEN_SCALE)
        log("[OPEN_ANIM] Started after first image load")

    def _sync_zoom_state(self, state: Any) -> None:
        state.is_zoomed = state.view.scale > state.last_fit_view.scale
        if abs(state.view.scale - 1.0) < 0.01:
            state.zoom_state_cycle = 0
        elif abs(state.view.scale - state.last_fit_view.scale) < 0.01:
            state.zoom_state_cycle = 1
        else:
            state.zoom_state_cycle = 2

    def _is_texture_in_use(self, state: Any, ti: Optional[TextureInfo]) -> bool:
        if not ti:
            return False
        tex = getattr(ti, "tex", None)
        if not tex:
            return False
        for ref in (state.waiting_prev_snapshot, state.switch_anim_prev_tex):
            if ref and getattr(ref, "tex", None) is tex:
                return True
        return False

    def _active_texture_ids(self, state: Any) -> set[int]:
        active = set()
        for texture in (
            getattr(state.cache, "curr", None),
            getattr(state.cache, "prev", None),
            getattr(state.cache, "next", None),
            state.waiting_prev_snapshot,
            state.switch_anim_prev_tex,
        ):
            if texture and getattr(texture, "tex", None):
                tex_id = getattr(texture.tex, "id", 0)
                if tex_id:
                    active.add(tex_id)
        return active

    def _compute_fit_view(self, state: Any, frac: float):
        ti = state.cache.curr
        if not ti:
            from ..types import ViewParams

            return ViewParams()
        return compute_fit_view_pure(ti.w, ti.h, state.screenW, state.screenH, frac)

    def _sanitize_view(self, state: Any, view: Any, ti: TextureInfo):
        return sanitize_view_pure(view, ti.w, ti.h, state.screenW, state.screenH)
