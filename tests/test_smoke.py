from __future__ import annotations

import os
import json
import sys
import time
import unittest
from collections import OrderedDict, deque
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from imagura import config
from imagura.gallery.behavior import GalleryBehavior
from imagura.image_metadata.exif_cache import ExifMetadataCache
from imagura.image_loading import CurrentAndNeighborLoader
from imagura.image_sorting import resort_preserving_current, sort_image_paths
from imagura.image_utils import list_supported_files
from imagura.playback import AnimatedContentPlayback
from imagura.platform.file_deletion import delete_to_trash
from imagura.platform.file_dialog import _open_image_file_dialog_pywin32, build_image_file_filter
from imagura.services.animated_content_cache import AnimatedContentCache
from imagura.services.large_texture_cache import LargeTextureCache
from imagura.services.loader import AsyncContentLoader
from imagura.services.thumbnails import ThumbnailService
from imagura.state.gallery import GalleryState
from imagura.state.ui import ContextMenuState, ToolbarState
from imagura.transforms import flip_image_file, rotate_image_file
from imagura.types import BitmapThumb, LoadPriority, TextureInfo, ViewParams
from imagura.ui.context_menu import get_context_menu_item_at
from imagura.ui.gallery_sort_control import MENU_ITEM_H, MENU_PADDING, _menu_rect, handle_gallery_sort_input
from imagura.ui.toolbar import get_toolbar_button_at, is_in_toolbar_zone
from imagura.view_math import clamp_pan, compute_fit_view
from imagura.viewers import get_registry
from imagura.zoom import (
    ScaleOverlayController,
    ToggleZoomAnimationController,
    ZoomAnimationController,
    apply_manual_zoom,
    scale_overlay_text,
    zoom_mode_label,
)


def scratch_root() -> Path:
    root = Path(__file__).resolve().parents[1] / ".test_tmp" / f"pid-{os.getpid()}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def scratch_path(name: str) -> Path:
    path = scratch_root() / f"{time.time_ns()}-{name}"
    path.mkdir(parents=True, exist_ok=False)
    return path


class ViewMathSmokeTests(unittest.TestCase):
    def test_compute_fit_view_centers_image(self) -> None:
        view = compute_fit_view(1000, 500, 800, 600, 0.95)

        self.assertLessEqual(view.scale, 0.95)
        self.assertAlmostEqual(view.offx, 20.0)
        self.assertAlmostEqual(view.offy, 110.0)

    def test_clamp_pan_keeps_small_image_centered(self) -> None:
        view = clamp_pan(ViewParams(scale=0.5, offx=-1000, offy=-1000), 200, 100, 800, 600)

        self.assertAlmostEqual(view.offx, 0.0)
        self.assertAlmostEqual(view.offy, 0.0)


class ViewerSmokeTests(unittest.TestCase):
    def test_registry_contains_static_and_animated_formats(self) -> None:
        exts = get_registry().supported_extensions()

        self.assertIn(".png", exts)
        self.assertIn(".jpg", exts)
        self.assertIn(".gif", exts)
        self.assertIn(".webp", exts)

    def test_list_supported_files_uses_registry_extensions(self) -> None:
        root = scratch_path("supported-files")
        (root / "a.png").write_bytes(b"")
        (root / "b.webp").write_bytes(b"")
        (root / "c.txt").write_text("ignored", encoding="utf-8")

        names = [Path(path).name for path in list_supported_files(str(root))]

        self.assertEqual(names, ["a.png", "b.webp"])

    def test_static_viewer_loads_cyrillic_filename(self) -> None:
        root = scratch_path("unicode-static-load")
        image_path = root / "\u041c\u0435\u0442\u0440\u043e.png"
        Image.new("RGB", (3, 2), (20, 40, 60)).save(image_path)

        viewer = get_registry().get_viewer(str(image_path))
        img = viewer.load_cpu(str(image_path))
        try:
            self.assertEqual((img.width, img.height), (3, 2))
        finally:
            viewer.cleanup_cpu_data(img)

    def test_gif_viewer_cache_snapshot_survives_runtime_cleanup(self) -> None:
        root = scratch_path("gif-cache-snapshot")
        gif_path = root / "animated.gif"
        frames = [
            Image.new("RGBA", (4, 4), (255, 0, 0, 255)),
            Image.new("RGBA", (4, 4), (0, 255, 0, 255)),
        ]
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=50,
            loop=0,
        )

        viewer = get_registry().get_viewer(str(gif_path))
        cpu_data = viewer.load_cpu(str(gif_path))
        cached_cpu = viewer.clone_cpu_data_for_cache(cpu_data)
        viewer.cleanup_cpu_data(cpu_data)

        runtime_cpu = viewer.clone_cached_cpu_data(cached_cpu)
        try:
            self.assertTrue(viewer.is_animated(runtime_cpu))
            self.assertEqual((runtime_cpu.width, runtime_cpu.height), (4, 4))
            self.assertEqual(len(cached_cpu.frames_rgba), 2)
            self.assertEqual(len(runtime_cpu.frames_rgba), 2)
            self.assertIsNot(cached_cpu.frames_rgba, runtime_cpu.frames_rgba)
        finally:
            viewer.cleanup_cpu_data(runtime_cpu)
            viewer.cleanup_cached_cpu_data(cached_cpu)


