#!imagura2_async_fixed.py
"""Imagura - Fast async image viewer."""
from __future__ import annotations
import os
import sys
import ctypes
import atexit
import traceback
from dataclasses import dataclass, field
from collections import OrderedDict, deque
from typing import List, Tuple, Optional, Deque, Callable, Any, Dict
from queue import PriorityQueue, Empty
from threading import Thread, Lock
import math
from datetime import datetime

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Import from new modules
import imagura.config as cfg  # For dynamic access to config values
from imagura.config import (
    TARGET_FPS, ASYNC_WORKERS,
    ANIM_SWITCH_KEYS_MS, ANIM_SWITCH_GALLERY_MS, ANIM_TOGGLE_ZOOM_MS,
    ANIM_OPEN_MS, ANIM_ZOOM_MS, GALLERY_SLIDE_MS,
    FIT_DEFAULT_SCALE, FIT_OPEN_SCALE, OPEN_ALPHA_START,
    ZOOM_STEP_KEYS, ZOOM_STEP_WHEEL, MAX_ZOOM,
    CLOSE_BTN_RADIUS, CLOSE_BTN_MARGIN, CLOSE_BTN_ALPHA_MIN,
    CLOSE_BTN_ALPHA_FAR, CLOSE_BTN_ALPHA_MAX, CLOSE_BTN_ALPHA_HOVER,
    CLOSE_BTN_BG_ALPHA_MAX, NAV_BTN_RADIUS, NAV_BTN_BG_ALPHA_MAX,
    MAX_IMAGE_DIMENSION, MAX_FILE_SIZE_MB,
    GALLERY_HEIGHT_FRAC, GALLERY_TRIGGER_FRAC, GALLERY_THUMB_SPACING,
    GALLERY_MIN_SCALE, GALLERY_MIN_ALPHA, GALLERY_SETTLE_DEBOUNCE_S,
    THUMB_CACHE_LIMIT, THUMB_PRELOAD_SPAN, THUMB_BUILD_BUDGET_PER_FRAME,
    DOUBLE_CLICK_TIME_MS, IDLE_THRESHOLD_SECONDS, BG_MODES,
    KEY_REPEAT_DELAY, KEY_REPEAT_INTERVAL,
    TOOLBAR_TRIGGER_FRAC, TOOLBAR_HEIGHT, TOOLBAR_BTN_RADIUS, TOOLBAR_BTN_SPACING,
    TOOLBAR_BG_ALPHA, TOOLBAR_SLIDE_MS,
    MENU_ITEM_HEIGHT, MENU_ITEM_WIDTH, MENU_PADDING, MENU_BG_ALPHA, MENU_HOVER_ALPHA,
    FONT_SIZE, FONT_ANTIALIAS,
    KEY_TOGGLE_HUD, KEY_TOGGLE_FILENAME, KEY_CYCLE_BG, KEY_DELETE_IMAGE,
    KEY_ZOOM_IN, KEY_ZOOM_IN_ALT, KEY_ZOOM_OUT, KEY_ZOOM_OUT_ALT, KEY_TOGGLE_ZOOM,
    KEY_NEXT_IMAGE, KEY_NEXT_IMAGE_ALT, KEY_PREV_IMAGE, KEY_PREV_IMAGE_ALT, KEY_CLOSE,
)
from imagura.math_utils import clamp, lerp, ease_out_quad, ease_in_out_cubic
from imagura.rl_compat import (
    rl, RL_VERSION, RL_WHITE,
    make_rect as RL_Rect, make_vec2 as RL_V2, make_color as RL_Color,
    draw_text as RL_DrawText, measure_text, load_image as rl_load_image,
    get_texture_id, is_texture_valid,
)
from imagura.win_utils import (
    WinBlur, get_work_area, get_short_path_name, get_window_handle_from_raylib,
)
from imagura.image_utils import (
    probe_image_dimensions, is_heavy_image, list_images, get_thumb_cache_path,
)
from imagura.logging import log, now, increment_frame, get_frame
from imagura.types import (
    LoadPriority, LoadTask, UIEvent,
    ViewParams, TextureInfo, ImageCache, BitmapThumb,
)
from imagura.view_math import (
    compute_fit_scale, center_view_for, compute_fit_view,
    clamp_pan as clamp_pan_pure, recompute_view_anchor_zoom as anchor_zoom_pure,
    view_for_1to1_centered as view_1to1_pure, sanitize_view as sanitize_view_pure,
)
from imagura.animation import (
    AnimationController, AnimationType,
    ToggleZoomAnimation, ZoomAnimation,
    create_toggle_zoom_animation, create_zoom_animation,
)
from imagura.state import AppState
from imagura.state.ui import ToolbarButtonId, MenuItemId
from imagura.clipboard import copy_image_to_clipboard
from imagura.transforms import rotate_image_file, flip_image_file

# Aliases for compatibility
RL_VER = RL_VERSION
_RL_WHITE = RL_WHITE


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

    def poll_ui_events(self, max_events: int = 100):
        events_to_process = []
        with self.ui_lock:
            count = 0
            while self.ui_events and count < max_events:
                event = self.ui_events.popleft()
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



# AppState is now imported from imagura.state (see imagura/state/app_state.py)
# It uses composition of sub-states while providing backward-compatible properties.


def load_unicode_font(font_size: int = None):
    """Load a Unicode font with Cyrillic support and optional antialiasing."""
    if font_size is None:
        font_size = FONT_SIZE

    font_paths = [
        "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
    ]

    # Build character set: ASCII + Cyrillic
    # ASCII: 32-126, Cyrillic: 0x400-0x4FF (1024-1279)
    codepoints = list(range(32, 127)) + list(range(0x400, 0x500))

    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                if hasattr(rl, 'ffi'):
                    # cffi version
                    cp_array = rl.ffi.new(f'int[{len(codepoints)}]', codepoints)
                    font = rl.LoadFontEx(font_path.encode('utf-8'), font_size, cp_array, len(codepoints))
                else:
                    # ctypes version
                    import ctypes
                    cp_array = (ctypes.c_int * len(codepoints))(*codepoints)
                    try:
                        font = rl.LoadFontEx(font_path, font_size, cp_array, len(codepoints))
                    except TypeError:
                        font = rl.LoadFontEx(font_path.encode('utf-8'), font_size, cp_array, len(codepoints))

                if hasattr(font, 'texture') and hasattr(font.texture, 'id') and font.texture.id > 0:
                    # Apply antialiasing (bilinear filtering) to font texture
                    if FONT_ANTIALIAS:
                        try:
                            # TEXTURE_FILTER_BILINEAR = 1
                            rl.SetTextureFilter(font.texture, 1)
                            log(f"[FONT] Antialiasing enabled")
                        except Exception as e:
                            log(f"[FONT] Could not set antialias filter: {e!r}")

                    log(f"[FONT] Loaded unicode font (size={font_size}): {os.path.basename(font_path)}")
                    return font
            except Exception as e:
                log(f"[FONT][ERR] Failed to load {font_path}: {e!r}")

    log(f"[FONT] Using default font (no unicode support)")
    return None




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
    state.hwnd = get_window_handle_from_raylib()
    state.gallery_y = state.screenH
    state.unicode_font = None
    state.async_loader = AsyncImageLoader(load_image_cpu_only)
    state.idle_detector = IdleDetector()
    log(f"[INIT] RL_VER={RL_VER} workarea={w}x{h} window={state.screenW}x{state.screenH} hwnd={state.hwnd}")


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
    """Wrapper for clamp_pan_pure that accepts TextureInfo."""
    return clamp_pan_pure(view, img.w, img.h, screenW, screenH)


def recompute_view_anchor_zoom(view: ViewParams, new_scale: float, anchor: Tuple[int, int],
                               img: TextureInfo) -> ViewParams:
    """Wrapper for anchor_zoom_pure that accepts TextureInfo."""
    return anchor_zoom_pure(view, new_scale, anchor, img.w, img.h)


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
            # Use clamp_pan instead of sanitize_view to preserve pan position
            state.view = clamp_pan(state.zoom_anim_to, state.cache.curr, state.screenW, state.screenH)
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
        log(f"[BLUR] Enabled using method: {WinBlur._active_method}")
    else:
        WinBlur.disable(hwnd)
        log("[BLUR] Disabled")


# Track current blur state to avoid calling DWM APIs every frame
_current_blur_enabled: Optional[bool] = None


