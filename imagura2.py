from __future__ import annotations
import os, sys, time, ctypes, atexit, traceback
from dataclasses import dataclass, field
from collections import OrderedDict, deque
from typing import List, Tuple, Optional, Deque
import math

TARGET_FPS = 120
ANIM_SWITCH_KEYS_MS = 200
ANIM_SWITCH_GALLERY_MS = 100
ANIM_TOGGLE_ZOOM_MS = 150
ANIM_OPEN_MS = 700
ANIM_ZOOM_MS = 100
FIT_DEFAULT_SCALE = 0.95
FIT_OPEN_SCALE = 0.60
OPEN_ALPHA_START = 0.4
ZOOM_STEP_KEYS = 0.01
ZOOM_STEP_WHEEL = 0.1
CLOSE_BTN_RADIUS = 28
CLOSE_BTN_MARGIN = 20
CLOSE_BTN_ALPHA_MIN = 0.0
CLOSE_BTN_ALPHA_FAR = 0.1
CLOSE_BTN_ALPHA_MAX = 0.5
CLOSE_BTN_ALPHA_HOVER = 1.0
CLOSE_BTN_BG_ALPHA_MAX = 0.5
NAV_BTN_RADIUS = 40
NAV_BTN_BG_ALPHA_MAX = 0.5
MAX_IMAGE_DIMENSION = 8192
MAX_FILE_SIZE_MB = 200
GALLERY_HEIGHT_FRAC = 0.12
GALLERY_TRIGGER_FRAC = 0.08
GALLERY_SLIDE_MS = 150
GALLERY_THUMB_SPACING = 20
GALLERY_MIN_SCALE = 0.7
GALLERY_MIN_ALPHA = 0.3
THUMB_CACHE_LIMIT = 400
THUMB_PADDING = 6
THUMB_PRELOAD_SPAN = 40
THUMB_BUILD_BUDGET_PER_FRAME = 2
DOUBLE_CLICK_TIME_MS = 300
BG_MODES = [
    {"color": (0, 0, 0), "opacity": 0.5, "blur": True},
    {"color": (0, 0, 0), "opacity": 1.0, "blur": False},
    {"color": (255, 255, 255), "opacity": 1.0, "blur": False},
    {"color": (255, 255, 255), "opacity": 0.5, "blur": True},
]
IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tga", ".gif", ".qoi"}

try:
    import raylibpy as rl

    RL_VER = "raylibpy"
except Exception:
    import raylib as rl

    RL_VER = "python-raylib"

_RL_WHITE = getattr(rl, "RAYWHITE", rl.WHITE)
now = time.perf_counter


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
        r = rl.ffi.new("Rectangle *")
        r[0].x = float(x)
        r[0].y = float(y)
        r[0].width = float(w)
        r[0].height = float(h)
        return r[0]
    return _CTypesRect(float(x), float(y), float(w), float(h))


def RL_V2(x, y):
    if hasattr(rl, 'Vector2'):
        try:
            return rl.Vector2(x, y)
        except Exception:
            pass
    if hasattr(rl, 'ffi'):
        v = rl.ffi.new("Vector2 *")
        v[0].x = float(x)
        v[0].y = float(y)
        return v[0]
    return _CTypesVec2(float(x), float(y))


def RL_DrawText(text: str, x: int, y: int, size: int, color):
    try:
        rl.DrawText(text, x, y, size, color)
    except TypeError:
        rl.DrawText(text.encode('utf-8'), x, y, size, color)


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


