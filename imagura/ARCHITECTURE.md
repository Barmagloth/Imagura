# Imagura Architecture Notes

For the current work-in-progress state, test commands, fixed regressions, and
next-step notes, read `imagura/HANDOFF.md`.

## Direction

`imagura2.py` is the compatibility launcher and migration shell. New behavior
should move into package modules under `imagura/` and then be wired back into
the old loop until the old loop can be deleted.

## Boundaries

- `viewers/`: CPU-side decoding by format. No window or navigation logic.
- `services/loader.py`: background CPU loading and UI-thread callback delivery.
- `services/textures.py`: main-thread GPU texture upload/unload ownership.
- `services/large_texture_cache.py`: FIFO session cache for heavy full-size GPU textures.
- `services/animated_content_cache.py`: FIFO RAM cache for decoded animated frame data.
- `services/thumbnails.py`: gallery thumbnail queueing and cache eviction.
- `image_sorting.py`: gallery sort keys, natural filename order, direction handling, and current-file preservation.
- `image_loading/content_loader.py`: viewer-registry dispatch for CPU-side file loading.
- `image_loading/current_and_neighbors.py`: async orchestration for the current image and prev/next textures.
- `image_metadata/exif_cache.py`: bounded EXIF metadata reading for HUD display.
- `gallery/behavior.py`: gallery visibility, scrolling, and target navigation.
- `gallery/renderer.py`: gallery drawing; reports clicked thumbnail index.
- `playback/animated_content.py`: animated current-image playback lifecycle.
- `platform/file_deletion.py`: platform trash/recycle-bin integration.
- `platform/file_dialog.py`: Windows native image-open dialog for packaged empty startup.
- `user_settings.py`: user-writable JSON settings persistence (low-level read/write).
- `settings_persistence.py`: settings schema (`SETTINGS_TABS`), validation, and the pure config save/apply impl (no UI, no globals magic). Leaf module; must not import `imagura2`.
- `ui/text_overlays.py`: filename, HUD, scale overlay, and shared text-shadow drawing.
- `ui/toolbar.py`: top toolbar hit-testing, input update, icon drawing, and rendering.
- `ui/context_menu.py`: right-click context menu hit-testing, input update, and rendering.
- `ui/gallery_sort_control.py`: lower-gallery sort label, direction toggle, menu hit-testing, and rendering.
- `ui/settings_modal.py`: settings modal rendering, hit-testing, and input handling. Saves route through `imagura2.save_config_value` so runtime globals stay mirrored.
- `zoom/scale_overlay.py`: scale overlay text and fade/trigger state logic.
- `zoom/zoom_animation.py`: wheel/key zoom tween state updates.
- `zoom/toggle_zoom_animation.py`: 1:1/Fit/Custom toggle zoom cycle.
- `zoom/manual_zoom.py`: anchored wheel/key zoom target calculation and custom-view persistence.
- `state/`: dataclasses and compatibility properties only.
- `AppController` (class in `imagura2.py`): owns the frame loop. Explicit phases
  `setup()` -> `_poll_async()` / `_update()` -> the frame block -> `_shutdown()`.
  The old MVC-style `renderer.py`, `app.py`, `input_handler.py`, `commands.py`
  (and the unused top-level `animation.py`) were a dead cluster and have been
  removed; recover from git history if ever needed.
- `win_utils.py`, `clipboard.py`: Windows integration points. Keep Linux
  equivalents possible by avoiding Windows calls from generic services.
- `packaging/windows/`: Windows PyInstaller one-dir build configuration.
- `tools/build_windows_exe.py`: Windows PyInstaller runner with explicit run id, workpath, and distpath options.

## Performance Policy

Prefer algorithmic and ownership fixes before native code:

- decode less, cache less, and unload deterministically;
- keep GPU calls on the main thread;
- cap animated decoded RGBA memory and cache it only within a fixed RAM budget;
- avoid stale async results with generation checks;
- only introduce C/Rust when profiling shows Python overhead in a tight loop.

Native modules are candidates for:

- thumbnail decode/resize batches;
- streaming animated image decode;
- color conversion and pixel format transforms.

Assembly is not a default target. SIMD through a C/Rust library is easier to
test, package, and keep portable across Windows and Linux.
