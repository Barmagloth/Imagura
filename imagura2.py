# imagura_main.py — Monolithic Raylib Image Viewer
# Windows-friendly, single-file, no deps beyond raylib bindings.
# Engine: raylib. Backdrop blur via WinAPI (DWM / SetWindowCompositionAttribute).
#
# FEATURES (per spec):
# - Borderless fullscreen window, HWND extracted and blur applied
# - Background modes cycle (V): color + opacity + blur flag (system blur toggled)
# - 3‑state zoom toggler (F / button bottom-right / double‑click mid): 1:1 → FIT → LAST_USER
# - Manual zoom (wheel / Up,Down) with mouse‑anchor; pan with LMB when zoomed
# - Page switch (A/Left, D/Right or edge‑clicks) when not zoomed with slide animation
# - Gallery with thumbnails at bottom, slides in/out on mouse near bottom (trigger zone)
# - Thumb cache with LRU cap, budgeted building per frame
# - Open/zoom/switch/gallery slide are eased with tiny linear lerps
# - Defensive error handling around raylib API differences (raylibpy vs python‑raylib)
#
# Tested on: Python 3.10/3.11, raylibpy 5.x and python‑raylib 5.x, Windows 11.

from __future__ import annotations
import os, sys, time, ctypes, atexit, traceback
from dataclasses import dataclass, field
from collections import OrderedDict, deque
from typing import List, Tuple, Optional, Deque

# ===================== CONSTANTS =====================
TARGET_FPS = 60
ANIM_SWITCH_MS = 150
ANIM_TOGGLE_ZOOM_MS = 150
ANIM_OPEN_MS = 200
FIT_DEFAULT_SCALE = 0.95
FIT_OPEN_SCALE = 0.80
ZOOM_STEP_KEYS = 0.01
UI_BTN_TOGGLE_ZOOM_SIZE = (30, 30)
UI_BTN_TOGGLE_ZOOM_MARGIN_FRAC = 0.10  # 10% margin from bottom-right
GALLERY_HEIGHT_FRAC = 0.12  # 12% of screenH
GALLERY_TRIGGER_FRAC = 0.08  # bottom 8% trigger zone
GALLERY_SLIDE_MS = 150
THUMB_CACHE_LIMIT = 400
THUMB_PADDING = 6
THUMB_PRELOAD_SPAN = 40
THUMB_BUILD_BUDGET_PER_FRAME = 2
DOUBLE_CLICK_TIME_MS = 300
BG_MODES = [
    {"color": (0, 0, 0), "opacity": 0.5, "blur": True},  # default
    {"color": (0, 0, 0), "opacity": 1.0, "blur": False},
    {"color": (255, 255, 255), "opacity": 1.0, "blur": False},
    {"color": (255, 255, 255), "opacity": 0.5, "blur": True},
]
IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".gif", ".qoi"}

# ===================== RAYLIB BINDING SHIM =====================
try:
    import raylibpy as rl

    RL_VER = "raylibpy"
except Exception:
    import raylib as rl

    RL_VER = "python-raylib"

_RL_WHITE = getattr(rl, "RAYWHITE", rl.WHITE)
now = time.perf_counter


# ---------- small helpers for FFI variations ----------
class _CTypesRect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float), ("width", ctypes.c_float), ("height", ctypes.c_float)]


class _CTypesVec2(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float), ("y", ctypes.c_float)]


def RL_Rect(x, y, w, h):
    if hasattr(rl, 'Rectangle'):
        try:
            return rl.Rectangle(x, y, w, h)
        except Exception:
            pass
    if hasattr(rl, 'ffi'):
        r = rl.ffi.new("Rectangle *");
        r[0].x = float(x);
        r[0].y = float(y);
        r[0].width = float(w);
        r[0].height = float(h);
        return r[0]
    return _CTypesRect(float(x), float(y), float(w), float(h))


def RL_V2(x, y):
    if hasattr(rl, 'Vector2'):
        try:
            return rl.Vector2(x, y)
        except Exception:
            pass
    if hasattr(rl, 'ffi'):
        v = rl.ffi.new("Vector2 *");
        v[0].x = float(x);
        v[0].y = float(y);
        return v[0]
    return _CTypesVec2(float(x), float(y))


def RL_DrawText(text: str, x: int, y: int, size: int, color):
    try:
        rl.DrawText(text, x, y, size, color)
    except TypeError:
        rl.DrawText(text.encode('utf-8'), x, y, size, color)


# Helper: universal color ctor across bindings
def RL_Color(r: int, g: int, b: int, a: int):
    ctor = getattr(rl, "Color", None)
    if ctor:
        try:
            return ctor(int(r), int(g), int(b), int(a))
        except Exception:
            pass
    base = rl.WHITE if (int(r) + int(g) + int(b)) >= 384 else rl.BLACK
    alpha = max(0.0, min(1.0, int(a) / 255.0))
    try:
        return rl.Fade(base, float(alpha))
    except Exception:
        return base


# ===================== LOGGING =====================
_start = now();
_frame = 0


def log(msg: str):
    t = now() - _start
    line = f"[{t:7.3f}s F{_frame:06d}] {msg}\n"
    try:
        sys.stdout.write(line)
    except Exception:
        sys.stdout.buffer.write(line.encode('utf-8', 'replace'))
    try:
        sys.stdout.flush()
    except Exception:
        pass


