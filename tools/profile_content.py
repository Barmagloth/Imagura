"""Profile Imagura CPU-side content loading over a directory of real files.

This scans a folder and times per-file probe / heaviness / full CPU decode via
the production viewer registry. It needs actual image files on disk.

For a self-contained CPU *hotspot* benchmark that needs zero external assets
(it generates synthetic images) and times the documented native-rewrite
candidates from ``imagura/ARCHITECTURE.md`` (full decode, thumbnail
decode+resize, animated GIF decode, RGB<->RGBA conversion), use the companion
harness instead::

    python tools/profile_hotspots.py
    python tools/profile_hotspots.py --json

See ``docs/profiling.md`` for methodology, measured numbers, and the
native-rewrite recommendation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image

from imagura.config import MAX_ANIM_FRAMES, MAX_ANIM_MEMORY_MB, MAX_IMAGE_DIMENSION
from imagura.image_utils import list_supported_files
from imagura.viewers import get_registry


def now() -> float:
    return time.perf_counter()


def elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0


def file_size_mb(path: str) -> float:
    try:
        return os.path.getsize(path) / (1024 * 1024)
    except OSError:
        return 0.0


def estimate_animation_budget(path: str) -> Optional[Dict[str, Any]]:
    try:
        with Image.open(path) as img:
            if not getattr(img, "is_animated", False):
                return None

            frames = int(getattr(img, "n_frames", 1))
            width, height = img.size
    except Exception as exc:
        return {"error": repr(exc)}

    out_w, out_h = width, height
    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        scale = min(MAX_IMAGE_DIMENSION / width, MAX_IMAGE_DIMENSION / height)
        out_w = max(1, int(width * scale))
        out_h = max(1, int(height * scale))

    bytes_per_frame = max(1, out_w * out_h * 4)
    max_frames_by_memory = max(1, int((MAX_ANIM_MEMORY_MB * 1024 * 1024) // bytes_per_frame))
    kept_frames = min(frames, MAX_ANIM_FRAMES, max_frames_by_memory)

    return {
        "frames": frames,
        "kept_frames": kept_frames,
        "width": width,
        "height": height,
        "decoded_mb_full": frames * bytes_per_frame / (1024 * 1024),
        "decoded_mb_kept": kept_frames * bytes_per_frame / (1024 * 1024),
    }


def profile_one(path: str, decode: bool) -> Dict[str, Any]:
    registry = get_registry()
    viewer = registry.get_viewer(path)
    ext = Path(path).suffix.lower()
    row: Dict[str, Any] = {
        "path": path,
        "name": Path(path).name,
        "ext": ext,
        "size_mb": file_size_mb(path),
        "viewer": viewer.name() if viewer else None,
        "probe_ms": None,
        "heavy_ms": None,
        "decode_ms": None,
        "decode_peak_py_mb": None,
        "heavy": None,
        "error": None,
        "animation": estimate_animation_budget(path) if ext in {".gif", ".webp"} else None,
    }

    if viewer is None:
        row["error"] = "no viewer"
        return row

    start = now()
    try:
        row["dimensions"] = viewer.probe_dimensions(path)
    except Exception as exc:
        row["error"] = repr(exc)
    row["probe_ms"] = elapsed_ms(start)

    start = now()
    try:
        row["heavy"] = viewer.is_heavy(path)
    except Exception as exc:
        row["error"] = repr(exc)
    row["heavy_ms"] = elapsed_ms(start)

    if not decode:
        return row

    loaded = None
    tracemalloc.start()
    start = now()
    try:
        loaded = viewer.load_cpu(path)
        row["decode_ms"] = elapsed_ms(start)
        _, peak = tracemalloc.get_traced_memory()
        row["decode_peak_py_mb"] = peak / (1024 * 1024)
    except Exception as exc:
        row["decode_ms"] = elapsed_ms(start)
        row["error"] = repr(exc)
    finally:
        try:
            if loaded is not None:
                viewer.cleanup_cpu_data(loaded)
        finally:
            tracemalloc.stop()

    return row


def print_table(rows: List[Dict[str, Any]], scan_ms: float, total_files: int) -> None:
    print(f"scan_ms={scan_ms:.2f} total_files={total_files} profiled={len(rows)}")
    print("decode_ms probe_ms peak_py_mb size_mb heavy viewer ext name")
    for row in rows:
        decode_ms = row["decode_ms"]
        probe_ms = row["probe_ms"]
        peak = row["decode_peak_py_mb"]
        print(
            f"{decode_ms if decode_ms is not None else -1:9.2f} "
            f"{probe_ms if probe_ms is not None else -1:8.2f} "
            f"{peak if peak is not None else -1:10.2f} "
            f"{row['size_mb']:7.2f} "
            f"{str(row['heavy']):5} "
            f"{row['viewer'] or '-':7} "
            f"{row['ext']:5} "
            f"{row['name']}"
        )
        if row.get("animation"):
            print(f"  animation={row['animation']}")
        if row.get("error"):
            print(f"  error={row['error']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile Imagura CPU-side content loading.")
    parser.add_argument("path", nargs="?", default=".", help="Directory to scan.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum files to profile.")
    parser.add_argument("--no-decode", action="store_true", help="Only scan/probe, skip CPU decode.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    args = parser.parse_args()

    root = os.path.abspath(args.path)
    start = now()
    files = list_supported_files(root)
    scan_ms = elapsed_ms(start)
    selected = files[: max(0, args.limit)]

    rows = [profile_one(path, decode=not args.no_decode) for path in selected]
    rows.sort(key=lambda row: row["decode_ms"] if row["decode_ms"] is not None else -1, reverse=True)

    if args.json:
        print(json.dumps({"scan_ms": scan_ms, "total_files": len(files), "rows": rows}, ensure_ascii=False, indent=2))
    else:
        print_table(rows, scan_ms, len(files))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