def apply_bg_mode(state: AppState):
    global _current_blur_enabled

    mode = BG_MODES[state.bg_mode_index]
    blur_wanted = mode["blur"]

    # Only call DWM APIs when blur state actually changes
    if _current_blur_enabled != blur_wanted:
        win_set_blur(state.hwnd, blur_wanted)
        _current_blur_enabled = blur_wanted
        log(f"[BG] Blur {'enabled' if blur_wanted else 'disabled'}")

    c = mode["color"]
    a = clamp(state.bg_current_opacity, 0.0, 1.0)

    if blur_wanted:
        # For blur mode: clear to transparent, then draw semi-opaque overlay
        try:
            rl.ClearBackground(rl.BLANK)
        except Exception:
            rl.ClearBackground(RL_Color(0, 0, 0, 0))
        # Draw overlay only if opacity > 0
        if a > 0.01:
            rl.DrawRectangle(0, 0, state.screenW, state.screenH, RL_Color(c[0], c[1], c[2], int(255 * a)))
    else:
        # Solid background
        col = RL_Color(c[0], c[1], c[2], 255)
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


# Cache for image metadata to avoid re-reading EXIF every frame
_metadata_cache: Dict[str, Dict[str, str]] = {}


def get_image_metadata(filepath: str) -> Dict[str, str]:
    """Read EXIF metadata from image file. Returns cached result if available."""
    if filepath in _metadata_cache:
        return _metadata_cache[filepath]

    metadata: Dict[str, str] = {}

    if not HAS_PIL:
        _metadata_cache[filepath] = metadata
        return metadata

    try:
        with Image.open(filepath) as img:
            exif_data = img._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, str(tag_id))

                    # Date taken
                    if tag_name == 'DateTimeOriginal':
                        try:
                            dt = datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S')
                            metadata['date'] = dt.strftime('%Y-%m-%d %H:%M')
                        except (ValueError, TypeError):
                            metadata['date'] = str(value)

                    # Camera model
                    elif tag_name == 'Model':
                        metadata['camera'] = str(value).strip()

                    # Focal length
                    elif tag_name == 'FocalLength':
                        if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                            focal = value.numerator / value.denominator if value.denominator else 0
                            metadata['focal'] = f"{focal:.0f}mm"
                        else:
                            metadata['focal'] = f"{value}mm"

                    # Aperture
                    elif tag_name == 'FNumber':
                        if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                            f_num = value.numerator / value.denominator if value.denominator else 0
                            metadata['aperture'] = f"f/{f_num:.1f}"
                        else:
                            metadata['aperture'] = f"f/{value}"

                    # ISO
                    elif tag_name == 'ISOSpeedRatings':
                        metadata['iso'] = f"ISO {value}"

                    # Exposure time
                    elif tag_name == 'ExposureTime':
                        if hasattr(value, 'numerator') and hasattr(value, 'denominator'):
                            if value.denominator and value.numerator:
                                if value.numerator < value.denominator:
                                    metadata['exposure'] = f"1/{value.denominator // value.numerator}s"
                                else:
                                    exp = value.numerator / value.denominator
                                    metadata['exposure'] = f"{exp:.1f}s"
                        else:
                            metadata['exposure'] = f"{value}s"

    except Exception as e:
        log(f"[METADATA] Error reading EXIF from {filepath}: {e}")

    _metadata_cache[filepath] = metadata
    return metadata


def get_zoom_mode_label(state: AppState) -> str:
    """Get human-readable zoom mode label based on zoom_state_cycle."""
    if state.zoom_state_cycle == 0:
        return "1:1"
    elif state.zoom_state_cycle == 1:
        return "Fit"
    else:
        return "Custom"


def get_filename_text_color(state: AppState):
    mode = BG_MODES[state.bg_mode_index]
    bg_color = mode["color"]
    if bg_color == (0, 0, 0):
        return RL_Color(255, 255, 255, 255)
    else:
        return RL_Color(0, 0, 0, 255)


def draw_filename(state: AppState):
    """Draw image index and filename at top of screen."""
    if not state.show_filename or state.index >= len(state.current_dir_images):
        return

    filepath = state.current_dir_images[state.index]
    filename = os.path.basename(filepath)

    # Build info string: [index/total] filename
    total = len(state.current_dir_images)
    info_text = f"[{state.index + 1} / {total}] {filename}"

    font_size = cfg.FONT_DISPLAY_SIZE
    color = get_filename_text_color(state)
    shadow_color = RL_Color(0, 0, 0, 150)

    def draw_text_with_shadow(text: str, x: int, y: int, size: int, use_unicode: bool):
        """Helper to draw text with shadow effect and bold simulation."""
        text_bytes = text.encode('utf-8')
        if use_unicode and state.unicode_font:
            # Shadow passes
            for dx in range(-1, 2):
                for dy in range(1, 3):
                    rl.DrawTextEx(state.unicode_font, text_bytes,
                                  RL_V2(x + dx, y + dy), size, 1.0, shadow_color)
            # Main text with bold effect (draw twice with 1px offset)
            rl.DrawTextEx(state.unicode_font, text_bytes, RL_V2(x, y), size, 1.0, color)
            rl.DrawTextEx(state.unicode_font, text_bytes, RL_V2(x + 1, y), size, 1.0, color)
        else:
            # Fallback to default font
            for dx in range(-1, 2):
                for dy in range(1, 3):
                    RL_DrawText(text, x + dx, y + dy, size, shadow_color)
            # Bold effect
            RL_DrawText(text, x, y, size, color)
            RL_DrawText(text, x + 1, y, size, color)

    # Measure and center text
    if state.unicode_font:
        try:
            text_vec = rl.MeasureTextEx(state.unicode_font, info_text.encode('utf-8'), font_size, 1.0)
            text_width = int(text_vec.x)
            x = (state.screenW - text_width) // 2
            draw_text_with_shadow(info_text, x, 40, font_size, use_unicode=True)
            return
        except Exception:
            pass

    # Fallback measurement
    try:
        text_width = rl.MeasureText(info_text, font_size)
    except TypeError:
        text_width = rl.MeasureText(info_text.encode('utf-8'), font_size)

    x = (state.screenW - text_width) // 2
    draw_text_with_shadow(info_text, x, 40, font_size, use_unicode=False)


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


# ═══════════════════════════════════════════════════════════════════════════════
# Toolbar and Context Menu
# ═══════════════════════════════════════════════════════════════════════════════

def update_toolbar_alpha(state: AppState):
    """Animate toolbar visibility."""
    toolbar = state.ui.toolbar
    if abs(toolbar.alpha - toolbar.target_alpha) > 0.01:
        speed = 1000.0 / TOOLBAR_SLIDE_MS
        dt = rl.GetFrameTime()
        if toolbar.target_alpha > toolbar.alpha:
            toolbar.alpha = min(toolbar.target_alpha, toolbar.alpha + speed * dt)
        else:
            toolbar.alpha = max(toolbar.target_alpha, toolbar.alpha - speed * dt)
    else:
        toolbar.alpha = toolbar.target_alpha


def get_toolbar_panel_bounds(state: AppState) -> tuple:
    """Get toolbar panel bounds (x, width)."""
    sw = state.screenW
    toolbar = state.ui.toolbar
    n_buttons = len(toolbar.buttons)
    n_separators = sum(1 for btn in toolbar.buttons if btn.separator_after)
    separator_width = TOOLBAR_BTN_SPACING

    buttons_width = (n_buttons * (TOOLBAR_BTN_RADIUS * 2) +
                     (n_buttons - 1) * TOOLBAR_BTN_SPACING +
                     n_separators * separator_width)
    min_panel_width = buttons_width + TOOLBAR_BTN_RADIUS * 2 * 2
    panel_width = max(min_panel_width, int(sw * 0.6))
    panel_x = (sw - panel_width) // 2
    return (panel_x, panel_width)


def is_in_toolbar_zone(state: AppState, mouse_x: float, mouse_y: float) -> bool:
    """Check if mouse is in toolbar trigger zone (within panel bounds)."""
    if mouse_y >= state.screenH * TOOLBAR_TRIGGER_FRAC:
        return False
    panel_x, panel_width = get_toolbar_panel_bounds(state)
    return panel_x <= mouse_x <= panel_x + panel_width


def get_toolbar_button_at(state: AppState, mx: float, my: float) -> int:
    """Get toolbar button index at mouse position, or -1 if none."""
    toolbar = state.ui.toolbar
    if toolbar.alpha < 0.5:
        return -1

    n_buttons = len(toolbar.buttons)
    n_separators = sum(1 for btn in toolbar.buttons if btn.separator_after)
    separator_width = TOOLBAR_BTN_SPACING

    total_width = (n_buttons * (TOOLBAR_BTN_RADIUS * 2) +
                   (n_buttons - 1) * TOOLBAR_BTN_SPACING +
                   n_separators * separator_width)
    start_x = (state.screenW - total_width) // 2 + TOOLBAR_BTN_RADIUS
    cy = TOOLBAR_HEIGHT // 2

    current_x = start_x
    for i, btn in enumerate(toolbar.buttons):
        cx = current_x
        dx = mx - cx
        dy = my - cy
        if (dx * dx + dy * dy) <= (TOOLBAR_BTN_RADIUS * TOOLBAR_BTN_RADIUS):
            return i

        # Move to next button position
        current_x += TOOLBAR_BTN_RADIUS * 2 + TOOLBAR_BTN_SPACING
        if btn.separator_after:
            current_x += separator_width

    return -1