class ImageSortingSmokeTests(unittest.TestCase):
    def test_name_sort_is_natural_and_reversible(self) -> None:
        root = scratch_path("sort-name")
        paths = []
        for name in ("img10.png", "img2.png", "img1.png"):
            path = root / name
            path.write_bytes(b"x")
            paths.append(str(path))

        ascending = [Path(path).name for path in sort_image_paths(paths, "name", False)]
        descending = [Path(path).name for path in sort_image_paths(paths, "name", True)]

        self.assertEqual(ascending, ["img1.png", "img2.png", "img10.png"])
        self.assertEqual(descending, ["img10.png", "img2.png", "img1.png"])

    def test_size_sort_preserves_name_tiebreaker(self) -> None:
        root = scratch_path("sort-size")
        first = root / "b.png"
        second = root / "a.png"
        third = root / "c.png"
        first.write_bytes(b"xx")
        second.write_bytes(b"xx")
        third.write_bytes(b"x")

        names = [Path(path).name for path in sort_image_paths([str(first), str(second), str(third)], "size", False)]

        self.assertEqual(names, ["c.png", "a.png", "b.png"])

    def test_resort_preserves_current_path(self) -> None:
        root = scratch_path("sort-current")
        first = root / "b.png"
        second = root / "a.png"
        first.write_bytes(b"x")
        second.write_bytes(b"x")

        sorted_paths, index = resort_preserving_current([str(first), str(second)], str(first), "name", False)

        self.assertEqual([Path(path).name for path in sorted_paths], ["a.png", "b.png"])
        self.assertEqual(index, 1)


class LoaderSmokeTests(unittest.TestCase):
    def test_async_loader_delivers_result_on_poll(self) -> None:
        loader = AsyncContentLoader(lambda path: path.upper(), workers=1)
        events = []

        try:
            loader.submit(
                "abc",
                LoadPriority.CURRENT,
                lambda path, result, error: events.append((path, result, error)),
            )

            deadline = time.monotonic() + 2.0
            while not events and time.monotonic() < deadline:
                loader.poll_ui_events()
                time.sleep(0.01)
        finally:
            loader.shutdown()

        self.assertEqual(events, [("abc", "ABC", None)])

    def test_async_loader_delivers_errors_on_poll(self) -> None:
        def fail(_: str) -> object:
            raise RuntimeError("boom")

        loader = AsyncContentLoader(fail, workers=1)
        events = []

        try:
            loader.submit(
                "abc",
                LoadPriority.CURRENT,
                lambda path, result, error: events.append((path, result, error)),
            )

            deadline = time.monotonic() + 2.0
            while not events and time.monotonic() < deadline:
                loader.poll_ui_events()
                time.sleep(0.01)
        finally:
            loader.shutdown()

        self.assertEqual(events[0][0], "abc")
        self.assertIsNone(events[0][1])
        self.assertIsInstance(events[0][2], RuntimeError)