# ===================== WIN BLUR =====================
class WinBlur:
    DWMWA_SYSTEMBACKDROP_TYPE = 38
    DWMSBT_MAINWINDOW = 2
    DWMSBT_TRANSIENTWINDOW = 3

    @staticmethod
    def try_set_system_backdrop(hwnd, kind: int) -> bool:
        try:
            dwmapi = ctypes.windll.dwmapi
            value = ctypes.c_int(kind)
            res = dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), ctypes.c_uint(WinBlur.DWMWA_SYSTEMBACKDROP_TYPE),
                                               ctypes.byref(value), ctypes.sizeof(value))
            return res == 0
        except Exception:
            return False

    @staticmethod
    def set_legacy_blur(hwnd, enabled: bool):
        try:
            user32 = ctypes.windll.user32

            class ACCENT_POLICY(ctypes.Structure):
                _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                            ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]

            class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
                _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]

            WCA_ACCENT_POLICY = 19;
            ACCENT_ENABLE_BLURBEHIND = 3;
            ACCENT_DISABLED = 0
            accent = ACCENT_POLICY();
            accent.AccentState = ACCENT_ENABLE_BLURBEHIND if enabled else ACCENT_DISABLED;
            accent.AccentFlags = 2;
            accent.GradientColor = 0
            data = WINDOWCOMPOSITIONATTRIBDATA();
            data.Attribute = WCA_ACCENT_POLICY;
            data.Data = ctypes.addressof(accent);
            data.SizeOfData = ctypes.sizeof(accent)
            user32.SetWindowCompositionAttribute(ctypes.c_void_p(hwnd), ctypes.byref(data))
            return True
        except Exception:
            return False

    @staticmethod
    def enable(hwnd):
        if not hwnd: return
        if not WinBlur.try_set_system_backdrop(hwnd, WinBlur.DWMSBT_MAINWINDOW):
            WinBlur.try_set_system_backdrop(hwnd, WinBlur.DWMSBT_TRANSIENTWINDOW)
            WinBlur.set_legacy_blur(hwnd, True)

    @staticmethod
    def disable(hwnd):
        if not hwnd: return
        WinBlur.set_legacy_blur(hwnd, False)


# ===================== DATA STRUCTURES =====================
@dataclass
class TextureInfo:
    tex: rl.Texture2D
    w: int
    h: int


@dataclass
class ViewParams:
    scale: float = 1.0
    offx: float = 0.0
    offy: float = 0.0


@dataclass
class ImageCache:
    prev: Optional[TextureInfo] = None
    curr: Optional[TextureInfo] = None
    next: Optional[TextureInfo] = None


@dataclass
class BitmapThumb:
    texture: Optional[rl.Texture2D] = None
    size: Tuple[int, int] = (0, 0)
    src_path: str = ""
    ready: bool = False


@dataclass
class AppState:
    screenW: int = 0;
    screenH: int = 0
    hwnd: Optional[int] = None
    current_dir_images: List[str] = field(default_factory=list)
    index: int = 0
    cache: ImageCache = field(default_factory=ImageCache)
    thumb_cache: "OrderedDict[str,BitmapThumb]" = field(default_factory=OrderedDict)
    thumb_queue: Deque[str] = field(default_factory=deque)
    to_unload: List[rl.Texture2D] = field(default_factory=list)
    thumb_scroll_x: float = 0.0
    gallery_y: float = 0.0  # animated Y
    gallery_visible: bool = False
    bg_mode_index: int = 0
    bg_current_opacity: float = BG_MODES[0]["opacity"]
    bg_target_opacity: float = BG_MODES[0]["opacity"]
    last_fit_view: ViewParams = field(default_factory=ViewParams)
    view: ViewParams = field(default_factory=ViewParams)
    last_user_view: Optional[ViewParams] = None
    zoom_state_cycle: int = 1  # 0=ONE_TO_ONE, 1=FIT, 2=LAST_USER (start at FIT)
    is_zoomed: bool = False
    is_panning: bool = False
    pan_start_mouse: Tuple[float, float] = (0.0, 0.0)
    pan_start_offset: Tuple[float, float] = (0.0, 0.0)
    last_click_time: float = 0.0
    last_click_pos: Tuple[int, int] = (0, 0)
    show_hud: bool = False
    # session memory: persist view per image
    view_memory: dict = field(default_factory=dict)  # path -> ViewParams
    # nav buttons fade
    nav_left_alpha: float = 0.0
    nav_right_alpha: float = 0.0
    # animations
    open_anim_active: bool = False
    open_anim_t0: float = 0.0
    switch_anim_active: bool = False
    switch_anim_t0: float = 0.0
    switch_anim_direction: int = 0  # 1=right, -1=left
    switch_anim_prev_tex: Optional[TextureInfo] = None


# ===================== UTILS =====================

def clamp(v, a, b):
    return a if v < a else b if v > b else v


