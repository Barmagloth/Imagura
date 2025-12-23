"""Composite AppState - combines all sub-states with backward compatibility."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Deque, Tuple, Any
from collections import OrderedDict, deque

from .window import WindowState
from .images import ImageListState
from .view import ViewState
from .gallery import GalleryState
from .ui import UIState
from .input import InputState
from .animation import AnimationState
from .loading import LoadingState
from ..types import ViewParams, TextureInfo, ImageCache, BitmapThumb
from ..config import BG_MODES, ANIM_SWITCH_KEYS_MS


@dataclass
class AppState:
    """
    Composite application state with backward-compatible property accessors.

    New code should use sub-states directly:
        state.window.screen_w
        state.images.index
        state.view.is_zoomed

    Legacy code can use flat accessors:
        state.screenW
        state.index
        state.is_zoomed
    """
    # Sub-states (new architecture)
    window: WindowState = field(default_factory=WindowState)
    images: ImageListState = field(default_factory=ImageListState)
    view_state: ViewState = field(default_factory=ViewState)
    gallery: GalleryState = field(default_factory=GalleryState)
    ui: UIState = field(default_factory=UIState)
    input: InputState = field(default_factory=InputState)
    anim: AnimationState = field(default_factory=AnimationState)
    loading: LoadingState = field(default_factory=LoadingState)

    # ═══════════════════════════════════════════════════════════════════════
    # Backward-compatible properties - WindowState
    # ═══════════════════════════════════════════════════════════════════════

    @property
    def screenW(self) -> int:
        return self.window.screen_w

    @screenW.setter
    def screenW(self, value: int):
        self.window.screen_w = value

    @property
    def screenH(self) -> int:
        return self.window.screen_h

    @screenH.setter
    def screenH(self, value: int):
        self.window.screen_h = value

    @property
    def hwnd(self) -> Optional[int]:
        return self.window.hwnd

    @hwnd.setter
    def hwnd(self, value: Optional[int]):
        self.window.hwnd = value

    @property
    def unicode_font(self) -> Optional[Any]:
        return self.window.unicode_font

    @unicode_font.setter
    def unicode_font(self, value: Optional[Any]):
        self.window.unicode_font = value

    # ═══════════════════════════════════════════════════════════════════════
    # Backward-compatible properties - ImageListState
    # ═══════════════════════════════════════════════════════════════════════

    @property
    def current_dir_images(self) -> List[str]:
        return self.images.images

    @current_dir_images.setter
    def current_dir_images(self, value: List[str]):
        self.images.images = value

    @property
    def index(self) -> int:
        return self.images.index

    @index.setter
    def index(self, value: int):
        self.images.index = value

    @property
    def cache(self) -> ImageCache:
        return self.images.cache

    @cache.setter
    def cache(self, value: ImageCache):
        self.images.cache = value

    @property
    def thumb_cache(self) -> "OrderedDict[str, BitmapThumb]":
        return self.images.thumb_cache

    @thumb_cache.setter
    def thumb_cache(self, value: "OrderedDict[str, BitmapThumb]"):
        self.images.thumb_cache = value

    @property
    def thumb_queue(self) -> Deque[str]:
        return self.images.thumb_queue

    @thumb_queue.setter
    def thumb_queue(self, value: Deque[str]):
        self.images.thumb_queue = value

    @property
    def to_unload(self) -> List[Any]:
        return self.images.to_unload

    @to_unload.setter
    def to_unload(self, value: List[Any]):
        self.images.to_unload = value

    @property
    def view_memory(self) -> dict:
        return self.images.view_memory

    @view_memory.setter
    def view_memory(self, value: dict):
        self.images.view_memory = value

    @property
    def user_zoom_memory(self) -> dict:
        return self.images.user_zoom_memory

    @user_zoom_memory.setter
    def user_zoom_memory(self, value: dict):
        self.images.user_zoom_memory = value

    # ═══════════════════════════════════════════════════════════════════════
    # Backward-compatible properties - ViewState
    # ═══════════════════════════════════════════════════════════════════════

    @property
    def view(self) -> ViewParams:
        return self.view_state.view

    @view.setter
    def view(self, value: ViewParams):
        self.view_state.view = value

    @property
    def last_fit_view(self) -> ViewParams:
        return self.view_state.last_fit_view

    @last_fit_view.setter
    def last_fit_view(self, value: ViewParams):
        self.view_state.last_fit_view = value

    @property
    def zoom_state_cycle(self) -> int:
        return self.view_state.zoom_state_cycle

    @zoom_state_cycle.setter
    def zoom_state_cycle(self, value: int):
        self.view_state.zoom_state_cycle = value

    @property
    def is_zoomed(self) -> bool:
        return self.view_state.is_zoomed

    @is_zoomed.setter
    def is_zoomed(self, value: bool):
        self.view_state.is_zoomed = value

    # ═══════════════════════════════════════════════════════════════════════
    # Backward-compatible properties - GalleryState
    # ═══════════════════════════════════════════════════════════════════════

    @property
    def gallery_center_index(self) -> float:
        return self.gallery.center_index

    @gallery_center_index.setter
    def gallery_center_index(self, value: float):
        self.gallery.center_index = value

    @property
    def gallery_y(self) -> float:
        return self.gallery.y_position

    @gallery_y.setter
    def gallery_y(self, value: float):
        self.gallery.y_position = value

    @property
    def gallery_visible(self) -> bool:
        return self.gallery.visible

    @gallery_visible.setter
    def gallery_visible(self, value: bool):
        self.gallery.visible = value

    @property
    def gallery_target_index(self) -> Optional[int]:
        return self.gallery.target_index

    @gallery_target_index.setter
    def gallery_target_index(self, value: Optional[int]):
        self.gallery.target_index = value

    @property
    def gallery_last_wheel_time(self) -> float:
        return self.gallery.last_wheel_time

    @gallery_last_wheel_time.setter
    def gallery_last_wheel_time(self, value: float):
        self.gallery.last_wheel_time = value

    # ═══════════════════════════════════════════════════════════════════════
    # Backward-compatible properties - UIState
    # ═══════════════════════════════════════════════════════════════════════

    @property
    def show_hud(self) -> bool:
        return self.ui.show_hud

    @show_hud.setter
    def show_hud(self, value: bool):
        self.ui.show_hud = value

    @property
    def show_filename(self) -> bool:
        return self.ui.show_filename

    @show_filename.setter
    def show_filename(self, value: bool):
        self.ui.show_filename = value

    @property
    def nav_left_alpha(self) -> float:
        return self.ui.nav_left_alpha

    @nav_left_alpha.setter
    def nav_left_alpha(self, value: float):
        self.ui.nav_left_alpha = value

    @property
    def nav_right_alpha(self) -> float:
        return self.ui.nav_right_alpha

    @nav_right_alpha.setter
    def nav_right_alpha(self, value: float):
        self.ui.nav_right_alpha = value

    @property
    def close_btn_alpha(self) -> float:
        return self.ui.close_btn_alpha

    @close_btn_alpha.setter
    def close_btn_alpha(self, value: float):
        self.ui.close_btn_alpha = value

    @property
    def bg_mode_index(self) -> int:
        return self.ui.bg_mode_index

    @bg_mode_index.setter
    def bg_mode_index(self, value: int):
        self.ui.bg_mode_index = value

    @property
    def bg_current_opacity(self) -> float:
        return self.ui.bg_current_opacity

    @bg_current_opacity.setter
    def bg_current_opacity(self, value: float):
        self.ui.bg_current_opacity = value

    @property
    def bg_target_opacity(self) -> float:
        return self.ui.bg_target_opacity

    @bg_target_opacity.setter
    def bg_target_opacity(self, value: float):
        self.ui.bg_target_opacity = value

    # ═══════════════════════════════════════════════════════════════════════
    # Backward-compatible properties - InputState
    # ═══════════════════════════════════════════════════════════════════════

    @property
    def is_panning(self) -> bool:
        return self.input.is_panning

    @is_panning.setter
    def is_panning(self, value: bool):
        self.input.is_panning = value

    @property
    def pan_start_mouse(self) -> Tuple[float, float]:
        return self.input.pan_start_mouse

    @pan_start_mouse.setter
    def pan_start_mouse(self, value: Tuple[float, float]):
        self.input.pan_start_mouse = value

    @property
    def pan_start_offset(self) -> Tuple[float, float]:
        return self.input.pan_start_offset

    @pan_start_offset.setter
    def pan_start_offset(self, value: Tuple[float, float]):
        self.input.pan_start_offset = value

    @property
    def last_click_time(self) -> float:
        return self.input.last_click_time

    @last_click_time.setter
    def last_click_time(self, value: float):
        self.input.last_click_time = value

    @property
    def last_click_pos(self) -> Tuple[int, int]:
        return self.input.last_click_pos

    @last_click_pos.setter
    def last_click_pos(self, value: Tuple[int, int]):
        self.input.last_click_pos = value

    # ═══════════════════════════════════════════════════════════════════════
    # Backward-compatible properties - AnimationState
    # ═══════════════════════════════════════════════════════════════════════

    @property
    def open_anim_active(self) -> bool:
        return self.anim.open_active

    @open_anim_active.setter
    def open_anim_active(self, value: bool):
        self.anim.open_active = value

    @property
    def open_anim_t0(self) -> float:
        return self.anim.open_t0

    @open_anim_t0.setter
    def open_anim_t0(self, value: float):
        self.anim.open_t0 = value

    @property
    def switch_anim_active(self) -> bool:
        return self.anim.switch_active

    @switch_anim_active.setter
    def switch_anim_active(self, value: bool):
        self.anim.switch_active = value

    @property
    def switch_anim_t0(self) -> float:
        return self.anim.switch_t0

    @switch_anim_t0.setter
    def switch_anim_t0(self, value: float):
        self.anim.switch_t0 = value

    @property
    def switch_anim_duration_ms(self) -> int:
        return self.anim.switch_duration_ms

    @switch_anim_duration_ms.setter
    def switch_anim_duration_ms(self, value: int):
        self.anim.switch_duration_ms = value

    @property
    def switch_anim_direction(self) -> int:
        return self.anim.switch_direction

    @switch_anim_direction.setter
    def switch_anim_direction(self, value: int):
        self.anim.switch_direction = value

    @property
    def switch_anim_prev_tex(self) -> Optional[TextureInfo]:
        return self.anim.switch_prev_tex

    @switch_anim_prev_tex.setter
    def switch_anim_prev_tex(self, value: Optional[TextureInfo]):
        self.anim.switch_prev_tex = value

    @property
    def switch_anim_prev_view(self) -> ViewParams:
        return self.anim.switch_prev_view

    @switch_anim_prev_view.setter
    def switch_anim_prev_view(self, value: ViewParams):
        self.anim.switch_prev_view = value

    @property
    def switch_queue(self) -> Deque[Tuple[int, int]]:
        return self.anim.switch_queue

    @switch_queue.setter
    def switch_queue(self, value: Deque[Tuple[int, int]]):
        self.anim.switch_queue = value

    @property
    def zoom_anim_active(self) -> bool:
        return self.anim.zoom_active

    @zoom_anim_active.setter
    def zoom_anim_active(self, value: bool):
        self.anim.zoom_active = value

    @property
    def zoom_anim_t0(self) -> float:
        return self.anim.zoom_t0

    @zoom_anim_t0.setter
    def zoom_anim_t0(self, value: float):
        self.anim.zoom_t0 = value

    @property
    def zoom_anim_from(self) -> ViewParams:
        return self.anim.zoom_from

    @zoom_anim_from.setter
    def zoom_anim_from(self, value: ViewParams):
        self.anim.zoom_from = value

    @property
    def zoom_anim_to(self) -> ViewParams:
        return self.anim.zoom_to

    @zoom_anim_to.setter
    def zoom_anim_to(self, value: ViewParams):
        self.anim.zoom_to = value

    @property
    def toggle_zoom_active(self) -> bool:
        return self.anim.toggle_zoom_active

    @toggle_zoom_active.setter
    def toggle_zoom_active(self, value: bool):
        self.anim.toggle_zoom_active = value

    @property
    def toggle_zoom_t0(self) -> float:
        return self.anim.toggle_zoom_t0

    @toggle_zoom_t0.setter
    def toggle_zoom_t0(self, value: float):
        self.anim.toggle_zoom_t0 = value

    @property
    def toggle_zoom_from(self) -> ViewParams:
        return self.anim.toggle_zoom_from

    @toggle_zoom_from.setter
    def toggle_zoom_from(self, value: ViewParams):
        self.anim.toggle_zoom_from = value

    @property
    def toggle_zoom_to(self) -> ViewParams:
        return self.anim.toggle_zoom_to

    @toggle_zoom_to.setter
    def toggle_zoom_to(self, value: ViewParams):
        self.anim.toggle_zoom_to = value

    @property
    def toggle_zoom_target_state(self) -> int:
        return self.anim.toggle_zoom_target_state

    @toggle_zoom_target_state.setter
    def toggle_zoom_target_state(self, value: int):
        self.anim.toggle_zoom_target_state = value

    # ═══════════════════════════════════════════════════════════════════════
    # Backward-compatible properties - LoadingState
    # ═══════════════════════════════════════════════════════════════════════

    @property
    def async_loader(self) -> Optional[Any]:
        return self.loading.async_loader

    @async_loader.setter
    def async_loader(self, value: Optional[Any]):
        self.loading.async_loader = value

    @property
    def idle_detector(self) -> Optional[Any]:
        return self.loading.idle_detector

    @idle_detector.setter
    def idle_detector(self, value: Optional[Any]):
        self.loading.idle_detector = value

    @property
    def loading_current(self) -> bool:
        return self.loading.loading_current

    @loading_current.setter
    def loading_current(self, value: bool):
        self.loading.loading_current = value

    @property
    def waiting_for_switch(self) -> bool:
        return self.loading.waiting_for_switch

    @waiting_for_switch.setter
    def waiting_for_switch(self, value: bool):
        self.loading.waiting_for_switch = value

    @property
    def waiting_prev_snapshot(self) -> Optional[TextureInfo]:
        return self.loading.waiting_prev_snapshot

    @waiting_prev_snapshot.setter
    def waiting_prev_snapshot(self, value: Optional[TextureInfo]):
        self.loading.waiting_prev_snapshot = value

    @property
    def waiting_prev_view(self) -> ViewParams:
        return self.loading.waiting_prev_view

    @waiting_prev_view.setter
    def waiting_prev_view(self, value: ViewParams):
        self.loading.waiting_prev_view = value

    @property
    def pending_target_index(self) -> Optional[int]:
        return self.loading.pending_target_index

    @pending_target_index.setter
    def pending_target_index(self, value: Optional[int]):
        self.loading.pending_target_index = value

    @property
    def pending_neighbors_load(self) -> bool:
        return self.loading.pending_neighbors_load

    @pending_neighbors_load.setter
    def pending_neighbors_load(self, value: bool):
        self.loading.pending_neighbors_load = value

    @property
    def pending_switch_duration_ms(self) -> int:
        return self.loading.pending_switch_duration_ms

    @pending_switch_duration_ms.setter
    def pending_switch_duration_ms(self, value: int):
        self.loading.pending_switch_duration_ms = value
