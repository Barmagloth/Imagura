#!imagura2_async_fixed.py
"""Imagura - Fast async image viewer."""
from __future__ import annotations
import os
import sys
import atexit
import traceback
from typing import Tuple, Optional
from threading import Thread
import math

# Import from new modules
import imagura.config as cfg  # For dynamic access to config values
from imagura.config import (
    TARGET_FPS, ASYNC_WORKERS,
    ANIM_SWITCH_KEYS_MS, ANIM_SWITCH_GALLERY_MS, ANIM_TOGGLE_ZOOM_MS, RAPID_NAV_SKIP_THRESHOLD,
    ANIM_OPEN_MS, ANIM_ZOOM_MS,
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
    SETTINGS_MODAL_COLORS_TRANSPARENT, SETTINGS_MODAL_COLORS_LIGHT, SETTINGS_MODAL_COLORS_DARK,
    SETTINGS_MODAL_WIDTH, SETTINGS_MODAL_HEIGHT, SETTINGS_MODAL_SHADOW_OFFSET,
    SETTINGS_MODAL_TITLE_Y, SETTINGS_MODAL_CLOSE_SIZE, SETTINGS_MODAL_CLOSE_MARGIN,
    SETTINGS_TAB_HEIGHT, SETTINGS_TAB_PADDING, SETTINGS_TAB_GAP, SETTINGS_TAB_START_X, SETTINGS_TAB_TOP_Y,
    SETTINGS_CONTENT_PADDING_X, SETTINGS_CONTENT_ITEM_HEIGHT, SETTINGS_CONTENT_SUB_INDENT,
    SETTINGS_CONTENT_VALUE_WIDTH, SETTINGS_CONTENT_VALUE_MARGIN, SETTINGS_CONTENT_BORDER_MARGIN,
    SETTINGS_CONTENT_FOOTER_HEIGHT,
    KEY_REPEAT_DELAY, KEY_REPEAT_INTERVAL,
    TOOLBAR_TRIGGER_FRAC, TOOLBAR_TRIGGER_MIN_PX, TOOLBAR_HEIGHT, TOOLBAR_BTN_RADIUS, TOOLBAR_BTN_SPACING,
    TOOLBAR_BG_ALPHA, TOOLBAR_SLIDE_MS,
    MENU_ITEM_HEIGHT, MENU_ITEM_WIDTH, MENU_PADDING, MENU_BG_ALPHA, MENU_HOVER_ALPHA,
    FONT_SIZE, FONT_ANTIALIAS,
    KEY_TOGGLE_HUD, KEY_TOGGLE_FILENAME, KEY_CYCLE_BG, KEY_DELETE_IMAGE,
    KEY_ZOOM_IN, KEY_ZOOM_IN_ALT, KEY_ZOOM_OUT, KEY_ZOOM_OUT_ALT, KEY_TOGGLE_ZOOM,
    KEY_NEXT_IMAGE, KEY_NEXT_IMAGE_ALT, KEY_PREV_IMAGE, KEY_PREV_IMAGE_ALT, KEY_CLOSE,
    KEY_TOGGLE_WINDOW,
    MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT, NAV_EDGE_MIN_PX, GALLERY_MIN_HEIGHT_PX,
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
    set_titlebar_dark,
)
from imagura.image_utils import list_supported_files
from imagura.image_sorting import resort_preserving_current, sort_image_paths
from imagura.logging import log, now, increment_frame, get_frame
from imagura.types import (
    ViewParams, TextureInfo,
)
from imagura.view_math import (
    compute_fit_scale as compute_fit_scale_pure,
    center_view_for as center_view_for_pure,
    compute_fit_view as compute_fit_view_pure,
    clamp_pan as clamp_pan_pure,
    view_for_1to1_centered as view_1to1_pure,
    sanitize_view as sanitize_view_pure,
)
from imagura.gallery import GalleryBehavior, GalleryRenderer
from imagura.image_loading import CurrentAndNeighborLoader, load_content_cpu
from imagura.playback import AnimatedContentPlayback
from imagura.platform import delete_to_trash, open_image_file_dialog
from imagura.services import (
    AnimatedContentCache,
    AsyncContentLoader,
    IdleDetector,
    LargeTextureCache,
    TextureManager,
    ThumbnailService,
)
from imagura.state import AppState
from imagura.state.ui import ToolbarButtonId, MenuItemId
from imagura.clipboard import copy_image_to_clipboard
from imagura.transforms import rotate_image_file, flip_image_file
from imagura.user_settings import load_user_settings, save_user_setting, user_settings_path
from imagura.settings_persistence import (
    SETTINGS_TABS,
    SETTINGS_ITEMS,
    get_settings_item_index,
    settings_definitions,
    validate_settings_value,
    apply_saved_settings_impl as _apply_saved_settings_impl,
    save_config_value_impl as _save_config_value_impl,
)
from imagura.ui import (
    draw_context_menu as draw_context_menu_ui,
    draw_filename_overlay,
    draw_gallery_sort_control,
    draw_hud,
    draw_scale_overlay,
    draw_settings_window,
    draw_toolbar as draw_toolbar_ui,
    get_settings_color_scheme,
    handle_gallery_sort_input,
    handle_context_menu_input,
    handle_settings_input,
    update_toolbar_alpha as update_toolbar_alpha_ui,
    update_toolbar_input,
)
from imagura.zoom import (
    ScaleOverlayController,
    ToggleZoomAnimationController,
    ZoomAnimationController,
    apply_manual_zoom,
)

# Aliases for compatibility
RL_VER = RL_VERSION
_RL_WHITE = RL_WHITE
_TEXTURE_MANAGER = TextureManager()
_THUMBNAIL_SERVICE = ThumbnailService(_TEXTURE_MANAGER)
_LARGE_TEXTURE_CACHE = LargeTextureCache()
_ANIMATED_CONTENT_CACHE = AnimatedContentCache()
_GALLERY_BEHAVIOR = GalleryBehavior()
_GALLERY_RENDERER = GalleryRenderer()
_ANIMATED_PLAYBACK = AnimatedContentPlayback()
_SCALE_OVERLAY = ScaleOverlayController(now)
_ZOOM_ANIMATION = ZoomAnimationController(now)
_TOGGLE_ZOOM_ANIMATION = ToggleZoomAnimationController(now)


def _make_error_texture(path: str) -> TextureInfo:
    ph = rl.GenImageColor(2, 2, _RL_WHITE)
    tex = rl.LoadTextureFromImage(ph)
    rl.UnloadImage(ph)
    return TextureInfo(tex=tex, w=2, h=2, path=path)


