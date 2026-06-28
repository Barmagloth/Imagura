# Windows Packaging

Imagura should be built as a PyInstaller one-dir app first. One-file packaging
can be added later, but one-dir gives faster startup and fewer surprises with
native raylib and pywin32 dependencies.

The signed/branded artifacts produced here:

- `imagura.ico` — multi-resolution app icon (256/128/64/48/32/16).
- `version_info.txt` — Windows version resource, generated from `pyproject.toml`.
- `Imagura-<version>-setup.exe` — Inno Setup installer (built separately).

## Build the executable

From `cmd.exe`:

```bat
cd /d R:\Projects\Imagura
py -m pip install -e .[windows-build,exif]
python -B tools\build_windows_exe.py --clean
```

Output:

```bat
dist\Imagura\Imagura.exe
```

The runner writes PyInstaller temporary files to the OS temp directory by
default and writes the final app to `dist`. Override these paths when needed:

```bat
python -B tools\build_windows_exe.py --clean --workpath C:\tmp\imagura-pyinstaller-build --distpath R:\Projects\Imagura\dist
```

For Codex or other long-running automation logs, mark the process explicitly:

```bat
python -B tools\build_windows_exe.py --clean --codex-run-id codex-windows-build
```

For diagnostic builds with a console window:

```bat
python -B tools\build_windows_exe.py --clean --debug-console
```

The build runner regenerates `version_info.txt` from `pyproject.toml` on every
run, then PyInstaller embeds both the icon and the version resource into
`Imagura.exe` (wired into the `EXE()` section of `imagura-win.spec` via `icon=`
and `version=`).

## App icon

`imagura.ico` is checked in, but it is generated from a small script so it can
be reproduced or restyled. Pillow is required (it is already an Imagura runtime
dependency).

```bat
python packaging\windows\make_icon.py
```

This writes `packaging\windows\imagura.ico` (multi-resolution: 256/128/64/48/32/16).
If Pillow is not installed, `python -m pip install pillow` first.

## Version metadata

`version_info.txt` is a PyInstaller `VSVersionInfo` resource populated from
`pyproject.toml` (version, product name `Imagura`, company `Barmagloth`,
copyright). It is regenerated automatically on every build, so it cannot drift
from `pyproject.toml`. To regenerate it without building:

```bat
python tools\build_windows_exe.py --write-version-info
```

The branding constants (company, copyright year, file description) live at the
top of `tools/build_windows_exe.py`; the version itself always comes from
`pyproject.toml`.

## File associations

Associations are handled by the installer (registry entries), **not** by runtime
code. The associated extensions are the formats Imagura actually supports,
confirmed from `imagura/config.py` (`IMG_EXTS`) and the viewer registry
(`imagura/viewers/`):

| Extension | Source |
| --------- | ------ |
| `.png`    | `IMG_EXTS` |
| `.jpg`    | `IMG_EXTS` |
| `.jpeg`   | `IMG_EXTS` |
| `.bmp`    | `IMG_EXTS` |
| `.gif`    | `IMG_EXTS` (`GifViewer` for animation) |
| `.tga`    | `IMG_EXTS` |
| `.qoi`    | `IMG_EXTS` |
| `.webp`   | `WebPViewer` |

> Note: `.tif`/`.tiff` are **not** supported by Imagura, so they are
> deliberately not associated.

The installer registers a single shared ProgID, `Imagura.Image`, and adds each
extension to its `OpenWithProgids` list (so Imagura appears in "Open with"
without hijacking an existing default). The registry layout written under
`HKEY_CURRENT_USER\Software\Classes` (`HKA` in the script resolves to per-user
for a non-admin install, per-machine for an admin install) is:

```
Software\Classes\Imagura.Image\                       (default) = "Imagura Image"
Software\Classes\Imagura.Image\DefaultIcon\           (default) = "<app>\Imagura.exe,0"
Software\Classes\Imagura.Image\shell\open\command\    (default) = "<app>\Imagura.exe" "%1"
Software\Classes\.png\OpenWithProgids\                Imagura.Image = ""
Software\Classes\.jpg\OpenWithProgids\                Imagura.Image = ""
...one OpenWithProgids entry per supported extension...
```

All of these are removed on uninstall (`uninsdeletekey` / `uninsdeletevalue`).

## Build the installer (Inno Setup)

The installer is described by `imagura.iss` and built with the Inno Setup 6
command-line compiler, `ISCC` (https://jrsoftware.org/isdl.php). Build the
PyInstaller one-dir app **first** so `dist\Imagura\` exists.

```bat
cd /d R:\Projects\Imagura
python -B tools\build_windows_exe.py --clean
iscc packaging\windows\imagura.iss
```

Output:

```bat
dist\installer\Imagura-2.0.0-setup.exe
```

Override the version on the command line if it differs from the default in the
script:

```bat
iscc /DMyAppVersion=2.0.0 packaging\windows\imagura.iss
```

The installer:

- installs to `Program Files\Imagura` (`{autopf}`),
- creates a Start Menu shortcut (and an uninstall entry),
- offers an optional desktop shortcut (unchecked by default),
- registers the file associations above (optional "associate" task, on by default),
- uninstalls cleanly, removing both files and all registry entries it created.

## Notes

- Build Windows executables on Windows. Cross-compiling the PyInstaller app from
  Linux is not a supported target.
- Double-clicking the exe without an image/folder argument opens a native Windows
  image picker through pywin32 when the startup directory has no supported images.
- Runtime settings are saved to `%APPDATA%\Imagura\settings.json`, not into the
  bundled application files.
- Keep platform-specific code behind `imagura/platform/`, `imagura/win_utils.py`,
  and `imagura/clipboard.py` so a Linux package can still be implemented later.
- The current spec intentionally does not bundle a custom font. The app loads
  common Windows system fonts for Unicode/Cyrillic text.
- Do not commit `build/` or `dist/` outputs unless release packaging explicitly
  needs archived artifacts.
- If `EndUpdateResourceW` fails with access denied while building on a mapped
  or restricted drive, retry with `--workpath` pointing at a writable local
  directory.