class CurrentAndNeighborLoaderSmokeTests(unittest.TestCase):
    def _state(self):
        state = SimpleNamespace()
        state.current_dir_images = ["a.png", "b.png", "c.png"]
        state.index = 0
        state.load_generation = 0
        state.async_loader = SimpleNamespace(submitted=[])
        state.async_loader.submit = lambda path, priority, callback: state.async_loader.submitted.append(
            (path, priority, callback)
        )
        state.thumb_queue = deque()
        state.thumb_cache = OrderedDict()
        state.cache = SimpleNamespace(curr=None, prev=None, next=None)
        state.waiting_prev_snapshot = None
        state.switch_anim_prev_tex = None
        state.loading_current = False
        state.view_memory = {}
        state.screenW = 800
        state.screenH = 600
        state.last_fit_view = ViewParams()
        state.view = ViewParams()
        state.is_zoomed = False
        state.zoom_state_cycle = 0
        state.waiting_for_switch = False
        state.pending_target_index = None
        state.open_anim_active = False
        state.open_anim_t0 = 0.0
        state.anim = SimpleNamespace(open_from_view=ViewParams())
        return state

    def _loader(self):
        class FakeTextureManager:
            def __init__(self) -> None:
                self.cleaned = []
                self.deferred = []
                self.converted = []

            def cleanup_cpu_data(self, loaded) -> None:
                self.cleaned.append(loaded)

            def defer_unload(self, state, texture) -> None:
                self.deferred.append(texture)

            def content_to_texture(self, loaded, path):
                self.converted.append((loaded, path))
                return TextureInfo(tex=f"tex:{path}", w=100, h=50, path=path)

        class FakeThumbnailService:
            def __init__(self) -> None:
                self.scheduled = []

            def schedule_around(self, state, around_index) -> None:
                self.scheduled.append(around_index)

        class FakeAnimatedPlayback:
            def __init__(self) -> None:
                self.stopped = 0
                self.started = []

            def stop(self, state) -> None:
                self.stopped += 1

            def start_if_animated(self, state, viewer, cpu_data) -> None:
                self.started.append((viewer, cpu_data))

        textures = FakeTextureManager()
        thumbs = FakeThumbnailService()
        playback = FakeAnimatedPlayback()
        loader = CurrentAndNeighborLoader(textures, thumbs, playback, lambda path: None, lambda: 1.0)
        return loader, textures, thumbs, playback

    def test_preload_submits_current_neighbors_and_thumbs(self) -> None:
        state = self._state()
        loader, _, thumbs, _ = self._loader()

        loader.preload(state, 1, skip_neighbors=False)

        submitted = [(path, priority) for path, priority, _ in state.async_loader.submitted]
        self.assertEqual(
            submitted,
            [
                ("b.png", LoadPriority.CURRENT),
                ("a.png", LoadPriority.NEIGHBOR),
                ("c.png", LoadPriority.NEIGHBOR),
            ],
        )
        self.assertEqual(state.index, 1)
        self.assertEqual(state.load_generation, 1)
        self.assertEqual(thumbs.scheduled, [1])

    def test_current_and_neighbor_callbacks_update_cache(self) -> None:
        state = self._state()
        loader, _, _, playback = self._loader()

        loader.preload(state, 1, skip_neighbors=False)
        current_callback = state.async_loader.submitted[0][2]
        prev_callback = state.async_loader.submitted[1][2]
        next_callback = state.async_loader.submitted[2][2]

        current_callback("b.png", ("viewer", "current-cpu"), None)
        prev_callback("a.png", ("viewer", "prev-cpu"), None)
        next_callback("c.png", ("viewer", "next-cpu"), None)

        self.assertEqual(state.cache.curr.path, "b.png")
        self.assertEqual(state.cache.prev.path, "a.png")
        self.assertEqual(state.cache.next.path, "c.png")
        self.assertFalse(state.loading_current)
        self.assertGreater(state.last_fit_view.scale, 0.0)
        self.assertEqual(playback.stopped, 1)
        self.assertEqual(playback.started, [("viewer", "current-cpu")])

    def test_heavy_cache_hit_sets_current_without_async_current_submit(self) -> None:
        state = self._state()
        root = scratch_path("large-cache-hit")
        prev_path = root / "a.png"
        current_path = root / "b.png"
        next_path = root / "c.png"
        prev_path.write_bytes(b"prev")
        current_path.write_bytes(b"0" * ((config.HEAVY_FILE_SIZE_MB * 1024 * 1024) + 1))
        next_path.write_bytes(b"next")
        state.current_dir_images = [str(prev_path), str(current_path), str(next_path)]

        cache = LargeTextureCache(max_mb=1, max_items=2)
        cache.put(TextureInfo(tex=SimpleNamespace(id=10), w=64, h=64, path=str(current_path)))
        loader, _, thumbs, playback = self._loader()
        loader.large_texture_cache = cache

        loader.preload(state, 1, skip_neighbors=False)

        submitted = [(path, priority) for path, priority, _ in state.async_loader.submitted]
        self.assertEqual(
            submitted,
            [(str(prev_path), LoadPriority.NEIGHBOR), (str(next_path), LoadPriority.NEIGHBOR)],
        )
        self.assertEqual(state.cache.curr.path, str(current_path))
        self.assertFalse(state.loading_current)
        self.assertEqual(playback.stopped, 1)
        self.assertEqual(thumbs.scheduled, [1])

    def test_animated_cache_hit_sets_current_without_async_current_submit(self) -> None:
        state = self._state()
        state.current_dir_images = ["a.gif", "b.gif", "c.gif"]

        class FakeAnimatedCache:
            def __init__(self) -> None:
                self.requested = []

            def get(self, path):
                self.requested.append(path)
                if path == "b.gif":
                    return "gif-viewer", "gif-cpu"
                return None

            def remove(self, path) -> bool:
                return False

        loader, textures, thumbs, playback = self._loader()
        animated_cache = FakeAnimatedCache()
        loader.animated_content_cache = animated_cache

        loader.preload(state, 1, skip_neighbors=False)

        submitted = [(path, priority) for path, priority, _ in state.async_loader.submitted]
        self.assertEqual(submitted, [("a.gif", LoadPriority.NEIGHBOR), ("c.gif", LoadPriority.NEIGHBOR)])
        self.assertEqual(animated_cache.requested, ["b.gif"])
        self.assertEqual(textures.converted, [(("gif-viewer", "gif-cpu"), "b.gif")])
        self.assertEqual(state.cache.curr.path, "b.gif")
        self.assertFalse(state.loading_current)
        self.assertEqual(playback.started, [("gif-viewer", "gif-cpu")])
        self.assertEqual(thumbs.scheduled, [1])

    def test_animated_current_callback_populates_animated_cache(self) -> None:
        state = self._state()

        class FakeViewer:
            def is_animated(self, cpu_data) -> bool:
                return cpu_data == "animated-cpu"

        class FakeAnimatedCache:
            def __init__(self) -> None:
                self.puts = []

            def get(self, path):
                return None

            def put(self, path, viewer, cpu_data) -> None:
                self.puts.append((path, viewer, cpu_data))

        viewer = FakeViewer()
        loader, _, _, _ = self._loader()
        animated_cache = FakeAnimatedCache()
        loader.animated_content_cache = animated_cache

        loader.preload(state, 1, skip_neighbors=True)
        current_callback = state.async_loader.submitted[0][2]
        current_callback("b.png", (viewer, "animated-cpu"), None)

        self.assertEqual(animated_cache.puts, [("b.png", viewer, "animated-cpu")])


