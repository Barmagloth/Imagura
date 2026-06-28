# Imagura Handoff

Last updated: 2026-06-24.

This repository is mid-refactor. Work is local; do not push unless asked.
`imagura2.py` is still the launcher and compatibility shell, but the frame loop
now lives in the `AppController` class (defined in `imagura2.py`) and the settings
modal moved into `imagura/ui/settings_modal.py` + `imagura/settings_persistence.py`.
New code should continue moving into explicit package modules under `imagura/`.

## How To Run

From `cmd.exe`:

```bat
cd /d R:\Projects\Imagura
python -B imagura2.py
```

Open a specific file or directory:

```bat
python -B imagura2.py "R:\Projects\Imagura\some file.png"
python -B imagura2.py "D:\Photos"
```

`-B` is used to avoid `.pyc` writes into `__pycache__`; the app can also run
without it if the local permission issue is gone.

## Test Discipline

Do not use plain `python -B -m unittest discover -s tests` as the default. A
previous run escaped control and took about two hours.

Use the bounded runner:

```bat
python -B tools\run_smoke_tests.py --codex-run-id codex-smoke --timeout 10
```

For one target:

```bat
python -B tools\run_unittest_target.py tests.test_smoke.ViewerSmokeTests --codex-run-id codex-viewer --timeout 10
```

When Codex runs Python, mark it:

```bat
set IMAGURA_CODEX_RUN=1
set IMAGURA_CODEX_RUN_ID=codex-descriptive-id
```

After Python runs, check:

```bat
Get-Process python,pythonw -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,CPU,StartTime
```

At the last checkpoint, smoke tests passed: 52 tests. AST + PyInstaller spec +
`pyproject.toml` check passed over 70 Python files.

## Current Architecture

See `imagura/ARCHITECTURE.md` for module boundaries. Main extracted areas:

- `viewers/`: CPU-side format loading by extension.
- `services/loader.py`: async CPU loader and UI-thread callback queue.
- `services/textures.py`: GPU texture upload/unload helpers.
- `services/large_texture_cache.py`: FIFO session cache for heavy full-size GPU textures.
- `services/animated_content_cache.py`: FIFO RAM cache for decoded animated frames.
- `services/thumbnails.py`: gallery thumbnail scheduling/cache eviction.
- `image_sorting.py`: gallery sort keys, direction handling, natural name order,
  and current-file preservation after resorting.
- `image_loading/content_loader.py`: viewer registry dispatch.
- `image_loading/current_and_neighbors.py`: current image plus prev/next async orchestration.
- `image_metadata/exif_cache.py`: bounded EXIF metadata cache.
- `gallery/behavior.py`: gallery visibility/scroll/target behavior.
- `gallery/renderer.py`: gallery drawing; returns clicked index.
- `playback/animated_content.py`: animated current-image playback lifecycle.
- `platform/file_deletion.py`: platform trash/recycle-bin integration.
- `platform/file_dialog.py`: Windows native image-open dialog for empty startup.
- `user_settings.py`: user-writable JSON settings persistence for packaged and source runs.
- `settings_persistence.py`: settings schema (`SETTINGS_TABS`), validation, and the pure config save/apply impl (no UI, no `globals()` magic).
- `ui/settings_modal.py`: settings modal render/hit-test/input, extracted from `imagura2.py`.
- `ui/text_overlays.py`: filename, HUD, scale overlay, and shared text-shadow drawing.
- `ui/toolbar.py`: top toolbar hit-testing, input update, icon drawing, and rendering.
- `ui/context_menu.py`: right-click context menu hit-testing, input update, and rendering.
- `ui/gallery_sort_control.py`: compact lower-gallery sort control and menu.
- `zoom/scale_overlay.py`: scale overlay text and fade/trigger state logic.
- `zoom/zoom_animation.py`: wheel/key zoom tween state updates.
- `zoom/toggle_zoom_animation.py`: 1:1/Fit/Custom toggle zoom cycle.
- `zoom/manual_zoom.py`: anchored wheel/key zoom target calculation and custom-view persistence.

