"""Generate ``imagura.ico`` from ``imagura.svg``.

``imagura.svg`` is an icon export composed of layered base64 PNG ``<image>``
elements (note the non-standard ``data:img/png`` URIs) on a 1080x1080 canvas,
with one layer using ``mix-blend-mode: overlay``. We composite the layers with
Pillow so no external SVG renderer (Inkscape/cairo/rsvg) is required, then emit
a multi-resolution Windows ``.ico`` (256, 128, 64, 48, 32, 16).

Usage (from the repo root, with Pillow installed)::

    python packaging/windows/make_icon.py

This writes ``packaging/windows/imagura.ico`` next to this script. To swap the
artwork, replace ``imagura.svg`` and re-run.
"""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path

try:
    from PIL import Image, ImageChops
except ImportError as exc:  # pragma: no cover - guarded for environments w/o Pillow
    raise SystemExit(
        "Pillow is required to generate the icon. Install it with:\n"
        "    python -m pip install pillow\n"
        "then re-run:  python packaging/windows/make_icon.py"
    ) from exc

HERE = Path(__file__).resolve().parent
SVG = HERE / "imagura.svg"
ICO = HERE / "imagura.ico"
CANVAS = 1080
SIZES = [256, 128, 64, 48, 32, 16]


def _attr(attrs: str, name: str) -> str | None:
    m = re.search(re.escape(name) + r'\s*=\s*"([^"]*)"', attrs)
    return m.group(1) if m else None


def compose(svg_text: str) -> "Image.Image":
    """Composite the SVG's layered ``<image>`` elements into one RGBA image."""
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    for m in re.finditer(r"<image\b([^>]*?)/?>", svg_text, re.S):
        attrs = m.group(1)
        href = _attr(attrs, "xlink:href") or _attr(attrs, "href")
        if not href or "base64," not in href:
            continue
        x = int(round(float(_attr(attrs, "x") or 0)))
        y = int(round(float(_attr(attrs, "y") or 0)))
        cls = _attr(attrs, "class") or ""
        raw = base64.b64decode(re.sub(r"\s+", "", href.split("base64,", 1)[1]))
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        layer = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        layer.alpha_composite(img, (x, y))
        if "cls-1" in cls and hasattr(ImageChops, "overlay"):
            blended = ImageChops.overlay(
                canvas.convert("RGB"), layer.convert("RGB")
            ).convert("RGBA")
            canvas = Image.composite(blended, canvas, layer.split()[3])
        else:
            canvas = Image.alpha_composite(canvas, layer)
    return canvas


def _write_runtime_icon(full: "Image.Image") -> Path:
    """Emit imagura/app_icon.py with the icon as a base64 PNG.

    The app uses this at runtime for the GLFW/raylib window icon. Embedding it as
    code (rather than a data file) keeps it working in the frozen PyInstaller exe
    without any resource-path handling.
    """
    runtime = HERE.parent.parent / "imagura" / "app_icon.py"
    small = full.resize((128, 128), Image.LANCZOS).convert("RGBA")
    buf = io.BytesIO()
    small.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    chunks = "\n".join('    "' + b64[i:i + 100] + '"' for i in range(0, len(b64), 100))
    runtime.write_text(
        '"""Runtime window icon (128x128 RGBA PNG, base64-encoded).\n\n'
        "Generated from imagura.svg by packaging/windows/make_icon.py.\n"
        'Do not edit by hand; re-run make_icon.py to regenerate.\n"""\n\n'
        "import base64\n\n"
        "ICON_PNG_BASE64 = (\n" + chunks + "\n)\n\n"
        "ICON_PNG_BYTES = base64.b64decode(ICON_PNG_BASE64)\n",
        encoding="utf-8",
    )
    return runtime


def main() -> int:
    if not SVG.exists():
        raise SystemExit(f"missing source SVG: {SVG}")
    full = compose(SVG.read_text(encoding="utf-8", errors="replace"))
    base = full.resize((256, 256), Image.LANCZOS)
    base.save(ICO, format="ICO", sizes=[(sz, sz) for sz in SIZES])
    print(f"[ICON] wrote {ICO} ({ICO.stat().st_size} bytes, sizes={SIZES})")
    runtime = _write_runtime_icon(full)
    print(f"[ICON] wrote {runtime} ({runtime.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
