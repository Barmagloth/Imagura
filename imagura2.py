#!imagura2_async_fixed.py
from __future__ import annotations
import os, sys, time, ctypes, atexit, traceback, struct, hashlib
from dataclasses import dataclass, field
from collections import OrderedDict, deque
from typing import List, Tuple, Optional, Deque, Callable, Any
from queue import PriorityQueue, Empty
from threading import Thread, Lock
from enum import IntEnum
import math

TARGET_FPS = 120
ANIM_SWITCH_KEYS_MS = 700
ANIM_SWITCH_GALLERY_MS = 10
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
HEAVY_FILE_SIZE_MB = 10
HEAVY_MIN_SHORT_SIDE = 4000
GALLERY_HEIGHT_FRAC = 0.12
GALLERY_TRIGGER_FRAC = 0.08
GALLERY_SLIDE_MS = 150
GALLERY_THUMB_SPACING = 20
GALLERY_MIN_SCALE = 0.7
GALLERY_MIN_ALPHA = 0.3
THUMB_CACHE_LIMIT = 400
THUMB_CACHE_DIR = ".imagura_cache"
THUMB_PADDING = 6
THUMB_PRELOAD_SPAN = 40
THUMB_BUILD_BUDGET_PER_FRAME = 2
DOUBLE_CLICK_TIME_MS = 300
IDLE_THRESHOLD_SECONDS = 0.5
ASYNC_WORKERS = 10
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


class LoadPriority(IntEnum):
    CURRENT = 0
    NEIGHBOR = 1
    GALLERY = 2


@dataclass
class LoadTask:
    path: str
    priority: LoadPriority
    callback: Callable
    timestamp: float = 0.0

    def __lt__(self, other):
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.timestamp < other.timestamp


@dataclass
class UIEvent:
    callback: Callable
    args: tuple


class AsyncImageLoader:
    def __init__(self, loader_func: Callable):
        self.task_queue = PriorityQueue()
        self.loader_func = loader_func
        self.running = True
        self.ui_events = deque()
        self.ui_lock = Lock()
        self.workers = []

        for _ in range(ASYNC_WORKERS):
            worker = Thread(target=self._worker_loop, daemon=True)
            worker.start()
            self.workers.append(worker)

    def _worker_loop(self):
        while self.running:
            try:
                task = self.task_queue.get(timeout=0.1)
            except Empty:
                continue

            result = None
            error = None

            try:
                result = self.loader_func(task.path)
            except Exception as e:
                error = e

            self._push_ui_event(task.callback, (task.path, result, error))
            self.task_queue.task_done()

    def _push_ui_event(self, callback: Callable, args: tuple):
        with self.ui_lock:
            self.ui_events.append(UIEvent(callback, args))

    def poll_ui_events(self, max_events: int = 100, filter_priority: bool = False):
        events_to_process = []
        with self.ui_lock:
            count = 0
            while self.ui_events and count < max_events:
                event = self.ui_events.popleft()
                if filter_priority:
                    continue
                events_to_process.append(event)
                count += 1

        for event in events_to_process:
            try:
                event.callback(*event.args)
            except Exception as e:
                log(f"[UI_EVENT][ERR] {e!r}")

    def submit(self, path: str, priority: LoadPriority, callback: Callable):
        task = LoadTask(path, priority, callback, now())
        self.task_queue.put(task)

    def shutdown(self):
        self.running = False
        for worker in self.workers:
            worker.join(timeout=1.0)


class IdleDetector:
    def __init__(self, threshold: float = IDLE_THRESHOLD_SECONDS):
        self.threshold = threshold
        self.last_activity = now()

    def mark_activity(self):
        self.last_activity = now()

    def is_idle(self) -> bool:
        return (now() - self.last_activity) >= self.threshold


def probe_image_dimensions(filepath: str) -> Optional[Tuple[int, int]]:
    ext = os.path.splitext(filepath)[1].lower()
    try:
        with open(filepath, 'rb') as f:
            header = f.read(64 * 1024)

        if ext in ('.jpg', '.jpeg'):
            return _probe_jpeg(header)
        elif ext == '.png':
            return _probe_png(header)
    except Exception:
        pass
    return None


def _probe_jpeg(data: bytes) -> Optional[Tuple[int, int]]:
    i = 0
    while i + 9 < len(data):
        if data[i] == 0xFF:
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                height = struct.unpack('>H', data[i + 5:i + 7])[0]
                width = struct.unpack('>H', data[i + 7:i + 9])[0]
                return (width, height)
            elif marker not in (0x00, 0xFF) and i + 3 < len(data):
                seg_len = struct.unpack('>H', data[i + 2:i + 4])[0]
                i += 2 + seg_len
            else:
                i += 1
        else:
            i += 1
    return None


