# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Imagura.

Usage:
    cd <project_root>
    pyinstaller installer/imagura.spec
"""

import os
import sys

block_cipher = None

# Project root is one level up from this spec file
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(SPECPATH)))

a = Analysis(
    ['../imagura2.py'],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[
        # Include the imagura package
        ('../imagura', 'imagura'),
    ],
    hiddenimports=[
        'imagura',
        'imagura.config',
        'imagura.app',
        'imagura.rl_compat',
        'imagura.types',
        'imagura.commands',
        'imagura.input_handler',
        'imagura.renderer',
        'imagura.animation',
        'imagura.image_utils',
        'imagura.view_math',
        'imagura.math_utils',
        'imagura.win_utils',
        'imagura.clipboard',
        'imagura.transforms',
        'imagura.logging',
        'imagura.user_config',
        'imagura.state',
        'imagura.state.app_state',
        'imagura.state.window',
        'imagura.state.images',
        'imagura.state.view',
        'imagura.state.gallery',
        'imagura.state.ui',
        'imagura.state.input',
        'imagura.state.animation',
        'imagura.state.loading',
        # raylib bindings
        'raylib',
        'raylibpy',
        # Optional
        'PIL',
        'PIL.Image',
        'PIL.ExifTags',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Imagura',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Windowed application, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='../installer/imagura.ico' if os.path.exists(os.path.join(SPECPATH, 'imagura.ico')) else None,
    version='../installer/version_info.txt' if os.path.exists(os.path.join(SPECPATH, 'version_info.txt')) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Imagura',
)