def draw_rotate_icon(cx: int, cy: int, r: float, clockwise: bool, color):
    """Draw rotation arrow icon."""
    segments = 8

    if clockwise:
        # Arc from top going clockwise (right, down, left)
        start_angle = -120  # Start from upper-left area
        arc_span = 270
        points = []
        for i in range(segments + 1):
            angle = math.radians(start_angle + (arc_span * i / segments))
            px = cx + r * math.cos(angle)
            py = cy + r * math.sin(angle)
            points.append((px, py))

        # Draw arc
        for i in range(len(points) - 1):
            rl.DrawLineEx(RL_V2(points[i][0], points[i][1]),
                         RL_V2(points[i+1][0], points[i+1][1]), 2.0, color)

        # Arrowhead at end - pointing in clockwise direction (tangent)
        end_angle = math.radians(start_angle + arc_span)
        end_x, end_y = points[-1]
        arrow_size = r * 0.5
        # Tangent for clockwise is perpendicular to radius, pointing "forward"
        tangent_angle = end_angle + math.pi / 2
        # Two lines forming arrowhead
        arr_angle1 = tangent_angle + math.radians(150)
        arr_angle2 = tangent_angle - math.radians(150)
        rl.DrawLineEx(RL_V2(end_x, end_y),
                     RL_V2(end_x + arrow_size * math.cos(arr_angle1),
                           end_y + arrow_size * math.sin(arr_angle1)), 2.0, color)
        rl.DrawLineEx(RL_V2(end_x, end_y),
                     RL_V2(end_x + arrow_size * math.cos(arr_angle2),
                           end_y + arrow_size * math.sin(arr_angle2)), 2.0, color)
    else:
        # Counter-clockwise: arc from top going left, down, right
        start_angle = -60
        arc_span = 270
        points = []
        for i in range(segments + 1):
            angle = math.radians(start_angle - (arc_span * i / segments))
            px = cx + r * math.cos(angle)
            py = cy + r * math.sin(angle)
            points.append((px, py))

        # Draw arc
        for i in range(len(points) - 1):
            rl.DrawLineEx(RL_V2(points[i][0], points[i][1]),
                         RL_V2(points[i+1][0], points[i+1][1]), 2.0, color)

        # Arrowhead at end - pointing in counter-clockwise direction
        end_angle = math.radians(start_angle - arc_span)
        end_x, end_y = points[-1]
        arrow_size = r * 0.5
        # Tangent for counter-clockwise is perpendicular to radius, pointing "backward"
        tangent_angle = end_angle - math.pi / 2
        arr_angle1 = tangent_angle + math.radians(150)
        arr_angle2 = tangent_angle - math.radians(150)
        rl.DrawLineEx(RL_V2(end_x, end_y),
                     RL_V2(end_x + arrow_size * math.cos(arr_angle1),
                           end_y + arrow_size * math.sin(arr_angle1)), 2.0, color)
        rl.DrawLineEx(RL_V2(end_x, end_y),
                     RL_V2(end_x + arrow_size * math.cos(arr_angle2),
                           end_y + arrow_size * math.sin(arr_angle2)), 2.0, color)


def draw_flip_icon(cx: int, cy: int, r: float, color):
    """Draw horizontal flip icon."""
    arrow_w = r * 0.6
    arrow_h = r * 0.8
    gap = r * 0.15

    # Left arrow
    rl.DrawLineEx(RL_V2(cx - gap - arrow_w, cy),
                 RL_V2(cx - gap, cy - arrow_h), 2.0, color)
    rl.DrawLineEx(RL_V2(cx - gap - arrow_w, cy),
                 RL_V2(cx - gap, cy + arrow_h), 2.0, color)
    rl.DrawLineEx(RL_V2(cx - gap, cy - arrow_h),
                 RL_V2(cx - gap, cy + arrow_h), 2.0, color)

    # Right arrow
    rl.DrawLineEx(RL_V2(cx + gap + arrow_w, cy),
                 RL_V2(cx + gap, cy - arrow_h), 2.0, color)
    rl.DrawLineEx(RL_V2(cx + gap + arrow_w, cy),
                 RL_V2(cx + gap, cy + arrow_h), 2.0, color)
    rl.DrawLineEx(RL_V2(cx + gap, cy - arrow_h),
                 RL_V2(cx + gap, cy + arrow_h), 2.0, color)


def draw_gear_icon(cx: int, cy: int, r: float, color):
    """Draw gear/settings icon."""
    # Outer circle with teeth
    teeth = 8
    outer_r = r
    inner_r = r * 0.6
    tooth_depth = r * 0.25

    # Draw gear teeth
    for i in range(teeth):
        angle = (2 * math.pi * i / teeth)
        next_angle = (2 * math.pi * (i + 0.5) / teeth)

        # Tooth outer corners
        x1 = cx + (outer_r + tooth_depth) * math.cos(angle - math.pi / teeth / 2)
        y1 = cy + (outer_r + tooth_depth) * math.sin(angle - math.pi / teeth / 2)
        x2 = cx + (outer_r + tooth_depth) * math.cos(angle + math.pi / teeth / 2)
        y2 = cy + (outer_r + tooth_depth) * math.sin(angle + math.pi / teeth / 2)

        # Tooth base corners
        x3 = cx + outer_r * math.cos(angle + math.pi / teeth / 2)
        y3 = cy + outer_r * math.sin(angle + math.pi / teeth / 2)
        x4 = cx + outer_r * math.cos(next_angle - math.pi / teeth / 2)
        y4 = cy + outer_r * math.sin(next_angle - math.pi / teeth / 2)

        # Draw tooth
        rl.DrawLineEx(RL_V2(x1, y1), RL_V2(x2, y2), 2.0, color)
        rl.DrawLineEx(RL_V2(x2, y2), RL_V2(x3, y3), 2.0, color)
        rl.DrawLineEx(RL_V2(x3, y3), RL_V2(x4, y4), 2.0, color)

        # Connect to next tooth
        x5 = cx + outer_r * math.cos(next_angle - math.pi / teeth / 2)
        y5 = cy + outer_r * math.sin(next_angle - math.pi / teeth / 2)
        x6 = cx + (outer_r + tooth_depth) * math.cos(next_angle - math.pi / teeth / 2)
        y6 = cy + (outer_r + tooth_depth) * math.sin(next_angle - math.pi / teeth / 2)

    # Draw inner circle (hole)
    segments = 16
    for i in range(segments):
        angle1 = 2 * math.pi * i / segments
        angle2 = 2 * math.pi * (i + 1) / segments
        x1 = cx + inner_r * math.cos(angle1)
        y1 = cy + inner_r * math.sin(angle1)
        x2 = cx + inner_r * math.cos(angle2)
        y2 = cy + inner_r * math.sin(angle2)
        rl.DrawLineEx(RL_V2(x1, y1), RL_V2(x2, y2), 2.0, color)