_CURRENT_AND_NEIGHBOR_LOADER = CurrentAndNeighborLoader(
    _TEXTURE_MANAGER,
    _THUMBNAIL_SERVICE,
    _ANIMATED_PLAYBACK,
    _make_error_texture,
    now,
    _LARGE_TEXTURE_CACHE,
    _ANIMATED_CONTENT_CACHE,
)


def _fullscreen_window_flags() -> int:
    return (
        rl.FLAG_WINDOW_UNDECORATED
        | getattr(rl, "FLAG_WINDOW_ALWAYS_RUN", 0)
        | getattr(rl, "FLAG_WINDOW_TRANSPARENT", 0)
    )



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




def _set_window_icon() -> None:
    """Set the GLFW/raylib window icon (shown in the windowed title bar and taskbar)."""
    try:
        from imagura.app_icon import ICON_PNG_BYTES
        from imagura.viewers.base import load_image_from_memory

        img = load_image_from_memory(".png", ICON_PNG_BYTES)
        rl.SetWindowIcon(img)
        try:
            rl.UnloadImage(img)
        except Exception:
            pass
    except Exception as exc:
        log(f"[INIT][WARN] SetWindowIcon failed: {exc!r}")


def init_window_and_blur(state: AppState):
    log("[INIT] Starting window initialization")
    x, y, w, h = get_work_area()
    if w == 0 or h == 0:
        mon = getattr(rl, 'GetCurrentMonitor', lambda: 0)()
        w, h = rl.GetMonitorWidth(mon), rl.GetMonitorHeight(mon)
        x, y = 0, 0

    log(f"[INIT] Creating window: {w}x{h} at ({x}, {y})")
    flags = _fullscreen_window_flags()
    try:
        rl.SetConfigFlags(flags)
    except Exception as exc:
        log(f"[INIT][WARN] SetConfigFlags failed: {exc!r}")

    try:
        rl.InitWindow(w, h, "Imagura")
    except TypeError:
        rl.InitWindow(w, h, b"Imagura")

    log("[INIT] Window created")
    _set_window_icon()

    try:
        rl.SetExitKey(0)
    except Exception:
        pass
    rl.SetWindowState(flags)
    try:
        rl.SetWindowPosition(x, y)
    except Exception:
        pass
    rl.SetTargetFPS(TARGET_FPS)
    state.screenW, state.screenH = rl.GetScreenWidth(), rl.GetScreenHeight()
    state.hwnd = get_window_handle_from_raylib()
    set_titlebar_dark(state.hwnd)
    state.gallery_y = state.screenH
    state.unicode_font = None
    state.async_loader = AsyncContentLoader(load_content_cpu)
    state.idle_detector = IdleDetector()
    log(f"[INIT] RL_VER={RL_VER} workarea={w}x{h} window={state.screenW}x{state.screenH} hwnd={state.hwnd}")


# After a window-mode toggle the OS rebuilds the frame (border + DWM) over
# several frames, transiently shifting the client area. We suppress image
# drawing until the framebuffer size matches the target again (capped), so the
# transitional title-bar-height jump is never shown — the blurred background
# fills the screen meanwhile.
_post_toggle_settle = {"active": False, "w": 0, "h": 0, "n": 0}