class LargeTextureCacheSmokeTests(unittest.TestCase):
    def _texture(self, path: str, tex_id: int, size: int = 128) -> TextureInfo:
        return TextureInfo(tex=SimpleNamespace(id=tex_id), w=size, h=size, path=path)

    def test_fifo_eviction_by_item_limit(self) -> None:
        cache = LargeTextureCache(max_mb=10, max_items=2)

        self.assertEqual(cache.put(self._texture("a.png", 1)), [])
        self.assertEqual(cache.put(self._texture("b.png", 2)), [])
        evicted = cache.put(self._texture("c.png", 3))

        self.assertEqual([texture.path for texture in evicted], ["a.png"])
        self.assertEqual(cache.cached_paths(), ["b.png", "c.png"])

    def test_get_does_not_refresh_fifo_order(self) -> None:
        cache = LargeTextureCache(max_mb=10, max_items=2)
        cache.put(self._texture("a.png", 1))
        cache.put(self._texture("b.png", 2))

        self.assertEqual(cache.get("a.png").path, "a.png")
        evicted = cache.put(self._texture("c.png", 3))

        self.assertEqual([texture.path for texture in evicted], ["a.png"])
        self.assertEqual(cache.cached_paths(), ["b.png", "c.png"])

    def test_oversized_texture_is_not_cached(self) -> None:
        cache = LargeTextureCache(max_mb=1, max_items=2)

        evicted = cache.put(self._texture("too-big.png", 1, size=1024))

        self.assertEqual(evicted, [])
        self.assertEqual(cache.cached_paths(), [])


class AnimatedContentCacheSmokeTests(unittest.TestCase):
    class FakeViewer:
        def __init__(self) -> None:
            self.cleaned = []

        def estimate_cache_bytes(self, cpu_data) -> int:
            return cpu_data["bytes"]

        def clone_cpu_data_for_cache(self, cpu_data):
            return {
                "bytes": cpu_data["bytes"],
                "frames": list(cpu_data["frames"]),
                "cached": True,
            }

        def clone_cached_cpu_data(self, cpu_data):
            return {
                "bytes": cpu_data["bytes"],
                "frames": list(cpu_data["frames"]),
                "runtime": True,
            }

        def cleanup_cached_cpu_data(self, cpu_data) -> None:
            self.cleaned.append(cpu_data)
            cpu_data["frames"] = []

    def test_get_returns_runtime_clone_without_refreshing_fifo_order(self) -> None:
        viewer = self.FakeViewer()
        cache = AnimatedContentCache(max_mb=1, max_items=2)

        cache.put("a.gif", viewer, {"bytes": 16, "frames": [b"a"]})
        cache.put("b.gif", viewer, {"bytes": 16, "frames": [b"b"]})
        hit_viewer, hit_cpu = cache.get("a.gif")
        cache.put("c.gif", viewer, {"bytes": 16, "frames": [b"c"]})

        self.assertIs(hit_viewer, viewer)
        self.assertEqual(hit_cpu, {"bytes": 16, "frames": [b"a"], "runtime": True})
        self.assertEqual(cache.cached_paths(), ["b.gif", "c.gif"])

    def test_cache_skips_oversized_decoded_content(self) -> None:
        viewer = self.FakeViewer()
        cache = AnimatedContentCache(max_mb=1, max_items=2)

        cache.put("huge.gif", viewer, {"bytes": (2 * 1024 * 1024), "frames": [b"x"]})

        self.assertEqual(cache.cached_paths(), [])


class ExifMetadataCacheSmokeTests(unittest.TestCase):
    def test_cache_limit_evicts_oldest_path(self) -> None:
        root = scratch_path("metadata-cache")
        first = root / "first.png"
        second = root / "second.png"
        Image.new("RGB", (2, 2), (255, 0, 0)).save(first)
        Image.new("RGB", (2, 2), (0, 255, 0)).save(second)

        cache = ExifMetadataCache(limit=1)

        self.assertEqual(cache.get(str(first)), {})
        self.assertEqual(cache.get(str(second)), {})
        self.assertEqual(cache.cached_paths(), [str(second)])


class ThumbnailSmokeTests(unittest.TestCase):
    def test_thumbnail_service_schedules_and_processes_budgeted_items(self) -> None:
        class FakeLoader:
            def __init__(self) -> None:
                self.submitted = []

            def submit(self, path, priority, callback) -> None:
                self.submitted.append((path, priority, callback))

        class FakeTextureManager:
            def build_thumbnail(self, loaded, target_h, path):
                return BitmapThumb(texture=f"tex:{path}", size=(target_h, target_h), src_path=path, ready=True)

            def unload_texture(self, tex) -> None:
                pass

        state = type("State", (), {})()
        state.current_dir_images = [f"img-{idx}.png" for idx in range(5)]
        state.thumb_queue = __import__("collections").deque()
        state.thumb_cache = __import__("collections").OrderedDict()
        state.async_loader = FakeLoader()
        state.screenH = 1000

        old_span = config.THUMB_PRELOAD_SPAN
        old_budget = config.THUMB_BUILD_BUDGET_PER_FRAME
        try:
            config.THUMB_PRELOAD_SPAN = 1
            config.THUMB_BUILD_BUDGET_PER_FRAME = 1
            service = ThumbnailService(FakeTextureManager())

            service.schedule_around(state, 2)
            self.assertEqual(list(state.thumb_queue), ["img-1.png", "img-2.png", "img-3.png"])

            service.process_queue(state)
            self.assertEqual(len(state.async_loader.submitted), 1)
            self.assertEqual(state.async_loader.submitted[0][0], "img-1.png")
            self.assertEqual(state.async_loader.submitted[0][1], LoadPriority.GALLERY)
            self.assertIn("img-1.png", state.thumb_cache)
        finally:
            config.THUMB_PRELOAD_SPAN = old_span
            config.THUMB_BUILD_BUDGET_PER_FRAME = old_budget

    def test_thumbnail_service_evicts_via_texture_manager(self) -> None:
        class FakeTextureManager:
            def __init__(self) -> None:
                self.unloaded = []

            def unload_texture(self, tex) -> None:
                self.unloaded.append(tex)

        state = type("State", (), {})()
        state.thumb_cache = __import__("collections").OrderedDict(
            [
                ("a", BitmapThumb(texture="tex-a", size=(1, 1), src_path="a", ready=True)),
                ("b", BitmapThumb(texture="tex-b", size=(1, 1), src_path="b", ready=True)),
            ]
        )

        old_limit = config.THUMB_CACHE_LIMIT
        manager = FakeTextureManager()
        try:
            config.THUMB_CACHE_LIMIT = 1
            ThumbnailService(manager).enforce_cache_limit(state)
            self.assertEqual(manager.unloaded, ["tex-a"])
            self.assertEqual(list(state.thumb_cache.keys()), ["b"])
        finally:
            config.THUMB_CACHE_LIMIT = old_limit