def draw_toolbar(state: AppState):
    """Draw top toolbar with action buttons."""
    toolbar = state.ui.toolbar
    if toolbar.alpha < 0.01:
        return

    sw = state.screenW
    alpha = toolbar.alpha

    # Count separators for width calculation
    n_buttons = len(toolbar.buttons)
    n_separators = sum(1 for btn in toolbar.buttons if btn.separator_after)
    separator_width = TOOLBAR_BTN_SPACING  # Extra spacing for separator

    buttons_width = (n_buttons * (TOOLBAR_BTN_RADIUS * 2) +
                     (n_buttons - 1) * TOOLBAR_BTN_SPACING +
                     n_separators * separator_width)
    min_panel_width = buttons_width + TOOLBAR_BTN_RADIUS * 2 * 2  # +1 button on each side
    panel_width = max(min_panel_width, int(sw * 0.6))  # 60% of screen or minimum

    panel_x = (sw - panel_width) // 2
    fade_width = 40  # Width of gradient fade on edges

    # Draw background panel with gradient edges
    bg_alpha_max = int(255 * TOOLBAR_BG_ALPHA * alpha)

    # Left fade gradient
    for i in range(fade_width):
        fade_alpha = int(bg_alpha_max * (i / fade_width))
        rl.DrawRectangle(panel_x + i, 0, 1, TOOLBAR_HEIGHT, RL_Color(0, 0, 0, fade_alpha))

    # Center solid part
    rl.DrawRectangle(panel_x + fade_width, 0, panel_width - fade_width * 2, TOOLBAR_HEIGHT,
                    RL_Color(0, 0, 0, bg_alpha_max))

    # Right fade gradient
    for i in range(fade_width):
        fade_alpha = int(bg_alpha_max * (1.0 - i / fade_width))
        rl.DrawRectangle(panel_x + panel_width - fade_width + i, 0, 1, TOOLBAR_HEIGHT,
                        RL_Color(0, 0, 0, fade_alpha))

    # Calculate button start position (centered within panel)
    start_x = (sw - buttons_width) // 2 + TOOLBAR_BTN_RADIUS
    cy = TOOLBAR_HEIGHT // 2

    current_x = start_x
    for i, btn in enumerate(toolbar.buttons):
        cx = current_x
        is_hover = (i == toolbar.hover_index)

        btn_alpha = int(255 * alpha)
        bg_btn_alpha = int(128 * alpha) if is_hover else int(80 * alpha)
        rl.DrawCircle(cx, cy, TOOLBAR_BTN_RADIUS, RL_Color(0, 0, 0, bg_btn_alpha))
        rl.DrawCircleLines(cx, cy, TOOLBAR_BTN_RADIUS, RL_Color(255, 255, 255, btn_alpha))

        # Draw icon
        icon_r = TOOLBAR_BTN_RADIUS * 0.45
        icon_color = RL_Color(255, 255, 255, btn_alpha)
        if btn.id == ToolbarButtonId.SETTINGS:
            draw_gear_icon(cx, cy, icon_r, icon_color)
        elif btn.id == ToolbarButtonId.ROTATE_CW:
            draw_rotate_icon(cx, cy, icon_r, clockwise=True, color=icon_color)
        elif btn.id == ToolbarButtonId.ROTATE_CCW:
            draw_rotate_icon(cx, cy, icon_r, clockwise=False, color=icon_color)
        elif btn.id == ToolbarButtonId.FLIP_H:
            draw_flip_icon(cx, cy, icon_r, icon_color)

        # Move to next button position
        current_x += TOOLBAR_BTN_RADIUS * 2 + TOOLBAR_BTN_SPACING

        # Draw separator after this button if needed
        if btn.separator_after and i < n_buttons - 1:
            sep_x = current_x - TOOLBAR_BTN_SPACING // 2
            sep_alpha = int(150 * alpha)
            rl.DrawLineEx(RL_V2(sep_x, cy - TOOLBAR_BTN_RADIUS * 0.7),
                         RL_V2(sep_x, cy + TOOLBAR_BTN_RADIUS * 0.7),
                         2.0, RL_Color(255, 255, 255, sep_alpha))
            current_x += separator_width


def get_context_menu_item_at(state: AppState, mx: float, my: float) -> int:
    """Get context menu item index at mouse position, or -1 if none."""
    menu = state.ui.context_menu
    if not menu.visible:
        return -1

    n_items = len(menu.items)
    menu_w = MENU_ITEM_WIDTH
    menu_h = n_items * MENU_ITEM_HEIGHT + MENU_PADDING * 2

    x = min(menu.x, state.screenW - menu_w - 5)
    y = min(menu.y, state.screenH - menu_h - 5)
    x = max(5, x)
    y = max(5, y)

    if not (x <= mx <= x + menu_w):
        return -1

    item_start_y = y + MENU_PADDING
    for i in range(n_items):
        item_y = item_start_y + i * MENU_ITEM_HEIGHT
        if item_y <= my < item_y + MENU_ITEM_HEIGHT:
            return i
    return -1


def draw_context_menu(state: AppState):
    """Draw right-click context menu."""
    menu = state.ui.context_menu
    if not menu.visible:
        return

    n_items = len(menu.items)
    if n_items == 0:
        return

    font_size = cfg.FONT_DISPLAY_SIZE
    menu_w = MENU_ITEM_WIDTH
    menu_h = n_items * MENU_ITEM_HEIGHT + MENU_PADDING * 2

    x = min(menu.x, state.screenW - menu_w - 5)
    y = min(menu.y, state.screenH - menu_h - 5)
    x = max(5, x)
    y = max(5, y)

    # Shadow
    rl.DrawRectangle(x + 4, y + 4, menu_w, menu_h, RL_Color(0, 0, 0, 100))
    # Background
    rl.DrawRectangle(x, y, menu_w, menu_h, RL_Color(40, 40, 40, int(255 * MENU_BG_ALPHA)))
    rl.DrawRectangleLines(x, y, menu_w, menu_h, RL_Color(80, 80, 80, 255))

    item_y = y + MENU_PADDING
    for i, item in enumerate(menu.items):
        is_hover = (i == menu.hover_index)

        if is_hover:
            rl.DrawRectangle(x + 2, item_y, menu_w - 4, MENU_ITEM_HEIGHT,
                           RL_Color(255, 255, 255, int(255 * MENU_HOVER_ALPHA)))

        text_color = RL_Color(255, 255, 255, 255) if is_hover else RL_Color(200, 200, 200, 255)
        text_x = x + MENU_PADDING + 8
        text_y = item_y + (MENU_ITEM_HEIGHT - font_size) // 2

        # Use unicode font for Cyrillic support
        if state.unicode_font:
            try:
                label_bytes = item.label.encode('utf-8')
                rl.DrawTextEx(state.unicode_font, label_bytes, RL_V2(text_x, text_y),
                             font_size, 1.0, text_color)
            except Exception:
                RL_DrawText(item.label, text_x, text_y, font_size, text_color)
        else:
            RL_DrawText(item.label, text_x, text_y, font_size, text_color)

        item_y += MENU_ITEM_HEIGHT


# Settings window configuration items
# Format: (display_label, config_key, value_type, min_val, max_val)
SETTINGS_ITEMS = [
    ("Performance", None, None, None, None),  # Section header
    ("TARGET_FPS", "TARGET_FPS", int, 30, 240),
    ("ASYNC_WORKERS", "ASYNC_WORKERS", int, 1, 32),
    ("Animation (ms)", None, None, None, None),  # Section header
    ("ANIM_SWITCH_KEYS_MS", "ANIM_SWITCH_KEYS_MS", int, 0, 2000),
    ("ANIM_OPEN_MS", "ANIM_OPEN_MS", int, 0, 2000),
    ("ANIM_ZOOM_MS", "ANIM_ZOOM_MS", int, 0, 500),
    ("GALLERY_SLIDE_MS", "GALLERY_SLIDE_MS", int, 0, 500),
    ("Zoom", None, None, None, None),  # Section header
    ("ZOOM_STEP_KEYS", "ZOOM_STEP_KEYS", float, 0.001, 0.1),
    ("ZOOM_STEP_WHEEL", "ZOOM_STEP_WHEEL", float, 0.01, 0.5),
    ("Font", None, None, None, None),  # Section header
    ("FONT_DISPLAY_SIZE", "FONT_DISPLAY_SIZE", int, 12, 72),
]


def get_settings_item_index(item_idx: int) -> int:
    """Convert visual item index to editable item index (skip headers)."""
    editable_idx = 0
    for i, item in enumerate(SETTINGS_ITEMS):
        if item[1] is not None:  # Not a header
            if i == item_idx:
                return editable_idx
            editable_idx += 1
    return -1


def save_config_value(config_key: str, value, val_type: type) -> bool:
    """Save a single config value to config.py file."""
    import imagura.config as cfg
    config_path = os.path.join(os.path.dirname(__file__), "imagura", "config.py")

    try:
        # Read current file
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find and replace the value
        import re
        if val_type == float:
            pattern = rf'^({config_key}\s*=\s*)[\d.]+(.*)$'
            replacement = rf'\g<1>{value}\2'
        else:
            pattern = rf'^({config_key}\s*=\s*)\d+(.*)$'
            replacement = rf'\g<1>{int(value)}\2'

        new_content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)

        if count == 0:
            log(f"[SETTINGS][ERR] Could not find {config_key} in config.py")
            return False

        # Write back
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        # Update runtime value
        setattr(cfg, config_key, val_type(value))
        log(f"[SETTINGS] Saved {config_key} = {value}")
        return True

    except Exception as e:
        log(f"[SETTINGS][ERR] Failed to save config: {e!r}")
        return False


