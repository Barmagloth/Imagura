from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "windows" / "imagura-win.spec"
PYPROJECT = ROOT / "pyproject.toml"
VERSION_INFO = ROOT / "packaging" / "windows" / "version_info.txt"

# Branding constants. Keep in sync with packaging/windows/imagura.iss.
COMPANY = "Barmagloth"
PRODUCT_NAME = "Imagura"
COPYRIGHT_YEAR = "2026"
FILE_DESCRIPTION = "Imagura - fast async image viewer"


def _read_pyproject() -> dict:
    """Parse pyproject.toml using the stdlib (tomllib on 3.11+, else a minimal fallback)."""
    text = PYPROJECT.read_text(encoding="utf-8")
    try:
        import tomllib  # Python 3.11+

        return tomllib.loads(text)
    except ModuleNotFoundError:
        pass
    try:
        import tomli  # type: ignore

        return tomli.loads(text)
    except ModuleNotFoundError:
        pass

    # Minimal fallback: pull the values we actually need out of [project].
    import re

    name = re.search(r'(?m)^\s*name\s*=\s*"([^"]+)"', text)
    version = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', text)
    return {
        "project": {
            "name": name.group(1) if name else PRODUCT_NAME,
            "version": version.group(1) if version else "0.0.0",
        }
    }


def _version_tuple(version: str) -> tuple[int, int, int, int]:
    """Turn 'a.b.c' into a 4-int tuple (a, b, c, 0) for the VS_FIXEDFILEINFO fields."""
    parts: list[int] = []
    for chunk in version.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    parts = (parts + [0, 0, 0, 0])[:4]
    return tuple(parts)  # type: ignore[return-value]


def render_version_info() -> str:
    """Build the PyInstaller VSVersionInfo resource text from pyproject metadata."""
    data = _read_pyproject()
    project = data.get("project", {})
    version = str(project.get("version", "0.0.0"))
    vt = _version_tuple(version)

    return f"""# UTF-8
#
# PyInstaller version resource for the Imagura Windows executable.
#
# DO NOT EDIT BY HAND. This file is regenerated from pyproject.toml by
# tools/build_windows_exe.py on every build (and can be produced manually with
# `python tools/build_windows_exe.py --write-version-info`). Editing it directly
# will be overwritten on the next build.
#
# For more details about fixed file info 'ffi' see:
# http://msdn.microsoft.com/en-us/library/ms646997.aspx
VSVersionInfo(
  ffi=FixedFileInfo(
    # filevers and prodvers must be 4-tuples of 16-bit ints (a.b.c.d).
    filevers={vt},
    prodvers={vt},
    # Contains a bitmask that specifies the valid bits 'flags'
    mask=0x3f,
    flags=0x0,
    # The operating system for which this file was designed. 0x4 = NT.
    OS=0x40004,
    # The general type of file. 0x1 = application.
    fileType=0x1,
    # The function of the file. 0x0 = the function is not defined.
    subtype=0x0,
    # Creation date and time stamp.
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          # 040904B0: U.S. English, Unicode (1200) codepage.
          u'040904B0',
          [
            StringStruct(u'CompanyName', u'{COMPANY}'),
            StringStruct(u'FileDescription', u'{FILE_DESCRIPTION}'),
            StringStruct(u'FileVersion', u'{version}'),
            StringStruct(u'InternalName', u'{PRODUCT_NAME}'),
            StringStruct(u'LegalCopyright', u'Copyright (c) {COPYRIGHT_YEAR} {COMPANY}'),
            StringStruct(u'OriginalFilename', u'{PRODUCT_NAME}.exe'),
            StringStruct(u'ProductName', u'{PRODUCT_NAME}'),
            StringStruct(u'ProductVersion', u'{version}')
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [0x0409, 1200])])
  ]
)
"""


def write_version_info() -> Path:
    """Regenerate version_info.txt from pyproject so the resource never drifts."""
    content = render_version_info()
    VERSION_INFO.write_text(content, encoding="utf-8")
    print(f"[VERSION] wrote {VERSION_INFO}", flush=True)
    return VERSION_INFO


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Windows Imagura executable with PyInstaller.")
    parser.add_argument("--clean", action="store_true", help="Remove PyInstaller temporary build cache.")
    parser.add_argument("--debug-console", action="store_true", help="Build with a console window for diagnostics.")
    parser.add_argument(
        "--write-version-info",
        action="store_true",
        help="Regenerate version_info.txt from pyproject.toml and exit (no build).",
    )
    parser.add_argument("--codex-run-id", default="", help="Optional marker for long-running Codex build processes.")
    parser.add_argument(
        "--workpath",
        default=os.environ.get("IMAGURA_BUILD_WORKPATH", str(Path(tempfile.gettempdir()) / "imagura-pyinstaller-build")),
        help="PyInstaller temporary build directory.",
    )
    parser.add_argument(
        "--distpath",
        default=os.environ.get("IMAGURA_BUILD_DISTPATH", str(ROOT / "dist")),
        help="Directory where the built application is written.",
    )
    args = parser.parse_args()

    if args.write_version_info:
        write_version_info()
        return 0

    # Always regenerate the version resource from pyproject so it cannot drift.
    write_version_info()

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm"]
    if args.clean:
        cmd.append("--clean")
    if args.workpath:
        cmd.extend(["--workpath", args.workpath])
    if args.distpath:
        cmd.extend(["--distpath", args.distpath])
    cmd.append(str(SPEC))

    if args.codex_run_id:
        print(f"[RUN_ID] {args.codex_run_id}", flush=True)
    print("[BUILD] " + " ".join(cmd), flush=True)
    env = os.environ.copy()
    if args.debug_console:
        env["IMAGURA_BUILD_CONSOLE"] = "1"
    else:
        env.pop("IMAGURA_BUILD_CONSOLE", None)
    return subprocess.call(cmd, cwd=str(ROOT), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