def toggle_window_mode(state: AppState):
    """Toggle between fullscreen (borderless) and windowed mode.

    In windowed mode:
    - Window size matches current image size (50%-100% scale)
    - If image >= screen size, window is maximized
    - Window has standard decorations (title bar, buttons)
    """
    ti = state.cache.curr
    WINDOWED_MIN = 300   # minimum windowed-mode window size (px)
    TITLE_BAR_H = 32     # title bar sits above the client area on screen

    if not state.windowed_mode:
        # ── Fullscreen → windowed ───────────────────────────────────────────
        work_x, work_y, work_w, work_h = get_work_area()
        if work_w == 0 or work_h == 0:
            work_w, work_h = state.screenW, state.screenH
            work_x, work_y = 0, 0

        state.window.fullscreen_x = work_x
        state.window.fullscreen_y = work_y
        state.window.fullscreen_w = work_w
        state.window.fullscreen_h = work_h

        if ti:
            scale = state.view.scale
            img_dw = ti.w * scale
            img_dh = ti.h * scale
            # Image's current absolute screen position (the fullscreen render
            # surface origin == work-area origin).
            img_sx = work_x + state.view.offx
            img_sy = work_y + state.view.offy
            fits = img_dw <= work_w + 0.5 and img_dh <= work_h + 0.5
        else:
            scale = 1.0
            img_dw = img_dh = 0.0
            img_sx, img_sy = float(work_x), float(work_y)
            fits = False

        if ti and fits:
            # Image fits on screen -> keep the current scale. Window = image
            # size (>= WINDOWED_MIN); positioned so the image stays where it is
            # on screen. Any extra window space (when the 200px min kicks in for
            # a zoomed-out image) is centered around the image.
            new_scale = scale
            win_w = max(WINDOWED_MIN, int(round(img_dw)))
            win_h = max(WINDOWED_MIN, int(round(img_dh)))
            win_x = int(round(img_sx - (win_w - img_dw) / 2.0))
            win_y = int(round(img_sy - (win_h - img_dh) / 2.0))
        else:
            # Image larger than the screen (or none) -> scale to fit, centered.
            if ti:
                new_scale = min(work_w * FIT_DEFAULT_SCALE / ti.w,
                                work_h * FIT_DEFAULT_SCALE / ti.h)
                img_dw = ti.w * new_scale
                img_dh = ti.h * new_scale
            else:
                new_scale = 1.0
                img_dw, img_dh = work_w * 0.5, work_h * 0.5
            win_w = max(WINDOWED_MIN, int(round(img_dw)))
            win_h = max(WINDOWED_MIN, int(round(img_dh)))
            win_x = work_x + (work_w - win_w) // 2
            win_y = work_y + (work_h - win_h) // 2

        # Clamp the window into the work area (the title bar above the client
        # area must remain on screen).
        win_x = max(work_x, min(win_x, work_x + work_w - win_w))
        win_y = max(work_y + TITLE_BAR_H, min(win_y, work_y + work_h - win_h))

        try:
            rl.ClearWindowState(rl.FLAG_WINDOW_UNDECORATED)
            rl.SetWindowState(rl.FLAG_WINDOW_RESIZABLE)
            rl.SetWindowMinSize(WINDOWED_MIN, WINDOWED_MIN)
        except Exception:
            pass
        try:
            rl.SetWindowSize(win_w, win_h)
            rl.SetWindowPosition(win_x, win_y)
        except Exception:
            pass

        state.windowed_mode = True
        # Use the size we just set, not GetScreenWidth() — raylib still reports
        # the old size on this frame, which would render one wrong frame (a
        # visible flicker) before settling.
        state.screenW, state.screenH = win_w, win_h
        _post_toggle_settle.update(active=True, w=win_w, h=win_h, n=0)
        # Same scale; image centered within the (possibly larger) window.
        if ti:
            state.view = ViewParams(
                scale=new_scale,
                offx=(state.screenW - ti.w * new_scale) / 2.0,
                offy=(state.screenH - ti.h * new_scale) / 2.0,
            )
            state.last_fit_view = compute_fit_view(state, FIT_DEFAULT_SCALE)

        state.hwnd = get_window_handle_from_raylib()
        set_titlebar_dark(state.hwnd)
        win_set_blur(state.hwnd, True)
        log(f"[WINDOW] Windowed: {win_w}x{win_h} scale={new_scale:.3f} "
            f"fits={bool(ti) and fits}")
    else:
        # ── Windowed → fullscreen ───────────────────────────────────────────
        # Capture the image's absolute screen position first so it stays put:
        # scale and position are preserved, the screen just opens up around it.
        try:
            wp = rl.GetWindowPosition()
            cur_win_x, cur_win_y = float(wp.x), float(wp.y)
        except Exception:
            cur_win_x = float(state.window.fullscreen_x)
            cur_win_y = float(state.window.fullscreen_y)
        cur_scale = state.view.scale
        img_sx = cur_win_x + state.view.offx
        img_sy = cur_win_y + state.view.offy

        try:
            rl.ClearWindowState(rl.FLAG_WINDOW_RESIZABLE)
        except Exception:
            pass
        flags = _fullscreen_window_flags()
        try:
            rl.SetWindowState(flags)
        except Exception:
            pass

        current_work_x, current_work_y, current_work_w, current_work_h = get_work_area()
        work_x = state.window.fullscreen_x
        work_y = state.window.fullscreen_y
        work_w = state.window.fullscreen_w
        work_h = state.window.fullscreen_h
        if (work_w == 0 or work_h == 0 or
                work_w != current_work_w or work_h != current_work_h or
                work_x != current_work_x or work_y != current_work_y):
            work_x, work_y = current_work_x, current_work_y
            work_w, work_h = current_work_w, current_work_h

        try:
            rl.SetWindowSize(work_w, work_h)
            rl.SetWindowPosition(work_x, work_y)
        except Exception:
            pass

        state.windowed_mode = False
        # Use the size we just set, not GetScreenWidth() (still stale this frame).
        state.screenW, state.screenH = work_w, work_h
        _post_toggle_settle.update(active=True, w=work_w, h=work_h, n=0)
        # Keep scale and on-screen position (fullscreen surface origin == work-area origin).
        if ti:
            nv = ViewParams(scale=cur_scale, offx=img_sx - work_x, offy=img_sy - work_y)
            state.view = clamp_pan(nv, ti, state.screenW, state.screenH)
            state.last_fit_view = compute_fit_view(state, FIT_DEFAULT_SCALE)

        state.hwnd = get_window_handle_from_raylib()
        set_titlebar_dark(state.hwnd)
        win_set_blur(state.hwnd, True)
        log(f"[WINDOW] Fullscreen: {work_w}x{work_h} scale={cur_scale:.3f}")


def unload_texture_deferred(state: AppState, ti: Optional[TextureInfo]):
    if _LARGE_TEXTURE_CACHE.contains_texture(ti):
        log(f"[FULL_CACHE][KEEP] {os.path.basename(ti.path)}")
        return
    _TEXTURE_MANAGER.defer_unload(state, ti)


def _same_texture(left: Optional[TextureInfo], right: Optional[TextureInfo]) -> bool:
    if not left or not right:
        return False
    left_id = getattr(left.tex, "id", 0)
    return left_id > 0 and left_id == getattr(right.tex, "id", 0)


def _is_texture_active(state: AppState, ti: Optional[TextureInfo]) -> bool:
    if not ti:
        return False
    for active in (
        state.cache.curr,
        state.cache.prev,
        state.cache.next,
        state.waiting_prev_snapshot,
        state.switch_anim_prev_tex,
    ):
        if _same_texture(active, ti):
            return True
    return False


def _active_texture_ids(state: Optional[AppState]) -> set[int]:
    if state is None:
        return set()
    active_ids = set()
    for texture in (
        state.cache.curr,
        state.cache.prev,
        state.cache.next,
        state.waiting_prev_snapshot,
        state.switch_anim_prev_tex,
    ):
        if texture and getattr(texture, "tex", None):
            tex_id = getattr(texture.tex, "id", 0)
            if tex_id:
                active_ids.add(tex_id)
    return active_ids


def drop_large_cached_path(state: AppState, path: str) -> None:
    cached = _LARGE_TEXTURE_CACHE.remove(path)
    if cached and not _is_texture_active(state, cached):
        _TEXTURE_MANAGER.defer_unload(state, cached)


def drop_cached_path(state: AppState, path: str) -> None:
    drop_large_cached_path(state, path)
    _ANIMATED_CONTENT_CACHE.remove(path)


def process_deferred_unloads(state: AppState):
    _TEXTURE_MANAGER.process_deferred_unloads(state)


def compute_fit_view(state, frac):
    """Compute fit view for current image using state dimensions."""
    ti = state.cache.curr
    if not ti:
        return ViewParams()
    return compute_fit_view_pure(ti.w, ti.h, state.screenW, state.screenH, frac)


def clamp_pan(view: ViewParams, img: TextureInfo, screenW: int, screenH: int) -> ViewParams:
    """Wrapper for clamp_pan_pure that accepts TextureInfo."""
    return clamp_pan_pure(view, img.w, img.h, screenW, screenH)


def start_zoom_animation(state: AppState, target_view: ViewParams):
    _ZOOM_ANIMATION.start(state, target_view)