class GalleryBehaviorSmokeTests(unittest.TestCase):
    def _state(self):
        state = type("State", (), {})()
        state.current_dir_images = ["a.png", "b.png", "c.png", "d.png", "e.png"]
        state.index = 0
        state.gallery_target_index = None
        state.gallery_center_index = 0.0
        state.gallery_last_wheel_time = 0.0
        state.switch_anim_active = False
        state.waiting_for_switch = False
        state.loading_current = False
        state.screenH = 1000
        state.gallery_y = 1000
        state.gallery_visible = False
        return state

    def test_reconcile_target_skips_animation_for_long_jumps(self) -> None:
        state = self._state()
        state.gallery_target_index = 4
        switches = []

        old_threshold = config.RAPID_NAV_SKIP_THRESHOLD
        try:
            config.RAPID_NAV_SKIP_THRESHOLD = 2
            GalleryBehavior().reconcile_target(
                state,
                now_s=1.0,
                switch_callback=lambda idx, animate, duration: switches.append((idx, animate, duration)),
            )
        finally:
            config.RAPID_NAV_SKIP_THRESHOLD = old_threshold

        self.assertEqual(switches, [(4, False, config.ANIM_SWITCH_KEYS_MS)])
        self.assertIsNone(state.gallery_target_index)

    def test_update_visibility_slides_toward_visible_position(self) -> None:
        state = self._state()
        behavior = GalleryBehavior()

        behavior.update_visibility_and_slide(state, mouse_y=990, frame_dt=0.016, gallery_height=100)

        self.assertTrue(state.gallery_visible)
        self.assertLess(state.gallery_y, 1000)
        self.assertGreaterEqual(state.gallery_y, 900)

    def test_sort_menu_can_force_gallery_visible_outside_panel(self) -> None:
        state = self._state()
        behavior = GalleryBehavior()

        behavior.update_visibility_and_slide(
            state,
            mouse_y=100,
            frame_dt=0.016,
            gallery_height=100,
            force_visible=True,
        )

        self.assertTrue(state.gallery_visible)
        self.assertLess(state.gallery_y, 1000)

    def test_update_scroll_moves_toward_target(self) -> None:
        state = self._state()
        state.gallery_target_index = 4

        GalleryBehavior().update_scroll(state, frame_dt=0.016)

        self.assertGreater(state.gallery_center_index, 0.0)
        self.assertLess(state.gallery_center_index, 4.0)


class UIControlsSmokeTests(unittest.TestCase):
    def test_toolbar_hit_testing_uses_visible_button_centers(self) -> None:
        state = SimpleNamespace(screenW=1000, screenH=800, ui=SimpleNamespace(toolbar=ToolbarState()))
        state.ui.toolbar.alpha = 1.0

        n_buttons = len(state.ui.toolbar.buttons)
        n_separators = sum(1 for btn in state.ui.toolbar.buttons if btn.separator_after)
        total_width = (
            n_buttons * (config.TOOLBAR_BTN_RADIUS * 2)
            + (n_buttons - 1) * config.TOOLBAR_BTN_SPACING
            + n_separators * config.TOOLBAR_BTN_SPACING
        )
        first_x = (state.screenW - total_width) // 2 + config.TOOLBAR_BTN_RADIUS
        y = config.TOOLBAR_HEIGHT // 2

        self.assertTrue(is_in_toolbar_zone(state, first_x, y))
        self.assertFalse(is_in_toolbar_zone(state, first_x, state.screenH))
        self.assertEqual(get_toolbar_button_at(state, first_x, y), 0)
        self.assertEqual(get_toolbar_button_at(state, 0, state.screenH), -1)

    def test_context_menu_hit_testing_clamps_to_screen(self) -> None:
        state = SimpleNamespace(screenW=200, screenH=160, ui=SimpleNamespace(context_menu=ContextMenuState()))
        state.ui.context_menu.show(190, 150)

        menu_x = max(5, min(190, state.screenW - config.MENU_ITEM_WIDTH - 5))
        menu_y = max(5, min(150, state.screenH - config.MENU_ITEM_HEIGHT - config.MENU_PADDING * 2 - 5))

        self.assertEqual(get_context_menu_item_at(state, menu_x + 10, menu_y + config.MENU_PADDING + 1), 0)
        self.assertEqual(get_context_menu_item_at(state, 1, 1), -1)

    def test_gallery_sort_menu_click_works_above_gallery_panel(self) -> None:
        state = SimpleNamespace(screenW=1000, screenH=800, gallery=GalleryState(), gallery_y=700)
        state.gallery.sort_menu_open = True
        gallery_height = 100
        menu_x, menu_y, _, _ = _menu_rect(state, gallery_height)

        result = handle_gallery_sort_input(
            state,
            menu_x + 20,
            menu_y + MENU_PADDING + MENU_ITEM_H + 1,
            True,
            gallery_height,
        )

        self.assertTrue(result.consumed_click)
        self.assertTrue(result.changed)
        self.assertEqual(state.gallery.sort_key, "modified")
        self.assertFalse(state.gallery.sort_menu_open)