def validate_settings_value(value_str: str, val_type: type, min_val, max_val) -> tuple:
    """Validate a settings value. Returns (is_valid, parsed_value, error_msg)."""
    if not value_str.strip():
        return False, None, "Empty value"

    try:
        if val_type == int:
            val = int(value_str)
        elif val_type == float:
            val = float(value_str)
        else:
            return False, None, "Unknown type"

        if min_val is not None and val < min_val:
            return False, None, f"Min: {min_val}"
        if max_val is not None and val > max_val:
            return False, None, f"Max: {max_val}"

        return True, val, None

    except ValueError:
        return False, None, "Invalid number"


def handle_settings_input(state: AppState) -> bool:
    """Handle input for settings window. Returns True if input was consumed."""
    import imagura.config as cfg  # Import at function start for nested functions

    settings = state.ui.settings
    if not settings.visible:
        return False

    mouse = rl.GetMousePosition()

    # Window dimensions (must match draw_settings_window)
    win_w = 400
    win_h = 500
    win_x = (state.screenW - win_w) // 2
    win_y = (state.screenH - win_h) // 2

    # Check close button click
    close_x = win_x + win_w - 35
    close_y = win_y + 5
    if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
        if close_x <= mouse.x <= close_x + 30 and close_y <= mouse.y <= close_y + 30:
            settings.hide()
            return True

    # Helper to save current editing value
    def save_current_edit() -> bool:
        """Save current edit value. Returns True if successful."""
        if settings.editing_item < 0:
            return True
        editable_idx = 0
        for item in SETTINGS_ITEMS:
            if item[1] is not None:  # Not a header
                if editable_idx == settings.editing_item:
                    label, config_key, val_type, min_val, max_val = item
                    is_valid, parsed_val, error = validate_settings_value(
                        settings.edit_value, val_type, min_val, max_val
                    )
                    if is_valid:
                        save_config_value(config_key, parsed_val, val_type)
                        # Update runtime config value
                        setattr(cfg, config_key, parsed_val)
                        log(f"[SETTINGS] Updated {config_key} = {parsed_val}")
                        return True
                    else:
                        log(f"[SETTINGS] Validation failed: {error}")
                        return False
                editable_idx += 1
        return True

    # Count total editable items
    total_editable = sum(1 for item in SETTINGS_ITEMS if item[1] is not None)

    # Handle editing mode
    if settings.editing_item >= 0:
        # Click handling - save current and possibly switch to another field
        if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
            item_y = win_y + 50
            item_h = 28
            val_x = win_x + win_w - 110
            val_w = 100

            # Find which field was clicked (if any)
            clicked_field = -1
            editable_idx = 0
            for item in SETTINGS_ITEMS:
                if item[1] is not None:  # Editable item
                    if (val_x - 5 <= mouse.x <= val_x + val_w + 5 and
                        item_y <= mouse.y <= item_y + item_h):
                        clicked_field = editable_idx
                        break
                    editable_idx += 1
                item_y += item_h

            if clicked_field == settings.editing_item:
                # Clicked on same field - do nothing
                pass
            elif clicked_field >= 0:
                # Clicked on another field - save current and switch
                if save_current_edit():
                    import imagura.config as cfg
                    # Find the config key for clicked field
                    editable_idx = 0
                    for item in SETTINGS_ITEMS:
                        if item[1] is not None:
                            if editable_idx == clicked_field:
                                current_val = getattr(cfg, item[1], 0)
                                settings.editing_item = clicked_field
                                settings.edit_value = str(current_val)
                                break
                            editable_idx += 1
                return True
            else:
                # Clicked outside any field - save and exit editing
                if save_current_edit():
                    settings.editing_item = -1
                    settings.edit_value = ""
                return True

        # Tab - save and move to next field
        if rl.IsKeyPressed(rl.KEY_TAB):
            if save_current_edit():
                import imagura.config as cfg
                if rl.IsKeyDown(rl.KEY_LEFT_SHIFT) or rl.IsKeyDown(rl.KEY_RIGHT_SHIFT):
                    # Shift+Tab - previous field
                    new_idx = (settings.editing_item - 1) % total_editable
                else:
                    # Tab - next field
                    new_idx = (settings.editing_item + 1) % total_editable

                # Find config key for new field
                editable_idx = 0
                for item in SETTINGS_ITEMS:
                    if item[1] is not None:
                        if editable_idx == new_idx:
                            current_val = getattr(cfg, item[1], 0)
                            settings.editing_item = new_idx
                            settings.edit_value = str(current_val)
                            break
                        editable_idx += 1
            return True

        # Get key input
        key = rl.GetCharPressed()
        while key > 0:
            # Allow digits, decimal point, minus
            if (48 <= key <= 57) or key == 46 or key == 45:  # 0-9, '.', '-'
                settings.edit_value += chr(key)
            key = rl.GetCharPressed()

        # Backspace
        if rl.IsKeyPressed(rl.KEY_BACKSPACE) and len(settings.edit_value) > 0:
            settings.edit_value = settings.edit_value[:-1]

        # Enter - save value and exit editing
        if rl.IsKeyPressed(rl.KEY_ENTER):
            if save_current_edit():
                settings.editing_item = -1
                settings.edit_value = ""
            return True

        # Escape - cancel editing (don't save)
        if rl.IsKeyPressed(rl.KEY_ESCAPE):
            settings.editing_item = -1
            settings.edit_value = ""
            return True

        return True  # Consume all input while editing

    # ESC closes settings when not editing
    if rl.IsKeyPressed(rl.KEY_ESCAPE):
        settings.hide()
        return True

    # Handle item click to start editing
    if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
        item_y = win_y + 50
        item_h = 28
        val_x = win_x + win_w - 110
        val_w = 100

        editable_idx = 0
        for item in SETTINGS_ITEMS:
            label, config_key, val_type, min_val, max_val = item if len(item) == 5 else (item[0], item[1], None, None, None)

            if config_key is not None:  # Editable item
                # Check if click is in value area
                if (val_x <= mouse.x <= val_x + val_w and
                    item_y <= mouse.y <= item_y + item_h):
                    import imagura.config as cfg
                    current_val = getattr(cfg, config_key, 0)
                    settings.editing_item = editable_idx
                    settings.edit_value = str(current_val)
                    return True
                editable_idx += 1

            item_y += item_h

    return False