def lerp(a, b, t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return a + (b - a) * t


def ease_log_in_out(t: float) -> float:
    """Logarithmic ease in-out для плавных анимаций"""
    if t <= 0.0: return 0.0
    if t >= 1.0: return 1.0
    if t < 0.5:
        return 0.5 * (1.0 - (1.0 - 2.0 * t) ** 2)
    else:
        return 0.5 * (1.0 + (2.0 * t - 1.0) ** 2)


# ===================== WINDOW INIT =====================

def raylib_get_hwnd() -> Optional[int]:
    try:
        if hasattr(rl, "get_window_handle"):
            return int(ctypes.cast(rl.get_window_handle(), ctypes.c_void_p).value or 0)
        if hasattr(rl, "GetWindowHandle"):
            return int(ctypes.cast(rl.GetWindowHandle(), ctypes.c_void_p).value or 0)
    except Exception:
        pass
    try:
        user32 = ctypes.windll.user32
        user32.FindWindowW.restype = ctypes.c_void_p
        return int(user32.FindWindowW(None, "Viewer")) or None
    except Exception:
        return None


def init_window_and_blur(state: AppState):
    mon = getattr(rl, 'GetCurrentMonitor', lambda: 0)()
    mw, mh = rl.GetMonitorWidth(mon), rl.GetMonitorHeight(mon)
    try:
        rl.InitWindow(mw, mh, "Viewer")
    except TypeError:
        rl.InitWindow(mw, mh, b"Viewer")
    try:
        rl.SetExitKey(0)
    except Exception:
        pass
    flags = rl.FLAG_WINDOW_UNDECORATED | rl.FLAG_WINDOW_MAXIMIZED | getattr(rl, 'FLAG_WINDOW_ALWAYS_RUN', 0)
    rl.SetWindowState(flags)
    rl.SetTargetFPS(TARGET_FPS)
    state.screenW, state.screenH = rl.GetScreenWidth(), rl.GetScreenHeight()
    state.hwnd = raylib_get_hwnd()
    WinBlur.enable(state.hwnd)
    state.gallery_y = state.screenH
    log(f"[INIT] RL_VER={RL_VER} size={state.screenW}x{state.screenH} hwnd={state.hwnd}")


# ===================== IO =====================

def list_images(dirpath: str) -> List[str]:
    try:
        names = sorted(os.listdir(dirpath))
    except Exception:
        return []
    out = []
    for n in names:
        p = os.path.join(dirpath, n)
        if os.path.isfile(p) and os.path.splitext(n)[1].lower() in IMG_EXTS:
            out.append(p)
    return out


# --- image/texture helpers ---

def _image_resize_mut(img, w: int, h: int):
    if hasattr(rl, 'ffi'):
        try:
            p = rl.ffi.new("Image *", img)
            try:
                rl.ImageResize(p, int(w), int(h))
            except Exception:
                rl.ImageResizeNN(p, int(w), int(h))
            return p[0]
        except Exception:
            pass
    for fn in (
            lambda im: rl.ImageResize(ctypes.byref(im), int(w), int(h)),
            lambda im: rl.ImageResize(im, int(w), int(h)),
            lambda im: rl.ImageResizeNN(ctypes.byref(im), int(w), int(h)),
            lambda im: rl.ImageResizeNN(im, int(w), int(h)),
    ):
        try:
            fn(img); return img
        except Exception:
            continue
    return img


def load_texture(path: str) -> TextureInfo:
    img = None
    try:
        try:
            img = rl.LoadImage(path)
        except Exception:
            img = rl.LoadImage(path.encode('utf-8'))
        w, h = img.width, img.height
        if w <= 0 or h <= 0: raise RuntimeError("empty image")
        tex = rl.LoadTextureFromImage(img)
        return TextureInfo(tex=tex, w=w, h=h)
    except Exception as e:
        log(f"[LOAD][ERR] {os.path.basename(path)}: {e!r}")
        ph = rl.GenImageColor(2, 2, _RL_WHITE);
        tex = rl.LoadTextureFromImage(ph)
        try:
            rl.UnloadImage(ph)
        except Exception:
            pass
        return TextureInfo(tex=tex, w=2, h=2)
    finally:
        try:
            if img is not None: rl.UnloadImage(img)
        except Exception:
            pass


def unload_texture_deferred(state: AppState, ti: Optional[TextureInfo]):
    tex = getattr(ti, 'tex', None)
    if getattr(tex, 'id', 0): state.to_unload.append(tex)


def process_deferred_unloads(state: AppState):
    while state.to_unload:
        tex = state.to_unload.pop()
        try:
            rl.UnloadTexture(tex)
        except Exception as e:
            log(f"[UNLOAD][ERR] {e!r}")


# --- thumbnails + LRU ---

def build_thumb_for(path: str, target_h: int) -> BitmapThumb:
    try:
        try:
            img = rl.LoadImage(path)
        except Exception:
            img = rl.LoadImage(path.encode('utf-8'))
    except Exception:
        return BitmapThumb(None, (0, 0), path, False)
    try:
        w, h = img.width, img.height
        if w <= 0 or h <= 0:
            return BitmapThumb(None, (0, 0), path, False)
        scale = max(1, target_h) / max(1, h)
        tw, th = max(1, int(w * scale)), max(1, int(h * scale))
        rimg = _image_resize_mut(img, tw, th)
        tex = rl.LoadTextureFromImage(rimg)
        try:
            rl.UnloadImage(rimg)
        except Exception:
            pass
        return BitmapThumb(tex, (tw, th), path, True)
    except Exception as e:
        return BitmapThumb(None, (0, 0), path, False)


def schedule_thumbs(state: AppState, around_index: int):
    n = len(state.current_dir_images)
    if n == 0: return
    lo = max(0, around_index - THUMB_PRELOAD_SPAN);
    hi = min(n - 1, around_index + THUMB_PRELOAD_SPAN)
    inq = set(state.thumb_queue);
    added = 0
    for i in range(lo, hi + 1):
        p = state.current_dir_images[i]
        if (p not in state.thumb_cache) and (p not in inq): state.thumb_queue.append(p); inq.add(p); added += 1


def process_thumb_queue(state: AppState):
    target_h = int(state.screenH * GALLERY_HEIGHT_FRAC * 0.8)
    budget = THUMB_BUILD_BUDGET_PER_FRAME;
    built = 0
    while budget > 0 and state.thumb_queue:
        p = state.thumb_queue.popleft()
        if p in state.thumb_cache: continue
        bt = build_thumb_for(p, target_h)
        state.thumb_cache[p] = bt
        budget -= 1;
        built += 1
    while len(state.thumb_cache) > THUMB_CACHE_LIMIT:
        _, bt = state.thumb_cache.popitem(last=False)
        if bt and bt.texture:
            unload_texture_deferred(state, TextureInfo(bt.texture, 0, 0))


# ===================== VIEW/RENDER =====================

def compute_fit_scale(iw, ih, sw, sh, frac):
    if iw == 0 or ih == 0: return 1.0
    return min(sw * frac / iw, sh * frac / ih)


def center_view_for(scale, iw, ih, sw, sh):
    return ViewParams(scale=scale, offx=(sw - iw * scale) / 2.0, offy=(sh - ih * scale) / 2.0)


def compute_fit_view(state, frac):
    ti = state.cache.curr
    if not ti: return ViewParams()
    s = compute_fit_scale(ti.w, ti.h, state.screenW, state.screenH, frac)
    return center_view_for(s, ti.w, ti.h, state.screenW, state.screenH)


def clamp_pan(view: ViewParams, img: TextureInfo, screenW: int, screenH: int) -> ViewParams:
    vw = img.w * view.scale
    vh = img.h * view.scale
    if vw <= screenW:
        view.offx = (screenW - vw) / 2.0
    else:
        view.offx = clamp(view.offx, screenW - vw, 0.0)
    if vh <= screenH:
        view.offy = (screenH - vh) / 2.0
    else:
        view.offy = clamp(view.offy, screenH - vh, 0.0)
    return view


def recompute_view_anchor_zoom(view: ViewParams, new_scale: float, anchor: Tuple[int, int],
                               img: TextureInfo) -> ViewParams:
    ax, ay = anchor
    old_scale = view.scale if view.scale and view.scale > 1e-6 else 1e-6
    wx = (ax - view.offx) / old_scale
    wy = (ay - view.offy) / old_scale
    nv = ViewParams(scale=max(0.01, float(new_scale)))
    nv.offx = ax - wx * nv.scale
    nv.offy = ay - wy * nv.scale
    return nv


# ---------- background modes ----------

def win_set_blur(hwnd, enabled: bool):
    if enabled:
        WinBlur.enable(hwnd)
    else:
        WinBlur.disable(hwnd)


def apply_bg_mode(state: AppState):
    mode = BG_MODES[state.bg_mode_index]
    win_set_blur(state.hwnd, mode["blur"])
    c = mode["color"];
    a = clamp(state.bg_current_opacity, 0.0, 1.0)

    if mode["blur"]:
        # For blur modes: clear to transparent, let backdrop blur show through
        try:
            rl.ClearBackground(rl.BLANK)
        except Exception:
            rl.ClearBackground(RL_Color(0, 0, 0, 0))
        # Draw tinted overlay
        rl.DrawRectangle(0, 0, state.screenW, state.screenH, RL_Color(c[0], c[1], c[2], int(255 * a)))
    else:
        # For solid modes: clear to opaque color directly
        col = RL_Color(c[0], c[1], c[2], int(255 * a))
        rl.ClearBackground(col)


# ---------- image rendering ----------

def render_image_at(ti: TextureInfo, v: ViewParams, alpha: float = 1.0):
    if not ti: return
    tint = RL_Color(255, 255, 255, int(255 * alpha))
    rl.DrawTexturePro(ti.tex, RL_Rect(0, 0, ti.w, ti.h), RL_Rect(v.offx, v.offy, ti.w * v.scale, ti.h * v.scale),
                      RL_V2(0, 0), 0.0, tint)


def render_image(state: AppState):
    ti = state.cache.curr
    if not ti: return

    # Open animation
    if state.open_anim_active:
        t = (now() - state.open_anim_t0) / (ANIM_OPEN_MS / 1000.0)
        if t >= 1.0:
            state.open_anim_active = False
            t = 1.0
        t = ease_log_in_out(t)
        # lerp scale from FIT_OPEN_SCALE to FIT_DEFAULT_SCALE
        from_view = compute_fit_view(state, FIT_OPEN_SCALE)
        to_view = state.last_fit_view
        v = ViewParams(
            scale=lerp(from_view.scale, to_view.scale, t),
            offx=lerp(from_view.offx, to_view.offx, t),
            offy=lerp(from_view.offy, to_view.offy, t),
        )
        render_image_at(ti, v, alpha=t)
        return

    # Switch animation
    if state.switch_anim_active and state.switch_anim_prev_tex:
        t = (now() - state.switch_anim_t0) / (ANIM_SWITCH_MS / 1000.0)
        if t >= 1.0:
            state.switch_anim_active = False
            unload_texture_deferred(state, state.switch_anim_prev_tex)
            state.switch_anim_prev_tex = None
            t = 1.0
        t = ease_log_in_out(t)

        # slide effect: old slides out, new slides in
        offset = state.screenW * state.switch_anim_direction
        prev_x = lerp(0, -offset, t)
        curr_x = lerp(offset, 0, t)

        # old image
        pv = ViewParams(scale=state.view.scale, offx=state.view.offx + prev_x, offy=state.view.offy)
        render_image_at(state.switch_anim_prev_tex, pv, alpha=1.0 - t)

        # new image
        cv = ViewParams(scale=state.view.scale, offx=state.view.offx + curr_x, offy=state.view.offy)
        render_image_at(ti, cv, alpha=t)
        return

    # Normal rendering
    render_image_at(ti, state.view)


# ---------- 1:1 button ----------

def btn_rect(state: AppState):
    bw, bh = UI_BTN_TOGGLE_ZOOM_SIZE
    mx = int(state.screenW * UI_BTN_TOGGLE_ZOOM_MARGIN_FRAC)
    my = int(state.screenH * UI_BTN_TOGGLE_ZOOM_MARGIN_FRAC)
    x = state.screenW - mx - bw
    y = state.screenH - my - bh
    return RL_Rect(x, y, bw, bh)


def draw_button_1to1(state: AppState):
    # hide button when gallery visible to avoid overlap
    gh = int(state.screenH * GALLERY_HEIGHT_FRAC)
    y_visible = state.screenH - gh
    if state.gallery_y < state.screenH - gh / 2:  # gallery more than halfway up
        return

    r = btn_rect(state)
    mouse = rl.GetMousePosition()
    hover = (r.x <= mouse.x <= r.x + r.width and r.y <= mouse.y <= r.y + r.height)
    rl.DrawRectangleLines(int(r.x), int(r.y), int(r.width), int(r.height), rl.WHITE if not hover else rl.YELLOW)
    RL_DrawText("1:1", int(r.x + 6), int(r.y + 6), 16, rl.WHITE)


def check_button_1to1_click(state: AppState) -> bool:
    """Returns True if button was clicked"""
    gh = int(state.screenH * GALLERY_HEIGHT_FRAC)
    if state.gallery_y < state.screenH - gh / 2:
        return False
    r = btn_rect(state)
    mouse = rl.GetMousePosition()
    hover = (r.x <= mouse.x <= r.x + r.width and r.y <= mouse.y <= r.y + r.height)
    return hover and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT)