def _probe_png(data: bytes) -> Optional[Tuple[int, int]]:
    if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n':
        return None
    width = struct.unpack('>I', data[16:20])[0]
    height = struct.unpack('>I', data[20:24])[0]
    return (width, height)


def is_heavy_image(filepath: str) -> bool:
    try:
        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        if file_size_mb >= HEAVY_FILE_SIZE_MB:
            return True
    except Exception:
        pass

    dims = probe_image_dimensions(filepath)
    if dims:
        w, h = dims
        if min(w, h) >= HEAVY_MIN_SHORT_SIDE:
            return True
    return False


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
        sys.stdout.flush()
    except Exception:
        try:
            sys.stderr.write(line)
            sys.stderr.flush()
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
    path: str = ""


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
    async_loader: Optional[AsyncImageLoader] = None
    idle_detector: Optional[IdleDetector] = None
    loading_current: bool = False
    waiting_for_switch: bool = False
    waiting_prev_snapshot: Optional[TextureInfo] = None
    waiting_prev_view: ViewParams = field(default_factory=ViewParams)
    pending_target_index: Optional[int] = None
    pending_neighbors_load: bool = False
    gallery_target_index: Optional[int] = None
    gallery_last_wheel_time: float = 0.0
    pending_switch_duration_ms: int = field(default=ANIM_SWITCH_KEYS_MS)


def get_thumb_cache_path(filepath: str) -> str:
    try:
        stat = os.stat(filepath)
        key_data = f"{filepath}|{stat.st_mtime_ns}|{stat.st_size}".encode('utf-8')
    except Exception:
        key_data = filepath.encode('utf-8')

    cache_key = hashlib.sha1(key_data).hexdigest()
    os.makedirs(THUMB_CACHE_DIR, exist_ok=True)
    return os.path.join(THUMB_CACHE_DIR, f"{cache_key}_thumb.qoi")


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def lerp(a, b, t):
    t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return a + (b - a) * t


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
                if hasattr(rl, 'ffi'):
                    font = rl.LoadFontEx(font_path.encode('utf-8'), font_size, rl.ffi.NULL, 0)
                else:
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
    log("[INIT] Starting window initialization")
    x, y, w, h = get_work_area()
    if w == 0 or h == 0:
        mon = getattr(rl, 'GetCurrentMonitor', lambda: 0)()
        w, h = rl.GetMonitorWidth(mon), rl.GetMonitorHeight(mon)
        x, y = 0, 0

    log(f"[INIT] Creating window: {w}x{h} at ({x}, {y})")
    try:
        rl.InitWindow(w, h, "Viewer")
    except TypeError:
        rl.InitWindow(w, h, b"Viewer")

    log("[INIT] Window created")

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
    state.unicode_font = None
    state.async_loader = AsyncImageLoader(load_image_cpu_only)
    state.idle_detector = IdleDetector()
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