class AnimatedPlaybackSmokeTests(unittest.TestCase):
    def test_stop_cleans_current_playback(self) -> None:
        class FakePlayback:
            def __init__(self) -> None:
                self.cleaned = False

            def cleanup(self) -> None:
                self.cleaned = True

        playback = FakePlayback()
        state = SimpleNamespace(playback=playback)

        AnimatedContentPlayback().stop(state)

        self.assertTrue(playback.cleaned)
        self.assertIsNone(state.playback)

    def test_start_if_animated_uses_viewer_factory(self) -> None:
        class FakeViewer:
            def is_animated(self, cpu_data) -> bool:
                return cpu_data == "animated"

            def create_playback(self, cpu_data):
                return f"playback:{cpu_data}"

        state = SimpleNamespace(playback=None)
        manager = AnimatedContentPlayback()

        manager.start_if_animated(state, FakeViewer(), "still")
        self.assertIsNone(state.playback)

        manager.start_if_animated(state, FakeViewer(), "animated")
        self.assertEqual(state.playback, "playback:animated")

    def test_advance_replaces_texture_and_reports_old_texture(self) -> None:
        new_tex = TextureInfo(tex="new", w=20, h=20, path="new.png")
        old_tex = TextureInfo(tex="old", w=10, h=10, path="old.png")

        class FakePlayback:
            playing = True

            def advance(self, dt_ms: float):
                self.dt_ms = dt_ms
                return new_tex

        playback = FakePlayback()
        state = SimpleNamespace(playback=playback, cache=SimpleNamespace(curr=old_tex))
        replaced = []

        result = AnimatedContentPlayback().advance(state, 16.0, replaced.append)

        self.assertIs(result, new_tex)
        self.assertIs(state.cache.curr, new_tex)
        self.assertEqual(replaced, [old_tex])
        self.assertEqual(playback.dt_ms, 16.0)


class TransformSmokeTests(unittest.TestCase):
    def test_animated_gif_transform_is_rejected(self) -> None:
        root = scratch_path("animated-transform")
        gif_path = root / "animated.gif"
        frames = [
            Image.new("RGBA", (4, 4), (255, 0, 0, 255)),
            Image.new("RGBA", (4, 4), (0, 255, 0, 255)),
        ]
        frames[0].save(
            gif_path,
            save_all=True,
            append_images=frames[1:],
            duration=50,
            loop=0,
        )

        self.assertFalse(rotate_image_file(str(gif_path), clockwise=True))
        self.assertFalse(flip_image_file(str(gif_path), horizontal=True))

        with Image.open(gif_path) as img:
            self.assertTrue(getattr(img, "is_animated", False))
            self.assertEqual(getattr(img, "n_frames", 1), 2)


class FileDeletionSmokeTests(unittest.TestCase):
    def test_non_windows_trash_path_is_non_destructive(self) -> None:
        root = scratch_path("trash-non-windows")
        target = root / "keep.png"
        target.write_bytes(b"keep")

        self.assertFalse(delete_to_trash(str(target), platform_name="linux"))
        self.assertTrue(target.exists())


class FileDialogSmokeTests(unittest.TestCase):
    def test_image_filter_contains_registered_formats_and_double_null(self) -> None:
        filter_text = build_image_file_filter()

        self.assertIn("Images\0", filter_text)
        self.assertIn("*.png", filter_text)
        self.assertIn("*.gif", filter_text)
        self.assertTrue(filter_text.endswith("\0\0"))

    def test_pywin32_dialog_path_returns_selected_file_without_ctypes(self) -> None:
        root = scratch_path("dialog-pywin32")
        selected = str(root / "picked.png")
        calls = []

        def fake_get_open_file_name_w(**kwargs):
            calls.append(kwargs)
            return selected, "", kwargs["Flags"]

        fake_win32gui = SimpleNamespace(GetOpenFileNameW=fake_get_open_file_name_w)
        fake_win32con = SimpleNamespace(
            OFN_EXPLORER=0x00080000,
            OFN_FILEMUSTEXIST=0x00001000,
            OFN_PATHMUSTEXIST=0x00000800,
            OFN_NOCHANGEDIR=0x00000008,
            OFN_HIDEREADONLY=0x00000004,
        )

        with patch.dict(
            sys.modules,
            {
                "pywintypes": SimpleNamespace(error=Exception),
                "win32con": fake_win32con,
                "win32gui": fake_win32gui,
            },
        ):
            self.assertEqual(_open_image_file_dialog_pywin32(str(root)), selected)

        self.assertEqual(calls[0]["InitialDir"], str(root))
        self.assertEqual(calls[0]["Title"], "Open image")
        self.assertIn("*.png", calls[0]["Filter"])


class ConfigSmokeTests(unittest.TestCase):
    def test_animation_limits_are_positive(self) -> None:
        self.assertGreater(config.MAX_ANIM_FRAMES, 0)
        self.assertGreater(config.MAX_ANIM_MEMORY_MB, 0)
        self.assertGreater(config.ANIMATED_CONTENT_CACHE_MAX_MB, 0)
        self.assertGreater(config.ANIMATED_CONTENT_CACHE_MAX_ITEMS, 0)
        self.assertIn(config.DEFAULT_GALLERY_SORT_KEY, {"name", "modified", "created", "size", "type", "date_taken"})


