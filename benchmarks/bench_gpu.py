"""GPU/raylib performance benchmarks for Imagura.

REQUIRES: Windows with display + raylib installed.
Run on your machine: python benchmarks/bench_gpu.py [path_to_images_dir]

Measures:
  1. load_image_cpu_only   — file read + decode + resize (CPU)
  2. LoadTextureFromImage   — CPU→GPU texture upload
  3. Gallery scroll latency — simulated thumbnail navigation at N=5K files
"""
from __future__ import annotations

import os
import sys
import time
import glob
import statistics
from typing import List, Tuple

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def find_test_images(directory: str, limit: int = 50) -> List[str]:
    """Find image files in directory for benchmarking."""
    from imagura.config import IMG_EXTS
    images = []
    for f in os.listdir(directory):
        if os.path.splitext(f)[1].lower() in IMG_EXTS:
            images.append(os.path.join(directory, f))
            if len(images) >= limit:
                break
    return images


def _bench(func, rounds, label):
    times = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        func()
        times.append((time.perf_counter() - t0) * 1000)
    med = statistics.median(times)
    lo, hi = min(times), max(times)
    print(f"  {label:.<55s} median={med:.3f}ms  min={lo:.3f}ms  max={hi:.3f}ms  (n={rounds})")
    return med


def main():
    # Try importing raylib — will fail without proper setup
    try:
        from imagura.rl_compat import rl
    except Exception as e:
        print(f"ERROR: Cannot import raylib: {e}")
        print("This benchmark requires Windows with raylib installed.")
        print("Install: pip install raylib")
        sys.exit(1)

    img_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    images = find_test_images(img_dir)

    if not images:
        print(f"No images found in {img_dir}")
        print("Usage: python benchmarks/bench_gpu.py <path_to_images_dir>")
        sys.exit(1)

    print("=" * 70)
    print("Imagura GPU Performance Benchmarks")
    print(f"Images directory: {img_dir} ({len(images)} files)")
    print("=" * 70)

    # Minimal raylib window for GPU context
    rl.SetConfigFlags(rl.FLAG_WINDOW_HIDDEN)
    rl.InitWindow(800, 600, b"Imagura Benchmark")
    rl.SetTargetFPS(0)  # Uncapped for benchmarking

    try:
        # ---------------------------------------------------------------
        # 1. CPU image decode
        # ---------------------------------------------------------------
        print("\n[1] CPU Image Decode (load_image_cpu_only)")

        # Import after raylib init
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

        # We'll use raylib's LoadImage directly
        from imagura.config import MAX_IMAGE_DIMENSION, MAX_FILE_SIZE_MB

        def bench_decode(path):
            img = rl.LoadImage(path.encode())
            if img.data:
                # Check if resize needed (mirrors load_image_cpu_only logic)
                w, h = img.width, img.height
                max_dim = MAX_IMAGE_DIMENSION
                if w > max_dim or h > max_dim:
                    ratio = max_dim / max(w, h)
                    new_w = int(w * ratio)
                    new_h = int(h * ratio)
                    rl.ImageResize(rl.byref(img) if hasattr(rl, 'byref') else img, new_w, new_h)
                rl.UnloadImage(img)

        # Categorize images by size
        small, medium, large = [], [], []
        for p in images:
            sz = os.path.getsize(p)
            if sz < 500_000:
                small.append(p)
            elif sz < 5_000_000:
                medium.append(p)
            else:
                large.append(p)

        if small:
            sample = small[0]
            sz_kb = os.path.getsize(sample) / 1024
            _bench(lambda: bench_decode(sample), rounds=min(50, len(small) * 10),
                   label=f"Small image ({sz_kb:.0f}KB)")

        if medium:
            sample = medium[0]
            sz_mb = os.path.getsize(sample) / (1024 * 1024)
            _bench(lambda: bench_decode(sample), rounds=min(20, len(medium) * 5),
                   label=f"Medium image ({sz_mb:.1f}MB)")

        if large:
            sample = large[0]
            sz_mb = os.path.getsize(sample) / (1024 * 1024)
            _bench(lambda: bench_decode(sample), rounds=min(10, len(large) * 3),
                   label=f"Large image ({sz_mb:.1f}MB)")

        # ---------------------------------------------------------------
        # 2. Texture upload (CPU → GPU)
        # ---------------------------------------------------------------
        print("\n[2] Texture Upload (LoadTextureFromImage)")

        def bench_texture_upload(path):
            img = rl.LoadImage(path.encode())
            if img.data:
                tex = rl.LoadTextureFromImage(img)
                rl.UnloadImage(img)
                if tex.id > 0:
                    rl.UnloadTexture(tex)

        if images:
            sample = images[0]
            _bench(lambda: bench_texture_upload(sample), rounds=30,
                   label=f"Upload {os.path.basename(sample)}")

        if medium:
            sample = medium[0]
            _bench(lambda: bench_texture_upload(sample), rounds=15,
                   label=f"Upload medium ({os.path.getsize(sample) / (1024*1024):.1f}MB)")

        # ---------------------------------------------------------------
        # 3. Simulated gallery scroll (thumbnail cache lookup throughput)
        # ---------------------------------------------------------------
        print("\n[3] Gallery Simulation")

        from collections import OrderedDict
        from imagura.types import BitmapThumb

        def bench_gallery_cache_lookup(n_files):
            """Simulate scrolling through N thumbnails with OrderedDict cache."""
            cache = OrderedDict()
            # Pre-populate cache
            for i in range(min(n_files, 400)):  # THUMB_CACHE_LIMIT
                path = f"/fake/dir/image_{i:05d}.jpg"
                cache[path] = BitmapThumb(texture=None, size=(120, 80), src_path=path, ready=True)

            # Simulate scroll: lookup 100 consecutive thumbs
            hits = 0
            for i in range(100):
                path = f"/fake/dir/image_{i + 150:05d}.jpg"
                if path in cache:
                    cache.move_to_end(path)
                    hits += 1

        _bench(lambda: bench_gallery_cache_lookup(5000), rounds=200,
               label="Cache lookup 100 thumbs (N=5K files)")

        # ---------------------------------------------------------------
        # 4. Frame timing (empty frame)
        # ---------------------------------------------------------------
        print("\n[4] Frame Overhead")

        def bench_empty_frame():
            rl.BeginDrawing()
            rl.ClearBackground(rl.BLACK)
            rl.EndDrawing()

        _bench(bench_empty_frame, rounds=100, label="Empty frame (BeginDrawing+EndDrawing)")

    finally:
        rl.CloseWindow()

    print("\n" + "=" * 70)
    print("Done. For realistic results, test with your actual image collection.")


if __name__ == "__main__":
    main()