# ---------- nav buttons (circular, edge-hover) ----------

def update_nav_buttons_fade(state: AppState):
    """Fade in/out nav buttons based on mouse position and zoom"""
    mouse = rl.GetMousePosition()
    zoom_threshold = state.last_fit_view.scale * 1.1
    is_significantly_zoomed = state.view.scale > zoom_threshold

    if not is_significantly_zoomed:
        # not zoomed, fade out
        state.nav_left_alpha = max(0.0, state.nav_left_alpha - 0.1)
        state.nav_right_alpha = max(0.0, state.nav_right_alpha - 0.1)
        return

    # zoomed: check hover
    edge_zone = state.screenW * 0.15
    hover_left = mouse.x < edge_zone
    hover_right = mouse.x > state.screenW - edge_zone

    # animate alpha
    fade_speed = 0.15
    if hover_left:
        state.nav_left_alpha = min(1.0, state.nav_left_alpha + fade_speed)
    else:
        state.nav_left_alpha = max(0.0, state.nav_left_alpha - fade_speed)

    if hover_right:
        state.nav_right_alpha = min(1.0, state.nav_right_alpha + fade_speed)
    else:
        state.nav_right_alpha = max(0.0, state.nav_right_alpha - fade_speed)


def draw_nav_buttons(state: AppState):
    """Draw circular navigation buttons at screen edges when zoomed"""
    if state.nav_left_alpha <= 0.01 and state.nav_right_alpha <= 0.01:
        return

    cy = state.screenH // 2
    radius = 40

    # left button
    if state.nav_left_alpha > 0.01 and state.index > 0:
        cx = 60
        alpha = int(state.nav_left_alpha * 200)
        rl.DrawCircle(cx, cy, radius, RL_Color(40, 40, 40, alpha))
        rl.DrawCircleLines(cx, cy, radius, RL_Color(255, 255, 255, alpha))
        # arrow
        RL_DrawText("<", cx - 10, cy - 12, 28, RL_Color(255, 255, 255, alpha))

        # click detection
        mouse = rl.GetMousePosition()
        dx = mouse.x - cx
        dy = mouse.y - cy
        if dx * dx + dy * dy <= radius * radius:
            if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                switch_to(state, state.index - 1, animate=True)

    # right button
    if state.nav_right_alpha > 0.01 and state.index < len(state.current_dir_images) - 1:
        cx = state.screenW - 60
        alpha = int(state.nav_right_alpha * 200)
        rl.DrawCircle(cx, cy, radius, RL_Color(40, 40, 40, alpha))
        rl.DrawCircleLines(cx, cy, radius, RL_Color(255, 255, 255, alpha))
        # arrow
        RL_DrawText(">", cx - 10, cy - 12, 28, RL_Color(255, 255, 255, alpha))

        # click detection
        mouse = rl.GetMousePosition()
        dx = mouse.x - cx
        dy = mouse.y - cy
        if dx * dx + dy * dy <= radius * radius:
            if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                switch_to(state, state.index + 1, animate=True)