class UserSettingsSmokeTests(unittest.TestCase):
    def test_save_config_value_writes_user_settings_and_updates_runtime(self) -> None:
        import imagura2

        root = scratch_path("user-settings")
        settings_path = root / "settings.json"
        old_config_value = config.TARGET_FPS
        old_global_value = imagura2.TARGET_FPS

        try:
            with patch.dict(os.environ, {"IMAGURA_USER_SETTINGS_PATH": str(settings_path)}):
                self.assertTrue(imagura2.save_config_value("TARGET_FPS", 99, int, None))

                data = json.loads(settings_path.read_text(encoding="utf-8"))
                self.assertEqual(data["TARGET_FPS"], 99)
                self.assertEqual(config.TARGET_FPS, 99)
                self.assertEqual(imagura2.TARGET_FPS, 99)
        finally:
            config.TARGET_FPS = old_config_value
            imagura2.TARGET_FPS = old_global_value

    def test_apply_saved_settings_loads_user_settings_into_runtime(self) -> None:
        import imagura2

        root = scratch_path("user-settings-load")
        settings_path = root / "settings.json"
        settings_path.write_text(json.dumps({"TARGET_FPS": 88}), encoding="utf-8")
        old_config_value = config.TARGET_FPS
        old_global_value = imagura2.TARGET_FPS

        try:
            with patch.dict(os.environ, {"IMAGURA_USER_SETTINGS_PATH": str(settings_path)}):
                imagura2.apply_saved_settings()

                self.assertEqual(config.TARGET_FPS, 88)
                self.assertEqual(imagura2.TARGET_FPS, 88)
        finally:
            config.TARGET_FPS = old_config_value
            imagura2.TARGET_FPS = old_global_value


class WindowFlagSmokeTests(unittest.TestCase):
    def test_fullscreen_flags_request_transparent_framebuffer(self) -> None:
        import imagura2

        transparent_flag = getattr(imagura2.rl, "FLAG_WINDOW_TRANSPARENT", 0)
        if transparent_flag:
            self.assertTrue(imagura2._fullscreen_window_flags() & transparent_flag)


class ScaleOverlaySmokeTests(unittest.TestCase):
    def test_zoom_mode_labels_match_cycle_states(self) -> None:
        from imagura.i18n import set_language
        set_language("en")
        self.assertEqual(zoom_mode_label(0), "1:1")
        self.assertEqual(zoom_mode_label(1), "Fit")
        self.assertEqual(zoom_mode_label(2), "Custom")

    def test_scale_overlay_text_uses_optional_mode_label(self) -> None:
        from imagura.i18n import set_language
        set_language("en")
        self.assertEqual(scale_overlay_text(1.25), "125%")
        self.assertEqual(scale_overlay_text(1.0, "real"), "Real (100%)")
        self.assertEqual(scale_overlay_text(0.5, "fit"), "Fit (50%)")
        self.assertEqual(scale_overlay_text(2.0, "custom"), "Custom (200%)")

    def test_controller_trigger_and_fade(self) -> None:
        now_value = {"value": 10.0}
        controller = ScaleOverlayController(lambda: now_value["value"], enabled_fn=lambda: True)
        state = SimpleNamespace(
            ui=SimpleNamespace(
                scale_overlay_mode="",
                scale_overlay_alpha=0.0,
                scale_last_change_time=0.0,
            )
        )

        self.assertTrue(controller.trigger(state, "fit"))
        self.assertEqual(state.ui.scale_overlay_mode, "fit")
        self.assertEqual(state.ui.scale_overlay_alpha, 1.0)
        self.assertEqual(state.ui.scale_last_change_time, 10.0)

        now_value["value"] = 10.5
        controller.update(state, frame_dt=0.25)
        self.assertEqual(state.ui.scale_overlay_alpha, 1.0)

        now_value["value"] = 11.1
        controller.update(state, frame_dt=0.25)
        self.assertEqual(state.ui.scale_overlay_alpha, 0.5)

    def test_controller_respects_disabled_overlay(self) -> None:
        controller = ScaleOverlayController(lambda: 1.0, enabled_fn=lambda: False)
        state = SimpleNamespace(
            ui=SimpleNamespace(
                scale_overlay_mode="",
                scale_overlay_alpha=0.0,
                scale_last_change_time=0.0,
            )
        )

        self.assertFalse(controller.trigger(state, "fit"))
        self.assertEqual(state.ui.scale_overlay_alpha, 0.0)