def update_zoom_animation(state: AppState):
    _ZOOM_ANIMATION.update(state, ANIM_ZOOM_MS)


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
    blur_wanted = mode["blur"] and bool(getattr(cfg, "BLUR_ENABLED", True))

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
    # Round destination coordinates to prevent subpixel rendering artifacts (1px line at edges)
    dst_x = round(v.offx)
    dst_y = round(v.offy)
    dst_w = round(ti.w * v.scale)
    dst_h = round(ti.h * v.scale)
    rl.DrawTexturePro(ti.tex, RL_Rect(0, 0, ti.w, ti.h), RL_Rect(dst_x, dst_y, dst_w, dst_h),
                      RL_V2(0, 0), 0.0, tint)


def draw_loading_indicator(state: AppState):
    if not state.loading_current and not state.transforming:
        return

    rl.DrawRectangle(0, 0, state.screenW, state.screenH, RL_Color(0, 0, 0, 120))

    cx = state.screenW // 2
    cy = state.screenH // 2
    radius = 50
    thickness = 6

    t = now() * 2.5
    angle = (t * 360.0) % 360.0

    rl.DrawRing(RL_V2(cx, cy), radius - thickness, radius, angle, angle + 90, 32, RL_Color(255, 255, 255, 220))

    from imagura.i18n import tr
    text = tr("misc.loading")
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

        dur = ANIM_OPEN_MS / 1000.0
        t = 1.0 if dur <= 0.0 else (now() - state.open_anim_t0) / dur
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
        from_view = state.anim.open_from_view
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
        dur = state.switch_anim_duration_ms / 1000.0
        t = 1.0 if dur <= 0.0 else (now() - state.switch_anim_t0) / dur
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
    # In windowed mode, system window buttons are used instead
    if state.windowed_mode:
        state.close_btn_alpha = 0.0
        return

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

    dt = rl.GetFrameTime()
    fade_speed = min(1.0, 18.0 * dt)
    diff = target_alpha - state.close_btn_alpha
    state.close_btn_alpha += diff * fade_speed


def draw_close_button(state: AppState):
    # In windowed mode, system window buttons are used instead
    if state.windowed_mode:
        return

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
    # In windowed mode, system window buttons are used instead
    if state.windowed_mode:
        return False

    if not rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
        return False
    mouse = rl.GetMousePosition()
    return is_point_in_close_button(state, mouse.x, mouse.y)


def trigger_scale_overlay(state: AppState, mode=""):
    """Trigger scale overlay. mode: '' for plain %, 'real'/'fit'/'custom' for labeled."""
    _SCALE_OVERLAY.trigger(state, mode)


def update_scale_overlay(state: AppState):
    """Fade out scale overlay after 1s delay."""
    _SCALE_OVERLAY.update(state, rl.GetFrameTime())


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
    dt = rl.GetFrameTime()
    zoom_threshold = state.last_fit_view.scale * 1.1
    is_significantly_zoomed = state.view.scale > zoom_threshold

    fade_speed = min(1.0, 18.0 * dt)

    if not is_significantly_zoomed:
        state.nav_left_alpha = max(0.0, state.nav_left_alpha - fade_speed)
        state.nav_right_alpha = max(0.0, state.nav_right_alpha - fade_speed)
        return

    cy = state.screenH // 2
    cx_left = 60
    cx_right = state.screenW - 60
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
# Settings modal: schema + persistence live in imagura.settings_persistence;
# rendering + input live in imagura.ui.settings_modal. The functions below are
# thin shims kept here so the module-level test contract holds: save_config_value
# and apply_saved_settings must remain importable as imagura2 attributes AND must
# mirror applied values into imagura2's own module globals.
# ═══════════════════════════════════════════════════════════════════════════════


def apply_runtime_config_change(config_key: str, state: Optional[AppState]) -> None:
    if config_key in {"FULL_IMAGE_CACHE_MAX_MB", "FULL_IMAGE_CACHE_MAX_ITEMS"}:
        protected_ids = _active_texture_ids(state) if state is not None else set()
        evicted = _LARGE_TEXTURE_CACHE.configure(
            max_mb=cfg.FULL_IMAGE_CACHE_MAX_MB,
            max_items=cfg.FULL_IMAGE_CACHE_MAX_ITEMS,
            protected_texture_ids=protected_ids,
        )
        if state is not None:
            for texture in evicted:
                _TEXTURE_MANAGER.defer_unload(state, texture)
    elif config_key in {"ANIMATED_CONTENT_CACHE_MAX_MB", "ANIMATED_CONTENT_CACHE_MAX_ITEMS"}:
        _ANIMATED_CONTENT_CACHE.configure(
            max_mb=cfg.ANIMATED_CONTENT_CACHE_MAX_MB,
            max_items=cfg.ANIMATED_CONTENT_CACHE_MAX_ITEMS,
        )
    elif config_key == "BLUR_ENABLED":
        # Force apply_bg_mode to re-evaluate blur on the next frame.
        global _current_blur_enabled
        _current_blur_enabled = None


def _mirror_config_global(config_key: str) -> None:
    """Mirror a config value into imagura2's own module globals (test contract)."""
    if config_key in globals():
        globals()[config_key] = getattr(cfg, config_key)


def save_config_value(config_key: str, value, val_type: type, state: Optional[AppState] = None) -> bool:
    """Save a single config value, then mirror it into imagura2's module globals.

    Delegates persistence to settings_persistence.save_config_value_impl and runs
    apply_runtime_config_change (cache reconfig) after a successful save, matching
    the original ordering (set config -> persist -> reconfigure caches).
    """
    ok = _save_config_value_impl(
        config_key, value, val_type, state, on_applied=apply_runtime_config_change
    )
    if ok:
        _mirror_config_global(config_key)
    return ok


def apply_saved_settings(state: Optional[AppState] = None) -> None:
    """Load persisted settings, then mirror applied values into imagura2 globals."""
    _apply_saved_settings_impl(state, on_applied=apply_runtime_config_change)
    for config_key in settings_definitions():
        _mirror_config_global(config_key)


def delete_current_image(state: AppState) -> bool:
    """
    Delete the current image to platform trash and navigate to next/prev.
    Returns True if successful.
    """
    if state.index >= len(state.current_dir_images):
        return False

    if len(state.current_dir_images) == 0:
        return False

    path = state.current_dir_images[state.index]
    old_index = state.index

    # First delete the file
    if not delete_to_trash(path):
        return False

    # Cleanup playback before unloading textures
    _ANIMATED_PLAYBACK.stop(state)
    drop_cached_path(state, path)

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
    drop_cached_path(state, path)

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


