# Imagura — Manual GUI QA Checklist

Self-contained verification plan for the 2026-06 refactor pass. Anyone (a human,
or an agent session with a display) can run this top-to-bottom without prior
context. It targets what the refactor changed and re-checks the surrounding
behavior for regressions.

## What changed in this pass (why this QA exists)

- Settings modal extracted from `imagura2.py` → `imagura/ui/settings_modal.py`
  (UI) + `imagura/settings_persistence.py` (schema/validation/save). The
  `imagura2.save_config_value` / `apply_saved_settings` shims still mirror values
  into `imagura2` globals. **Highest-risk area — test settings thoroughly.**
- Main loop moved into the `AppController` class in `imagura2.py`
  (`setup` → `_poll_async` / `_update` → frame block → `_shutdown`). Frame block
  is byte-identical to the old loop (no input/render reorder was done).
- Dead module cluster removed: `renderer.py`, `app.py`, `input_handler.py`,
  `commands.py`, top-level `animation.py`.
- Windows packaging: app icon, version metadata, file associations, Inno Setup
  installer.

These were verified automatically (smoke tests green, build clean, exe launches
and renders an image). NOT yet verified by hand: interactive settings, nav,
delete, caches, overlays, packaging install. That is this checklist.

## How to run the app

From `R:\Projects\Imagura` (`cmd.exe` or PowerShell):

- Source build:  `python -B imagura2.py "C:\path\to\image.png"`
- Packaged exe:  `dist\Imagura\Imagura.exe "C:\path\to\image.png"`
- Open a folder: pass a directory instead of a file.
- Empty start:   launch with no argument from a folder that has no images.

Automated baseline (should pass before manual QA):

```
python -B tools\run_smoke_tests.py --codex-run-id qa --timeout 60
```

Do NOT run `python -m unittest discover` — it has historically run away (~2h).

### Test assets to prepare
- A normal image (PNG/JPG).
- A heavy/large image (e.g. ≥ 20 MP) for the cache test.
- An animated GIF.
- A file with a non-Latin name, e.g. `Метро.png` (Unicode test).
- A folder containing several images for navigation/gallery.
- An empty folder (no images) for the empty-start test.

Legend: `[ ]` pass · `[F]` fail · note anything odd in **Notes**.

---

## A. Launch & render  (AppController.setup → run)

- [ ] A1. App launches on a single image and the image renders centered/fit.
- [ ] A2. No fatal dialog ("Press Enter to exit...") and process stays alive.
- [ ] A3. Launch on a **folder**: first image shows; gallery strip appears on
  hover at the bottom.
- [ ] A4. Close works: `Esc`, the hover close button (top-right), and the window
  close all exit cleanly (no hang, no leftover `Imagura`/`python` process).

## B. Settings modal  (NEW: settings_modal + settings_persistence + save shim)

Open settings via the top toolbar (hover top edge → gear/SETTINGS button).

- [ ] B1. Modal opens; background dims; the rest of the UI stops responding to
  clicks/keys while it is open.
- [ ] B2. **Cyrillic renders correctly** (mojibake regression check): tab names
  `Общие / Анимация / Интерфейс / Галерея / Ввод / Лимиты` and the field labels
  show real Cyrillic, not `Ð¾Ð±Ñ‰Ð¸Ðµ`-style garbage. Footer hints
  (`сохранить / отмена / закрыть` …) are also correct.
- [ ] B3. Switch between all tabs; layout is intact, no overlap/clipping.
- [ ] B4. Edit a numeric field (e.g. `TARGET_FPS`), press `Enter`. Value sticks.
- [ ] B5. Close settings, reopen — the edited value is still there (persisted).
- [ ] B6. **Restart the app** — the value loads from user settings
  (`%APPDATA%\Imagura\settings.json`). Confirm the JSON file exists and contains
  your change.
- [ ] B7. Mouse-wheel scrolls the settings content when it overflows.
- [ ] B8. Editing on one tab then switching tabs saves the in-progress edit
  (no lost value, no crash).
- [ ] B9. **Live cache reconfig** (the save→`apply_runtime_config_change` path):
  change `FULL_IMAGE_CACHE_MAX_MB` / `..._MAX_ITEMS` or the animated-cache limits,
  apply, and confirm the app stays stable and the current image is not unloaded.
- [ ] B10. Close settings via the `X` button and via `Esc` — both work.

## C. Navigation & gallery

- [ ] C1. `→` / `D` next image, `←` / `A` previous image.
- [ ] C2. **Hold** `→` — key-repeat advances after the initial delay (not one
  image per physical press only).
- [ ] C3. Edge-click navigation: click far-left / far-right edge switches image
  (when not significantly zoomed and not over the gallery panel).