def load_image_cpu_only(path: str):
    file_size_mb = os.path.getsize(path) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise RuntimeError(f"file too large: {file_size_mb:.1f}MB")

    safe_path = get_short_path_name(path)
    try:
        img = rl.LoadImage(safe_path)
    except Exception:
        img = rl.LoadImage(safe_path.encode('utf-8'))

    w, h = img.width, img.height
    if w <= 0 or h <= 0:
        raise RuntimeError("empty image")

    if w > MAX_IMAGE_DIMENSION or h > MAX_IMAGE_DIMENSION:
        scale = min(MAX_IMAGE_DIMENSION / w, MAX_IMAGE_DIMENSION / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        log(f"[LOAD_CPU][RESIZE] {os.path.basename(path)}: {w}x{h} -> {new_w}x{new_h}")
        img = _image_resize_mut(img, new_w, new_h)

    return img


def image_to_textureinfo(img, path: str) -> TextureInfo:
    tex = rl.LoadTextureFromImage(img)
    w, h = img.width, img.height
    try:
        rl.UnloadImage(img)
    except Exception:
        pass
    return TextureInfo(tex=tex, w=w, h=h, path=path)


def unload_texture_deferred(state: AppState, ti: Optional[TextureInfo]):
    if not ti:
        return
    tex = getattr(ti, 'tex', None)
    if not tex:
        return
    tex_id = getattr(tex, 'id', 0)
    if tex_id and tex_id > 0:
        state.to_unload.append(tex)
        log(f"[DEFER_UNLOAD] Queued: {os.path.basename(ti.path)} (id={tex_id})")


def process_deferred_unloads(state: AppState):
    while state.to_unload:
        tex = state.to_unload.pop()
        try:
            tex_id = getattr(tex, 'id', 0)
            if tex_id and tex_id > 0:
                rl.UnloadTexture(tex)
                log(f"[UNLOAD] Texture id={tex_id}")
        except Exception as e:
            log(f"[UNLOAD][ERR] {e!r}")


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
        if state.cache.curr:
            state.view = sanitize_view(state, state.zoom_anim_to, state.cache.curr)
        else:
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
    tex_id = getattr(ti.tex, 'id', 0)
    if not tex_id or tex_id <= 0:
        return
    tint = RL_Color(255, 255, 255, int(255 * alpha))
    rl.DrawTexturePro(ti.tex, RL_Rect(0, 0, ti.w, ti.h), RL_Rect(v.offx, v.offy, ti.w * v.scale, ti.h * v.scale),
                      RL_V2(0, 0), 0.0, tint)


def draw_loading_indicator(state: AppState):
    if not state.loading_current:
        return

    rl.DrawRectangle(0, 0, state.screenW, state.screenH, RL_Color(0, 0, 0, 120))

    cx = state.screenW // 2
    cy = state.screenH // 2
    radius = 50
    thickness = 6

    t = now() * 2.5
    angle = (t * 360.0) % 360.0

    rl.DrawRing(RL_V2(cx, cy), radius - thickness, radius, angle, angle + 90, 32, RL_Color(255, 255, 255, 220))

    text = "Loading..."
    font_size = 28
    try:
        text_width = rl.MeasureText(text, font_size)
    except TypeError:
        text_width = rl.MeasureText(text.encode('utf-8'), font_size)

    RL_DrawText(text, cx - text_width // 2, cy + radius + 30, font_size, RL_Color(255, 255, 255, 220))


def render_image(state: AppState):
    ti = state.cache.curr
    if not ti:
        return

    if state.open_anim_active:
        if state.open_anim_t0 == 0.0:
            return

        t = (now() - state.open_anim_t0) / (ANIM_OPEN_MS / 1000.0)
        if t >= 1.0:
            state.open_anim_active = False
            state.view = sanitize_view(state, state.last_fit_view, ti)
            state.bg_current_opacity = state.bg_target_opacity

            if state.pending_neighbors_load:
                state.pending_neighbors_load = False
                log(f"[OPEN_ANIM] Finished, starting deferred neighbor/thumb load")
                preload_neighbors(state, state.index, skip_neighbors=False)
            else:
                log(f"[OPEN_ANIM] Finished: scale={state.view.scale:.3f} off=({state.view.offx:.1f},{state.view.offy:.1f})")
            t = 1.0
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

            old_view = ViewParams(state.view.scale, state.view.offx, state.view.offy)
            state.view = sanitize_view(state, state.view, ti)
            if abs(old_view.offx - state.view.offx) > 1.0 or abs(old_view.offy - state.view.offy) > 1.0:
                log(f"[SWITCH_ANIM] Finished, sanitized: scale={old_view.scale:.3f}->{state.view.scale:.3f} off=({old_view.offx:.1f},{old_view.offy:.1f})->({state.view.offx:.1f},{state.view.offy:.1f})")
            else:
                log(f"[SWITCH_ANIM] Finished, view OK: scale={state.view.scale:.3f} off=({state.view.offx:.1f},{state.view.offy:.1f})")

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
        except Exception:
            pass

    try:
        text_width = rl.MeasureText(filename, font_size)
    except TypeError:
        text_width = rl.MeasureText(filename.encode('utf-8'), font_size)

    x = (state.screenW - text_width) // 2
    y = 40
    RL_DrawText(filename, x, y, font_size, color)


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


def schedule_thumbs(state: AppState, around_index: int):
    n = len(state.current_dir_images)
    if n == 0:
        return
    lo = max(0, around_index - THUMB_PRELOAD_SPAN)
    hi = min(n - 1, around_index + THUMB_PRELOAD_SPAN)
    inq = set(state.thumb_queue)
    for i in range(lo, hi + 1):
        p = state.current_dir_images[i]
        if (p not in state.thumb_cache) and (p not in inq):
            state.thumb_queue.append(p)
            inq.add(p)


def build_thumb_from_image(img, target_h: int, src_path: str) -> BitmapThumb:
    try:
        w, h = img.width, img.height
        if w <= 0 or h <= 0:
            return BitmapThumb(None, (0, 0), src_path, False)

        scale = target_h / h
        tw, th = max(1, int(w * scale)), target_h
        rimg = _image_resize_mut(img, tw, th)

        tex = rl.LoadTextureFromImage(rimg)
        try:
            rl.UnloadImage(rimg)
        except Exception:
            pass

        return BitmapThumb(tex, (tw, th), src_path, True)
    except Exception as e:
        log(f"[THUMB][ERR] {os.path.basename(src_path)}: {e!r}")
        return BitmapThumb(None, (0, 0), src_path, False)


def process_thumb_queue(state: AppState):
    target_h = int(state.screenH * GALLERY_HEIGHT_FRAC * 0.8)
    budget = THUMB_BUILD_BUDGET_PER_FRAME

    while budget > 0 and state.thumb_queue:
        p = state.thumb_queue.popleft()
        if p in state.thumb_cache:
            continue

        state.thumb_cache[p] = BitmapThumb(None, (0, 0), p, False)

        def on_thumb_loaded(path: str, img, error: Optional[Exception]):
            if error:
                log(f"[THUMB][ERR] {os.path.basename(path)}: {error!r}")
                state.thumb_cache[path] = BitmapThumb(None, (0, 0), path, False)
                return

            try:
                thumb = build_thumb_from_image(img, target_h, path)
                state.thumb_cache[path] = thumb
            except Exception as e:
                log(f"[THUMB][ERR] Failed to create texture: {e!r}")
                state.thumb_cache[path] = BitmapThumb(None, (0, 0), path, False)

        state.async_loader.submit(p, LoadPriority.GALLERY, on_thumb_loaded)
        budget -= 1

    while len(state.thumb_cache) > THUMB_CACHE_LIMIT:
        _, bt = state.thumb_cache.popitem(last=False)
        if bt and bt.texture:
            try:
                rl.UnloadTexture(bt.texture)
            except Exception:
                pass


def update_gallery_scroll(state: AppState):
    if state.gallery_target_index is not None:
        target = float(clamp(state.gallery_target_index, 0, max(0, len(state.current_dir_images) - 1)))
    else:
        target = float(state.index)

    current = state.gallery_center_index
    diff = target - current

    if abs(diff) < 0.01:
        state.gallery_center_index = target
        return

    speed = 0.25
    state.gallery_center_index += diff * speed


GALLERY_SETTLE_DEBOUNCE_S = 0.12


def reconcile_gallery_target(state: AppState):
    tgt = state.gallery_target_index
    if tgt is None:
        return

    if (now() - state.gallery_last_wheel_time) < GALLERY_SETTLE_DEBOUNCE_S:
        return

    if state.switch_anim_active or state.waiting_for_switch or state.loading_current:
        return

    n = len(state.current_dir_images)
    if n == 0:
        state.gallery_target_index = None
        return
    tgt = clamp(int(tgt), 0, n - 1)

    if state.index == tgt:
        state.gallery_target_index = None
        return

    step = 1 if tgt > state.index else -1
    switch_to(state, state.index + step, animate=True, anim_duration_ms=ANIM_SWITCH_GALLERY_MS)


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


def is_mouse_over_gallery(state: AppState) -> bool:
    mouse = rl.GetMousePosition()
    gh = int(state.screenH * GALLERY_HEIGHT_FRAC)
    y_visible = state.screenH - gh
    return y_visible <= mouse.y <= state.screenH and state.gallery_y < state.screenH


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


def preload_neighbors(state: AppState, new_index: int, skip_neighbors: bool = False):
    n = len(state.current_dir_images)
    if n == 0:
        return
    new_index = clamp(new_index, 0, n - 1)

    current_path = state.current_dir_images[new_index]
    old_index = state.index
    state.index = new_index

    is_heavy = is_heavy_image(current_path)

    log(f"[PRELOAD] Starting async load for index={new_index} path={os.path.basename(current_path)} heavy={is_heavy} skip_neighbors={skip_neighbors}")

    def on_current_loaded(path: str, img, error: Optional[Exception]):
        if error:
            log(f"[ASYNC][CURRENT][ERR] {os.path.basename(path)}: {error!r}")
            state.loading_current = False
            try:
                ph = rl.GenImageColor(2, 2, _RL_WHITE)
                tex = rl.LoadTextureFromImage(ph)
                rl.UnloadImage(ph)
                state.cache.curr = TextureInfo(tex=tex, w=2, h=2, path=path)
            except Exception:
                pass
            return

        try:
            state.cache.curr = image_to_textureinfo(img, path)
            state.loading_current = False
            state.last_fit_view = compute_fit_view(state, FIT_DEFAULT_SCALE)

            if path in state.view_memory:
                restored_view = state.view_memory[path]
                state.view = sanitize_view(state, restored_view, state.cache.curr)
                log(f"[ASYNC][CURRENT] Restored view: scale={state.view.scale:.3f} off=({state.view.offx:.1f},{state.view.offy:.1f})")

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
                log(f"[ASYNC][CURRENT] New view (FIT): scale={state.view.scale:.3f} off=({state.view.offx:.1f},{state.view.offy:.1f})")

            log(f"[ASYNC][CURRENT] Loaded: {os.path.basename(path)} tex_id={getattr(state.cache.curr.tex, 'id', 0)}")

            if state.waiting_for_switch and state.pending_target_index is not None:
                log(f"[SWITCH_ANIM] About to start: pending_duration={state.pending_switch_duration_ms}ms waiting={state.waiting_for_switch} target={state.pending_target_index}")
                direction = 1 if state.pending_target_index > old_index else -1
                if state.waiting_prev_snapshot:
                    state.switch_anim_prev_tex = state.waiting_prev_snapshot
                    state.switch_anim_prev_view = state.waiting_prev_view
                    state.switch_anim_active = True
                    state.switch_anim_t0 = now()
                    state.switch_anim_direction = direction
                    state.switch_anim_duration_ms = state.pending_switch_duration_ms
                    log(f"[SWITCH_ANIM] Started after load: actual_duration={state.switch_anim_duration_ms}ms")

                state.waiting_for_switch = False
                state.waiting_prev_snapshot = None
                state.pending_target_index = None
                state.pending_switch_duration_ms = ANIM_SWITCH_KEYS_MS
                log(f"[SWITCH_ANIM] Reset pending_duration to default: {ANIM_SWITCH_KEYS_MS}ms")

            if state.open_anim_active and state.open_anim_t0 == 0.0:
                state.open_anim_t0 = now()
                state.bg_current_opacity = 0.0
                state.pending_neighbors_load = True
                log(f"[OPEN_ANIM] Started after first image load")

        except Exception as e:
            log(f"[ASYNC][CURRENT][ERR] Failed to create texture: {e!r}")
            state.loading_current = False

    state.loading_current = is_heavy
    state.async_loader.submit(current_path, LoadPriority.CURRENT, on_current_loaded)

    if skip_neighbors:
        log(f"[PRELOAD] Skipping neighbors/thumbs during animation")
        return

    def on_neighbor_loaded(path: str, img, error: Optional[Exception]):
        if error:
            log(f"[ASYNC][NEIGHBOR][ERR] {os.path.basename(path)}: {error!r}")
            return

        try:
            idx = state.current_dir_images.index(path)
        except ValueError:
            return

        try:
            tex_info = image_to_textureinfo(img, path)

            if idx == state.index - 1:
                if state.cache.prev:
                    unload_texture_deferred(state, state.cache.prev)
                state.cache.prev = tex_info
                log(f"[ASYNC][PREV] Loaded: {os.path.basename(path)}")
            elif idx == state.index + 1:
                if state.cache.next:
                    unload_texture_deferred(state, state.cache.next)
                state.cache.next = tex_info
                log(f"[ASYNC][NEXT] Loaded: {os.path.basename(path)}")
        except Exception as e:
            log(f"[ASYNC][NEIGHBOR][ERR] Failed to create texture: {e!r}")

    if new_index - 1 >= 0:
        state.async_loader.submit(
            state.current_dir_images[new_index - 1],
            LoadPriority.NEIGHBOR,
            on_neighbor_loaded
        )
    if new_index + 1 < n:
        state.async_loader.submit(
            state.current_dir_images[new_index + 1],
            LoadPriority.NEIGHBOR,
            on_neighbor_loaded
        )

    schedule_thumbs(state, new_index)


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
        state.waiting_prev_snapshot = TextureInfo(
            tex=state.cache.curr.tex,
            w=state.cache.curr.w,
            h=state.cache.curr.h,
            path=state.cache.curr.path
        )
        state.waiting_prev_view = ViewParams(state.view.scale, state.view.offx, state.view.offy)
    else:
        state.waiting_prev_snapshot = None

    state.waiting_for_switch = True
    state.pending_target_index = idx

    state.pending_switch_duration_ms = anim_duration_ms

    old_prev = state.cache.prev
    old_next = state.cache.next
    old_curr = state.cache.curr if not animate else None

    state.cache.prev = None
    state.cache.next = None
    if not animate:
        state.cache.curr = None

    for ti in [old_prev, old_next, old_curr]:
        if ti and ti != state.waiting_prev_snapshot:
            unload_texture_deferred(state, ti)

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


def sanitize_view(state: AppState, view: ViewParams, ti: TextureInfo) -> ViewParams:
    v = ViewParams(view.scale, view.offx, view.offy)

    centered = center_view_for(v.scale, ti.w, ti.h, state.screenW, state.screenH)

    if abs(v.offx) < 5.0 and abs(v.offy) < 5.0:
        log(f"[SANITIZE] Near-zero offsets ({v.offx:.1f},{v.offy:.1f}) at scale={v.scale:.3f} -> centering to ({centered.offx:.1f},{centered.offy:.1f})")
        return centered

    if (abs(v.offx) < 5.0 and abs(v.offy) > 50.0) or (abs(v.offy) < 5.0 and abs(v.offx) > 50.0):
        log(f"[SANITIZE] Asymmetric offsets ({v.offx:.1f},{v.offy:.1f}) at scale={v.scale:.3f} -> centering to ({centered.offx:.1f},{centered.offy:.1f})")
        return centered

    if abs(v.scale - 1.0) < 0.01:
        centered_1to1 = view_for_1to1_centered(state)
        if abs(v.offx - centered_1to1.offx) > 50 or abs(v.offy - centered_1to1.offy) > 50:
            log(f"[SANITIZE] 1:1 with bad offsets ({v.offx:.1f},{v.offy:.1f}) vs centered ({centered_1to1.offx:.1f},{centered_1to1.offy:.1f}) -> fixing")
            return centered_1to1

    v = clamp_pan(v, ti, state.screenW, state.screenH)
    return v


def save_view_for_path(state: AppState, path: str, view: ViewParams):
    ti = state.cache.curr
    if not ti or not path:
        return

    v = sanitize_view(state, view, ti)
    state.view_memory[path] = ViewParams(v.scale, v.offx, v.offy)

    if abs(view.offx - v.offx) > 1.0 or abs(view.offy - v.offy) > 1.0:
        log(f"[SAVE_VIEW] {os.path.basename(path)}: CORRECTED scale={v.scale:.3f} off=({v.offx:.1f},{v.offy:.1f}) [was ({view.offx:.1f},{view.offy:.1f})]")
    else:
        log(f"[SAVE_VIEW] {os.path.basename(path)}: scale={v.scale:.3f} off=({v.offx:.1f},{v.offy:.1f})")


def cycle_zoom_state(state: AppState):
    next_state = {2: 0, 0: 1, 1: 2}[state.zoom_state_cycle]

    if next_state == 0:
        target = view_for_1to1_centered(state)
    elif next_state == 1:
        target = state.last_fit_view
    else:
        current_path = state.current_dir_images[state.index] if state.index < len(state.current_dir_images) else None
        if current_path and current_path in state.user_zoom_memory:
            target = state.user_zoom_memory[current_path]
        else:
            target = state.last_fit_view

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
        rl.EndDrawing()
        if t >= 1.0:
            break

    state.zoom_state_cycle = next_state
    state.is_zoomed = (state.view.scale > state.last_fit_view.scale)

    if state.index < len(state.current_dir_images):
        path = state.current_dir_images[state.index]
        save_view_for_path(state, path, state.view)
        if state.zoom_state_cycle == 2:
            state.user_zoom_memory[path] = ViewParams(state.view.scale, state.view.offx, state.view.offy)
            log(f"[CYCLE_ZOOM] Saved USER view: scale={state.view.scale:.3f}")


def apply_bg_opacity_anim(state: AppState):
    if state.open_anim_active:
        return
    delta = state.bg_target_opacity - state.bg_current_opacity
    if abs(delta) < 0.001:
        return
    step = (1.0 / (ANIM_SWITCH_KEYS_MS / 1000.0)) / TARGET_FPS
    state.bg_current_opacity += clamp(delta, -step, step)


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

    log("[MAIN] Starting application")

    start_path = None
    for a in sys.argv[1:]:
        p = os.path.abspath(a)
        log(f"[ARGS] Checking argument: {a} -> {p}")
        if os.path.exists(p):
            start_path = p
            log(f"[ARGS] Found valid path: {start_path}")
            break

    if not start_path:
        log("[ARGS] No valid path provided, using current directory")

    try:
        log("[INIT] Initializing window")
        init_window_and_blur(state := AppState())
        log("[INIT] Window initialized successfully")
    except Exception as e:
        log(f"[INIT][CRITICAL] Failed to initialize window: {e!r}")
        log(f"[INIT][CRITICAL] Traceback:\n{traceback.format_exc()}")
        return

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

    log(f"[DIR] Found {len(images)} images in {dirpath}")

    if not images:
        log("[DIR] No images found, showing error screen")
        try:
            while not rl.WindowShouldClose():
                rl.BeginDrawing()
                apply_bg_mode(state)
                RL_DrawText("No images found", 40, 40, 28, rl.GRAY)
                rl.EndDrawing()
        except Exception as e:
            log(f"[ERROR_SCREEN][ERR] {e!r}")
        finally:
            try:
                rl.CloseWindow()
            except Exception:
                pass
        return

    log(f"[PRELOAD] Loading initial image at index {start_index}")

    state.open_anim_active = True
    state.open_anim_t0 = 0.0
    state.view = ViewParams(scale=0.5, offx=state.screenW / 4, offy=state.screenH / 4)
    state.bg_current_opacity = 0.0

    preload_neighbors(state, start_index, skip_neighbors=True)
    state.gallery_center_index = float(start_index)
    schedule_thumbs(state, start_index)

    log(f"[START] Starting main loop")
    log(f"[DIR] {dirpath} files={len(images)} start={state.index} -> {os.path.basename(images[state.index])}")
    atexit.register(lambda: log(f"[EXIT] frames={_frame} thumbs={len(state.thumb_cache)} q={len(state.thumb_queue)}"))

    font_loaded = False
    blur_enabled = False
    first_render_done = False

    try:
        while True:
            if state.open_anim_active:
                state.async_loader.poll_ui_events(max_events=2, filter_priority=False)
            else:
                state.async_loader.poll_ui_events(max_events=100, filter_priority=False)

            if not font_loaded and state.cache.curr and first_render_done and not state.open_anim_active:
                state.unicode_font = load_unicode_font(24)
                font_loaded = True
                log("[INIT] Font loaded after first render")

            if not blur_enabled and state.cache.curr and first_render_done and not state.open_anim_active:
                mode = BG_MODES[state.bg_mode_index]
                if mode["blur"]:
                    WinBlur.enable(state.hwnd)
                blur_enabled = True
                log("[INIT] Blur enabled after first render")

            if state.cache.curr and state.open_anim_active and state.view.scale == 0.5:
                state.view = compute_fit_view(state, FIT_OPEN_SCALE)
                log(f"[MAIN] Set FIT_OPEN view for animation")

            process_deferred_unloads(state)
            update_zoom_animation(state)
            process_switch_queue(state)
            apply_bg_opacity_anim(state)
            update_close_button_alpha(state)
            update_nav_buttons_fade(state)
            update_gallery_visibility_and_slide(state)
            update_gallery_scroll(state)
            reconcile_gallery_target(state)

            if not state.open_anim_active:
                process_thumb_queue(state)

            should_close = rl.WindowShouldClose()
            if should_close:
                break

            rl.BeginDrawing()
            apply_bg_mode(state)

            mouse = rl.GetMousePosition()

            if check_close_button_click(state):
                break

            state.idle_detector.mark_activity()

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
                        save_view_for_path(state, path, nv)
                        state.user_zoom_memory[path] = ViewParams(nv.scale, nv.offx, nv.offy)

                if rl.IsKeyDown(rl.KEY_DOWN):
                    nv = recompute_view_anchor_zoom(state.view, state.view.scale * (1.0 - ZOOM_STEP_KEYS),
                                                    (int(mouse.x), int(mouse.y)), state.cache.curr)
                    nv = clamp_pan(nv, state.cache.curr, state.screenW, state.screenH)
                    start_zoom_animation(state, nv)
                    state.is_zoomed = (nv.scale > state.last_fit_view.scale)
                    state.zoom_state_cycle = 2
                    if state.index < len(state.current_dir_images):
                        path = state.current_dir_images[state.index]
                        save_view_for_path(state, path, nv)
                        state.user_zoom_memory[path] = ViewParams(nv.scale, nv.offx, nv.offy)

            wheel = rl.GetMouseWheelMove()
            if wheel != 0.0 and state.cache.curr and not state.open_anim_active:
                if is_mouse_over_gallery(state):
                    n = len(state.current_dir_images)
                    base = state.gallery_target_index if state.gallery_target_index is not None else state.index
                    if wheel > 0:
                        target = max(0, int(base) - 1)
                    else:
                        target = min(n - 1, int(base) + 1)
                    state.gallery_target_index = target
                    state.gallery_last_wheel_time = now()
                else:
                    nv = recompute_view_anchor_zoom(state.view, state.view.scale * (1.0 + wheel * ZOOM_STEP_WHEEL),
                                                    (int(mouse.x), int(mouse.y)), state.cache.curr)
                    nv = clamp_pan(nv, state.cache.curr, state.screenW, state.screenH)
                    start_zoom_animation(state, nv)
                    state.is_zoomed = (nv.scale > state.last_fit_view.scale)
                    state.zoom_state_cycle = 2
                    if state.index < len(state.current_dir_images):
                        path = state.current_dir_images[state.index]
                        save_view_for_path(state, path, nv)
                        state.user_zoom_memory[path] = ViewParams(nv.scale, nv.offx, nv.offy)

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

                if rl.IsMouseButtonPressed(
                        rl.MOUSE_BUTTON_LEFT) and state.is_zoomed and over_img and not is_point_in_close_button(state,
                                                                                                                mouse.x,
                                                                                                                mouse.y):
                    state.is_panning = True
                    state.pan_start_mouse = (mouse.x, mouse.y)
                    state.pan_start_offset = (state.view.offx, state.view.offy)

                if rl.IsMouseButtonReleased(rl.MOUSE_BUTTON_LEFT):
                    if state.is_panning:
                        state.is_panning = False
                        if state.cache.curr and state.index < len(state.current_dir_images):
                            path = state.current_dir_images[state.index]
                            state.zoom_state_cycle = 2
                            save_view_for_path(state, path, state.view)
                            state.user_zoom_memory[path] = ViewParams(state.view.scale, state.view.offx,
                                                                      state.view.offy)

                if state.is_panning:
                    dx = mouse.x - state.pan_start_mouse[0]
                    dy = mouse.y - state.pan_start_mouse[1]
                    nv = ViewParams(scale=state.view.scale, offx=state.pan_start_offset[0] + dx,
                                    offy=state.pan_start_offset[1] + dy)
                    state.view = clamp_pan(nv, state.cache.curr, state.screenW, state.screenH)

            if not state.open_anim_active:
                edge_left = (mouse.x <= state.screenW * 0.10)
                edge_right = (mouse.x >= state.screenW * 0.90)

                if rl.IsKeyPressed(rl.KEY_RIGHT) or rl.IsKeyPressed(rl.KEY_D):
                    if state.index + 1 < len(state.current_dir_images):
                        switch_to(state, state.index + 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)
                if rl.IsKeyPressed(rl.KEY_LEFT) or rl.IsKeyPressed(rl.KEY_A):
                    if state.index - 1 >= 0:
                        switch_to(state, state.index - 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)

                zoom_threshold = state.last_fit_view.scale * 1.1
                is_significantly_zoomed = state.view.scale > zoom_threshold

                gh = int(state.screenH * GALLERY_HEIGHT_FRAC)
                yv = state.screenH - gh
                in_gallery_panel = (yv <= mouse.y <= state.screenH)

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

            if state.cache.curr and not first_render_done:
                first_render_done = True
                log("[RENDER] First render completed")

            draw_nav_buttons(state)
            draw_close_button(state)
            draw_filename(state)

            try:
                render_gallery(state)
            except Exception as e:
                log(f"[DRAW][GALLERY][EXC] {e!r}\n{traceback.format_exc()}")

            draw_loading_indicator(state)

            if state.show_hud:
                hud_y = state.screenH - 180
                line_spacing = 24
                RL_DrawText(f"RL={RL_VER}", 12, hud_y, 16, rl.LIGHTGRAY)
                RL_DrawText(f"idx={state.index + 1}/{len(state.current_dir_images)} zoom={state.view.scale:.3f}", 12,
                            hud_y + line_spacing, 16, rl.LIGHTGRAY)
                RL_DrawText(f"loading={state.loading_current} idle={state.idle_detector.is_idle()}", 12,
                            hud_y + line_spacing * 2, 16, rl.LIGHTGRAY)
                if state.cache.curr:
                    tid = getattr(state.cache.curr.tex, 'id', 0)
                    RL_DrawText(f"curr_tex_id={tid} w={state.cache.curr.w} h={state.cache.curr.h}", 12,
                                hud_y + line_spacing * 3, 16, rl.LIGHTGRAY)
                else:
                    RL_DrawText(f"curr_tex=None", 12, hud_y + line_spacing * 3, 16, rl.LIGHTGRAY)

            rl.EndDrawing()
            _frame += 1
            if rl.IsKeyPressed(rl.KEY_ESCAPE):
                break
            if should_close:
                break
    except Exception as e:
        log(f"[MAIN][CRITICAL] Unhandled exception in main loop: {e!r}")
        log(f"[MAIN][CRITICAL] Traceback:\n{traceback.format_exc()}")
    finally:
        log("[CLEANUP] Starting cleanup")
        if state.async_loader:
            log("[CLEANUP] Shutting down async loader")
            state.async_loader.shutdown()
        log("[CLEANUP] Processing deferred unloads")
        process_deferred_unloads(state)
        log("[CLEANUP] Unloading thumbnails")
        for bt in list(state.thumb_cache.values()):
            try:
                if bt.texture:
                    rl.UnloadTexture(bt.texture)
            except Exception:
                pass
        log("[CLEANUP] Unloading cached textures")
        for ti in (state.cache.prev, state.cache.curr, state.cache.next):
            try:
                if ti and getattr(ti.tex, 'id', 0):
                    rl.UnloadTexture(ti.tex)
            except Exception:
                pass
        try:
            log("[CLEANUP] Closing window")
            rl.CloseWindow()
        except Exception:
            pass
        log("[CLEANUP] Cleanup complete")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"[FATAL] Fatal error: {e!r}")
        log(f"[FATAL] Traceback:\n{traceback.format_exc()}")
        input("Press Enter to exit...")
        sys.exit(1)