def invalidate_cached_path(state: AppState, path: str) -> None:
    """Drop stale textures/thumbs for a file changed outside the normal loader path."""
    drop_cached_path(state, path)

    for cache_attr in ("prev", "curr", "next"):
        ti = getattr(state.cache, cache_attr)
        if ti and ti.path == path:
            unload_texture_deferred(state, ti)
            setattr(state.cache, cache_attr, None)

    if path in state.thumb_cache:
        bt = state.thumb_cache.pop(path)
        if bt.texture:
            try:
                rl.UnloadTexture(bt.texture)
            except Exception:
                pass

    if path not in state.thumb_queue:
        state.thumb_queue.append(path)


def run_transform_async(state: AppState, transform_func, path: str, **kwargs):
    """Run an image transform in a background thread with spinner."""
    if state.transforming:
        return
    state.transforming = True

    def worker():
        success = False
        try:
            success = transform_func(path, **kwargs)
        except Exception as e:
            log(f"[TRANSFORM] Error: {e}")

        def on_done(st, transformed_path=path, ok=success):
            st.transforming = False
            if ok:
                current_path = None
                if st.index < len(st.current_dir_images):
                    current_path = st.current_dir_images[st.index]
                if current_path == transformed_path:
                    reload_current_image(st)
                else:
                    invalidate_cached_path(st, transformed_path)

        state.async_loader.push_ui_event(on_done, (state,))

    t = Thread(target=worker, daemon=True)
    t.start()


def schedule_thumbs(state: AppState, around_index: int):
    _THUMBNAIL_SERVICE.schedule_around(state, around_index)


def get_gallery_height(screen_h: int) -> int:
    """Calculate gallery height with minimum constraint."""
    return _THUMBNAIL_SERVICE.gallery_height(screen_h)


def process_thumb_queue(state: AppState):
    _THUMBNAIL_SERVICE.process_queue(state)


def update_gallery_scroll(state: AppState):
    _GALLERY_BEHAVIOR.update_scroll(state, rl.GetFrameTime())


def reconcile_gallery_target(state: AppState):
    _GALLERY_BEHAVIOR.reconcile_target(
        state,
        now(),
        lambda idx, animate, duration_ms: switch_to(state, idx, animate=animate, anim_duration_ms=duration_ms),
    )


def update_gallery_visibility_and_slide(state: AppState):
    mouse = rl.GetMousePosition()
    _GALLERY_BEHAVIOR.update_visibility_and_slide(
        state,
        mouse.y,
        rl.GetFrameTime(),
        get_gallery_height(state.screenH),
        force_visible=state.gallery.sort_menu_open,
    )


def is_mouse_over_gallery(state: AppState) -> bool:
    mouse = rl.GetMousePosition()
    return _GALLERY_BEHAVIOR.is_mouse_over(state, mouse.y, get_gallery_height(state.screenH))


def render_gallery(state: AppState):
    mouse = rl.GetMousePosition()
    left_clicked = rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT)
    gallery_height = get_gallery_height(state.screenH)
    sort_result = handle_gallery_sort_input(state, mouse.x, mouse.y, left_clicked, gallery_height)
    if sort_result.changed:
        apply_gallery_sort(state)

    clicked_index = _GALLERY_RENDERER.render(
        state,
        mouse.x,
        mouse.y,
        left_clicked and not sort_result.consumed_click,
        gallery_height,
    )
    draw_gallery_sort_control(state, gallery_height)
    return clicked_index


def apply_gallery_sort(state: AppState) -> None:
    current_path = state.current_dir_images[state.index] if state.index < len(state.current_dir_images) else None
    sorted_paths, new_index = resort_preserving_current(
        state.current_dir_images,
        current_path,
        state.gallery.sort_key,
        state.gallery.sort_desc,
    )
    state.current_dir_images = sorted_paths
    state.index = new_index
    state.gallery_target_index = None
    state.gallery_center_index = float(new_index)
    for ti in (state.cache.prev, state.cache.next):
        unload_texture_deferred(state, ti)
    state.cache.prev = None
    state.cache.next = None
    state.thumb_queue.clear()
    schedule_thumbs(state, new_index)


def sorted_supported_files_for_state(state: AppState, dirpath: str) -> list[str]:
    return sort_image_paths(list_supported_files(dirpath), state.gallery.sort_key, state.gallery.sort_desc)


def scan_start_images(state: AppState, start_path: Optional[str]) -> tuple[str, list[str], int]:
    """Resolve the startup directory, sorted images, and initial index."""
    if start_path and os.path.isdir(start_path):
        dirpath = start_path
        images = sorted_supported_files_for_state(state, dirpath)
        return dirpath, images, 0

    dirpath = os.path.dirname(start_path) if start_path else os.getcwd()
    images = sorted_supported_files_for_state(state, dirpath)
    if not start_path:
        return dirpath, images, 0

    try:
        start_index = images.index(os.path.join(dirpath, os.path.basename(start_path)))
    except ValueError:
        start_index = 0
    return dirpath, images, start_index


def prompt_for_start_image(state: AppState, initial_dir: str) -> Optional[str]:
    selected = open_image_file_dialog(state.hwnd, initial_dir)
    if selected and os.path.exists(selected):
        log(f"[DIALOG] Selected start image: {selected}")
        return selected
    log("[DIALOG] No image selected")
    return None


def _no_images_button_rects(state: AppState) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    button_w = 170
    button_h = 40
    gap = 14
    total_w = button_w * 2 + gap
    x = (state.screenW - total_w) // 2
    y = state.screenH // 2 + 64
    return (x, y, button_w, button_h), (x + button_w + gap, y, button_w, button_h)


def _point_in_rect(x: float, y: float, rect: tuple[int, int, int, int]) -> bool:
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def _measure_ui_text(text: str, font_size: int) -> int:
    try:
        return int(rl.MeasureText(text, font_size))
    except TypeError:
        return int(rl.MeasureText(text.encode("utf-8"), font_size))