`imagura2.py` still contains window setup, transform dispatch, the service
singletons, and the `AppController` frame loop. The loop was split into explicit
phases: `setup()` -> per-frame `_poll_async()` / `_update()` -> the frame block
(settings input, `BeginDrawing`, input, render, `EndDrawing`) -> `_shutdown()`.
The settings UI was extracted to `imagura/ui/settings_modal.py`;
`imagura2.save_config_value` / `apply_saved_settings` remain as thin shims that
mirror values into `imagura2`'s module globals (a contract the smoke tests pin).

Deferred sub-step (needs manual GUI QA, not done): fully separating input from
render so input runs before `BeginDrawing`. The delete fast-path currently does
`EndDrawing()+continue` mid-frame, so that reorder must be done carefully and
verified in the real GUI; it was intentionally left out of the headless refactor.

## Packaging

Windows packaging has a first-pass PyInstaller one-dir setup:

- `packaging/windows/imagura-win.spec` (now wires `icon=` and `version=`)
- `packaging/windows/README.md`
- `packaging/windows/make_icon.py` + `packaging/windows/imagura.ico` (generated multi-res icon)
- `packaging/windows/version_info.txt` (auto-generated from `pyproject.toml` by the build runner)
- `packaging/windows/imagura.iss` (Inno Setup installer: shortcuts, file associations, uninstall)
- `tools/build_windows_exe.py` (regenerates `version_info.txt` each build; `--write-version-info` flag)

