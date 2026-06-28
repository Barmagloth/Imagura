"""CPU hotspot profiling harness for Imagura's content pipeline.

Backlog item 6: "Profile before native rewrites."

This is a *self-contained* CPU benchmark. It times the documented native-rewrite
candidates from ``imagura/ARCHITECTURE.md`` ("Performance Policy"):

  * full-image CPU decode (the non-GPU part of the load path);
  * thumbnail decode + resize (single and batch);
  * animated GIF frame decode (per-frame and full GIF);
  * pixel/color format conversion (RGB<->RGBA via Pillow and via raylib).

IMPORTANT — what this harness can and cannot measure in CI / headless:

  * It CAN measure CPU-side decode/resize/convert work. raylib's image
    functions (``LoadImageFromMemory``, ``ImageResize``, ``ImageFormat``) run
    on the CPU and need no GPU window, so they are exercised here.
  * It CANNOT measure GPU texture upload (``LoadTextureFromImage`` /
    ``UpdateTexture``). Those require an OpenGL context from an open raylib
    window. This environment has no display/GPU, so the GPU-upload stage is
    reported as NOT MEASURED.

If no sample images are supplied (``--images DIR``), the harness GENERATES
synthetic test images at a few sizes so it runs with zero external assets.
Pillow is used when available; otherwise it falls back to writing raw BMP.

Runs are BOUNDED: small iteration counts plus a hard wall-clock cap so nothing
can run away.

Usage (bounded one-shot commands)::

    python tools/profile_hotspots.py
    python tools/profile_hotspots.py --iterations 5 --json
    python tools/profile_hotspots.py --images path/to/dir
    python tools/profile_hotspots.py --keep-temp   # keep generated samples
"""

from __future__ import annotations

import argparse
import io
import json
import os
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# --- Optional dependencies -------------------------------------------------

try:
    from PIL import Image as PILImage  # noqa: N814

    HAVE_PIL = True
except Exception:  # pragma: no cover - exercised only when Pillow missing
    PILImage = None  # type: ignore
    HAVE_PIL = False

try:
    from imagura.rl_compat import rl, RL_VERSION

    HAVE_RL = True
    RL_HAS_FFI = hasattr(rl, "ffi")
    # Silence raylib's per-decode INFO spam so the report table stays clean.
    try:
        rl.SetTraceLogLevel(getattr(rl, "LOG_WARNING", 4))
    except Exception:
        pass
except Exception:  # pragma: no cover - raylib not installed
    rl = None  # type: ignore
    RL_VERSION = "<none>"
    HAVE_RL = False
    RL_HAS_FFI = False

# Reuse the production helpers so we profile the *real* code paths.
try:
    from imagura.viewers.base import load_image_from_memory, _image_resize_mut

    HAVE_VIEWER_HELPERS = True
except Exception:  # pragma: no cover
    load_image_from_memory = None  # type: ignore
    _image_resize_mut = None  # type: ignore
    HAVE_VIEWER_HELPERS = False


# --- Bounded-run guard -----------------------------------------------------

#: Hard cap so a pathological case cannot run away. Checked between benchmarks.
DEFAULT_WALL_CAP_S = 90.0
#: Per-benchmark cap: stop iterating early once this much time is spent.
PER_BENCH_CAP_S = 8.0
#: Default iteration count per benchmark (kept small on purpose).
DEFAULT_ITERATIONS = 5


def now() -> float:
    return time.perf_counter()


# --- Result model ----------------------------------------------------------


@dataclass
class BenchResult:
    name: str
    stage: str  # cpu-decode | cpu-resize | cpu-convert | cpu-anim | gpu-upload
    iters: int
    ms_min: float
    ms_mean: float
    ms_median: float
    megapixels: float
    bytes_in: int
    notes: str = ""
    measured: bool = True

    @property
    def mp_per_s(self) -> float:
        if self.ms_mean <= 0:
            return 0.0
        return self.megapixels / (self.ms_mean / 1000.0)

    @property
    def mb_per_s(self) -> float:
        # Throughput against decoded RGBA bytes (megapixels * 4).
        if self.ms_mean <= 0:
            return 0.0
        rgba_mb = (self.megapixels * 1_000_000 * 4) / (1024 * 1024)
        return rgba_mb / (self.ms_mean / 1000.0)