_start = now()
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

            WCA_ACCENT_POLICY = 19
            ACCENT_ENABLE_BLURBEHIND = 3
            ACCENT_DISABLED = 0
            accent = ACCENT_POLICY()
            accent.AccentState = ACCENT_ENABLE_BLURBEHIND if enabled else ACCENT_DISABLED
            accent.AccentFlags = 2
            accent.GradientColor = 0
            data = WINDOWCOMPOSITIONATTRIBDATA()
            data.Attribute = WCA_ACCENT_POLICY
            data.Data = ctypes.addressof(accent)
            data.SizeOfData = ctypes.sizeof(accent)
            user32.SetWindowCompositionAttribute(ctypes.c_void_p(hwnd), ctypes.byref(data))
            return True
        except Exception:
            return False

    @staticmethod
    def enable(hwnd):
        if not hwnd:
            return
        if not WinBlur.try_set_system_backdrop(hwnd, WinBlur.DWMSBT_MAINWINDOW):
            WinBlur.try_set_system_backdrop(hwnd, WinBlur.DWMSBT_TRANSIENTWINDOW)
            WinBlur.set_legacy_blur(hwnd, True)

    @staticmethod
    def disable(hwnd):
        if not hwnd:
            return
        WinBlur.set_legacy_blur(hwnd, False)


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
    screenW: int = 0
    screenH: int = 0
    hwnd: Optional[int] = None
    unicode_font: Optional[any] = None
    current_dir_images: List[str] = field(default_factory=list)
    index: int = 0
    cache: ImageCache = field(default_factory=ImageCache)
    thumb_cache: "OrderedDict[str,BitmapThumb]" = field(default_factory=OrderedDict)
    thumb_queue: Deque[str] = field(default_factory=deque)
    to_unload: List[rl.Texture2D] = field(default_factory=list)
    gallery_center_index: float = 0.0
    gallery_y: float = 0.0
    gallery_visible: bool = False
    bg_mode_index: int = 0
    bg_current_opacity: float = BG_MODES[0]["opacity"]
    bg_target_opacity: float = BG_MODES[0]["opacity"]
    last_fit_view: ViewParams = field(default_factory=ViewParams)
    view: ViewParams = field(default_factory=ViewParams)
    zoom_state_cycle: int = 1
    is_zoomed: bool = False
    is_panning: bool = False
    pan_start_mouse: Tuple[float, float] = (0.0, 0.0)
    pan_start_offset: Tuple[float, float] = (0.0, 0.0)
    last_click_time: float = 0.0
    last_click_pos: Tuple[int, int] = (0, 0)
    show_hud: bool = False
    show_filename: bool = False
    view_memory: dict = field(default_factory=dict)
    user_zoom_memory: dict = field(default_factory=dict)
    nav_left_alpha: float = 0.0
    nav_right_alpha: float = 0.0
    close_btn_alpha: float = 0.0
    open_anim_active: bool = False
    open_anim_t0: float = 0.0
    switch_anim_active: bool = False
    switch_anim_t0: float = 0.0
    switch_anim_duration_ms: int = 0
    switch_anim_direction: int = 0
    switch_anim_prev_tex: Optional[TextureInfo] = None
    switch_anim_prev_view: ViewParams = field(default_factory=ViewParams)
    switch_queue: Deque[Tuple[int, int]] = field(default_factory=deque)
    zoom_anim_active: bool = False
    zoom_anim_t0: float = 0.0
    zoom_anim_from: ViewParams = field(default_factory=ViewParams)
    zoom_anim_to: ViewParams = field(default_factory=ViewParams)


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def lerp(a, b, t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return a + (b - a) * t


def ease_log_in_out(t: float) -> float:
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    if t < 0.5:
        return 0.5 * (1.0 - (1.0 - 2.0 * t) ** 2)
    else:
        return 0.5 * (1.0 + (2.0 * t - 1.0) ** 2)


def ease_out_quad(t: float) -> float:
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    return 1.0 - (1.0 - t) * (1.0 - t)


def ease_in_out_cubic(t: float) -> float:
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    if t < 0.5:
        return 4.0 * t * t * t
    else:
        p = 2.0 * t - 2.0
        return 1.0 + 0.5 * p * p * p


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


def load_unicode_font(font_size: int = 24):
    font_paths = [
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
    ]

    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                # Пробуем загрузить с NULL для автоматического определения глифов
                if hasattr(rl, 'ffi'):
                    # Для cffi биндингов
                    font = rl.LoadFontEx(font_path.encode('utf-8'), font_size, rl.ffi.NULL, 0)
                else:
                    # Для ctypes биндингов - пробуем с None
                    try:
                        font = rl.LoadFontEx(font_path, font_size, None, 0)
                    except:
                        font = rl.LoadFontEx(font_path.encode('utf-8'), font_size, None, 0)

                if hasattr(font, 'texture') and hasattr(font.texture, 'id') and font.texture.id > 0:
                    log(f"[FONT] Loaded unicode font: {os.path.basename(font_path)}")
                    return font
            except Exception as e:
                log(f"[FONT][ERR] Failed to load {font_path}: {e!r}")

    log(f"[FONT] Using default font (no unicode support)")
    return None


def get_work_area() -> Tuple[int, int, int, int]:
    try:
        user32 = ctypes.windll.user32

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        rect = RECT()
        SPI_GETWORKAREA = 48
        user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    except Exception:
        return 0, 0, 0, 0


def init_window_and_blur(state: AppState):
    x, y, w, h = get_work_area()
    if w == 0 or h == 0:
        mon = getattr(rl, 'GetCurrentMonitor', lambda: 0)()
        w, h = rl.GetMonitorWidth(mon), rl.GetMonitorHeight(mon)
        x, y = 0, 0

    try:
        rl.InitWindow(w, h, "Viewer")
    except TypeError:
        rl.InitWindow(w, h, b"Viewer")
    try:
        rl.SetExitKey(0)
    except Exception:
        pass
    flags = rl.FLAG_WINDOW_UNDECORATED | getattr(rl, 'FLAG_WINDOW_ALWAYS_RUN', 0)
    rl.SetWindowState(flags)
    try:
        rl.SetWindowPosition(x, y)
    except Exception:
        pass
    rl.SetTargetFPS(TARGET_FPS)
    state.screenW, state.screenH = rl.GetScreenWidth(), rl.GetScreenHeight()
    state.hwnd = raylib_get_hwnd()
    state.gallery_y = state.screenH
    state.unicode_font = load_unicode_font(24)
    log(f"[INIT] RL_VER={RL_VER} workarea={w}x{h} window={state.screenW}x{state.screenH} hwnd={state.hwnd}")


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
            fn(img)
            return img
        except Exception:
            continue
    return img


def get_short_path_name(long_path: str) -> str:
    try:
        if sys.platform != 'win32':
            return long_path

        from ctypes import wintypes

        _GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
        _GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        _GetShortPathNameW.restype = wintypes.DWORD

        output_buf_size = 0
        while True:
            output_buf = ctypes.create_unicode_buffer(output_buf_size)
            needed = _GetShortPathNameW(long_path, output_buf, output_buf_size)
            if needed == 0:
                return long_path
            if needed <= output_buf_size:
                return output_buf.value
            output_buf_size = needed
    except Exception:
        return long_path


def load_texture(path: str) -> TextureInfo:
    img = None
    try:
        # Проверка размера файла
        file_size_mb = os.path.getsize(path) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            log(f"[LOAD][SKIP] {os.path.basename(path)}: file too large ({file_size_mb:.1f}MB)")
            raise RuntimeError(f"file too large: {file_size_mb:.1f}MB")

        safe_path = get_short_path_name(path)
        try:
            img = rl.LoadImage(safe_path)
        except Exception:
            img = rl.LoadImage(safe_path.encode('utf-8'))

        w, h = img.width, img.height
        if w <= 0 or h <= 0:
            raise RuntimeError("empty image")

        # Масштабирование больших изображений
        needs_resize = False
        new_w, new_h = w, h

        if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
            scale = min(MAX_IMAGE_DIMENSION / w, MAX_IMAGE_DIMENSION / h)
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            needs_resize = True
            log(f"[LOAD][RESIZE] {os.path.basename(path)}: {w}x{h} -> {new_w}x{new_h}")

        if needs_resize:
            img = _image_resize_mut(img, new_w, new_h)

        tex = rl.LoadTextureFromImage(img)
        return TextureInfo(tex=tex, w=new_w, h=new_h)
    except Exception as e:
        log(f"[LOAD][ERR] {os.path.basename(path)}: {e!r}")
        ph = rl.GenImageColor(2, 2, _RL_WHITE)
        tex = rl.LoadTextureFromImage(ph)
        try:
            rl.UnloadImage(ph)
        except Exception:
            pass
        return TextureInfo(tex=tex, w=2, h=2)
    finally:
        try:
            if img is not None:
                rl.UnloadImage(img)
        except Exception:
            pass


def unload_texture_deferred(state: AppState, ti: Optional[TextureInfo]):
    tex = getattr(ti, 'tex', None)
    if getattr(tex, 'id', 0):
        state.to_unload.append(tex)


def process_deferred_unloads(state: AppState):
    while state.to_unload:
        tex = state.to_unload.pop()
        try:
            rl.UnloadTexture(tex)
        except Exception as e:
            log(f"[UNLOAD][ERR] {e!r}")


def build_thumb_for(path: str, target_h: int) -> BitmapThumb:
    try:
        # Проверка размера файла для миниатюр
        file_size_mb = os.path.getsize(path) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            log(f"[THUMB][SKIP] {os.path.basename(path)}: file too large ({file_size_mb:.1f}MB)")
            return BitmapThumb(None, (0, 0), path, False)

        safe_path = get_short_path_name(path)
        try:
            img = rl.LoadImage(safe_path)
        except Exception:
            img = rl.LoadImage(safe_path.encode('utf-8'))
    except Exception as e:
        log(f"[THUMB][ERR] {os.path.basename(path)}: load failed - {e!r}")
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
        log(f"[THUMB][ERR] {os.path.basename(path)}: resize failed - {e!r}")
        return BitmapThumb(None, (0, 0), path, False)


def schedule_thumbs(state: AppState, around_index: int):
    n = len(state.current_dir_images)
    if n == 0:
        return
    lo = max(0, around_index - THUMB_PRELOAD_SPAN)
    hi = min(n - 1, around_index + THUMB_PRELOAD_SPAN)
    inq = set(state.thumb_queue)
    added = 0
    for i in range(lo, hi + 1):
        p = state.current_dir_images[i]
        if (p not in state.thumb_cache) and (p not in inq):
            state.thumb_queue.append(p)
            inq.add(p)
            added += 1


def process_thumb_queue(state: AppState):
    target_h = int(state.screenH * GALLERY_HEIGHT_FRAC * 0.8)
    budget = THUMB_BUILD_BUDGET_PER_FRAME
    built = 0
    while budget > 0 and state.thumb_queue:
        p = state.thumb_queue.popleft()
        if p in state.thumb_cache:
            continue
        bt = build_thumb_for(p, target_h)
        state.thumb_cache[p] = bt
        budget -= 1
        built += 1
    while len(state.thumb_cache) > THUMB_CACHE_LIMIT:
        _, bt = state.thumb_cache.popitem(last=False)
        if bt and bt.texture:
            unload_texture_deferred(state, TextureInfo(bt.texture, 0, 0))


def compute_fit_scale(iw, ih, sw, sh, frac):
    if iw == 0 or ih == 0:
        return 1.0
    return min(sw * frac / iw, sh * frac / ih)


def center_view_for(scale, iw, ih, sw, sh):
    return ViewParams(scale=scale, offx=(sw - iw * scale) / 2.0, offy=(sh - ih * scale) / 2.0)


def compute_fit_view(state, frac):
    ti = state.cache.curr
    if not ti:
        return ViewParams()
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


def start_zoom_animation(state: AppState, target_view: ViewParams):
    state.zoom_anim_active = True
    state.zoom_anim_t0 = now()
    state.zoom_anim_from = ViewParams(state.view.scale, state.view.offx, state.view.offy)
    state.zoom_anim_to = target_view


def update_zoom_animation(state: AppState):
    if not state.zoom_anim_active:
        return

    t = (now() - state.zoom_anim_t0) / (ANIM_ZOOM_MS / 1000.0)
    if t >= 1.0:
        state.zoom_anim_active = False
        state.view = state.zoom_anim_to
        return

    t_eased = ease_out_quad(t)
    state.view = ViewParams(
        scale=lerp(state.zoom_anim_from.scale, state.zoom_anim_to.scale, t_eased),
        offx=lerp(state.zoom_anim_from.offx, state.zoom_anim_to.offx, t_eased),
        offy=lerp(state.zoom_anim_from.offy, state.zoom_anim_to.offy, t_eased),
    )


def win_set_blur(hwnd, enabled: bool):
    if enabled:
        WinBlur.enable(hwnd)
    else:
        WinBlur.disable(hwnd)


def apply_bg_mode(state: AppState):
    mode = BG_MODES[state.bg_mode_index]
    win_set_blur(state.hwnd, mode["blur"])
    c = mode["color"]
    a = clamp(state.bg_current_opacity, 0.0, 1.0)

    if mode["blur"]:
        try:
            rl.ClearBackground(rl.BLANK)
        except Exception:
            rl.ClearBackground(RL_Color(0, 0, 0, 0))
        rl.DrawRectangle(0, 0, state.screenW, state.screenH, RL_Color(c[0], c[1], c[2], int(255 * a)))
    else:
        col = RL_Color(c[0], c[1], c[2], int(255 * a))
        rl.ClearBackground(col)


def render_image_at(ti: TextureInfo, v: ViewParams, alpha: float = 1.0):
    if not ti:
        return
    tint = RL_Color(255, 255, 255, int(255 * alpha))
    rl.DrawTexturePro(ti.tex, RL_Rect(0, 0, ti.w, ti.h), RL_Rect(v.offx, v.offy, ti.w * v.scale, ti.h * v.scale),
                      RL_V2(0, 0), 0.0, tint)


def render_image(state: AppState):
    ti = state.cache.curr
    if not ti:
        return

    if state.open_anim_active:
        if state.open_anim_t0 == 0.0:
            log(f"[OPEN_ANIM] Timer not started yet, skipping render")
            return

        t = (now() - state.open_anim_t0) / (ANIM_OPEN_MS / 1000.0)
        if t >= 1.0:
            state.open_anim_active = False
            state.view = state.last_fit_view
            state.bg_current_opacity = state.bg_target_opacity
            log(f"[OPEN_ANIM] Animation complete at t={t:.3f}")
            t = 1.0
        if t <= 0.1 or t >= 0.9:
            log(f"[OPEN_ANIM] t={t:.3f} t_eased={ease_out_quad(t):.3f} scale={state.view.scale:.3f}")
        t_eased = ease_out_quad(t)
        from_view = compute_fit_view(state, FIT_OPEN_SCALE)
        to_view = state.last_fit_view
        v = ViewParams(
            scale=lerp(from_view.scale, to_view.scale, t_eased),
            offx=lerp(from_view.offx, to_view.offx, t_eased),
            offy=lerp(from_view.offy, to_view.offy, t_eased),
        )
        alpha = lerp(OPEN_ALPHA_START, 1.0, t_eased)
        state.bg_current_opacity = lerp(0.0, state.bg_target_opacity, t_eased)
        render_image_at(ti, v, alpha=alpha)
        return

    if state.switch_anim_active and state.switch_anim_prev_tex:
        t = (now() - state.switch_anim_t0) / (state.switch_anim_duration_ms / 1000.0)
        if t >= 1.0:
            state.switch_anim_active = False
            unload_texture_deferred(state, state.switch_anim_prev_tex)
            state.switch_anim_prev_tex = None
            t = 1.0
        t_eased = ease_in_out_cubic(t)

        offset = state.screenW * state.switch_anim_direction
        prev_x = lerp(0, -offset, t_eased)
        curr_x = lerp(offset, 0, t_eased)

        pv = ViewParams(
            scale=state.switch_anim_prev_view.scale,
            offx=state.switch_anim_prev_view.offx + prev_x,
            offy=state.switch_anim_prev_view.offy
        )
        render_image_at(state.switch_anim_prev_tex, pv, alpha=1.0 - t_eased)

        cv = ViewParams(scale=state.view.scale, offx=state.view.offx + curr_x, offy=state.view.offy)
        render_image_at(ti, cv, alpha=t_eased)
        return

    render_image_at(ti, state.view)


def get_close_button_pos(state: AppState) -> Tuple[int, int]:
    # Расстояние от края экрана до центра кнопки (одинаковое для обеих осей)
    dist = CLOSE_BTN_MARGIN + CLOSE_BTN_RADIUS
    cx = state.screenW - dist
    cy = dist
    return cx, cy


def is_point_in_close_button(state: AppState, x: float, y: float) -> bool:
    cx, cy = get_close_button_pos(state)
    dx = x - cx
    dy = y - cy
    dist = math.sqrt(dx * dx + dy * dy)
    return dist <= CLOSE_BTN_RADIUS


def update_close_button_alpha(state: AppState):
    mouse = rl.GetMousePosition()
    cx, cy = get_close_button_pos(state)

    dx = mouse.x - cx
    dy = mouse.y - cy
    dist = math.sqrt(dx * dx + dy * dy)

    trigger_radius = CLOSE_BTN_RADIUS * 3

    if dist > trigger_radius:
        target_alpha = CLOSE_BTN_ALPHA_MIN
    elif dist <= CLOSE_BTN_RADIUS:
        target_alpha = CLOSE_BTN_ALPHA_HOVER
    elif dist <= CLOSE_BTN_RADIUS * 1.5:
        target_alpha = CLOSE_BTN_ALPHA_MAX
    else:
        t = (trigger_radius - dist) / (trigger_radius - CLOSE_BTN_RADIUS * 1.5)
        target_alpha = lerp(CLOSE_BTN_ALPHA_FAR, CLOSE_BTN_ALPHA_MAX, t)

    fade_speed = 0.15
    diff = target_alpha - state.close_btn_alpha
    state.close_btn_alpha += diff * fade_speed


def draw_close_button(state: AppState):
    if state.close_btn_alpha < 0.01:
        return

    cx, cy = get_close_button_pos(state)

    btn_alpha = int(state.close_btn_alpha * 255)
    bg_alpha = int(state.close_btn_alpha * CLOSE_BTN_BG_ALPHA_MAX * 255)

    rl.DrawCircle(cx, cy, CLOSE_BTN_RADIUS, RL_Color(0, 0, 0, bg_alpha))

    rl.DrawCircleLines(cx, cy, CLOSE_BTN_RADIUS, RL_Color(255, 255, 255, btn_alpha))

    cross_size = CLOSE_BTN_RADIUS * 0.5
    rl.DrawLineEx(
        RL_V2(cx - cross_size, cy - cross_size),
        RL_V2(cx + cross_size, cy + cross_size),
        2.0,
        RL_Color(255, 255, 255, btn_alpha)
    )
    rl.DrawLineEx(
        RL_V2(cx + cross_size, cy - cross_size),
        RL_V2(cx - cross_size, cy + cross_size),
        2.0,
        RL_Color(255, 255, 255, btn_alpha)
    )


def check_close_button_click(state: AppState) -> bool:
    if not rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
        return False

    mouse = rl.GetMousePosition()
    return is_point_in_close_button(state, mouse.x, mouse.y)


def get_filename_text_color(state: AppState):
    mode = BG_MODES[state.bg_mode_index]
    bg_color = mode["color"]
    if bg_color == (0, 0, 0):
        return RL_Color(255, 255, 255, 255)
    else:
        return RL_Color(0, 0, 0, 255)


def draw_filename(state: AppState):
    if not state.show_filename or state.index >= len(state.current_dir_images):
        return

    filepath = state.current_dir_images[state.index]
    filename = os.path.basename(filepath)

    font_size = 24
    color = get_filename_text_color(state)

    if state.unicode_font:
        try:
            filename_bytes = filename.encode('utf-8')
            text_vec = rl.MeasureTextEx(state.unicode_font, filename_bytes, font_size, 1.0)
            text_width = int(text_vec.x)
            x = (state.screenW - text_width) // 2
            y = 40
            rl.DrawTextEx(state.unicode_font, filename_bytes, RL_V2(x, y), font_size, 1.0, color)
            return
        except Exception as e:
            log(f"[FONT][ERR] DrawTextEx failed: {e!r}")

    try:
        text_width = rl.MeasureText(filename, font_size)
    except TypeError:
        text_width = rl.MeasureText(filename.encode('utf-8'), font_size)

    x = (state.screenW - text_width) // 2
    y = 40
    RL_DrawText(filename, x, y, font_size, color)


def update_nav_buttons_fade(state: AppState):
    mouse = rl.GetMousePosition()
    zoom_threshold = state.last_fit_view.scale * 1.1
    is_significantly_zoomed = state.view.scale > zoom_threshold

    if not is_significantly_zoomed:
        state.nav_left_alpha = max(0.0, state.nav_left_alpha - 0.1)
        state.nav_right_alpha = max(0.0, state.nav_right_alpha - 0.1)
        return

    cy = state.screenH // 2
    cx_left = 60
    cx_right = state.screenW - 60

    fade_speed = 0.15
    trigger_radius = NAV_BTN_RADIUS * 3

    # Left button
    if state.index > 0:
        dx = mouse.x - cx_left
        dy = mouse.y - cy
        dist = math.sqrt(dx * dx + dy * dy)

        if dist > trigger_radius:
            target_alpha = 0.0
        elif dist <= NAV_BTN_RADIUS:
            target_alpha = 1.0
        elif dist <= NAV_BTN_RADIUS * 1.5:
            target_alpha = CLOSE_BTN_ALPHA_MAX
        else:
            t = (trigger_radius - dist) / (trigger_radius - NAV_BTN_RADIUS * 1.5)
            target_alpha = lerp(CLOSE_BTN_ALPHA_FAR, CLOSE_BTN_ALPHA_MAX, t)

        diff = target_alpha - state.nav_left_alpha
        state.nav_left_alpha += diff * fade_speed
    else:
        state.nav_left_alpha = max(0.0, state.nav_left_alpha - fade_speed)

    # Right button
    if state.index < len(state.current_dir_images) - 1:
        dx = mouse.x - cx_right
        dy = mouse.y - cy
        dist = math.sqrt(dx * dx + dy * dy)

        if dist > trigger_radius:
            target_alpha = 0.0
        elif dist <= NAV_BTN_RADIUS:
            target_alpha = 1.0
        elif dist <= NAV_BTN_RADIUS * 1.5:
            target_alpha = CLOSE_BTN_ALPHA_MAX
        else:
            t = (trigger_radius - dist) / (trigger_radius - NAV_BTN_RADIUS * 1.5)
            target_alpha = lerp(CLOSE_BTN_ALPHA_FAR, CLOSE_BTN_ALPHA_MAX, t)

        diff = target_alpha - state.nav_right_alpha
        state.nav_right_alpha += diff * fade_speed
    else:
        state.nav_right_alpha = max(0.0, state.nav_right_alpha - fade_speed)


def draw_arrow_left(cx: int, cy: int, size: float, color):
    points = [
        RL_V2(cx + size * 0.4, cy - size * 0.6),
        RL_V2(cx - size * 0.4, cy),
        RL_V2(cx + size * 0.4, cy + size * 0.6),
    ]
    rl.DrawLineEx(points[0], points[1], 2.5, color)
    rl.DrawLineEx(points[1], points[2], 2.5, color)


def draw_arrow_right(cx: int, cy: int, size: float, color):
    points = [
        RL_V2(cx - size * 0.4, cy - size * 0.6),
        RL_V2(cx + size * 0.4, cy),
        RL_V2(cx - size * 0.4, cy + size * 0.6),
    ]
    rl.DrawLineEx(points[0], points[1], 2.5, color)
    rl.DrawLineEx(points[1], points[2], 2.5, color)


def draw_nav_buttons(state: AppState):
    if state.nav_left_alpha <= 0.01 and state.nav_right_alpha <= 0.01:
        return

    cy = state.screenH // 2

    if state.nav_left_alpha > 0.01 and state.index > 0:
        cx = 60
        alpha = int(state.nav_left_alpha * 255)
        bg_alpha = int(state.nav_left_alpha * NAV_BTN_BG_ALPHA_MAX * 255)

        rl.DrawCircle(cx, cy, NAV_BTN_RADIUS, RL_Color(0, 0, 0, bg_alpha))
        rl.DrawCircleLines(cx, cy, NAV_BTN_RADIUS, RL_Color(255, 255, 255, alpha))
        draw_arrow_left(cx, cy, 18, RL_Color(255, 255, 255, alpha))

        mouse = rl.GetMousePosition()
        dx = mouse.x - cx
        dy = mouse.y - cy
        if dx * dx + dy * dy <= NAV_BTN_RADIUS * NAV_BTN_RADIUS:
            if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                switch_to(state, state.index - 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)

    if state.nav_right_alpha > 0.01 and state.index < len(state.current_dir_images) - 1:
        cx = state.screenW - 60
        alpha = int(state.nav_right_alpha * 255)
        bg_alpha = int(state.nav_right_alpha * NAV_BTN_BG_ALPHA_MAX * 255)

        rl.DrawCircle(cx, cy, NAV_BTN_RADIUS, RL_Color(0, 0, 0, bg_alpha))
        rl.DrawCircleLines(cx, cy, NAV_BTN_RADIUS, RL_Color(255, 255, 255, alpha))
        draw_arrow_right(cx, cy, 18, RL_Color(255, 255, 255, alpha))

        mouse = rl.GetMousePosition()
        dx = mouse.x - cx
        dy = mouse.y - cy
        if dx * dx + dy * dy <= NAV_BTN_RADIUS * NAV_BTN_RADIUS:
            if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                switch_to(state, state.index + 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)


def update_gallery_scroll(state: AppState):
    target = float(state.index)
    current = state.gallery_center_index
    diff = target - current

    if abs(diff) < 0.01:
        state.gallery_center_index = target
        return

    speed = 0.2
    state.gallery_center_index += diff * speed


def render_gallery(state: AppState):
    n = len(state.current_dir_images)
    if n == 0:
        return

    sw, sh = state.screenW, state.screenH
    gh = int(sh * GALLERY_HEIGHT_FRAC)
    y_hidden = sh
    y_visible = sh - gh
    state.gallery_y = clamp(state.gallery_y, y_visible, y_hidden)
    y = int(state.gallery_y)

    alpha_panel = 1.0 - ((state.gallery_y - y_visible) / (y_hidden - y_visible))
    rl.DrawRectangle(0, y, sw, gh, RL_Color(0, 0, 0, int(255 * 0.6 * alpha_panel)))

    mouse = rl.GetMousePosition()
    center_x = sw // 2
    base_thumb_h = int(gh * 0.8)

    visible_range = 10
    start_idx = max(0, int(state.gallery_center_index) - visible_range)
    end_idx = min(n - 1, int(state.gallery_center_index) + visible_range)

    thumb_positions = {}

    center_idx = int(state.gallery_center_index)
    thumb_positions[center_idx] = 0.0

    cumulative_offset = 0.0
    for idx in range(center_idx - 1, start_idx - 1, -1):
        p = state.current_dir_images[idx]
        bt = state.thumb_cache.get(p)

        distance = abs(idx - state.gallery_center_index)
        scale_factor = lerp(1.0, GALLERY_MIN_SCALE, min(1.0, distance / visible_range))
        if bt and bt.ready and bt.texture:
            w_curr = int(bt.size[0] * scale_factor)
        else:
            w_curr = int(base_thumb_h * 1.4 * scale_factor)

        next_idx = idx + 1
        next_p = state.current_dir_images[next_idx]
        next_bt = state.thumb_cache.get(next_p)
        next_distance = abs(next_idx - state.gallery_center_index)
        next_scale = lerp(1.0, GALLERY_MIN_SCALE, min(1.0, next_distance / visible_range))
        if next_bt and next_bt.ready and next_bt.texture:
            w_next = int(next_bt.size[0] * next_scale)
        else:
            w_next = int(base_thumb_h * 1.4 * next_scale)

        cumulative_offset -= (w_curr / 2.0 + GALLERY_THUMB_SPACING + w_next / 2.0)
        thumb_positions[idx] = cumulative_offset

    cumulative_offset = 0.0
    for idx in range(center_idx + 1, end_idx + 1):
        p = state.current_dir_images[idx]
        bt = state.thumb_cache.get(p)

        distance = abs(idx - state.gallery_center_index)
        scale_factor = lerp(1.0, GALLERY_MIN_SCALE, min(1.0, distance / visible_range))
        if bt and bt.ready and bt.texture:
            w_curr = int(bt.size[0] * scale_factor)
        else:
            w_curr = int(base_thumb_h * 1.4 * scale_factor)

        prev_idx = idx - 1
        prev_p = state.current_dir_images[prev_idx]
        prev_bt = state.thumb_cache.get(prev_p)
        prev_distance = abs(prev_idx - state.gallery_center_index)
        prev_scale = lerp(1.0, GALLERY_MIN_SCALE, min(1.0, prev_distance / visible_range))
        if prev_bt and prev_bt.ready and prev_bt.texture:
            w_prev = int(prev_bt.size[0] * prev_scale)
        else:
            w_prev = int(base_thumb_h * 1.4 * prev_scale)

        cumulative_offset += (w_prev / 2.0 + GALLERY_THUMB_SPACING + w_curr / 2.0)
        thumb_positions[idx] = cumulative_offset

    center_frac = state.gallery_center_index - int(state.gallery_center_index)
    center_int = int(state.gallery_center_index)
    offset_adjust = 0.0
    if center_frac > 0 and center_int + 1 in thumb_positions and center_int in thumb_positions:
        offset_adjust = lerp(thumb_positions[center_int], thumb_positions[center_int + 1], center_frac)

    for idx in range(start_idx, end_idx + 1):
        if idx not in thumb_positions:
            continue

        p = state.current_dir_images[idx]
        bt = state.thumb_cache.get(p)

        distance = abs(idx - state.gallery_center_index)

        scale_factor = lerp(1.0, GALLERY_MIN_SCALE, min(1.0, distance / visible_range))

        alpha_factor = lerp(1.0, GALLERY_MIN_ALPHA, min(1.0, distance / visible_range))

        if bt and bt.ready and bt.texture and getattr(bt.texture, 'id', 0):
            scaled_w = int(bt.size[0] * scale_factor)
            scaled_h = int(bt.size[1] * scale_factor)

            thumb_center_x = center_x + int(thumb_positions[idx] - offset_adjust)
            thumb_x = thumb_center_x - scaled_w // 2
            thumb_y = y + (gh - scaled_h) // 2

            is_hover = (thumb_x <= mouse.x <= thumb_x + scaled_w) and (thumb_y <= mouse.y <= thumb_y + scaled_h)
            final_alpha = 1.0 if is_hover else alpha_factor

            try:
                src_rect = RL_Rect(0, 0, bt.size[0], bt.size[1])
                dst_rect = RL_Rect(thumb_x, thumb_y, scaled_w, scaled_h)
                tint = RL_Color(255, 255, 255, int(255 * final_alpha * alpha_panel))
                rl.DrawTexturePro(bt.texture, src_rect, dst_rect, RL_V2(0, 0), 0.0, tint)
            except Exception as e:
                log(f"[DRAW][THUMB][ERR] {os.path.basename(p)}: {e!r}")

            if idx == state.index:
                rl.DrawRectangleLines(thumb_x - 2, thumb_y - 2, scaled_w + 4, scaled_h + 4,
                                      RL_Color(255, 255, 255, int(255 * alpha_panel)))

            if is_hover and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                switch_to(state, idx)
        else:
            scaled_w = int(base_thumb_h * 1.4 * scale_factor)
            scaled_h = int(base_thumb_h * scale_factor)
            thumb_center_x = center_x + int(thumb_positions[idx] - offset_adjust)
            thumb_x = thumb_center_x - scaled_w // 2
            thumb_y = y + (gh - scaled_h) // 2

            rl.DrawRectangle(thumb_x, thumb_y, scaled_w, scaled_h,
                             RL_Color(64, 64, 64, int(255 * alpha_factor * alpha_panel)))


def is_mouse_over_gallery(state: AppState) -> bool:
    mouse = rl.GetMousePosition()
    gh = int(state.screenH * GALLERY_HEIGHT_FRAC)
    y_visible = state.screenH - gh
    return y_visible <= mouse.y <= state.screenH and state.gallery_y < state.screenH


def preload_neighbors(state: AppState, new_index: int):
    n = len(state.current_dir_images)
    if n == 0:
        state.cache = ImageCache()
        state.index = 0
        return
    new_index = clamp(new_index, 0, n - 1)

    if state.cache.curr and state.index < len(state.current_dir_images):
        old_path = state.current_dir_images[state.index]
        state.view_memory[old_path] = ViewParams(state.view.scale, state.view.offx, state.view.offy)

    to_unload = [state.cache.prev, state.cache.next]
    if not state.switch_anim_active:
        to_unload.append(state.cache.curr)

    for ti in to_unload:
        if ti:
            unload_texture_deferred(state, ti)

    def _safe(path):
        try:
            return load_texture(path)
        except Exception as e:
            log(f"[LOAD][SAFE][ERR] {os.path.basename(path)}: {e!r}")
            return None

    cur = _safe(state.current_dir_images[new_index])
    prev = _safe(state.current_dir_images[new_index - 1]) if new_index - 1 >= 0 else None
    nxt = _safe(state.current_dir_images[new_index + 1]) if new_index + 1 < n else None
    state.cache = ImageCache(prev=prev, curr=cur, next=nxt)
    state.index = new_index
    schedule_thumbs(state, new_index)
    state.last_fit_view = compute_fit_view(state, FIT_DEFAULT_SCALE)

    new_path = state.current_dir_images[new_index]
    if new_path in state.view_memory:
        state.view = state.view_memory[new_path]
        state.is_zoomed = (state.view.scale > state.last_fit_view.scale)

        if abs(state.view.scale - 1.0) < 0.01:
            state.zoom_state_cycle = 0
        elif abs(state.view.scale - state.last_fit_view.scale) < 0.01:
            state.zoom_state_cycle = 1
        else:
            state.zoom_state_cycle = 2
    else:
        state.view = state.last_fit_view
        state.is_zoomed = False
        state.zoom_state_cycle = 1


def switch_to(state: AppState, idx: int, animate: bool = True, anim_duration_ms: int = ANIM_SWITCH_KEYS_MS):
    if idx == state.index:
        return

    direction = 1 if idx > state.index else -1

    if state.switch_anim_active:
        if len(state.switch_queue) < 20:
            state.switch_queue.append((direction, anim_duration_ms))
        return

    state.is_panning = False

    if animate and state.cache.curr:
        state.switch_anim_prev_tex = TextureInfo(state.cache.curr.tex, state.cache.curr.w, state.cache.curr.h)
        state.switch_anim_prev_view = ViewParams(state.view.scale, state.view.offx, state.view.offy)
        state.switch_anim_active = True
        state.switch_anim_t0 = now()
        state.switch_anim_direction = direction
        state.switch_anim_duration_ms = anim_duration_ms

    preload_neighbors(state, idx)


def process_switch_queue(state: AppState):
    if state.switch_anim_active or len(state.switch_queue) == 0:
        return

    direction, duration_ms = state.switch_queue.popleft()

    n = len(state.current_dir_images)
    if direction > 0:
        target_idx = min(n - 1, state.index + 1)
    else:
        target_idx = max(0, state.index - 1)

    if target_idx != state.index:
        switch_to(state, target_idx, animate=True, anim_duration_ms=duration_ms)


def view_for_1to1_centered(state: AppState) -> ViewParams:
    ti = state.cache.curr
    if not ti:
        return state.view
    return center_view_for(1.0, ti.w, ti.h, state.screenW, state.screenH)


def cycle_zoom_state(state: AppState):
    next_state = {0: 1, 1: 2, 2: 0}[state.zoom_state_cycle]

    if next_state == 0:
        target = view_for_1to1_centered(state)
    elif next_state == 1:
        target = state.last_fit_view
    else:
        current_path = state.current_dir_images[state.index] if state.index < len(state.current_dir_images) else None
        if current_path and current_path in state.user_zoom_memory:
            target = state.user_zoom_memory[current_path]
            log(f"[ZOOM] Restoring user zoom: scale={target.scale:.3f}")
        else:
            target = state.last_fit_view
            log(f"[ZOOM] No user zoom saved, using FIT")

    t0 = now()
    dur = ANIM_TOGGLE_ZOOM_MS / 1000.0
    v_from = state.view
    ti = state.cache.curr
    while True:
        if rl.WindowShouldClose():
            break
        rl.BeginDrawing()
        apply_bg_mode(state)
        t = (now() - t0) / dur
        if t >= 1.0:
            t = 1.0
        t_eased = ease_in_out_cubic(t)
        cur = ViewParams(
            scale=lerp(v_from.scale, target.scale, t_eased),
            offx=lerp(v_from.offx, target.offx, t_eased),
            offy=lerp(v_from.offy, target.offy, t_eased),
        )
        state.view = clamp_pan(cur, ti, state.screenW, state.screenH)
        render_image(state)
        draw_close_button(state)
        render_gallery(state)
        rl.EndDrawing()
        if t >= 1.0:
            break

    state.zoom_state_cycle = next_state
    state.is_zoomed = (state.view.scale > state.last_fit_view.scale)

    current_path = state.current_dir_images[state.index] if state.index < len(state.current_dir_images) else None
    if current_path:
        state.view_memory[current_path] = ViewParams(state.view.scale, state.view.offx, state.view.offy)


def apply_bg_opacity_anim(state: AppState):
    if state.open_anim_active:
        return
    delta = state.bg_target_opacity - state.bg_current_opacity
    if abs(delta) < 0.001:
        return
    step = (1.0 / (ANIM_SWITCH_KEYS_MS / 1000.0)) / TARGET_FPS
    state.bg_current_opacity += clamp(delta, -step, step)


def update_gallery_visibility_and_slide(state: AppState):
    mouse = rl.GetMousePosition()
    gh = int(state.screenH * GALLERY_HEIGHT_FRAC)
    y_hidden = state.screenH
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
    t = now()
    if (t - state.last_click_time) < (DOUBLE_CLICK_TIME_MS / 1000.0):
        dx = abs(x - state.last_click_pos[0])
        dy = abs(y - state.last_click_pos[1])
        if dx < 10 and dy < 10:
            state.last_click_time = 0.0
            return True
    state.last_click_time = t
    state.last_click_pos = (x, y)
    return False


def main():
    global _frame
    start_path = None
    for a in sys.argv[1:]:
        p = os.path.abspath(a)
        if os.path.exists(p):
            start_path = p
            break
    init_window_and_blur(state := AppState())

    if start_path and os.path.isdir(start_path):
        dirpath = start_path
        images = list_images(dirpath)
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
            rl.BeginDrawing()
            apply_bg_mode(state)
            RL_DrawText("No images found", 40, 40, 28, rl.GRAY)
            rl.EndDrawing()
        rl.CloseWindow()
        return

    preload_neighbors(state, start_index)
    state.last_fit_view = compute_fit_view(state, FIT_DEFAULT_SCALE)
    state.gallery_center_index = float(start_index)
    schedule_thumbs(state, state.index)

    state.open_anim_active = True
    state.open_anim_t0 = 0.0
    state.view = compute_fit_view(state, FIT_OPEN_SCALE)
    state.bg_current_opacity = 0.0
    log(f"[OPEN_ANIM] Preparing animation: view.scale={state.view.scale:.3f} target={state.last_fit_view.scale:.3f}")

    log(f"[DIR] {dirpath} files={len(images)} start={state.index} -> {os.path.basename(images[state.index])}")
    atexit.register(lambda: log(f"[EXIT] frames={_frame} thumbs={len(state.thumb_cache)} q={len(state.thumb_queue)}"))

    first_iteration = True

    try:
        while True:
            if first_iteration:
                if state.open_anim_active and state.open_anim_t0 == 0.0:
                    state.open_anim_t0 = now()
                    log(f"[OPEN_ANIM] Timer started at t={state.open_anim_t0}")
                mode = BG_MODES[state.bg_mode_index]
                if mode["blur"]:
                    WinBlur.enable(state.hwnd)
                    log(f"[INIT] Blur enabled")
                first_iteration = False

            process_thumb_queue(state)
            process_deferred_unloads(state)
            update_gallery_visibility_and_slide(state)
            update_gallery_scroll(state)
            update_zoom_animation(state)
            process_switch_queue(state)
            apply_bg_opacity_anim(state)
            update_nav_buttons_fade(state)
            update_close_button_alpha(state)

            should_close = rl.WindowShouldClose()
            if should_close:
                break
            rl.BeginDrawing()
            apply_bg_mode(state)

            mouse = rl.GetMousePosition()

            # Check close button FIRST - if clicked, ignore all other input
            if check_close_button_click(state):
                break

            if rl.IsKeyPressed(rl.KEY_I):
                state.show_hud = not state.show_hud

            if rl.IsKeyPressed(rl.KEY_N):
                state.show_filename = not state.show_filename

            if rl.IsKeyPressed(rl.KEY_V):
                state.bg_mode_index = (state.bg_mode_index + 1) % len(BG_MODES)
                state.bg_target_opacity = BG_MODES[state.bg_mode_index]["opacity"]

            if state.cache.curr and not state.open_anim_active:
                if rl.IsKeyDown(rl.KEY_UP):
                    nv = recompute_view_anchor_zoom(state.view, state.view.scale * (1.0 + ZOOM_STEP_KEYS),
                                                    (int(mouse.x), int(mouse.y)), state.cache.curr)
                    nv = clamp_pan(nv, state.cache.curr, state.screenW, state.screenH)
                    start_zoom_animation(state, nv)
                    state.is_zoomed = (nv.scale > state.last_fit_view.scale)
                    state.zoom_state_cycle = 2
                    if state.index < len(state.current_dir_images):
                        path = state.current_dir_images[state.index]
                        state.view_memory[path] = nv
                        state.user_zoom_memory[path] = nv
                        log(f"[ZOOM] Saved user zoom: scale={nv.scale:.3f}")
                if rl.IsKeyDown(rl.KEY_DOWN):
                    nv = recompute_view_anchor_zoom(state.view, state.view.scale * (1.0 - ZOOM_STEP_KEYS),
                                                    (int(mouse.x), int(mouse.y)), state.cache.curr)
                    nv = clamp_pan(nv, state.cache.curr, state.screenW, state.screenH)
                    start_zoom_animation(state, nv)
                    state.is_zoomed = (nv.scale > state.last_fit_view.scale)
                    state.zoom_state_cycle = 2
                    if state.index < len(state.current_dir_images):
                        path = state.current_dir_images[state.index]
                        state.view_memory[path] = nv
                        state.user_zoom_memory[path] = nv
                        log(f"[ZOOM] Saved user zoom: scale={nv.scale:.3f}")

            wheel = rl.GetMouseWheelMove()
            if wheel != 0.0 and state.cache.curr and not state.open_anim_active:
                if is_mouse_over_gallery(state):
                    n = len(state.current_dir_images)
                    if wheel > 0:
                        new_idx = max(0, state.index - 1)
                        if new_idx != state.index:
                            switch_to(state, new_idx, animate=True, anim_duration_ms=ANIM_SWITCH_GALLERY_MS)
                    else:
                        new_idx = min(n - 1, state.index + 1)
                        if new_idx != state.index:
                            switch_to(state, new_idx, animate=True, anim_duration_ms=ANIM_SWITCH_GALLERY_MS)
                else:
                    nv = recompute_view_anchor_zoom(state.view, state.view.scale * (1.0 + wheel * ZOOM_STEP_WHEEL),
                                                    (int(mouse.x), int(mouse.y)), state.cache.curr)
                    nv = clamp_pan(nv, state.cache.curr, state.screenW, state.screenH)
                    start_zoom_animation(state, nv)
                    state.is_zoomed = (nv.scale > state.last_fit_view.scale)
                    state.zoom_state_cycle = 2
                    if state.index < len(state.current_dir_images):
                        path = state.current_dir_images[state.index]
                        state.view_memory[path] = nv
                        state.user_zoom_memory[path] = nv

            mid_left = state.screenW * 0.33
            mid_right = state.screenW * 0.66
            mid_top = state.screenH * 0.33
            mid_bot = state.screenH * 0.66
            in_mid = (mid_left <= mouse.x <= mid_right and mid_top <= mouse.y <= mid_bot)

            if rl.IsKeyPressed(rl.KEY_F):
                cycle_zoom_state(state)

            if in_mid and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                if detect_double_click(state, int(mouse.x), int(mouse.y)):
                    cycle_zoom_state(state)

            if state.cache.curr and not state.open_anim_active:
                img_rect = RL_Rect(state.view.offx, state.view.offy, state.cache.curr.w * state.view.scale,
                                   state.cache.curr.h * state.view.scale)
                over_img = (
                        img_rect.x <= mouse.x <= img_rect.x + img_rect.width and img_rect.y <= mouse.y <= img_rect.y + img_rect.height)

                # Don't start panning if clicked on close button
                if rl.IsMouseButtonPressed(
                        rl.MOUSE_BUTTON_LEFT) and state.is_zoomed and over_img and not is_point_in_close_button(state,
                                                                                                                mouse.x,
                                                                                                                mouse.y):
                    state.is_panning = True
                    state.pan_start_mouse = (mouse.x, mouse.y)
                    state.pan_start_offset = (state.view.offx, state.view.offy)
                if rl.IsMouseButtonReleased(rl.MOUSE_BUTTON_LEFT):
                    state.is_panning = False
                if state.is_panning:
                    dx = mouse.x - state.pan_start_mouse[0]
                    dy = mouse.y - state.pan_start_mouse[1]
                    nv = ViewParams(scale=state.view.scale, offx=state.pan_start_offset[0] + dx,
                                    offy=state.pan_start_offset[1] + dy)
                    state.view = clamp_pan(nv, state.cache.curr, state.screenW, state.screenH)
                    state.zoom_state_cycle = 2
                    if state.index < len(state.current_dir_images):
                        path = state.current_dir_images[state.index]
                        state.view_memory[path] = state.view
                        state.user_zoom_memory[path] = state.view

            if not state.open_anim_active:
                edge_left = (mouse.x <= state.screenW * 0.10)
                edge_right = (mouse.x >= state.screenW * 0.90)
                gh = int(state.screenH * GALLERY_HEIGHT_FRAC)
                yv = state.screenH - gh
                in_gallery_panel = (yv <= mouse.y <= state.screenH)

                zoom_threshold = state.last_fit_view.scale * 1.1
                is_significantly_zoomed = state.view.scale > zoom_threshold

                if rl.IsKeyPressed(rl.KEY_RIGHT) or rl.IsKeyPressed(rl.KEY_D):
                    if state.index + 1 < len(state.current_dir_images):
                        switch_to(state, state.index + 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)
                if rl.IsKeyPressed(rl.KEY_LEFT) or rl.IsKeyPressed(rl.KEY_A):
                    if state.index - 1 >= 0:
                        switch_to(state, state.index - 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)

                if not is_significantly_zoomed and not in_gallery_panel:
                    if edge_right and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                        if state.index + 1 < len(state.current_dir_images):
                            switch_to(state, state.index + 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)
                    if edge_left and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                        if state.index - 1 >= 0:
                            switch_to(state, state.index - 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)

            if check_close_button_click(state):
                break

            render_image(state)
            draw_nav_buttons(state)
            draw_close_button(state)
            draw_filename(state)
            try:
                render_gallery(state)
            except Exception as e:
                log(f"[DRAW][GALLERY][EXC] {e!r}\n{traceback.format_exc()}")

            if state.show_hud:
                hud_y = state.screenH - 120
                line_spacing = 24
                RL_DrawText(f"RL={RL_VER}", 12, hud_y, 16, rl.LIGHTGRAY)
                RL_DrawText(f"idx={state.index + 1}/{len(state.current_dir_images)} zoom={state.view.scale:.3f}", 12,
                            hud_y + line_spacing, 16, rl.LIGHTGRAY)
                cx, cy = get_close_button_pos(state)
                dist_right = state.screenW - cx
                dist_top = cy
                RL_DrawText(f"close_btn: cx={cx} cy={cy} dist_R={dist_right} dist_T={dist_top}", 12,
                            hud_y + line_spacing * 2, 16, rl.LIGHTGRAY)

            rl.EndDrawing()
            _frame += 1
            if rl.IsKeyPressed(rl.KEY_ESCAPE):
                break
            if should_close:
                break
    finally:
        process_deferred_unloads(state)
        for bt in list(state.thumb_cache.values()):
            try:
                if bt.texture:
                    rl.UnloadTexture(bt.texture)
            except Exception as e:
                log(f"[CLEANUP][THUMB][ERR] {e!r}")
        for ti in (state.cache.prev, state.cache.curr, state.cache.next):
            try:
                if ti and getattr(ti.tex, 'id', 0):
                    rl.UnloadTexture(ti.tex)
            except Exception as e:
                log(f"[CLEANUP][TEX][ERR] {e!r}")
        try:
            rl.CloseWindow()
        except Exception as e:
            log(f"[CLOSE][ERR] {e!r}")


if __name__ == '__main__':
    main()