# ---------- gallery ----------

def _thumbs_total_width(state: AppState, gallery_h: int) -> int:
    x = THUMB_PADDING
    for p in state.current_dir_images:
        bt = state.thumb_cache.get(p)
        if bt and bt.ready and bt.texture:
            x += bt.size[0] + THUMB_PADDING
        else:
            x += int(gallery_h * 0.8 * 1.4) + THUMB_PADDING
    return x


def render_gallery(state: AppState):
    n = len(state.current_dir_images)
    if n == 0: return
    sw, sh = state.screenW, state.screenH
    gh = int(sh * GALLERY_HEIGHT_FRAC)
    y_hidden = sh;
    y_visible = sh - gh
    state.gallery_y = clamp(state.gallery_y, y_visible, y_hidden)
    y = int(state.gallery_y)

    # fade-in effect based on slide position
    alpha = 1.0 - ((state.gallery_y - y_visible) / (y_hidden - y_visible))
    rl.DrawRectangle(0, y, sw, gh, RL_Color(0, 0, 0, int(255 * 0.6 * alpha)))

    total_w = _thumbs_total_width(state, gh);
    max_scroll = max(0, total_w - sw)
    state.thumb_scroll_x = clamp(state.thumb_scroll_x, 0.0, float(max_scroll))

    # center if content narrower than screen
    x_offset = max(0, (sw - total_w) // 2) if total_w < sw else 0
    x = x_offset + THUMB_PADDING - int(state.thumb_scroll_x)
    idx = 0;
    mouse = rl.GetMousePosition()
    for p in state.current_dir_images:
        bt = state.thumb_cache.get(p)
        if bt and bt.ready and bt.texture and getattr(bt.texture, 'id', 0):
            th_y = y + (gh - bt.size[1]) // 2
            try:
                rl.DrawTexture(bt.texture, int(x), int(th_y), rl.WHITE)
            except Exception as e:
                log(f"[DRAW][THUMB][ERR] {os.path.basename(p)}: {e!r}")
            if idx == state.index:
                rl.DrawRectangleLines(int(x - 2), int(th_y - 2), int(bt.size[0] + 4), int(bt.size[1] + 4), rl.WHITE)
            if (x <= mouse.x <= x + bt.size[0]) and (th_y <= mouse.y <= th_y + bt.size[1]):
                if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                    switch_to(state, idx)
            x += bt.size[0] + THUMB_PADDING
        else:
            ph_h = int(gh * 0.8);
            ph_w = int(ph_h * 1.4);
            th_y = y + (gh - ph_h) // 2
            rl.DrawRectangle(int(x), int(th_y), int(ph_w), int(ph_h), rl.DARKGRAY)
            x += ph_w + THUMB_PADDING
        idx += 1
    if y <= mouse.y <= y + gh:
        wheel = rl.GetMouseWheelMove()
        if wheel != 0.0:
            state.thumb_scroll_x = clamp(state.thumb_scroll_x - wheel * 60.0, 0.0, float(max_scroll))


# ===================== NAV / SWITCH =====================

def preload_neighbors(state: AppState, new_index: int):
    n = len(state.current_dir_images)
    if n == 0:
        state.cache = ImageCache();
        state.index = 0;
        return
    new_index = clamp(new_index, 0, n - 1)

    # save current view to memory
    if state.cache.curr and state.index < len(state.current_dir_images):
        old_path = state.current_dir_images[state.index]
        state.view_memory[old_path] = ViewParams(state.view.scale, state.view.offx, state.view.offy)

    for ti in (state.cache.prev, state.cache.curr, state.cache.next):
        if ti: unload_texture_deferred(state, ti)

    def _safe(path):
        try:
            return load_texture(path)
        except Exception as e:
            log(f"[LOAD][SAFE][ERR] {os.path.basename(path)}: {e!r}"); return None

    cur = _safe(state.current_dir_images[new_index])
    prev = _safe(state.current_dir_images[new_index - 1]) if new_index - 1 >= 0 else None
    nxt = _safe(state.current_dir_images[new_index + 1]) if new_index + 1 < n else None
    state.cache = ImageCache(prev=prev, curr=cur, next=nxt);
    state.index = new_index
    schedule_thumbs(state, new_index)
    state.last_fit_view = compute_fit_view(state, FIT_DEFAULT_SCALE)

    # restore view from memory if exists, else use fit
    new_path = state.current_dir_images[new_index]
    if new_path in state.view_memory:
        state.view = state.view_memory[new_path]
        state.is_zoomed = (state.view.scale > state.last_fit_view.scale)
    else:
        state.view = state.last_fit_view
        state.is_zoomed = False


def switch_to(state: AppState, idx: int, animate: bool = True):
    if idx == state.index: return
    direction = 1 if idx > state.index else -1

    # Kill panning state - prevents ghost-drag on destination image
    state.is_panning = False

    # Save current texture for animation
    if animate and state.cache.curr:
        state.switch_anim_prev_tex = TextureInfo(state.cache.curr.tex, state.cache.curr.w, state.cache.curr.h)
        state.switch_anim_active = True
        state.switch_anim_t0 = now()
        state.switch_anim_direction = direction

    preload_neighbors(state, idx)


# ===================== ZOOM STATE CYCLE =====================

def view_for_1to1_centered(state: AppState) -> ViewParams:
    ti = state.cache.curr
    if not ti: return state.view
    return center_view_for(1.0, ti.w, ti.h, state.screenW, state.screenH)


def cycle_zoom_state(state: AppState):
    next_state = {0: 1, 1: 2, 2: 0}[state.zoom_state_cycle]
    if next_state == 0:
        target = view_for_1to1_centered(state)
    elif next_state == 1:
        target = state.last_fit_view
    else:
        target = state.last_user_view or state.last_fit_view

    # animate
    t0 = now();
    dur = ANIM_TOGGLE_ZOOM_MS / 1000.0
    v_from = state.view;
    ti = state.cache.curr
    while True:
        if rl.WindowShouldClose(): break
        rl.BeginDrawing()
        apply_bg_mode(state)
        t = (now() - t0) / dur
        if t >= 1.0: t = 1.0
        t_eased = ease_log_in_out(t)
        cur = ViewParams(
            scale=lerp(v_from.scale, target.scale, t_eased),
            offx=lerp(v_from.offx, target.offx, t_eased),
            offy=lerp(v_from.offy, target.offy, t_eased),
        )
        state.view = clamp_pan(cur, ti, state.screenW, state.screenH)
        render_image(state)
        draw_button_1to1(state)
        render_gallery(state)
        rl.EndDrawing()
        if t >= 1.0: break
    state.zoom_state_cycle = next_state
    state.is_zoomed = (state.view.scale > state.last_fit_view.scale)


# ===================== MAIN =====================

def apply_bg_opacity_anim(state: AppState):
    delta = state.bg_target_opacity - state.bg_current_opacity
    if abs(delta) < 0.001: return
    step = (1.0 / (ANIM_SWITCH_MS / 1000.0)) / TARGET_FPS
    state.bg_current_opacity += clamp(delta, -step, step)


def update_gallery_visibility_and_slide(state: AppState):
    mouse = rl.GetMousePosition()
    gh = int(state.screenH * GALLERY_HEIGHT_FRAC)
    y_hidden = state.screenH;
    y_visible = state.screenH - gh
    in_trigger = (mouse.y >= state.screenH * (1.0 - GALLERY_TRIGGER_FRAC))
    in_panel = (y_visible <= mouse.y <= y_hidden)
    want_show = in_trigger or in_panel
    state.gallery_visible = want_show
    cur = state.gallery_y
    tgt = y_visible if want_show else y_hidden
    step = (gh / (GALLERY_SLIDE_MS / 1000.0)) / TARGET_FPS
    if abs(cur - tgt) <= step:
        state.gallery_y = tgt
    else:
        state.gallery_y = cur - step if cur > tgt else cur + step


def detect_double_click(state: AppState, x: int, y: int) -> bool:
    """Детектор двойного клика с учетом времени и позиции"""
    t = now()
    if (t - state.last_click_time) < (DOUBLE_CLICK_TIME_MS / 1000.0):
        dx = abs(x - state.last_click_pos[0])
        dy = abs(y - state.last_click_pos[1])
        if dx < 10 and dy < 10:  # в пределах 10px
            state.last_click_time = 0.0  # reset
            return True
    state.last_click_time = t
    state.last_click_pos = (x, y)
    return False


def main():
    global _frame
    start_path = None
    for a in sys.argv[1:]:
        p = os.path.abspath(a)
        if os.path.exists(p): start_path = p; break
    init_window_and_blur(state := AppState())

    if start_path and os.path.isdir(start_path):
        dirpath = start_path;
        images = list_images(dirpath);
        start_index = 0
    else:
        dirpath = os.path.dirname(start_path) if start_path else os.getcwd()
        images = list_images(dirpath)
        if start_path:
            try:
                start_index = images.index(os.path.join(dirpath, os.path.basename(start_path)))
            except ValueError:
                start_index = 0
        else:
            start_index = 0
    state.current_dir_images = images

    if not images:
        while not rl.WindowShouldClose():
            rl.BeginDrawing();
            apply_bg_mode(state);
            RL_DrawText("No images found", 40, 40, 28, rl.GRAY);
            rl.EndDrawing()
        rl.CloseWindow();
        return

    preload_neighbors(state, start_index)
    state.last_fit_view = compute_fit_view(state, FIT_DEFAULT_SCALE);
    state.view = state.last_fit_view
    schedule_thumbs(state, state.index)

    # Open animation if launched by file
    if start_path and os.path.isfile(start_path):
        state.open_anim_active = True
        state.open_anim_t0 = now()

    log(f"[DIR] {dirpath} files={len(images)} start={state.index} -> {os.path.basename(images[state.index])}")
    atexit.register(lambda: log(f"[EXIT] frames={_frame} thumbs={len(state.thumb_cache)} q={len(state.thumb_queue)}"))

    try:
        while True:
            process_thumb_queue(state)
            process_deferred_unloads(state)
            update_gallery_visibility_and_slide(state)
            apply_bg_opacity_anim(state)
            update_nav_buttons_fade(state)

            should_close = rl.WindowShouldClose()
            if should_close:
                break
            rl.BeginDrawing();
            apply_bg_mode(state)

            mouse = rl.GetMousePosition()

            # HUD toggle
            if rl.IsKeyPressed(rl.KEY_I):
                state.show_hud = not state.show_hud

            if rl.IsKeyPressed(rl.KEY_V):
                state.bg_mode_index = (state.bg_mode_index + 1) % len(BG_MODES)
                state.bg_target_opacity = BG_MODES[state.bg_mode_index]["opacity"]

            if state.cache.curr and not state.switch_anim_active and not state.open_anim_active:
                if rl.IsKeyDown(rl.KEY_UP):
                    nv = recompute_view_anchor_zoom(state.view, state.view.scale * (1.0 + ZOOM_STEP_KEYS),
                                                    (int(mouse.x), int(mouse.y)), state.cache.curr)
                    state.view = clamp_pan(nv, state.cache.curr, state.screenW, state.screenH);
                    state.is_zoomed = (state.view.scale > state.last_fit_view.scale);
                    state.last_user_view = state.view;
                    state.zoom_state_cycle = 2
                if rl.IsKeyDown(rl.KEY_DOWN):
                    nv = recompute_view_anchor_zoom(state.view, state.view.scale * (1.0 - ZOOM_STEP_KEYS),
                                                    (int(mouse.x), int(mouse.y)), state.cache.curr)
                    state.view = clamp_pan(nv, state.cache.curr, state.screenW, state.screenH);
                    state.is_zoomed = (state.view.scale > state.last_fit_view.scale);
                    state.last_user_view = state.view;
                    state.zoom_state_cycle = 2

            wheel = rl.GetMouseWheelMove()
            if wheel != 0.0 and state.cache.curr and not state.switch_anim_active and not state.open_anim_active:
                nv = recompute_view_anchor_zoom(state.view, state.view.scale * (1.0 + wheel * 0.1),
                                                (int(mouse.x), int(mouse.y)), state.cache.curr)
                state.view = clamp_pan(nv, state.cache.curr, state.screenW, state.screenH);
                state.is_zoomed = (state.view.scale > state.last_fit_view.scale);
                state.last_user_view = state.view;
                state.zoom_state_cycle = 2

            # F or double-click mid for zoom cycle
            mid_left = state.screenW * 0.33;
            mid_right = state.screenW * 0.66;
            mid_top = state.screenH * 0.33;
            mid_bot = state.screenH * 0.66
            in_mid = (mid_left <= mouse.x <= mid_right and mid_top <= mouse.y <= mid_bot)

            if rl.IsKeyPressed(rl.KEY_F) or check_button_1to1_click(state):
                cycle_zoom_state(state)

            if in_mid and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                if detect_double_click(state, int(mouse.x), int(mouse.y)):
                    cycle_zoom_state(state)

            # panning
            if state.cache.curr and not state.switch_anim_active and not state.open_anim_active:
                img_rect = RL_Rect(state.view.offx, state.view.offy, state.cache.curr.w * state.view.scale,
                                   state.cache.curr.h * state.view.scale)
                over_img = (
                            img_rect.x <= mouse.x <= img_rect.x + img_rect.width and img_rect.y <= mouse.y <= img_rect.y + img_rect.height)
                if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT) and state.is_zoomed and over_img:
                    state.is_panning = True;
                    state.pan_start_mouse = (mouse.x, mouse.y);
                    state.pan_start_offset = (state.view.offx, state.view.offy)
                if rl.IsMouseButtonReleased(rl.MOUSE_BUTTON_LEFT): state.is_panning = False
                if state.is_panning:
                    dx = mouse.x - state.pan_start_mouse[0];
                    dy = mouse.y - state.pan_start_mouse[1]
                    nv = ViewParams(scale=state.view.scale, offx=state.pan_start_offset[0] + dx,
                                    offy=state.pan_start_offset[1] + dy)
                    state.view = clamp_pan(nv, state.cache.curr, state.screenW, state.screenH);
                    state.last_user_view = state.view;
                    state.zoom_state_cycle = 2

            # page switch
            if not state.switch_anim_active and not state.open_anim_active:
                edge_left = (mouse.x <= state.screenW * 0.10)
                edge_right = (mouse.x >= state.screenW * 0.90)
                gh = int(state.screenH * GALLERY_HEIGHT_FRAC);
                yv = state.screenH - gh
                in_gallery_panel = (yv <= mouse.y <= state.screenH)

                # block page switch only if SIGNIFICANTLY zoomed (>10% over fit)
                zoom_threshold = state.last_fit_view.scale * 1.1
                is_significantly_zoomed = state.view.scale > zoom_threshold

                # keyboard always works regardless of zoom
                if rl.IsKeyPressed(rl.KEY_RIGHT) or rl.IsKeyPressed(rl.KEY_D):
                    if state.index + 1 < len(state.current_dir_images): switch_to(state, state.index + 1, animate=True)
                if rl.IsKeyPressed(rl.KEY_LEFT) or rl.IsKeyPressed(rl.KEY_A):
                    if state.index - 1 >= 0: switch_to(state, state.index - 1, animate=True)

                # edge clicks only when NOT significantly zoomed and NOT in gallery
                if not is_significantly_zoomed and not in_gallery_panel:
                    if edge_right and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                        if state.index + 1 < len(state.current_dir_images): switch_to(state, state.index + 1,
                                                                                      animate=True)
                    if edge_left and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                        if state.index - 1 >= 0: switch_to(state, state.index - 1, animate=True)

            render_image(state)
            draw_nav_buttons(state)
            draw_button_1to1(state)
            try:
                render_gallery(state)
            except Exception as e:
                log(f"[DRAW][GALLERY][EXC] {e!r}\n{traceback.format_exc()}")

            # HUD - optional diagnostic overlay
            if state.show_hud:
                hud_y = state.screenH - 80
                line_spacing = 24
                RL_DrawText(f"RL={RL_VER}", 12, hud_y, 16, rl.LIGHTGRAY)
                RL_DrawText(f"idx={state.index + 1}/{len(state.current_dir_images)} zoom={state.view.scale:.3f}", 12,
                            hud_y + line_spacing, 16, rl.LIGHTGRAY)

            rl.EndDrawing()
            _frame += 1
            if rl.IsKeyPressed(rl.KEY_ESCAPE): break
            if should_close: break
    finally:
        process_deferred_unloads(state)
        for bt in list(state.thumb_cache.values()):
            try:
                if bt.texture: rl.UnloadTexture(bt.texture)
            except Exception as e:
                log(f"[CLEANUP][THUMB][ERR] {e!r}")
        for ti in (state.cache.prev, state.cache.curr, state.cache.next):
            try:
                if ti and getattr(ti.tex, 'id', 0): rl.UnloadTexture(ti.tex)
            except Exception as e:
                log(f"[CLEANUP][TEX][ERR] {e!r}")
        try:
            rl.CloseWindow()
        except Exception as e:
            log(f"[CLOSE][ERR] {e!r}")


if __name__ == '__main__':
    main()