def _timed(fn: Callable[[], Any], iters: int, cap_s: float) -> Tuple[List[float], int]:
    """Run ``fn`` up to ``iters`` times or until ``cap_s`` elapses.

    Returns (samples_ms, actual_iters). Always runs at least once.
    """
    samples: List[float] = []
    deadline = now() + cap_s
    n = 0
    while n < iters:
        start = now()
        fn()
        samples.append((now() - start) * 1000.0)
        n += 1
        if now() >= deadline:
            break
    return samples, n


def _make_result(
    name: str,
    stage: str,
    samples: List[float],
    iters: int,
    megapixels: float,
    bytes_in: int,
    notes: str = "",
) -> BenchResult:
    return BenchResult(
        name=name,
        stage=stage,
        iters=iters,
        ms_min=min(samples),
        ms_mean=statistics.fmean(samples),
        ms_median=statistics.median(samples),
        megapixels=megapixels,
        bytes_in=bytes_in,
        notes=notes,
    )


# --- Synthetic image generation -------------------------------------------

#: (label, width, height). Small / medium(1080p) / large(4K).
SYNTH_SIZES: List[Tuple[str, int, int]] = [
    ("small_256", 256, 256),
    ("medium_1080p", 1920, 1080),
    ("large_4k", 3840, 2160),
]


_RGB_CACHE: Dict[Tuple[int, int], bytes] = {}


def _synthetic_rgb_bytes(w: int, h: int) -> bytes:
    """Generate non-trivial RGB pixel data (gradient + noise-ish pattern).

    Avoids a flat color so JPEG/PNG sizes and decode costs are realistic.
    Uses numpy when available (fast); otherwise falls back to a bounded
    pure-Python loop. Results are cached per size so repeated benchmark setup
    does not regenerate large buffers.
    """
    cached = _RGB_CACHE.get((w, h))
    if cached is not None:
        return cached

    try:
        import numpy as np

        xs = np.arange(w, dtype=np.uint32)
        ys = np.arange(h, dtype=np.uint32)
        gx, gy = np.meshgrid(xs, ys)
        r = ((gx * 73 + gy * 17) & 0xFF).astype(np.uint8)
        g = ((gy * 131) & 0xFF).astype(np.uint8)
        b = ((gx ^ gy) & 0xFF).astype(np.uint8)
        arr = np.dstack((r, g, b))
        out = arr.tobytes()
    except Exception:
        out_ba = bytearray(w * h * 3)
        for y in range(h):
            ybyte = (y * 131) & 0xFF
            base = y * w * 3
            for x in range(w):
                i = base + x * 3
                out_ba[i] = (x * 73 + y * 17) & 0xFF
                out_ba[i + 1] = ybyte
                out_ba[i + 2] = (x ^ y) & 0xFF
        out = bytes(out_ba)

    _RGB_CACHE[(w, h)] = out
    return out


def _write_bmp(path: Path, w: int, h: int, rgb: bytes) -> None:
    """Minimal 24-bit BMP writer (fallback when Pillow is unavailable)."""
    import struct

    row_padded = (w * 3 + 3) & ~3
    pixel_bytes = row_padded * h
    file_size = 54 + pixel_bytes
    with open(path, "wb") as f:
        # BITMAPFILEHEADER
        f.write(b"BM")
        f.write(struct.pack("<IHHI", file_size, 0, 0, 54))
        # BITMAPINFOHEADER
        f.write(struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, pixel_bytes, 2835, 2835, 0, 0))
        pad = b"\x00" * (row_padded - w * 3)
        # BMP rows are bottom-up, pixels BGR.
        for y in range(h - 1, -1, -1):
            base = y * w * 3
            row = bytearray(w * 3)
            for x in range(w):
                i = base + x * 3
                row[x * 3] = rgb[i + 2]
                row[x * 3 + 1] = rgb[i + 1]
                row[x * 3 + 2] = rgb[i]
            f.write(row)
            f.write(pad)


@dataclass
class SampleSet:
    png: Dict[str, Path] = field(default_factory=dict)
    jpg: Dict[str, Path] = field(default_factory=dict)
    bmp: Dict[str, Path] = field(default_factory=dict)
    gif: Optional[Path] = None
    sizes: Dict[str, Tuple[int, int]] = field(default_factory=dict)


