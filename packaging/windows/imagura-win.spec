# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path(SPECPATH).parents[1]
CONSOLE = os.environ.get("IMAGURA_BUILD_CONSOLE") == "1"

# Branding resources live next to this spec. Each is optional: if the file is
# missing the build still succeeds (PyInstaller treats None as "no resource").
_ICON_PATH = Path(SPECPATH) / "imagura.ico"
_VERSION_PATH = Path(SPECPATH) / "version_info.txt"
ICON = str(_ICON_PATH) if _ICON_PATH.exists() else None
VERSION = str(_VERSION_PATH) if _VERSION_PATH.exists() else None

hiddenimports = (
    collect_submodules("PIL")
    + collect_submodules("raylib")
    + [
        "win32api",
        "win32clipboard",
        "win32con",
        "win32gui",
        "pywintypes",
    ]
)

a = Analysis(
    [str(ROOT / "imagura2.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Imagura",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
    version=VERSION,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Imagura",
)