class ZoomAnimationSmokeTests(unittest.TestCase):
    def test_zoom_animation_start_and_complete_without_texture(self) -> None:
        now_value = {"value": 5.0}
        controller = ZoomAnimationController(lambda: now_value["value"])
        state = SimpleNamespace(
            view=ViewParams(scale=1.0, offx=10.0, offy=20.0),
            zoom_anim_active=False,
            zoom_anim_t0=0.0,
            zoom_anim_from=ViewParams(),
            zoom_anim_to=ViewParams(),
            cache=SimpleNamespace(curr=None),
            screenW=800,
            screenH=600,
        )
        target = ViewParams(scale=2.0, offx=30.0, offy=40.0)

        controller.start(state, target)
        self.assertTrue(state.zoom_anim_active)
        self.assertEqual(state.zoom_anim_t0, 5.0)
        self.assertEqual(state.zoom_anim_from, ViewParams(scale=1.0, offx=10.0, offy=20.0))

        now_value["value"] = 5.2
        controller.update(state, duration_ms=100)
        self.assertFalse(state.zoom_anim_active)
        self.assertEqual(state.view, target)

    def test_toggle_zoom_uses_saved_custom_view_and_saves_on_finish(self) -> None:
        now_value = {"value": 10.0}
        controller = ToggleZoomAnimationController(lambda: now_value["value"])
        custom = ViewParams(scale=2.0, offx=-120.0, offy=-80.0)
        state = SimpleNamespace(
            toggle_zoom_active=False,
            toggle_zoom_t0=0.0,
            toggle_zoom_from=ViewParams(),
            toggle_zoom_to=ViewParams(),
            toggle_zoom_target_state=0,
            view=ViewParams(scale=1.0, offx=0.0, offy=0.0),
            last_fit_view=ViewParams(scale=0.5, offx=10.0, offy=20.0),
            zoom_state_cycle=1,
            is_zoomed=False,
            cache=SimpleNamespace(curr=TextureInfo(tex=SimpleNamespace(id=1), w=2000, h=1000, path="x.png")),
            screenW=800,
            screenH=600,
            current_dir_images=["x.png"],
            index=0,
            user_zoom_memory={"x.png": custom},
        )
        overlays = []
        saved = []

        controller.start(state, lambda st, mode: overlays.append(mode))

        self.assertTrue(state.toggle_zoom_active)
        self.assertEqual(state.toggle_zoom_target_state, 2)
        self.assertEqual(state.toggle_zoom_to, custom)
        self.assertEqual(overlays, ["custom"])

        now_value["value"] = 10.2
        controller.update(state, duration_ms=100, save_view=lambda st, path, view: saved.append((path, view.copy())))

        self.assertFalse(state.toggle_zoom_active)
        self.assertEqual(state.zoom_state_cycle, 2)
        self.assertTrue(state.is_zoomed)
        self.assertEqual(saved[0][0], "x.png")
        self.assertEqual(state.user_zoom_memory["x.png"], state.view)


class ManualZoomSmokeTests(unittest.TestCase):
    def _state(self):
        return SimpleNamespace(
            view=ViewParams(scale=1.0, offx=0.0, offy=0.0),
            last_fit_view=ViewParams(scale=0.5, offx=10.0, offy=20.0),
            is_zoomed=False,
            zoom_state_cycle=1,
            cache=SimpleNamespace(curr=TextureInfo(tex=SimpleNamespace(id=1), w=1000, h=500, path="x.png")),
            screenW=800,
            screenH=600,
            current_dir_images=["x.png"],
            index=0,
            user_zoom_memory={},
        )

    def test_apply_manual_zoom_starts_animation_and_saves_custom_view(self) -> None:
        state = self._state()
        started = []
        overlays = []
        saved = []

        applied = apply_manual_zoom(
            state,
            scale_multiplier=1.5,
            anchor=(400, 300),
            max_zoom=4.0,
            start_zoom_animation=lambda st, view: started.append(view.copy()),
            trigger_scale_overlay=lambda st: overlays.append(True),
            save_view_for_path=lambda st, path, view: saved.append((path, view.copy())),
        )

        self.assertTrue(applied)
        self.assertEqual(len(started), 1)
        self.assertAlmostEqual(started[0].scale, 1.5)
        self.assertEqual(overlays, [True])
        self.assertEqual(state.zoom_state_cycle, 2)
        self.assertTrue(state.is_zoomed)
        self.assertEqual(saved[0][0], "x.png")
        self.assertEqual(state.user_zoom_memory["x.png"], started[0])

    def test_apply_manual_zoom_respects_min_and_max_scale(self) -> None:
        state = self._state()
        started = []

        apply_manual_zoom(
            state,
            scale_multiplier=99.0,
            anchor=(400, 300),
            max_zoom=2.0,
            start_zoom_animation=lambda st, view: started.append(view.copy()),
            trigger_scale_overlay=lambda st: None,
            save_view_for_path=lambda st, path, view: None,
        )
        self.assertAlmostEqual(started[-1].scale, 2.0)

        state.view = ViewParams(scale=0.5, offx=0.0, offy=0.0)
        state.last_fit_view = ViewParams(scale=0.8, offx=0.0, offy=0.0)
        apply_manual_zoom(
            state,
            scale_multiplier=0.1,
            anchor=(400, 300),
            max_zoom=2.0,
            start_zoom_animation=lambda st, view: started.append(view.copy()),
            trigger_scale_overlay=lambda st: None,
            save_view_for_path=lambda st, path, view: None,
        )
        self.assertAlmostEqual(started[-1].scale, 0.4)

    def test_apply_manual_zoom_without_current_texture_is_noop(self) -> None:
        state = self._state()
        state.cache.curr = None

        applied = apply_manual_zoom(
            state,
            scale_multiplier=1.5,
            anchor=(400, 300),
            max_zoom=4.0,
            start_zoom_animation=lambda st, view: self.fail("animation should not start"),
            trigger_scale_overlay=lambda st: self.fail("overlay should not trigger"),
            save_view_for_path=lambda st, path, view: self.fail("view should not save"),
        )

        self.assertFalse(applied)


class TextureTypeSmokeTests(unittest.TestCase):
    def test_texture_info_copy_refs_same_texture(self) -> None:
        tex = object()
        original = TextureInfo(tex=tex, w=10, h=20, path="x.png")

        copied = original.copy_ref()

        self.assertIs(copied.tex, tex)
        self.assertEqual((copied.w, copied.h, copied.path), (10, 20, "x.png"))


if __name__ == "__main__":
    unittest.main()
