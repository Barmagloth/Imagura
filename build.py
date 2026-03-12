"""Build script for Imagura.

Creates a standalone Windows executable using PyInstaller,
then optionally builds an installer using Inno Setup.

Usage:
    python build.py              # Build .exe only
    python build.py --installer  # Build .exe + Inno Setup installer
    python build.py --clean      # Clean build artifacts
    python build.py --onefile    # Build single-file .exe (slower startup)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(PROJECT_ROOT, "dist")
BUILD_DIR = os.path.join(PROJECT_ROOT, "build")
SPEC_FILE = os.path.join(PROJECT_ROOT, "installer", "imagura.spec")
ISS_FILE = os.path.join(PROJECT_ROOT, "installer", "imagura_setup.iss")


def clean():
    """Remove build artifacts."""
    for d in [DIST_DIR, BUILD_DIR]:
        if os.path.exists(d):
            print(f"Removing {d}")
            shutil.rmtree(d)
    # Remove __pycache__ dirs
    for root, dirs, _ in os.walk(PROJECT_ROOT):
        for d in dirs:
            if d == "__pycache__":
                path = os.path.join(root, d)
                print(f"Removing {path}")
                shutil.rmtree(path)
    print("Clean complete.")


def check_pyinstaller():
    """Check if PyInstaller is installed."""
    try:
        import PyInstaller
        print(f"PyInstaller {PyInstaller.__version__} found.")
        return True
    except ImportError:
        print("ERROR: PyInstaller not installed.")
        print("Install it: pip install pyinstaller")
        return False


def check_inno_setup() -> str | None:
    """Find Inno Setup compiler. Returns path or None."""
    # Common install locations
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path

    # Try PATH
    result = shutil.which("ISCC")
    if result:
        return result

    return None


def build_exe(onefile=False):
    """Build executable with PyInstaller."""
    if not check_pyinstaller():
        return False

    print("\n" + "=" * 60)
    print("Building Imagura executable...")
    print("=" * 60 + "\n")

    if onefile:
        # Single-file mode (slower startup, but one file)
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",
            "--windowed",
            "--name", "Imagura",
            "--add-data", f"imagura{os.pathsep}imagura",
            "--hidden-import", "raylib",
            "--hidden-import", "imagura.user_config",
            "--hidden-import", "imagura.state.app_state",
            "--exclude-module", "tkinter",
            "--exclude-module", "matplotlib",
            "--exclude-module", "numpy",
            "--exclude-module", "pytest",
        ]
        # Add icon if exists
        ico = os.path.join(PROJECT_ROOT, "installer", "imagura.ico")
        if os.path.exists(ico):
            cmd.extend(["--icon", ico])
        # Add version info
        vi = os.path.join(PROJECT_ROOT, "installer", "version_info.txt")
        if os.path.exists(vi):
            cmd.extend(["--version-file", vi])

        cmd.append("imagura2.py")
    else:
        # Directory mode (faster startup, used by installer)
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm",
            SPEC_FILE,
        ]

    print(f"Running: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("\nERROR: PyInstaller build failed!")
        return False

    print("\nBuild successful!")

    # Show output location
    if onefile:
        exe_path = os.path.join(DIST_DIR, "Imagura.exe")
    else:
        exe_path = os.path.join(DIST_DIR, "Imagura", "Imagura.exe")

    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"Output: {exe_path} ({size_mb:.1f} MB)")
    else:
        print(f"Output directory: {DIST_DIR}")

    return True


def build_installer():
    """Build Inno Setup installer."""
    iscc = check_inno_setup()
    if not iscc:
        print("\nWARNING: Inno Setup not found. Skipping installer build.")
        print("Install Inno Setup 6 from: https://jrsoftware.org/isdl.php")
        print("Or download portable: https://jrsoftware.org/ispack.php")
        return False

    print(f"\nInno Setup found: {iscc}")

    # Check that PyInstaller output exists
    app_dir = os.path.join(DIST_DIR, "Imagura")
    if not os.path.isdir(app_dir):
        print(f"ERROR: PyInstaller output not found at {app_dir}")
        print("Run 'python build.py' first to build the executable.")
        return False

    print("\n" + "=" * 60)
    print("Building Imagura installer...")
    print("=" * 60 + "\n")

    cmd = [iscc, ISS_FILE]
    print(f"Running: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("\nERROR: Inno Setup build failed!")
        return False

    # Find output
    setup_exe = os.path.join(DIST_DIR, "Imagura_Setup_2.0.0.exe")
    if os.path.exists(setup_exe):
        size_mb = os.path.getsize(setup_exe) / (1024 * 1024)
        print(f"\nInstaller: {setup_exe} ({size_mb:.1f} MB)")
    else:
        print(f"\nInstaller built in: {DIST_DIR}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Build Imagura for Windows")
    parser.add_argument("--installer", action="store_true", help="Also build Inno Setup installer")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts")
    parser.add_argument("--onefile", action="store_true", help="Build single-file .exe")
    args = parser.parse_args()

    os.chdir(PROJECT_ROOT)

    if args.clean:
        clean()
        return

    print("Imagura Build System")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Project: {PROJECT_ROOT}")

    if sys.platform != "win32":
        print("\nWARNING: Building on non-Windows platform.")
        print("The resulting executable will only work on Windows.")
        print("For best results, build on Windows.\n")

    # Step 1: Build .exe
    if not build_exe(onefile=args.onefile):
        sys.exit(1)

    # Step 2: Build installer (if requested)
    if args.installer:
        if args.onefile:
            print("\nWARNING: --installer requires directory mode (without --onefile).")
            print("Rebuilding in directory mode for installer...")
            if not build_exe(onefile=False):
                sys.exit(1)
        if not build_installer():
            print("\nExecutable was built successfully, but installer failed.")
            sys.exit(1)

    print("\n" + "=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)

    if args.installer:
        print("\nDeliverables:")
        print(f"  Portable:  dist/Imagura/Imagura.exe")
        print(f"  Installer: dist/Imagura_Setup_2.0.0.exe")
    elif args.onefile:
        print(f"\n  Portable: dist/Imagura.exe")
    else:
        print(f"\n  Portable: dist/Imagura/Imagura.exe")
        print(f"\n  Tip: run 'python build.py --installer' to also create a Setup installer.")


if __name__ == "__main__":
    main()