Building the installer needs Inno Setup 6/7 (`ISCC`). Verified with Inno Setup
7.0.1: `ISCC packaging\windows\imagura.iss` produces
`dist\installer\Imagura-2.0.0-setup.exe` (~23 MB). Run the PyInstaller build
first so `dist\Imagura\` exists. See `packaging/windows/README.md`.

Build from `cmd.exe` on Windows:

```bat
cd /d R:\Projects\Imagura
py -m pip install -e .[windows-build,exif]
python -B tools\build_windows_exe.py --clean
```

Expected output:

```bat
dist\Imagura\Imagura.exe
```

The build runner now accepts `--codex-run-id`, `--workpath`, and `--distpath`.
By default, temporary PyInstaller work files go to the OS temp directory and
the final app goes to `dist`.

The current session successfully built:

```bat
dist\Imagura\Imagura.exe
```

Observed size: 7,827,643 bytes. The GUI executable was not launched from Codex;
the verified step is package creation, not manual GUI smoke.

## Fixed Regressions During Refactor

### Unicode Filenames

Static image loading no longer passes Unicode paths directly to
`raylib.LoadImage(path)`. `ImageViewer` reads bytes through Python
`open(path, "rb")` and calls `load_image_from_memory`. The regression was
reported with Cyrillic file names such as `Метро.png`, but the fix covers
normal Unicode file names generally for static images because raylib no longer
receives the file path.

Coverage:

- `ViewerSmokeTests.test_static_viewer_loads_cyrillic_filename`

### Transparent Background

Window creation now includes `FLAG_WINDOW_TRANSPARENT` before `InitWindow` via
`SetConfigFlags(_fullscreen_window_flags())`. This is required for raylib's
transparent framebuffer behavior.

Coverage:

- `WindowFlagSmokeTests.test_fullscreen_flags_request_transparent_framebuffer`

### Heavy File Repeat Loading

Heavy, non-animated full-size images are cached in VRAM through
`LargeTextureCache`. On cache hit, `CurrentAndNeighborLoader` sets
`state.cache.curr` directly without submitting a `CURRENT` async task, so the
`LOADING` indicator should not appear while the item remains in cache.

Defaults:

- `FULL_IMAGE_CACHE_MAX_MB = 256`
- `FULL_IMAGE_CACHE_MAX_ITEMS = 4`

The cache is FIFO, not LRU. `get()` does not refresh ordering. The cache is
session-only and stores GPU textures, not files on disk. Disk cache was not used
because the expensive part for this UX is decode plus GPU upload.

Invalidation happens on transform/delete for the changed path.

Coverage:

- `LargeTextureCacheSmokeTests`
- `CurrentAndNeighborLoaderSmokeTests.test_heavy_cache_hit_sets_current_without_async_current_submit`

### Animated GIF Repeat Loading

Animated GIFs are cached separately from full-size textures. `AnimatedContentCache`
keeps decoded RGBA frames and frame durations in RAM with FIFO eviction. On cache
hit, `CurrentAndNeighborLoader` rebuilds a fresh current texture from the cached
first frame and starts playback without submitting a `CURRENT` async task, so the
`LOADING` indicator should not appear while the GIF remains in cache.

Defaults:

- `ANIMATED_CONTENT_CACHE_MAX_MB = 256`
- `ANIMATED_CONTENT_CACHE_MAX_ITEMS = 4`

The cache stores CPU frame data only, not GPU textures or playback state. Each
cache hit clones the cached frame list for runtime playback so playback cleanup
does not destroy the cached copy. Very large GIFs are skipped if their decoded
RGBA frames exceed the cache budget.

Invalidation happens on transform/delete for the changed path.

Coverage:

- `AnimatedContentCacheSmokeTests`
- `ViewerSmokeTests.test_gif_viewer_cache_snapshot_survives_runtime_cleanup`
- `CurrentAndNeighborLoaderSmokeTests.test_animated_cache_hit_sets_current_without_async_current_submit`
- `CurrentAndNeighborLoaderSmokeTests.test_animated_current_callback_populates_animated_cache`

### Gallery Sorting

The lower gallery now has a compact sort control. The label opens a menu for:

- Name
- Modified date
- Created date
- Size
- Type
- Date taken / EXIF

The arrow toggles ascending/descending. Resorting preserves the currently open
file when possible, re-centers the gallery target, clears stale thumbnail queue
work, and unloads prev/next textures so neighbors are rebuilt in the new order.

Initial directory scans also use the configured gallery sort state instead of
hard-coded filename order.

The direction indicator is drawn as a small line icon, not a text arrow, because
the selected font path may not contain arrow glyphs and rendered `?` in the
packaged app. The sort popup opens above the gallery strip, so an open popup
now forces the gallery to remain visible; otherwise moving the pointer from the
gallery into the popup can make the gallery slide away.

Coverage:

- `ImageSortingSmokeTests`
- `GalleryBehaviorSmokeTests.test_sort_menu_can_force_gallery_visible_outside_panel`
- `UIControlsSmokeTests.test_gallery_sort_menu_click_works_above_gallery_panel`

### Runtime Cache Settings

The settings UI now exposes:

- `FULL_IMAGE_CACHE_MAX_MB`
- `FULL_IMAGE_CACHE_MAX_ITEMS`
- `ANIMATED_CONTENT_CACHE_MAX_MB`
- `ANIMATED_CONTENT_CACHE_MAX_ITEMS`
- `MAX_ANIM_FRAMES`
- `MAX_ANIM_MEMORY_MB`

Changing cache size/item limits applies to the live cache instances. Full-image
cache reconfiguration protects currently active textures from accidental unload.

Settings are persisted to a user-writable JSON file, not by editing
`imagura/config.py`. On Windows the default path is:

```bat
%APPDATA%\Imagura\settings.json
```

On Linux the default path is:

```text
~/.config/imagura/settings.json
```

The saved JSON is loaded at startup and applied to both `imagura.config` and
legacy globals imported into `imagura2.py`. This matters because much of the
compatibility shell still reads module-level imported constants.

Coverage:

- `UserSettingsSmokeTests`

### Empty Startup / No Images

The packaged exe can be launched by double-clicking from `dist\Imagura`, where
the current directory usually contains no images. That previously fell into a
minimal `No images found` loop that did not handle `Esc` because the app disables
raylib's default exit key with `SetExitKey(0)`.

Current behavior:

- If startup scanning finds no images and no explicit path was passed, the app
  opens a native Windows image picker.
- If the picker is cancelled, the empty screen has visible `Open image...` and
  `Exit` buttons.
- `Esc`, the hover close button, and the settings toolbar path work in the empty
  screen.
- The picker uses `win32gui.GetOpenFileNameW` first. A ctypes common-dialog
  path remains as fallback and logs `CommDlgExtendedError` when it fails.
- The PyInstaller spec explicitly includes `pywintypes` for this dialog path.

Coverage:

- `FileDialogSmokeTests`

## Important Ownership Notes

GPU texture ownership is the main risk area.

- If a texture is in `LargeTextureCache`, `unload_texture_deferred` must not
  unload it when leaving the current image.
- Evicted cache entries are handed to `TextureManager.defer_unload`.
- Cleanup clears `LargeTextureCache` before unloading `state.cache.prev/curr/next`
  to avoid double-unloading active textures.
- Animated GIFs are not cached in `LargeTextureCache`; decoded frames live in
  `AnimatedContentCache`, while playback owns the current texture updates.
- Cleanup stops playback before clearing `AnimatedContentCache`.

## Current Known Constraints

- `imagura2.py` is still large and should keep shrinking.
- Settings labels in `imagura2.py` appear mojibake in source; avoid broad edits
  there unless necessary.
- Windows behavior matters first, but generic services should remain portable to
  Linux. Keep Windows calls in `win_utils.py`, `clipboard.py`, or a future
  `platform/` boundary.
- Do not push to git unless the user explicitly asks.
- Do not revert unrelated dirty worktree changes.

## Manual QA Checklist

A fuller, hand-off-ready checklist (settings, delete fast-path, packaging, etc.)
lives in `docs/QA_CHECKLIST.md`. The quick list below stays here for convenience.

Run these in the real GUI after changes that touch loading/rendering:

1. Cyrillic and non-Latin filenames render in the filename overlay and gallery.
2. Transparent background still works in fullscreen/window transparency mode.
3. Double-clicking `dist\Imagura\Imagura.exe` with no adjacent images opens the
   file picker; cancelling it leaves an empty screen where `Esc` exits.
4. Heavy static image repeat-open hits `LargeTextureCache` without `LOADING`.
5. Animated GIF repeat-open hits `AnimatedContentCache` without `LOADING`.
6. Rotate/flip/delete invalidate the relevant caches.
7. HUD, filename overlay, scale overlay, toolbar, context menu, and gallery sort
   controls do not overlap.
8. Sort by Name/Modified/Created/Size/Type/Date taken in both directions; the
   current file stays selected and thumbnails rebuild around the new order.
9. Change a numeric setting, press Enter, reopen settings, and confirm the value
   remains changed. Restart the app and confirm it loads from user settings.
10. `dist\Imagura\Imagura.exe` launches on Windows after packaging.

## Future Refactoring Backlog

Done in the 2026-06-24 pass: settings UI extracted, main loop -> `AppController`
(except the input/render reorder noted above), dead legacy cluster removed,
Windows packaging polished, profiling harness + report written
(see `docs/profiling.md`).

Remaining:

1. Linux implementation for `platform/file_deletion.py` without falling back to
   permanent deletion. (Backlogged on request.)
2. Finish the `AppController` split: separate input from render (input before
   `BeginDrawing`), handling the delete fast-path's mid-frame `EndDrawing`;
   verify in the real GUI. Optionally move `AppController` into its own module
   once the free functions it calls also migrate out of `imagura2.py`.
3. Performance (from `docs/profiling.md`): no native rewrite is justified yet --
   every measured hotspot is already in C (raylib `stb_image` / Pillow). Prefer
   algorithmic wins first: persist thumbnails to disk, decode at reduced scale,
   drop the WebP/GIF in-memory PNG round-trip, and stream/decode-ahead animated
   frames. Re-profile GPU texture upload on a machine with a display before any
   playback-perf decision (it could not be measured headless).
4. Set real branding (author/license/copyright) in `pyproject.toml` and the
   `.iss` `[Setup]` block (currently "Barmagloth" / 2026). The installer itself
   now compiles: `ISCC packaging\windows\imagura.iss` -> `dist\installer\`.