- [ ] C4. Click a gallery thumbnail — jumps to that image; current stays
  selected/centered.
- [ ] C5. Switch animation between images looks smooth; no flicker or leak from
  the old texture.

## D. Zoom & pan

- [ ] D1. Mouse-wheel over the image zooms toward the cursor.
- [ ] D2. Zoom-in / zoom-out keys work.
- [ ] D3. Double-click toggles 1:1 / Fit; the scale overlay appears and fades.
- [ ] D4. Drag (left-button) pans a zoomed image; release keeps the view; the
  per-image custom view is remembered when you come back.

## E. Delete fast-path  (watch the deferred input/render concern)

The delete handler does `EndDrawing(); increment_frame(); continue` mid-frame.
The input/render reorder was intentionally NOT done, so this should behave as
before — confirm there is no new flicker, freeze, or crash on the delete frame.

- [ ] E1. Press `Del` on an image — it goes to the Recycle Bin (recoverable) and
  the viewer advances to the next/prev image.
- [ ] E2. Delete the **last** remaining image — app closes cleanly.
- [ ] E3. No one-frame flash, freeze, or draw glitch on the delete frame.
- [ ] E4. `Del` does nothing while the settings modal is open or during the
  open animation (by design).

## F. Transforms & cache invalidation

- [ ] F1. Rotate CW / CCW and Flip-H (toolbar) update the image on disk and on
  screen.
- [ ] F2. After a transform, re-opening that image shows the new orientation
  (cache was invalidated, not serving the stale texture).
- [ ] F3. Animated GIFs correctly **refuse** in-place rotate/flip (logged skip,
  no corruption).

## G. Caches (no spurious LOADING)

- [ ] G1. Open a heavy image, go away, come back — second open is instant with
  **no `LOADING` indicator** (LargeTextureCache hit).
- [ ] G2. Open an animated GIF, leave, return — plays immediately, **no
  `LOADING`** (AnimatedContentCache hit).

## H. Overlays & chrome (no overlap)

- [ ] H1. HUD (toggle key), filename overlay (toggle key), scale overlay,
  toolbar, context menu (right-click), and the lower-gallery sort control do not
  overlap or fight each other.
- [ ] H2. Sort menu: sort by Name / Modified / Created / Size / Type / Date-taken
  in both directions; the current file stays selected and thumbnails rebuild.
- [ ] H3. The sort popup opens above the gallery strip and keeps the gallery
  visible while the pointer moves into it.

## I. Window, background, Unicode

- [ ] I1. Transparent background mode (cycle-BG key) shows the desktop through
  the window in fullscreen / transparency mode.
- [ ] I2. Toggle windowed mode (`F`); resizing the window re-fits the image.
- [ ] I3. A file named `Метро.png` (and other Unicode names) renders in the
  filename overlay and the gallery without `?`/boxes.

## J. Empty startup

- [ ] J1. Launch the **packaged exe** (`dist\Imagura\Imagura.exe`) by
  double-click from a folder with no adjacent images → a native Windows file
  picker opens.
- [ ] J2. Cancel the picker → an empty screen with visible `Open image...` and
  `Exit` buttons.
- [ ] J3. `Esc`, the hover close button, and the toolbar path all work on the
  empty screen.

## K. Packaging & installer  (NEW)

Build (if needed): `python -B tools\build_windows_exe.py --clean`, then
`& 'C:\Program Files\Inno Setup 7\ISCC.exe' packaging\windows\imagura.iss`.

- [ ] K1. `dist\Imagura\Imagura.exe` shows the Imagura **icon** in Explorer, and
  Properties → Details shows **version 2.0.0** / product "Imagura".
- [ ] K2. Run `dist\installer\Imagura-2.0.0-setup.exe`: installs to Program
  Files, creates a Start Menu shortcut (and a desktop shortcut if the optional
  task is checked).
- [ ] K3. Installed shortcuts launch the app and carry the icon.
- [ ] K4. File associations: after install with the "Associate" task, right-click
  a `.png`/`.jpg` → "Open with" lists **Imagura**, and opening via the
  association launches the app on that file.
- [ ] K5. Uninstall (Apps & features) removes the app and the association
  registry entries cleanly; no leftover Program Files folder.

---

## Sign-off

- Build / commit under test: ________________________
- Tester / date: ____________________________________
- Result: ☐ all pass ☐ pass with notes ☐ blockers found
- Notes / failures (item id → what happened):
  - 
  - 

> Priority if time-boxed: **B (settings), E (delete), A (launch), K (installer)**
> are the areas this refactor actually changed. C/D/F/G/H/I/J are regression
> sweeps of untouched behavior.