def draw_settings_window(state: AppState):
    """Draw settings window overlay."""
    import imagura.config as cfg  # Import at start to avoid scope issues

    settings = state.ui.settings
    if not settings.visible:
        return

    # Window dimensions
    win_w = 400
    win_h = 500
    win_x = (state.screenW - win_w) // 2
    win_y = (state.screenH - win_h) // 2

    # Darken background
    rl.DrawRectangle(0, 0, state.screenW, state.screenH, RL_Color(0, 0, 0, 150))

    # Window background
    rl.DrawRectangle(win_x, win_y, win_w, win_h, RL_Color(30, 30, 30, 250))
    rl.DrawRectangleLines(win_x, win_y, win_w, win_h, RL_Color(100, 100, 100, 255))

    # Font size from config
    font_size = cfg.FONT_DISPLAY_SIZE

    # Title
    title = "Настройки"
    if state.unicode_font:
        try:
            rl.DrawTextEx(state.unicode_font, title.encode('utf-8'),
                          RL_V2(win_x + 20, win_y + 15), font_size, 1.0, RL_Color(255, 255, 255, 255))
        except Exception:
            RL_DrawText("Settings", win_x + 20, win_y + 15, font_size, RL_Color(255, 255, 255, 255))
    else:
        RL_DrawText("Settings", win_x + 20, win_y + 15, font_size, RL_Color(255, 255, 255, 255))

    # Close button (X)
    close_x = win_x + win_w - 30
    close_y = win_y + 10
    if state.unicode_font:
        try:
            rl.DrawTextEx(state.unicode_font, b"X",
                          RL_V2(close_x, close_y), font_size, 1.0, RL_Color(200, 200, 200, 255))
        except Exception:
            RL_DrawText("X", close_x, close_y, font_size, RL_Color(200, 200, 200, 255))
    else:
        RL_DrawText("X", close_x, close_y, font_size, RL_Color(200, 200, 200, 255))

    # Settings items
    item_y = win_y + 50
    item_h = 28
    padding_x = 20
    val_x = win_x + win_w - 110
    val_w = 90

    editable_idx = 0

    for item in SETTINGS_ITEMS:
        label, config_key, val_type, min_val, max_val = item if len(item) == 5 else (item[0], item[1], None, None, None)

        if config_key is None:
            # Section header
            rl.DrawRectangle(win_x, item_y, win_w, item_h, RL_Color(50, 50, 50, 255))
            if state.unicode_font:
                try:
                    rl.DrawTextEx(state.unicode_font, label.encode('utf-8'),
                                  RL_V2(win_x + padding_x, item_y + 6), font_size, 1.0, RL_Color(180, 180, 180, 255))
                except Exception:
                    RL_DrawText(label, win_x + padding_x, item_y + 6, font_size, RL_Color(180, 180, 180, 255))
            else:
                RL_DrawText(label, win_x + padding_x, item_y + 6, font_size, RL_Color(180, 180, 180, 255))
        else:
            # Config item
            current_val = getattr(cfg, config_key, "?")

            # Draw label
            label_text = f"  {label}:"
            if state.unicode_font:
                try:
                    rl.DrawTextEx(state.unicode_font, label_text.encode('utf-8'),
                                  RL_V2(win_x + padding_x, item_y + 6), font_size, 1.0, RL_Color(200, 200, 200, 255))
                except Exception:
                    RL_DrawText(label_text, win_x + padding_x, item_y + 6, font_size, RL_Color(200, 200, 200, 255))
            else:
                RL_DrawText(label_text, win_x + padding_x, item_y + 6, font_size, RL_Color(200, 200, 200, 255))

            # Check if this item is being edited
            is_editing = (settings.editing_item == editable_idx)

            # Draw value background (edit field)
            if is_editing:
                rl.DrawRectangle(val_x - 5, item_y + 2, val_w + 10, item_h - 4, RL_Color(60, 60, 80, 255))
                rl.DrawRectangleLines(val_x - 5, item_y + 2, val_w + 10, item_h - 4, RL_Color(100, 150, 255, 255))
                # Draw edit value with cursor
                display_val = settings.edit_value
                cursor = "|" if (int(now() * 2) % 2 == 0) else ""
                edit_text = display_val + cursor
                if state.unicode_font:
                    try:
                        rl.DrawTextEx(state.unicode_font, edit_text.encode('utf-8'),
                                      RL_V2(val_x, item_y + 6), font_size, 1.0, RL_Color(255, 255, 255, 255))
                    except Exception:
                        RL_DrawText(edit_text, val_x, item_y + 6, font_size, RL_Color(255, 255, 255, 255))
                else:
                    RL_DrawText(edit_text, val_x, item_y + 6, font_size, RL_Color(255, 255, 255, 255))
            else:
                # Hover highlight
                mouse = rl.GetMousePosition()
                if (val_x - 5 <= mouse.x <= val_x + val_w + 5 and
                    item_y <= mouse.y <= item_y + item_h):
                    rl.DrawRectangle(val_x - 5, item_y + 2, val_w + 10, item_h - 4, RL_Color(50, 50, 60, 255))

                val_str = str(current_val)
                if state.unicode_font:
                    try:
                        rl.DrawTextEx(state.unicode_font, val_str.encode('utf-8'),
                                      RL_V2(val_x, item_y + 6), font_size, 1.0, RL_Color(100, 200, 255, 255))
                    except Exception:
                        RL_DrawText(val_str, val_x, item_y + 6, font_size, RL_Color(100, 200, 255, 255))
                else:
                    RL_DrawText(val_str, val_x, item_y + 6, font_size, RL_Color(100, 200, 255, 255))

            editable_idx += 1

        item_y += item_h

    # Footer hint
    if settings.editing_item >= 0:
        hint = "Enter: Сохранить | Esc: Отмена"
    else:
        hint = "Клик по значению для редактирования | Esc: Закрыть"
    hint_size = max(12, font_size - 4)  # Slightly smaller than main font
    if state.unicode_font:
        try:
            rl.DrawTextEx(state.unicode_font, hint.encode('utf-8'),
                          RL_V2(win_x + 20, win_y + win_h - 30), hint_size, 1.0, RL_Color(120, 120, 120, 255))
        except Exception:
            RL_DrawText(hint, win_x + 20, win_y + win_h - 30, hint_size, RL_Color(120, 120, 120, 255))
    else:
        RL_DrawText(hint, win_x + 20, win_y + win_h - 30, hint_size, RL_Color(120, 120, 120, 255))


def delete_to_recycle_bin(file_path: str) -> bool:
    """
    Delete a file to the Windows recycle bin.

    Uses SHFileOperationW from shell32.dll.
    Returns True if successful, False otherwise.
    """
    if sys.platform != 'win32':
        log(f"[DELETE] Recycle bin not supported on {sys.platform}")
        return False

    try:
        import ctypes
        from ctypes import wintypes

        # SHFILEOPSTRUCTW structure
        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", wintypes.LPCWSTR),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", wintypes.WORD),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        # Constants
        FO_DELETE = 3
        FOF_ALLOWUNDO = 0x0040  # Send to recycle bin
        FOF_NOCONFIRMATION = 0x0010  # No confirmation dialog
        FOF_SILENT = 0x0004  # No progress dialog

        shell32 = ctypes.windll.shell32

        # Path must be double-null terminated
        path_double_null = file_path + '\0\0'

        file_op = SHFILEOPSTRUCTW()
        file_op.hwnd = None
        file_op.wFunc = FO_DELETE
        file_op.pFrom = path_double_null
        file_op.pTo = None
        file_op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
        file_op.fAnyOperationsAborted = False
        file_op.hNameMappings = None
        file_op.lpszProgressTitle = None

        result = shell32.SHFileOperationW(ctypes.byref(file_op))

        if result == 0 and not file_op.fAnyOperationsAborted:
            log(f"[DELETE] Sent to recycle bin: {os.path.basename(file_path)}")
            return True
        else:
            log(f"[DELETE][ERR] SHFileOperationW failed: {result}")
            return False

    except Exception as e:
        log(f"[DELETE][ERR] Failed to delete: {e!r}")
        return False


def delete_current_image(state: AppState) -> bool:
    """
    Delete the current image to recycle bin and navigate to next/prev.
    Returns True if successful.
    """
    if state.index >= len(state.current_dir_images):
        return False

    if len(state.current_dir_images) == 0:
        return False

    path = state.current_dir_images[state.index]
    old_index = state.index

    # First delete the file
    if not delete_to_recycle_bin(path):
        return False

    # Unload all cached textures (curr, prev, next) since indices shift
    for ti in (state.cache.curr, state.cache.prev, state.cache.next):
        if ti:
            try:
                if getattr(ti.tex, 'id', 0):
                    state.to_unload.append(ti.tex)
            except Exception:
                pass
    state.cache.curr = None
    state.cache.prev = None
    state.cache.next = None

    # Remove from thumbnail cache
    if path in state.thumb_cache:
        bt = state.thumb_cache.pop(path)
        if bt.texture:
            try:
                rl.UnloadTexture(bt.texture)
            except Exception:
                pass

    # Remove from image list
    state.current_dir_images.pop(old_index)

    # Adjust index
    n = len(state.current_dir_images)
    if n == 0:
        # No more images - will exit
        log("[DELETE] No more images in directory")
        return True

    # Stay at same position or go to last if at end
    if old_index >= n:
        state.index = n - 1
    else:
        state.index = old_index

    # Load new current image
    preload_neighbors(state, state.index, skip_neighbors=False)

    # Update gallery center - reset target and jump to new index
    state.gallery_target_index = None
    state.gallery_center_index = float(state.index)
    schedule_thumbs(state, state.index)

    log(f"[DELETE] Now showing index {state.index} of {n}")
    return True


def reload_current_image(state: AppState):
    """Reload current image after transformation."""
    if state.index >= len(state.current_dir_images):
        return

    path = state.current_dir_images[state.index]
    log(f"[TRANSFORM] Reloading image: {os.path.basename(path)}")

    # Unload current texture
    if state.cache.curr:
        try:
            if getattr(state.cache.curr.tex, 'id', 0):
                state.to_unload.append(state.cache.curr.tex)
        except Exception:
            pass
        state.cache.curr = None

    # Also invalidate thumbnail
    if path in state.thumb_cache:
        bt = state.thumb_cache.pop(path)
        if bt.texture:
            try:
                rl.UnloadTexture(bt.texture)
            except Exception:
                pass

    # Schedule thumbnail reload
    if path not in state.thumb_queue:
        state.thumb_queue.append(path)

    # Reload
    preload_neighbors(state, state.index, skip_neighbors=True)


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
    if GALLERY_SLIDE_MS <= 0:
        # Instant transition when slide time is 0
        state.gallery_y = tgt
    else:
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
    """Get 1:1 centered view for current image."""
    ti = state.cache.curr
    if not ti:
        return state.view
    return view_1to1_pure(ti.w, ti.h, state.screenW, state.screenH)


def sanitize_view(state: AppState, view: ViewParams, ti: TextureInfo) -> ViewParams:
    """Wrapper for sanitize_view_pure that uses AppState dimensions."""
    return sanitize_view_pure(view, ti.w, ti.h, state.screenW, state.screenH)


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