def _draw_no_images_button(rect: tuple[int, int, int, int], label: str, hovered: bool) -> None:
    x, y, w, h = rect
    bg = RL_Color(255, 255, 255, 58 if hovered else 38)
    border = RL_Color(255, 255, 255, 210 if hovered else 150)
    text_color = RL_Color(255, 255, 255, 235)
    rl.DrawRectangle(x, y, w, h, bg)
    rl.DrawRectangleLines(x, y, w, h, border)
    font_size = 18
    tw = _measure_ui_text(label, font_size)
    RL_DrawText(label, x + (w - tw) // 2, y + (h - font_size) // 2, font_size, text_color)


def draw_no_images_screen(state: AppState, dirpath: str, mouse_x: float, mouse_y: float) -> None:
    from imagura.i18n import tr
    title = tr("empty.no_images")
    path_text = dirpath
    if len(path_text) > 96:
        path_text = f"{path_text[:42]}...{path_text[-51:]}"
    hint = tr("empty.hint")

    title_size = 30
    path_size = 18
    hint_size = 17
    center_x = state.screenW // 2
    base_y = state.screenH // 2 - 64

    title_w = _measure_ui_text(title, title_size)
    path_w = _measure_ui_text(path_text, path_size)
    hint_w = _measure_ui_text(hint, hint_size)

    RL_DrawText(title, center_x - title_w // 2, base_y, title_size, RL_Color(255, 255, 255, 230))
    RL_DrawText(path_text, center_x - path_w // 2, base_y + 44, path_size, RL_Color(210, 210, 210, 210))
    RL_DrawText(hint, center_x - hint_w // 2, base_y + 76, hint_size, RL_Color(190, 190, 190, 190))

    open_rect, exit_rect = _no_images_button_rects(state)
    _draw_no_images_button(open_rect, tr("empty.open"), _point_in_rect(mouse_x, mouse_y, open_rect))
    _draw_no_images_button(exit_rect, tr("empty.exit"), _point_in_rect(mouse_x, mouse_y, exit_rect))


def run_no_images_screen(state: AppState, dirpath: str) -> Optional[str]:
    """Show an interactive empty-state screen.

    Returns a selected image path when the user chooses one, or None when the
    window should close.
    """
    while not rl.WindowShouldClose():
        update_close_button_alpha(state)
        update_toolbar_alpha_ui(state)

        settings_active = state.ui.settings.visible
        if settings_active:
            handle_settings_input(state)

        mouse = rl.GetMousePosition()
        open_rect, exit_rect = _no_images_button_rects(state)
        left_clicked = rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT)

        toolbar_clicked_button = update_toolbar_input(state, mouse, settings_active)
        toolbar_consumed_click = toolbar_clicked_button is not None
        if toolbar_clicked_button is not None:
            if toolbar_clicked_button.id == ToolbarButtonId.SETTINGS:
                state.ui.settings.show()
            else:
                log(f"[TOOLBAR] Ignored without current image: {toolbar_clicked_button.tooltip}")

        if not settings_active:
            if rl.IsKeyPressed(KEY_CLOSE):
                return None
            if not toolbar_consumed_click and check_close_button_click(state):
                return None
            if left_clicked and not toolbar_consumed_click:
                if _point_in_rect(mouse.x, mouse.y, open_rect):
                    selected = prompt_for_start_image(state, dirpath)
                    if selected:
                        return selected
                elif _point_in_rect(mouse.x, mouse.y, exit_rect):
                    return None

        rl.BeginDrawing()
        apply_bg_mode(state)
        draw_no_images_screen(state, dirpath, mouse.x, mouse.y)
        draw_close_button(state)
        draw_toolbar_ui(state)
        draw_settings_window(state)
        rl.EndDrawing()
        increment_frame()

    return None


def preload_neighbors(state: AppState, new_index: int, skip_neighbors: bool = False):
    _CURRENT_AND_NEIGHBOR_LOADER.preload(state, new_index, skip_neighbors)


def switch_to(state: AppState, idx: int, animate: bool = True, anim_duration_ms: int = ANIM_SWITCH_KEYS_MS):
    if idx == state.index:
        return

    direction = 1 if idx > state.index else -1

    if state.switch_anim_active:
        if len(state.switch_queue) < 20:
            state.switch_queue.append((direction, anim_duration_ms))
        return

    # Cleanup playback for the file we're leaving
    _ANIMATED_PLAYBACK.stop(state)

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

    if len(state.switch_queue) >= RAPID_NAV_SKIP_THRESHOLD:
        net = sum(d for d, _ in state.switch_queue)
        state.switch_queue.clear()
        n = len(state.current_dir_images)
        target_idx = max(0, min(n - 1, state.index + net))
        if target_idx != state.index:
            switch_to(state, target_idx, animate=False)
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


_VIEW_MEMORY_LIMIT = 500

def save_view_for_path(state: AppState, path: str, view: ViewParams):
    ti = state.cache.curr
    if not ti or not path:
        return

    v = sanitize_view(state, view, ti)
    state.view_memory[path] = ViewParams(v.scale, v.offx, v.offy)
    while len(state.view_memory) > _VIEW_MEMORY_LIMIT:
        oldest = next(iter(state.view_memory))
        del state.view_memory[oldest]
    while len(state.user_zoom_memory) > _VIEW_MEMORY_LIMIT:
        oldest = next(iter(state.user_zoom_memory))
        del state.user_zoom_memory[oldest]

    if abs(view.offx - v.offx) > 1.0 or abs(view.offy - v.offy) > 1.0:
        log(f"[SAVE_VIEW] {os.path.basename(path)}: CORRECTED scale={v.scale:.3f} off=({v.offx:.1f},{v.offy:.1f}) [was ({view.offx:.1f},{view.offy:.1f})]")
    else:
        log(f"[SAVE_VIEW] {os.path.basename(path)}: scale={v.scale:.3f} off=({v.offx:.1f},{v.offy:.1f})")


def start_toggle_zoom_animation(state: AppState):
    """Start non-blocking toggle zoom animation (F key / double-click)."""
    _TOGGLE_ZOOM_ANIMATION.start(state, trigger_scale_overlay)


def update_toggle_zoom_animation(state: AppState):
    """Update toggle zoom animation each frame."""
    _TOGGLE_ZOOM_ANIMATION.update(state, ANIM_TOGGLE_ZOOM_MS, save_view_for_path)


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


class AppController:
    def __init__(self):
        self.state = AppState()
        self.font_loaded = False
        self.blur_enabled = False
        self.first_render_done = False

    def setup(self, start_path) -> bool:
        state = self.state

        try:
            log("[INIT] Initializing window")
            init_window_and_blur(state)
            log("[INIT] Window initialized successfully")
        except Exception as e:
            log(f"[INIT][CRITICAL] Failed to initialize window: {e!r}")
            log(f"[INIT][CRITICAL] Traceback:\n{traceback.format_exc()}")
            return False

        dirpath, images, start_index = scan_start_images(state, start_path)

        state.current_dir_images = images

        log(f"[DIR] Found {len(images)} images in {dirpath}")

        if not images and not start_path:
            selected_path = prompt_for_start_image(state, dirpath)
            if selected_path:
                start_path = selected_path
                dirpath, images, start_index = scan_start_images(state, start_path)
                state.current_dir_images = images
                log(f"[DIR] Found {len(images)} images in {dirpath}")

        if not images:
            log("[DIR] No images found, showing interactive empty screen")
            while not images:
                selected_path = run_no_images_screen(state, dirpath)
                if not selected_path:
                    break
                start_path = selected_path
                dirpath, images, start_index = scan_start_images(state, start_path)
                state.current_dir_images = images
                log(f"[DIR] Found {len(images)} images in {dirpath}")

            if not images:
                try:
                    rl.CloseWindow()
                except Exception:
                    pass
                return False

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

        return True

    def _poll_async(self):
        state = self.state
        if state.open_anim_active:
            state.async_loader.poll_ui_events(max_events=2)
        else:
            state.async_loader.poll_ui_events(max_events=100)

    def _update(self):
        state = self.state
        if not self.font_loaded and state.cache.curr and self.first_render_done and not state.open_anim_active:
            state.unicode_font = load_unicode_font()
            self.font_loaded = True
            log("[INIT] Font loaded after first render")

        if not self.blur_enabled and state.cache.curr and self.first_render_done and not state.open_anim_active:
            # Initial blur setup is now handled by apply_bg_mode via _current_blur_enabled
            self.blur_enabled = True
            log("[INIT] Background mode active after first render")

        if state.cache.curr and state.open_anim_active and state.view.scale == 0.5:
            state.view = compute_fit_view(state, FIT_OPEN_SCALE)
            log(f"[MAIN] Set FIT_OPEN view for animation")

        process_deferred_unloads(state)

        # Advance animated content playback
        _ANIMATED_PLAYBACK.advance(
            state,
            rl.GetFrameTime() * 1000.0,
            lambda old_ti: unload_texture_deferred(state, old_ti),
        )

        update_zoom_animation(state)
        update_toggle_zoom_animation(state)
        process_switch_queue(state)
        apply_bg_opacity_anim(state)
        update_close_button_alpha(state)
        update_nav_buttons_fade(state)
        update_scale_overlay(state)
        update_gallery_visibility_and_slide(state)
        update_gallery_scroll(state)
        reconcile_gallery_target(state)
        update_toolbar_alpha_ui(state)

        if not state.open_anim_active:
            process_thumb_queue(state)

    def run(self):
        state = self.state

        # Key repeat state for navigation
        nav_key_state = {
            'next': {'pressed_time': 0.0, 'last_repeat': 0.0},
            'prev': {'pressed_time': 0.0, 'last_repeat': 0.0},
        }

        try:
            while True:
                self._poll_async()
                self._update()

                should_close = rl.WindowShouldClose()
                if should_close:
                    break

                # Handle window resize in windowed mode
                # Only update screen dimensions - view will adapt automatically
                if state.windowed_mode:
                    new_w = rl.GetScreenWidth()
                    new_h = rl.GetScreenHeight()
                    if new_w != state.screenW or new_h != state.screenH:
                        state.screenW = new_w
                        state.screenH = new_h
                        # Keep the current zoom on resize (don't snap to fit);
                        # refresh the fit reference and clamp the view into the
                        # new window bounds.
                        if state.cache.curr:
                            state.last_fit_view = compute_fit_view(state, FIT_DEFAULT_SCALE)
                            state.view = clamp_pan(state.view, state.cache.curr, new_w, new_h)

                # Handle settings window input first (blocks other input when visible)
                settings_active = state.ui.settings.visible
                if settings_active:
                    handle_settings_input(state)

                rl.BeginDrawing()
                apply_bg_mode(state)

                mouse = rl.GetMousePosition()

                # ─── Context Menu Input ─────────────────────────────────────────────
                context_menu_result = handle_context_menu_input(state, mouse, settings_active)
                menu_consumed_click = context_menu_result.consumed_click
                if context_menu_result.clicked_item is not None:
                    item = context_menu_result.clicked_item
                    log(f"[MENU] Clicked: {item.label}")
                    if item.id == MenuItemId.COPY and state.index < len(state.current_dir_images):
                        copy_image_to_clipboard(state.current_dir_images[state.index])

                # ─── Toolbar Input ──────────────────────────────────────────────────
                toolbar_clicked_button = update_toolbar_input(state, mouse, menu_consumed_click)
                toolbar_consumed_click = toolbar_clicked_button is not None
                if toolbar_clicked_button is not None:
                    log(f"[TOOLBAR] Clicked: {toolbar_clicked_button.tooltip}")

                    if toolbar_clicked_button.id == ToolbarButtonId.SETTINGS:
                        state.ui.settings.show()
                    elif state.index < len(state.current_dir_images):
                        path = state.current_dir_images[state.index]

                        if toolbar_clicked_button.id == ToolbarButtonId.ROTATE_CW:
                            run_transform_async(state, rotate_image_file, path, clockwise=True)
                        elif toolbar_clicked_button.id == ToolbarButtonId.ROTATE_CCW:
                            run_transform_async(state, rotate_image_file, path, clockwise=False)
                        elif toolbar_clicked_button.id == ToolbarButtonId.FLIP_H:
                            run_transform_async(state, flip_image_file, path, horizontal=True)

                # ─── Regular Input ──────────────────────────────────────────────────
                # Track if any UI element consumed the click
                input_consumed = menu_consumed_click or toolbar_consumed_click or settings_active

                if not input_consumed and check_close_button_click(state):
                    break

                # Only mark activity on actual user input (mouse move, key/button press, wheel)
                _mouse_delta = rl.GetMouseDelta()
                if (_mouse_delta.x != 0 or _mouse_delta.y != 0
                        or rl.GetMouseWheelMove() != 0
                        or rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT)
                        or rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_RIGHT)
                        or rl.GetKeyPressed() != 0):
                    state.idle_detector.mark_activity()

                # Block all keyboard input when settings menu is open
                if not settings_active:
                    if rl.IsKeyPressed(KEY_TOGGLE_HUD):
                        state.show_hud = not state.show_hud

                    if rl.IsKeyPressed(KEY_TOGGLE_FILENAME):
                        state.show_filename = not state.show_filename

                    if rl.IsKeyPressed(KEY_CYCLE_BG):
                        state.bg_mode_index = (state.bg_mode_index + 1) % len(BG_MODES)
                        state.bg_target_opacity = BG_MODES[state.bg_mode_index]["opacity"]

                # DEL key - delete image to recycle bin (NEVER when settings active)
                if rl.IsKeyPressed(KEY_DELETE_IMAGE) and not state.open_anim_active and not settings_active:
                    if delete_current_image(state):
                        if len(state.current_dir_images) == 0:
                            # No more images - close app
                            break
                        rl.EndDrawing()
                        increment_frame()
                        continue

                if state.cache.curr and not state.open_anim_active and not state.toggle_zoom_active and not settings_active:
                    if rl.IsKeyDown(KEY_ZOOM_IN) or rl.IsKeyDown(KEY_ZOOM_IN_ALT):
                        apply_manual_zoom(
                            state,
                            1.0 + ZOOM_STEP_KEYS,
                            (int(mouse.x), int(mouse.y)),
                            MAX_ZOOM,
                            start_zoom_animation,
                            trigger_scale_overlay,
                            save_view_for_path,
                        )

                    if rl.IsKeyDown(KEY_ZOOM_OUT) or rl.IsKeyDown(KEY_ZOOM_OUT_ALT):
                        apply_manual_zoom(
                            state,
                            1.0 - ZOOM_STEP_KEYS,
                            (int(mouse.x), int(mouse.y)),
                            MAX_ZOOM,
                            start_zoom_animation,
                            trigger_scale_overlay,
                            save_view_for_path,
                        )

                wheel = rl.GetMouseWheelMove()
                # Mouse wheel zoom - blocked when settings menu is open (settings has its own scroll)
                if wheel != 0.0 and state.cache.curr and not state.open_anim_active and not state.toggle_zoom_active and not settings_active:
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
                        apply_manual_zoom(
                            state,
                            1.0 + wheel * ZOOM_STEP_WHEEL,
                            (int(mouse.x), int(mouse.y)),
                            MAX_ZOOM,
                            start_zoom_animation,
                            trigger_scale_overlay,
                            save_view_for_path,
                        )

                # Double-click zone: everywhere except navigation edges
                # Use adaptive edge zones: at least NAV_EDGE_MIN_PX or 10% of screen
                edge_zone = max(state.screenW * 0.10, NAV_EDGE_MIN_PX)
                not_on_edge = (mouse.x > edge_zone and
                              mouse.x < state.screenW - edge_zone)

                if not settings_active:
                    if rl.IsKeyPressed(KEY_TOGGLE_ZOOM) and not state.toggle_zoom_active:
                        start_toggle_zoom_animation(state)

                    # Toggle window mode (F key)
                    if rl.IsKeyPressed(KEY_TOGGLE_WINDOW):
                        toggle_window_mode(state)

                # Always track clicks for double-click detection, even during animation
                if not_on_edge and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT) and not input_consumed:
                    is_double = detect_double_click(state, int(mouse.x), int(mouse.y))
                    if is_double and not state.toggle_zoom_active:
                        start_toggle_zoom_animation(state)

                if state.cache.curr and not state.open_anim_active and not state.toggle_zoom_active and not settings_active:
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

                if not state.open_anim_active and not settings_active:
                    # Use adaptive edge zones for navigation
                    nav_edge = max(state.screenW * 0.10, NAV_EDGE_MIN_PX)
                    edge_left = (mouse.x <= nav_edge)
                    edge_right = (mouse.x >= state.screenW - nav_edge)

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

                    gh = get_gallery_height(state.screenH)
                    yv = state.screenH - gh
                    gallery_is_visible = state.gallery_y < state.screenH
                    in_gallery_panel = gallery_is_visible and (yv <= mouse.y <= state.screenH)

                    if not is_significantly_zoomed and not in_gallery_panel and not input_consumed:
                        if edge_right and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                            if state.index + 1 < len(state.current_dir_images):
                                switch_to(state, state.index + 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)
                        if edge_left and rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
                            if state.index - 1 >= 0:
                                switch_to(state, state.index - 1, animate=True, anim_duration_ms=ANIM_SWITCH_KEYS_MS)

                _settle = _post_toggle_settle
                if _settle["active"]:
                    _settle["n"] += 1
                    # Re-assert the dark title bar: DWM often applies the dark
                    # caption a few frames late (the "only after F twice" issue).
                    set_titlebar_dark(state.hwnd)
                    size_ok = (rl.GetScreenWidth() == _settle["w"] and
                               rl.GetScreenHeight() == _settle["h"])
                    if (size_ok and _settle["n"] >= 2) or _settle["n"] > 15:
                        _settle["active"] = False
                if not _settle["active"]:
                    render_image(state)

                if state.cache.curr and not self.first_render_done:
                    self.first_render_done = True
                    log("[RENDER] First render completed")

                draw_nav_buttons(state)
                draw_close_button(state)
                draw_filename_overlay(state)
                draw_scale_overlay(state)

                try:
                    clicked_gallery_idx = render_gallery(state)
                    if clicked_gallery_idx is not None:
                        switch_to(state, clicked_gallery_idx)
                except Exception as e:
                    log(f"[DRAW][GALLERY][EXC] {e!r}\n{traceback.format_exc()}")

                draw_loading_indicator(state)

                draw_hud(state)

                # Draw toolbar, context menu and settings (on top of everything)
                draw_toolbar_ui(state)
                draw_context_menu_ui(state)
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
            self._shutdown()

    def _shutdown(self):
        state = self.state
        log("[CLEANUP] Starting cleanup")
        if state.async_loader:
            log("[CLEANUP] Shutting down async loader")
            state.async_loader.shutdown()
        if state.playback:
            log("[CLEANUP] Cleaning up playback")
            _ANIMATED_PLAYBACK.stop(state)
        log("[CLEANUP] Processing deferred unloads")
        process_deferred_unloads(state)
        log("[CLEANUP] Unloading thumbnails")
        for bt in list(state.thumb_cache.values()):
            try:
                if bt.texture:
                    rl.UnloadTexture(bt.texture)
            except Exception:
                pass
        log("[CLEANUP] Unloading large texture cache")
        for ti in _LARGE_TEXTURE_CACHE.clear():
            if not _is_texture_active(state, ti):
                _TEXTURE_MANAGER.unload_texture(ti.tex)
        log("[CLEANUP] Clearing animated content cache")
        _ANIMATED_CONTENT_CACHE.clear()
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


def main():
    log("[MAIN] Starting application")
    from imagura.i18n import load_persisted_language
    load_persisted_language()
    apply_saved_settings()

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

    controller = AppController()
    if not controller.setup(start_path):
        return
    controller.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"[FATAL] Fatal error: {e!r}")
        log(f"[FATAL] Traceback:\n{traceback.format_exc()}")
        input("Press Enter to exit...")
        sys.exit(1)
