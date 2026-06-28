# CPU Profiling: Hotspots & Native-Rewrite Decision

Backlog item 6 — *"Profile before native rewrites."*

This document records a CPU-side profiling pass over Imagura's content pipeline
and gives a per-candidate recommendation against the
[Performance Policy](../imagura/ARCHITECTURE.md) ("only introduce C/Rust when
profiling shows Python overhead in a tight loop").

**Bottom line:** none of the documented native-rewrite candidates is justified
yet. Every measured hotspot is already executing inside a C library (raylib's
`stb_image` decoder or Pillow), not in a Python loop. A C/Rust rewrite would
replace one C decoder with another and save little. The remaining wins are
algorithmic/ownership fixes (decode less, cache smarter, persist thumbnails),
which the policy explicitly says to do first.

---

## 1. Methodology

### Harness

`tools/profile_hotspots.py` is a self-contained CPU benchmark. It exercises the
**real production code paths** (it imports `imagura.viewers.base`'s
`load_image_from_memory` / `_image_resize_mut` and uses Pillow exactly as the
viewers do) and times the four documented candidate stages:

1. **Full-image CPU decode** — `raylib LoadImageFromMemory` (the non-GPU core of
   `ImageViewer.load_cpu`).
2. **Thumbnail decode + resize** — decode then `ImageResize`, single and batched
   (the CPU half of `BaseViewer.make_thumbnail`).
3. **Animated GIF decode** — Pillow `open`/`seek`/`convert("RGBA")`/`tobytes`,
   per-frame and full GIF (mirrors `GifViewer.load_cpu`).
4. **Pixel/color format conversion** — RGB↔RGBA via Pillow `.convert()` and via
   raylib `ImageFormat` (with a decode-only baseline subtracted to isolate the
   convert cost).

If no real images are passed, the harness **generates synthetic images**
(numpy-vectorised gradient pattern, Pillow encode) at three sizes — small 256²,
medium 1080p (1920×1080), large 4K (3840×2160) — plus a 24-frame 480×270 GIF, so
it runs with zero external assets. A `--images DIR` flag profiles real files.

Timing uses `time.perf_counter`. Each benchmark reports `min_ms`, `mean_ms`,
`MP/s` (megapixels of source per second) and `MB/s` (decoded RGBA throughput).
Runs are **bounded**: small iteration counts, an 8 s per-benchmark cap, and a
90 s hard wall-clock cap. The full run completes in ~11 s.

### Commands

```bash
# Default: synthetic images, table output (this is what produced the numbers below)
python tools/profile_hotspots.py --iterations 9

# JSON for machine consumption
python tools/profile_hotspots.py --json

# Profile a directory of real images instead of synthetic ones
python tools/profile_hotspots.py --images path/to/images

# Keep the generated synthetic samples for inspection
python tools/profile_hotspots.py --keep-temp
```

The older `tools/profile_content.py` remains for scanning a directory of real
files (per-file probe / heaviness / decode + peak Python memory). It needs
images on disk; `profile_hotspots.py` does not.

### Environment

| Field | Value |
|---|---|
| OS | Windows 10, x64 |
| Python | 3.13.1 |
| Pillow | 12.0.0 |
| raylib binding | `raylib` CFFI (STATIC 5.5.0.4); `raylibpy` not installed |
| numpy | 2.4.3 (synthetic-image generation only) |
| Display / GPU | **none** (headless) |

> **raylib binding note.** This box has the CFFI `raylib` binding, not
> `raylibpy`. `rl_compat` reports it as `"python-raylib"` but `hasattr(rl,"ffi")`
> is true, so the FFI image paths are the ones exercised. raylib's image
> functions (`LoadImageFromMemory`, `ImageResize`, `ImageFormat`) are pure-CPU
> and run fine without a window.

---

## 2. What can and cannot be measured headless

| Stage | Where it runs | Measured here? |
|---|---|---|
| Full-image decode (`LoadImageFromMemory`) | CPU (stb_image, in raylib C) | ✅ yes |
| Resize (`ImageResize`) | CPU (raylib C) | ✅ yes |
| Animated GIF decode (Pillow) | CPU (Pillow C) | ✅ yes |
| RGB↔RGBA conversion (Pillow / `ImageFormat`) | CPU | ✅ yes |
| **GPU texture upload** (`LoadTextureFromImage`, `UpdateTexture`) | **GPU** | ❌ **NOT MEASURED** |

**GPU texture upload is NOT MEASURED.** `LoadTextureFromImage` and the
per-frame `UpdateTexture` used by animated playback require an active
OpenGL context, which only exists once a raylib **window** is open. This
environment has no display/GPU, so those calls cannot run here. The harness
emits an explicit `NOT MEASURED` row for them rather than faking a number.

This matters for the policy decision: the *upload* side of the pipeline is the
one place where a tight per-frame loop touches the GPU, and it is exactly the
part we could not profile. Any future decision about animated-playback
performance must be re-profiled **on a machine with a display** (open a window,
time `UpdateTexture` per frame). See §6.

---

## 3. Measured numbers

Synthetic images, 9 iterations per benchmark, full run ≈ 11 s.
`MP/s` = source megapixels per second; `MB/s` = decoded RGBA MB per second
(higher is better). Numbers vary ±10–15 % run to run (small iteration counts,
Windows scheduler); use them as orders of magnitude, not precise constants.

### Full-image CPU decode (raylib `LoadImageFromMemory`)

| Input | Size | mean ms | MP/s |
|---|---|---:|---:|
| PNG | 256×256 | 0.55 | 119 |
| PNG | 1920×1080 (2.1 MP) | 17.3 | 120 |
| PNG | 3840×2160 (8.3 MP) | 66.2 | 125 |
| JPEG | 256×256 | 0.72 | 91 |
| JPEG | 1920×1080 | 21.6 | 96 |
| JPEG | 3840×2160 | 87.1 | 95 |

Decode cost is **linear in pixel count** (constant ~120 MP/s PNG, ~95 MP/s
JPEG). No fixed Python overhead — at 256² it is sub-millisecond.

### Thumbnail decode + resize (raylib decode + `ImageResize`)

| Input | Op | mean ms | MP/s |
|---|---|---:|---:|
| PNG 256×256 | decode + resize → 200×200 | 1.02 | 64 |
| PNG 1920×1080 | decode + resize → 355×200 | 20.5 | 101 |
| PNG 3840×2160 | decode + resize → 355×200 | 82.0 | 101 |
| PNG 256×256 ×8 | **batch of 8** thumbnails | 6.06 | 87 |

The resize itself is cheap; this stage is **decode-dominated** (compare the
decode-only row above). The batch of 8 small thumbnails = 6.06 ms ≈ 0.76 ms
each, i.e. **no extra per-item Python overhead** beyond the C calls — the loop
is just N back-to-back C decodes.

### Animated GIF decode (Pillow)

| Op | mean ms | MP/s |
|---|---:|---:|
| Full GIF, 480×270 × 24 frames | 52.0 | 60 |
| Single frame, 480×270 | 2.2 | 59 |

The slowest per-megapixel CPU stage (~60 MP/s vs ~120 for raster decode),
because each frame does `seek` + palette→RGBA `convert` + `tobytes` in Pillow.
Still ~2 ms/frame at this size, all inside Pillow's C.

### Pixel/color conversion

| Op | Size | mean ms | MP/s |
|---|---|---:|---:|
| Pillow RGB→RGBA `.tobytes()` | 256² | 0.14 | 467 |
| Pillow RGB→RGBA `.tobytes()` | 1080p | 10.2 | 204 |
| Pillow RGB→RGBA `.tobytes()` | 4K | 40.3 | 206 |
| Pillow RGBA→RGB `.tobytes()` | 1080p | 9.1 | 228 |
| Pillow RGBA→RGB `.tobytes()` | 4K | 35.9 | 231 |
| raylib `ImageFormat` →RGBA8 (convert-only) | 1080p | ~14.3 | — |
| raylib `ImageFormat` →RGBA8 (convert-only) | 4K | ~79.4 | — |

Pillow's `.convert()` is fast (200–500 MP/s, vectorised C). raylib's
`ImageFormat` convert-only is slower but still entirely C-side. **`.tobytes()`
copies bytes out** — the convert proper is faster than the table suggests.

### GPU upload

| Op | Result |
|---|---|
| `LoadTextureFromImage` / `UpdateTexture` | **NOT MEASURED** — needs an open raylib/OpenGL window; no display/GPU here. |

---

## 4. Hotspot identification

Ranked by per-megapixel CPU cost (slowest first):

1. **Animated GIF decode (~60 MP/s)** — slowest per pixel; multiplied by frame
   count, so a long GIF is the single largest CPU job in the pipeline.
2. **Full-image / thumbnail decode (~95–125 MP/s)** — the dominant cost for
   large stills; linear in pixels. Resize is a minor add-on.
3. **Color conversion** — only material at 4K (~40 ms Pillow, ~79 ms raylib);
   negligible at thumbnail sizes.

Crucially, **every one of these is time spent inside a C library**, not in a
Python loop:

| Stage | Hot code actually executing |
|---|---|
| Full / thumbnail decode | raylib `stb_image` (C) |
| Resize | raylib `ImageResize` (C) |
| GIF decode | Pillow's C codec + `convert` |
| Conversion | Pillow C / raylib `ImageFormat` (C) |

The Python layer around them is a thin dispatch (`load_cpu`, `make_thumbnail`)
called **once per image** — it does not loop over pixels. The batch benchmark
confirms there is no hidden per-item Python tax: 8 thumbnails cost 8× one
thumbnail.

This is the key distinction the Performance Policy asks for:

- **"Python overhead in a tight loop"** (a good native candidate) — *not found*.
- **"Already in C"** (not a candidate) — *this is every measured stage*.

---

## 5. Recommendation per candidate

The policy lists three native candidates. Verdict for each:

### a) Thumbnail decode/resize batches — ❌ native rewrite NOT justified

Decode is already C (`stb_image`); resize is already C (`ImageResize`); the
batch loop adds no Python overhead. A C/Rust thumbnailer would swap one C
decoder for another for low single-digit-percent gains.

**Do instead (algorithmic, per policy):**
- **Persist thumbnails to disk.** `get_thumb_cache_path` already computes a
  `.qoi` cache path keyed on mtime+size, but the gallery path
  (`ThumbnailService` → `make_thumbnail`) re-decodes the full-resolution source
  every gallery build. Caching decoded thumbnails on disk removes the **whole**
  decode cost on repeat views — far more than SIMD could.
- **Decode at reduced scale where the codec allows it** (e.g. JPEG DCT scaling)
  instead of decoding full-res then shrinking. This cuts the dominant decode
  cost itself.

### b) Streaming animated decode — ❌ native rewrite NOT justified (CPU side)

GIF decode is the slowest per-pixel stage but it is Pillow's C codec, not
Python. A native decoder would help only marginally on CPU.

**Do instead:**
- The current `GifViewer.load_cpu` already decodes **all** kept frames eagerly
  to RGBA up front (bounded by `MAX_ANIM_FRAMES` / `MAX_ANIM_MEMORY_MB`) — that
  is the "decode less" lever. True *streaming* (decode-ahead a few frames during
  playback instead of all at load) is an **ownership/scheduling** change, not a
  language change, and is the right next step if load latency on long GIFs is a
  problem.
- **The real animated-playback risk is GPU upload, which we could not measure
  here.** `advance_frame` calls `UpdateTexture` every frame change. Profile that
  on a machine with a display before considering any native work for playback
  (§6). If `UpdateTexture` is the bottleneck, the fix is GPU-side (PBO / texture
  streaming), still not a CPU C rewrite.

### c) Color conversion / pixel format transforms — ❌ native rewrite NOT justified

Pillow's `.convert()` runs at 200–500 MP/s in C; raylib `ImageFormat` is C too.
Conversion is negligible at thumbnail sizes and only ~40 ms even at 4K.

**Do instead:**
- **Avoid conversions rather than speed them up.** The WebP/GIF paths currently
  decode → `convert("RGBA")` → re-encode **PNG in memory** → hand to raylib
  `LoadImageFromMemory` (which decodes the PNG *again*). That PNG round-trip is
  pure waste: a direct raw-RGBA → raylib `Image` handoff removes a full encode
  **and** a full decode. This is a bigger, simpler win than SIMD on the convert.

---

## 6. Caveats & follow-ups

- **GPU upload is unmeasured** (no display). Re-profile `LoadTextureFromImage`
  and per-frame `UpdateTexture` on a machine with a window before any decision
  about animated-playback or large-texture performance. The harness already
  marks this stage explicitly.
- **Synthetic vs real images.** Synthetic gradients compress and decode like
  typical photos for *order-of-magnitude* purposes, but exact MP/s on real JPEGs
  (especially progressive ones) will differ. Re-run with `--images DIR` against
  representative assets before locking in any constant.
- **Binding caveat.** Measured against the CFFI `raylib` binding. `raylibpy`
  (ctypes) may have different per-call FFI overhead; that overhead is per-image,
  not per-pixel, so it does not change the conclusion, but verify if the
  packaged build ships `raylibpy`.
- **Variance.** Small iteration counts on Windows give ±10–15 % noise. The
  conclusions rest on order-of-magnitude gaps, not fragile margins.

### TL;DR

No native (C/Rust/SIMD) rewrite is warranted today. The hot paths are already
in C. Spend the effort on the policy's preferred levers first: **persist
thumbnails**, **decode at reduced scale**, **drop the WebP/GIF PNG round-trip**,
and **stream/decode-ahead animated frames**. Re-profile GPU upload on real
hardware before revisiting the animated-playback path.