def start_toggle_zoom_animation(state: AppState):
    """Start non-blocking toggle zoom animation (F key / double-click)."""
    if state.toggle_zoom_active:
        return  # Already animating

    if not state.cache.curr:
        return

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

    state.toggle_zoom_active = True
    state.toggle_zoom_t0 = now()
    state.toggle_zoom_from = ViewParams(state.view.scale, state.view.offx, state.view.offy)
    state.toggle_zoom_to = target
    state.toggle_zoom_target_state = next_state
    log(f"[TOGGLE_ZOOM] Started: {state.zoom_state_cycle} -> {next_state}")


def update_toggle_zoom_animation(state: AppState):
    """Update toggle zoom animation each frame."""
    if not state.toggle_zoom_active:
        return

    ti = state.cache.curr
    if not ti:
        state.toggle_zoom_active = False
        return

    t = (now() - state.toggle_zoom_t0) / (ANIM_TOGGLE_ZOOM_MS / 1000.0)

    if t >= 1.0:
        # Animation finished
        state.toggle_zoom_active = False
        state.view = clamp_pan(state.toggle_zoom_to, ti, state.screenW, state.screenH)
        state.zoom_state_cycle = state.toggle_zoom_target_state
        state.is_zoomed = (state.view.scale > state.last_fit_view.scale)

        if state.index < len(state.current_dir_images):
            path = state.current_dir_images[state.index]
            save_view_for_path(state, path, state.view)
            if state.zoom_state_cycle == 2:
                state.user_zoom_memory[path] = ViewParams(state.view.scale, state.view.offx, state.view.offy)
                log(f"[TOGGLE_ZOOM] Saved USER view: scale={state.view.scale:.3f}")

        log(f"[TOGGLE_ZOOM] Finished: state={state.zoom_state_cycle} scale={state.view.scale:.3f}")
        return

    t_eased = ease_in_out_cubic(t)
    cur = ViewParams(
        scale=lerp(state.toggle_zoom_from.scale, state.toggle_zoom_to.scale, t_eased),
        offx=lerp(state.toggle_zoom_from.offx, state.toggle_zoom_to.offx, t_eased),
        offy=lerp(state.toggle_zoom_from.offy, state.toggle_zoom_to.offy, t_eased),
    )
    state.view = clamp_pan(cur, ti, state.screenW, state.screenH)


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
    atexit.register(lambda: log(f"[EXIT] frames={get_frame()} thumbs={len(state.thumb_cache)} q={len(state.thumb_queue)}"))

    font_loaded = False
    blur_enabled = False
    first_render_done = False

    # Key repeat state for navigation
    nav_key_state = {
        'next': {'pressed_time': 0.0, 'last_repeat': 0.0},
        'prev': {'pressed_time': 0.0, 'last_repeat': 0.0},
    }

    try:
        while True:
            if state.open_anim_active:
                state.async_loader.poll_ui_events(max_events=2)
            else:
                state.async_loader.poll_ui_events(max_events=100)

            if not font_loaded and state.cache.curr and first_render_done and not state.open_anim_active:
                state.unicode_font = load_unicode_font()
                font_loaded = True
                log("[INIT] Font loaded after first render")

            if not blur_enabled and state.cache.curr and first_render_done and not state.open_anim_active:
                # Initial blur setup is now handled by apply_bg_mode via _current_blur_enabled
                blur_enabled = True
                log("[INIT] Background mode active after first render")

            if state.cache.curr and state.open_anim_active and state.view.scale == 0.5:
                state.view = compute_fit_view(state, FIT_OPEN_SCALE)
                log(f"[MAIN] Set FIT_OPEN view for animation")

            process_deferred_unloads(state)
            update_zoom_animation(state)
            update_toggle_zoom_animation(state)
            process_switch_queue(state)
            apply_bg_opacity_anim(state)
            update_close_button_alpha(state)
            update_nav_buttons_fade(state)
            update_gallery_visibility_and_slide(state)
            update_gallery_scroll(state)
            reconcile_gallery_target(state)
            update_toolbar_alpha(state)

            if not state.open_anim_active:
                process_thumb_queue(state)

            should_close = rl.WindowShouldClose()
            if should_close:
                break

            # Handle settings window input first (blocks other input when visible)
            if state.ui.settings.visible:
                handle_settings_input(state)

            rl.BeginDrawing()
            apply_bg_mode(state)

            mouse = rl.GetMousePosition()

            # ─── Context Menu Input ─────────────────────────────────────────────
            menu = state.ui.context_menu
            menu_consumed_click = False  # Track if menu consumed the click

            if menu.visible:
                menu.hover_index = get_context_menu_item_at(state, mouse.x, mouse.y)

                if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                    menu_consumed_click = True  # Block click from propagating
                    if menu.hover_index >= 0:
                        item = menu.items[menu.hover_index]
                        log(f"[MENU] Clicked: {item.label}")
                        # Execute action
                        if item.id == MenuItemId.COPY:
                            if state.index < len(state.current_dir_images):
                                path = state.current_dir_images[state.index]
                                copy_image_to_clipboard(path)
                    menu.hide()

                if rl.IsKeyPressed(KEY_CLOSE):
                    menu.hide()

            # Right-click shows context menu (don't skip rendering)
            # Don't show context menu when settings window is open
            if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_RIGHT) and not menu.visible and not state.ui.settings.visible:
                menu.show(int(mouse.x), int(mouse.y))

            # ─── Toolbar Input ──────────────────────────────────────────────────
            toolbar = state.ui.toolbar

            # Update toolbar visibility based on mouse position
            if is_in_toolbar_zone(state, mouse.x, mouse.y):
                toolbar.target_alpha = 1.0
            else:
                toolbar.target_alpha = 0.0

            # Update toolbar hover
            if toolbar.alpha > 0.1:
                toolbar.hover_index = get_toolbar_button_at(state, mouse.x, mouse.y)
            else:
                toolbar.hover_index = -1

            # Toolbar button click
            toolbar_consumed_click = False
            if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT) and toolbar.hover_index >= 0 and not menu_consumed_click:
                toolbar_consumed_click = True
                btn = toolbar.buttons[toolbar.hover_index]
                log(f"[TOOLBAR] Clicked: {btn.tooltip}")

                if btn.id == ToolbarButtonId.SETTINGS:
                    state.ui.settings.show()
                elif state.index < len(state.current_dir_images):
                    path = state.current_dir_images[state.index]

                    if btn.id == ToolbarButtonId.ROTATE_CW:
                        if rotate_image_file(path, clockwise=True):
                            reload_current_image(state)
                    elif btn.id == ToolbarButtonId.ROTATE_CCW:
                        if rotate_image_file(path, clockwise=False):
                            reload_current_image(state)
                    elif btn.id == ToolbarButtonId.FLIP_H:
                        if flip_image_file(path, horizontal=True):
                            reload_current_image(state)

            # ─── Regular Input ──────────────────────────────────────────────────
            # Track if any UI element consumed the click
            input_consumed = menu_consumed_click or toolbar_consumed_click

            if not input_consumed and check_close_button_click(state):
                break

            state.idle_detector.mark_activity()

            if rl.IsKeyPressed(KEY_TOGGLE_HUD):
                state.show_hud = not state.show_hud

            if rl.IsKeyPressed(KEY_TOGGLE_FILENAME):
                state.show_filename = not state.show_filename

            if rl.IsKeyPressed(KEY_CYCLE_BG):
                state.bg_mode_index = (state.bg_mode_index + 1) % len(BG_MODES)
                state.bg_target_opacity = BG_MODES[state.bg_mode_index]["opacity"]

            # DEL key - delete image to recycle bin
            if rl.IsKeyPressed(KEY_DELETE_IMAGE) and not state.open_anim_active:
                if delete_current_image(state):
                    if len(state.current_dir_images) == 0:
                        # No more images - close app
                        break
                    rl.EndDrawing()
                    increment_frame()
                    continue

            if state.cache.curr and not state.open_anim_active and not state.toggle_zoom_active:
                if rl.IsKeyDown(KEY_ZOOM_IN) or rl.IsKeyDown(KEY_ZOOM_IN_ALT):
                    new_scale = min(state.view.scale * (1.0 + ZOOM_STEP_KEYS), MAX_ZOOM)
                    nv = recompute_view_anchor_zoom(state.view, new_scale,
                                                    (int(mouse.x), int(mouse.y)), state.cache.curr)
                    nv = clamp_pan(nv, state.cache.curr, state.screenW, state.screenH)
                    start_zoom_animation(state, nv)
                    state.is_zoomed = (nv.scale > state.last_fit_view.scale)
                    state.zoom_state_cycle = 2
                    if state.index < len(state.current_dir_images):
                        path = state.current_dir_images[state.index]
                        save_view_for_path(state, path, nv)
                        state.user_zoom_memory[path] = ViewParams(nv.scale, nv.offx, nv.offy)

                if rl.IsKeyDown(KEY_ZOOM_OUT) or rl.IsKeyDown(KEY_ZOOM_OUT_ALT):
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
            if wheel != 0.0 and state.cache.curr and not state.open_anim_active and not state.toggle_zoom_active:
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
                    new_scale = min(state.view.scale * (1.0 + wheel * ZOOM_STEP_WHEEL), MAX_ZOOM)
                    nv = recompute_view_anchor_zoom(state.view, new_scale,
                                                    (int(mouse.x), int(mouse.y)), state.cache.curr)
                    nv = clamp_pan(nv, state.cache.curr, state.screenW, state.screenH)
                    start_zoom_animation(state, nv)
                    state.is_zoomed = (nv.scale > state.last_fit_view.scale)
                    state.zoom_state_cycle = 2
                    if state.index < len(state.current_dir_images):
                        path = state.current_dir_images[state.index]
                        save_view_for_path(state, path, nv)
                        state.user_zoom_memory[path] = ViewParams(nv.scale, nv.offx, nv.offy)

            # Double-click zone: everywhere except navigation edges (10% on each side)
            edge_margin = 0.10
            not_on_edge = (mouse.x > state.screenW * edge_margin and
                          mouse.x < state.screenW * (1 - edge_margin))

            if rl.IsKeyPressed(KEY_TOGGLE_ZOOM) and not state.toggle_zoom_active:
                start_toggle_zoom_animation(state)

            # Always track clicks for double-click detection, even during animation
            if not_on_edge and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT) and not input_consumed:
                is_double = detect_double_click(state, int(mouse.x), int(mouse.y))
                if is_double and not state.toggle_zoom_active:
                    start_toggle_zoom_animation(state)

            if state.cache.curr and not state.open_anim_active and not state.toggle_zoom_active:
                img_rect = RL_Rect(state.view.offx, state.view.offy, state.cache.curr.w * state.view.scale,
                                   state.cache.curr.h * state.view.scale)
                over_img = (
                        img_rect.x <= mouse.x <= img_rect.x + img_rect.width and img_rect.y <= mouse.y <= img_rect.y + img_rect.height)

                # Allow panning in any zoom mode (not just when zoomed)
                if rl.IsMouseButtonPressed(
                        rl.MOUSE_BUTTON_LEFT) and over_img and not is_point_in_close_button(state,
                                                                                            mouse.x,
                                                                                            mouse.y) and not input_consumed:
                    state.is_panning = True
                    state.pan_start_mouse = (mouse.x, mouse.y)
                    state.pan_start_offset = (state.view.offx, state.view.offy)

                if rl.IsMouseButtonReleased(rl.MOUSE_BUTTON_LEFT):
                    if state.is_panning:
                        # Check if actual panning occurred (mouse moved significantly)
                        dx = abs(mouse.x - state.pan_start_mouse[0])
                        dy = abs(mouse.y - state.pan_start_mouse[1])
                        actually_panned = dx > 5 or dy > 5

                        state.is_panning = False
                        if actually_panned and state.cache.curr and state.index < len(state.current_dir_images):
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

                # Navigation with key repeat support
                current_time = now()

                # Next image (Right, D)
                next_down = rl.IsKeyDown(KEY_NEXT_IMAGE) or rl.IsKeyDown(KEY_NEXT_IMAGE_ALT)
                if next_down:
                    should_trigger = False
                    if nav_key_state['next']['pressed_time'] == 0.0:
                        # Key just pressed
                        nav_key_state['next']['pressed_time'] = current_time
                        nav_key_state['next']['last_repeat'] = current_time
                        should_trigger = True
                    elif current_time - nav_key_state['next']['pressed_time'] >= KEY_REPEAT_DELAY:
                        # Key held long enough, check repeat interval
                        if current_time - nav_key_state['next']['last_repeat'] >= KEY_REPEAT_INTERVAL:
                            nav_key_state['next']['last_repeat'] = current_time
                            should_trigger = True

                    if should_trigger and state.index + 1 < len(state.current_dir_images):
                        switch_to(state, state.index + 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)
                else:
                    nav_key_state['next']['pressed_time'] = 0.0

                # Previous image (Left, A)
                prev_down = rl.IsKeyDown(KEY_PREV_IMAGE) or rl.IsKeyDown(KEY_PREV_IMAGE_ALT)
                if prev_down:
                    should_trigger = False
                    if nav_key_state['prev']['pressed_time'] == 0.0:
                        # Key just pressed
                        nav_key_state['prev']['pressed_time'] = current_time
                        nav_key_state['prev']['last_repeat'] = current_time
                        should_trigger = True
                    elif current_time - nav_key_state['prev']['pressed_time'] >= KEY_REPEAT_DELAY:
                        # Key held long enough, check repeat interval
                        if current_time - nav_key_state['prev']['last_repeat'] >= KEY_REPEAT_INTERVAL:
                            nav_key_state['prev']['last_repeat'] = current_time
                            should_trigger = True

                    if should_trigger and state.index - 1 >= 0:
                        switch_to(state, state.index - 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)
                else:
                    nav_key_state['prev']['pressed_time'] = 0.0

                zoom_threshold = state.last_fit_view.scale * 1.1
                is_significantly_zoomed = state.view.scale > zoom_threshold

                gh = int(state.screenH * GALLERY_HEIGHT_FRAC)
                yv = state.screenH - gh
                in_gallery_panel = (yv <= mouse.y <= state.screenH)

                if not is_significantly_zoomed and not in_gallery_panel and not input_consumed:
                    if edge_right and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                        if state.index + 1 < len(state.current_dir_images):
                            switch_to(state, state.index + 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)
                    if edge_left and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                        if state.index - 1 >= 0:
                            switch_to(state, state.index - 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)

            if not input_consumed and check_close_button_click(state):
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
                hud_font_size = cfg.FONT_DISPLAY_SIZE
                line_spacing = hud_font_size + 4
                hud_color = RL_Color(200, 200, 200, 255)

                # Build HUD lines
                hud_lines = []

                # Line 1: Index/total
                total = len(state.current_dir_images)
                hud_lines.append(f"[{state.index + 1}/{total}]")

                # Line 2: Zoom with mode label
                zoom_pct = int(state.view.scale * 100)
                zoom_mode = get_zoom_mode_label(state)
                hud_lines.append(f"{zoom_pct}% ({zoom_mode})")

                # Line 3: Resolution (use 'x' for cross-platform compatibility)
                if state.cache.curr:
                    hud_lines.append(f"{state.cache.curr.w} x {state.cache.curr.h}")

                # Line 4+: Metadata from EXIF
                if state.index < len(state.current_dir_images):
                    filepath = state.current_dir_images[state.index]
                    metadata = get_image_metadata(filepath)
                    if metadata:
                        # Date taken
                        if 'date' in metadata:
                            hud_lines.append(metadata['date'])
                        # Camera settings on one line
                        camera_info = []
                        if 'camera' in metadata:
                            camera_info.append(metadata['camera'])
                        if camera_info:
                            hud_lines.append(' '.join(camera_info))
                        # Exposure settings
                        exp_info = []
                        if 'focal' in metadata:
                            exp_info.append(metadata['focal'])
                        if 'aperture' in metadata:
                            exp_info.append(metadata['aperture'])
                        if 'exposure' in metadata:
                            exp_info.append(metadata['exposure'])
                        if 'iso' in metadata:
                            exp_info.append(metadata['iso'])
                        if exp_info:
                            hud_lines.append(' | '.join(exp_info))

                # Calculate Y position from bottom
                hud_y = state.screenH - (len(hud_lines) * line_spacing + 20)

                # Draw HUD with unicode font if available
                for i, line in enumerate(hud_lines):
                    y_pos = hud_y + i * line_spacing
                    if state.unicode_font:
                        try:
                            rl.DrawTextEx(state.unicode_font, line.encode('utf-8'),
                                          RL_V2(12, y_pos), hud_font_size, 1.0, hud_color)
                            continue
                        except Exception:
                            pass
                    RL_DrawText(line, 12, y_pos, hud_font_size, hud_color)

            # Draw toolbar, context menu and settings (on top of everything)
            draw_toolbar(state)
            draw_context_menu(state)
            draw_settings_window(state)

            rl.EndDrawing()
            increment_frame()

            # Skip other key handling when settings is open
            if state.ui.settings.visible:
                continue

            if rl.IsKeyPressed(KEY_CLOSE):
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