def generate_synthetic_samples(out_dir: Path) -> SampleSet:
    """Create synthetic PNG/JPEG/BMP + an animated GIF in ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = SampleSet()

    for label, w, h in SYNTH_SIZES:
        samples.sizes[label] = (w, h)
        rgb = _synthetic_rgb_bytes(w, h)
        if HAVE_PIL:
            im = PILImage.frombytes("RGB", (w, h), rgb)
            p_png = out_dir / f"{label}.png"
            im.save(p_png, format="PNG", compress_level=1)
            samples.png[label] = p_png

            p_jpg = out_dir / f"{label}.jpg"
            im.save(p_jpg, format="JPEG", quality=85)
            samples.jpg[label] = p_jpg

            p_bmp = out_dir / f"{label}.bmp"
            im.save(p_bmp, format="BMP")
            samples.bmp[label] = p_bmp
            im.close()
        else:
            p_bmp = out_dir / f"{label}.bmp"
            _write_bmp(p_bmp, w, h, rgb)
            samples.bmp[label] = p_bmp

    # Animated GIF: small frames, several of them (only with Pillow).
    if HAVE_PIL:
        gw, gh, nframes = 480, 270, 24
        frames = []
        for k in range(nframes):
            rgb = _synthetic_rgb_bytes(gw, gh)
            im = PILImage.frombytes("RGB", (gw, gh), rgb)
            # Shift palette each frame so deltas are real.
            im = im.point(lambda v, kk=k: (v + kk * 7) & 0xFF)
            frames.append(im.convert("P", palette=PILImage.ADAPTIVE))
        p_gif = out_dir / "anim_480x270_24f.gif"
        frames[0].save(
            p_gif,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=60,
            loop=0,
        )
        for fr in frames:
            fr.close()
        samples.gif = p_gif
        samples.sizes["gif"] = (gw, gh)

    return samples


# --- Benchmarks ------------------------------------------------------------


def bench_full_decode(samples: SampleSet, iters: int) -> List[BenchResult]:
    """Full-image CPU decode: raylib LoadImageFromMemory (the load_cpu core)."""
    results: List[BenchResult] = []
    if not (HAVE_RL and HAVE_VIEWER_HELPERS):
        return results

    for fmt_name, table in (("png", samples.png), ("jpg", samples.jpg)):
        for label, path in table.items():
            data = path.read_bytes()
            ext = path.suffix.lower()
            w, h = samples.sizes[label]
            mp = (w * h) / 1_000_000

            holder: Dict[str, Any] = {}

            def run(d=data, e=ext, hold=holder):
                img = load_image_from_memory(e, d)
                hold["img"] = img

            def cleanup(hold=holder):
                img = hold.pop("img", None)
                if img is not None:
                    try:
                        rl.UnloadImage(img)
                    except Exception:
                        pass

            samples_ms: List[float] = []
            deadline = now() + PER_BENCH_CAP_S
            n = 0
            while n < iters:
                start = now()
                run()
                samples_ms.append((now() - start) * 1000.0)
                cleanup()
                n += 1
                if now() >= deadline:
                    break

            results.append(
                _make_result(
                    f"full_decode {fmt_name} {label}",
                    "cpu-decode",
                    samples_ms,
                    n,
                    mp,
                    len(data),
                    notes=f"raylib LoadImageFromMemory ({w}x{h})",
                )
            )
    return results


def bench_thumbnail(samples: SampleSet, iters: int, target_h: int = 200) -> List[BenchResult]:
    """Thumbnail decode + resize (single). Mirrors BaseViewer.make_thumbnail CPU half."""
    results: List[BenchResult] = []
    if not (HAVE_RL and HAVE_VIEWER_HELPERS):
        return results

    for label, path in samples.png.items():
        data = path.read_bytes()
        ext = path.suffix.lower()
        w, h = samples.sizes[label]
        mp = (w * h) / 1_000_000
        scale = target_h / h
        tw, th = max(1, int(w * scale)), target_h

        def run(d=data, e=ext, tw=tw, th=th):
            img = load_image_from_memory(e, d)
            # _image_resize_mut mutates/realloc's the image's pixel buffer in
            # place; the original `img` struct's data pointer is freed by
            # ImageResize. Mirror production make_thumbnail() and only unload
            # the resized result (never both — that would double-free).
            rimg = _image_resize_mut(img, tw, th)
            try:
                rl.UnloadImage(rimg)
            except Exception:
                pass

        samples_ms, n = _timed(run, iters, PER_BENCH_CAP_S)
        results.append(
            _make_result(
                f"thumb decode+resize png {label}",
                "cpu-resize",
                samples_ms,
                n,
                mp,
                len(data),
                notes=f"decode {w}x{h} -> resize {tw}x{th}",
            )
        )
    return results


def bench_thumbnail_batch(samples: SampleSet, iters: int, target_h: int = 200, batch: int = 8) -> List[BenchResult]:
    """Thumbnail batch: decode+resize N images in a tight Python loop.

    This is the gallery-build pattern: many small thumbnails back to back.
    The Python per-iteration overhead is what a native batch op would remove.
    """
    results: List[BenchResult] = []
    if not (HAVE_RL and HAVE_VIEWER_HELPERS):
        return results
    if "small_256" not in samples.png:
        return results

    path = samples.png["small_256"]
    data = path.read_bytes()
    ext = path.suffix.lower()
    w, h = samples.sizes["small_256"]
    mp_total = (w * h * batch) / 1_000_000
    scale = target_h / h
    tw, th = max(1, int(w * scale)), target_h

    def run(d=data, e=ext, tw=tw, th=th, batch=batch):
        for _ in range(batch):
            img = load_image_from_memory(e, d)
            # See bench_thumbnail: only the resized result is unloaded.
            rimg = _image_resize_mut(img, tw, th)
            try:
                rl.UnloadImage(rimg)
            except Exception:
                pass

    samples_ms, n = _timed(run, iters, PER_BENCH_CAP_S)
    results.append(
        _make_result(
            f"thumb batch x{batch} small_256",
            "cpu-resize",
            samples_ms,
            n,
            mp_total,
            len(data) * batch,
            notes=f"{batch} thumbnails per op, {w}x{h} -> {tw}x{th}",
        )
    )
    return results


def bench_gif(samples: SampleSet, iters: int) -> List[BenchResult]:
    """Animated GIF decode: per-frame and full GIF (mirrors GifViewer.load_cpu)."""
    results: List[BenchResult] = []
    if not (HAVE_PIL and samples.gif):
        return results

    gw, gh = samples.sizes["gif"]
    path = samples.gif

    # --- Full GIF decode: open + seek + convert("RGBA") + tobytes for all frames.
    def run_full(p=path):
        pil = PILImage.open(p)
        n = getattr(pil, "n_frames", 1)
        for i in range(n):
            pil.seek(i)
            frame = pil.convert("RGBA")
            _ = frame.tobytes()
        pil.close()

    samples_ms, niter = _timed(run_full, iters, PER_BENCH_CAP_S)
    # Determine frame count once for megapixel accounting.
    pil = PILImage.open(path)
    nframes = getattr(pil, "n_frames", 1)
    pil.close()
    mp_full = (gw * gh * nframes) / 1_000_000
    results.append(
        _make_result(
            f"gif full decode ({nframes}f)",
            "cpu-anim",
            samples_ms,
            niter,
            mp_full,
            path.stat().st_size,
            notes=f"Pillow seek+convert RGBA+tobytes, {gw}x{gh} x{nframes}",
        )
    )

    # --- Per-frame decode: convert one frame to RGBA bytes.
    def run_one(p=path):
        pil = PILImage.open(p)
        pil.seek(0)
        frame = pil.convert("RGBA")
        _ = frame.tobytes()
        pil.close()

    samples_ms, niter = _timed(run_one, iters, PER_BENCH_CAP_S)
    mp_one = (gw * gh) / 1_000_000
    results.append(
        _make_result(
            "gif per-frame decode (1f)",
            "cpu-anim",
            samples_ms,
            niter,
            mp_one,
            path.stat().st_size,
            notes=f"open+seek(0)+convert RGBA+tobytes, {gw}x{gh}",
        )
    )
    return results


def bench_color_convert(samples: SampleSet, iters: int) -> List[BenchResult]:
    """Pixel/color format conversion: RGB<->RGBA via Pillow and via raylib."""
    results: List[BenchResult] = []

    for label in ("small_256", "medium_1080p", "large_4k"):
        if label not in samples.sizes:
            continue
        w, h = samples.sizes[label]
        mp = (w * h) / 1_000_000
        rgb = _synthetic_rgb_bytes(w, h) if not HAVE_PIL else None

        # --- Pillow RGB -> RGBA convert + tobytes (the GIF/WebP convert path).
        if HAVE_PIL:
            base = PILImage.frombytes("RGB", (w, h), _synthetic_rgb_bytes(w, h))

            def run_pil_rgba(b=base):
                _ = b.convert("RGBA").tobytes()

            samples_ms, n = _timed(run_pil_rgba, iters, PER_BENCH_CAP_S)
            results.append(
                _make_result(
                    f"convert PIL RGB->RGBA {label}",
                    "cpu-convert",
                    samples_ms,
                    n,
                    mp,
                    w * h * 3,
                    notes="Pillow .convert('RGBA').tobytes()",
                )
            )

            # --- Pillow RGBA -> RGB (drop alpha).
            base_rgba = base.convert("RGBA")

            def run_pil_rgb(b=base_rgba):
                _ = b.convert("RGB").tobytes()

            samples_ms, n = _timed(run_pil_rgb, iters, PER_BENCH_CAP_S)
            results.append(
                _make_result(
                    f"convert PIL RGBA->RGB {label}",
                    "cpu-convert",
                    samples_ms,
                    n,
                    mp,
                    w * h * 4,
                    notes="Pillow .convert('RGB').tobytes()",
                )
            )
            base.close()
            base_rgba.close()

        # --- raylib ImageFormat: in-place pixel format transform (C-side).
        if HAVE_RL and HAVE_VIEWER_HELPERS and HAVE_PIL:
            png_buf = io.BytesIO()
            PILImage.frombytes("RGB", (w, h), _synthetic_rgb_bytes(w, h)).save(
                png_buf, format="PNG", compress_level=1
            )
            png_data = png_buf.getvalue()
            UNCOMPRESSED_R8G8B8A8 = getattr(rl, "PIXELFORMAT_UNCOMPRESSED_R8G8B8A8", 7)

            # Decode-only baseline so the ImageFormat convert cost can be isolated.
            def run_decode_only(d=png_data):
                img = load_image_from_memory(".png", d)
                try:
                    rl.UnloadImage(img)
                except Exception:
                    pass

            base_ms, _ = _timed(run_decode_only, iters, PER_BENCH_CAP_S)
            decode_mean = statistics.fmean(base_ms)

            def run_rl_fmt(d=png_data, fmt=UNCOMPRESSED_R8G8B8A8):
                img = load_image_from_memory(".png", d)
                if RL_HAS_FFI:
                    p = rl.ffi.new("Image *", img)
                    rl.ImageFormat(p, fmt)
                    out = p[0]
                else:
                    import ctypes

                    rl.ImageFormat(ctypes.byref(img), fmt)
                    out = img
                try:
                    rl.UnloadImage(out)
                except Exception:
                    pass

            samples_ms, n = _timed(run_rl_fmt, iters, PER_BENCH_CAP_S)
            convert_only_mean = max(0.0, statistics.fmean(samples_ms) - decode_mean)
            results.append(
                _make_result(
                    f"convert raylib ->RGBA8 {label}",
                    "cpu-convert",
                    samples_ms,
                    n,
                    mp,
                    len(png_data),
                    notes=(
                        f"raylib LoadImageFromMemory + ImageFormat; "
                        f"decode_baseline~{decode_mean:.2f}ms, "
                        f"convert_only~{convert_only_mean:.2f}ms"
                    ),
                )
            )
    return results


def gpu_upload_placeholder() -> BenchResult:
    """GPU texture upload is NOT MEASURED in a headless environment."""
    return BenchResult(
        name="gpu texture upload (LoadTextureFromImage / UpdateTexture)",
        stage="gpu-upload",
        iters=0,
        ms_min=0.0,
        ms_mean=0.0,
        ms_median=0.0,
        megapixels=0.0,
        bytes_in=0,
        notes="NOT MEASURED: requires an open raylib/OpenGL window (no display/GPU here)",
        measured=False,
    )


# --- Output ----------------------------------------------------------------


def print_table(results: List[BenchResult]) -> None:
    header = (
        f"{'benchmark':<34} {'stage':<11} {'iters':>5} "
        f"{'min_ms':>9} {'mean_ms':>9} {'MP/s':>8} {'MB/s':>9}"
    )
    print(header)
    print("-" * len(header))
    for r in results:
        if not r.measured:
            print(f"{r.name:<34} {r.stage:<11} {'-':>5} {'-':>9} {'-':>9} {'-':>8} {'-':>9}")
            print(f"    {r.notes}")
            continue
        print(
            f"{r.name:<34} {r.stage:<11} {r.iters:>5} "
            f"{r.ms_min:>9.3f} {r.ms_mean:>9.3f} {r.mp_per_s:>8.1f} {r.mb_per_s:>9.1f}"
        )
        if r.notes:
            print(f"    {r.notes}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Imagura CPU hotspot profiler.")
    parser.add_argument(
        "--images",
        default=None,
        help="Directory of real sample images. If omitted, synthetic images are generated.",
    )
    parser.add_argument(
        "--iterations", type=int, default=DEFAULT_ITERATIONS, help="Iterations per benchmark."
    )
    parser.add_argument("--target-h", type=int, default=200, help="Thumbnail target height (px).")
    parser.add_argument("--batch", type=int, default=8, help="Thumbnails per batch op.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    parser.add_argument(
        "--keep-temp", action="store_true", help="Keep generated synthetic images for inspection."
    )
    parser.add_argument(
        "--wall-cap", type=float, default=DEFAULT_WALL_CAP_S, help="Hard wall-clock cap (seconds)."
    )
    args = parser.parse_args()

    iters = max(1, min(50, int(args.iterations)))  # bounded
    started = now()

    env = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "have_pil": HAVE_PIL,
        "pil_version": getattr(PILImage, "__version__", None) if HAVE_PIL else None,
        "have_raylib": HAVE_RL,
        "raylib_binding": RL_VERSION if HAVE_RL else None,
        "raylib_ffi": RL_HAS_FFI,
    }

    tmp_dir: Optional[tempfile.TemporaryDirectory] = None
    if args.images:
        sample_root = Path(args.images)
        samples = _load_real_samples(sample_root)
        sample_note = f"real images from {sample_root}"
    else:
        if args.keep_temp:
            sample_path = ROOT / "tools" / "_synthetic_samples"
            samples = generate_synthetic_samples(sample_path)
            sample_note = f"synthetic images in {sample_path}"
        else:
            tmp_dir = tempfile.TemporaryDirectory(prefix="imagura_prof_")
            samples = generate_synthetic_samples(Path(tmp_dir.name))
            sample_note = "synthetic images (temp dir)"

    results: List[BenchResult] = []

    def maybe_run(fn: Callable[[], List[BenchResult]]):
        if now() - started >= args.wall_cap:
            return
        results.extend(fn())

    maybe_run(lambda: bench_full_decode(samples, iters))
    maybe_run(lambda: bench_thumbnail(samples, iters, args.target_h))
    maybe_run(lambda: bench_thumbnail_batch(samples, iters, args.target_h, args.batch))
    maybe_run(lambda: bench_gif(samples, iters))
    maybe_run(lambda: bench_color_convert(samples, iters))
    results.append(gpu_upload_placeholder())

    total_s = now() - started

    if tmp_dir is not None:
        tmp_dir.cleanup()

    if args.json:
        payload = {
            "env": env,
            "sample_note": sample_note,
            "iterations": iters,
            "total_seconds": round(total_s, 3),
            "results": [asdict(r) | {"mp_per_s": r.mp_per_s, "mb_per_s": r.mb_per_s} for r in results],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"env: python={env['python']} pil={env['pil_version']} "
              f"raylib={env['raylib_binding']} (ffi={env['raylib_ffi']})")
        print(f"samples: {sample_note}")
        print(f"iterations/bench: {iters}   total_wall: {total_s:.2f}s "
              f"(cap {args.wall_cap:.0f}s)\n")
        print_table(results)

    return 0


def _load_real_samples(root: Path) -> SampleSet:
    """Build a SampleSet from a directory of real images (best effort)."""
    samples = SampleSet()
    if not root.is_dir():
        print(f"WARNING: {root} is not a directory; no real samples loaded.", file=sys.stderr)
        return samples
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        label = path.stem
        if HAVE_PIL:
            try:
                with PILImage.open(path) as im:
                    samples.sizes[label] = im.size
                    is_anim = getattr(im, "is_animated", False)
            except Exception:
                continue
        else:
            samples.sizes[label] = (0, 0)
            is_anim = False
        if ext in (".png",):
            samples.png[label] = path
        elif ext in (".jpg", ".jpeg"):
            samples.jpg[label] = path
        elif ext == ".bmp":
            samples.bmp[label] = path
        elif ext == ".gif" and is_anim and samples.gif is None:
            samples.gif = path
            samples.sizes["gif"] = samples.sizes.get(label, (0, 0))
    return samples


if __name__ == "__main__":
    raise SystemExit(main())
