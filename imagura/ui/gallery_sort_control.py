"""Sort control drawn inside the bottom gallery strip."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..image_sorting import SORT_OPTIONS, sort_label
from ..math_utils import clamp
from ..rl_compat import make_color as RL_Color
from ..rl_compat import make_vec2 as RL_V2
from ..rl_compat import rl
from .text_overlays import draw_text_raw, measure_text_width

if TYPE_CHECKING:
    from ..state import AppState


CONTROL_X = 12
CONTROL_Y_MARGIN = 8
CONTROL_H = 28
CONTROL_LABEL_W = 96
CONTROL_ARROW_W = 28
CONTROL_W = CONTROL_LABEL_W + CONTROL_ARROW_W
MENU_ITEM_H = 26
MENU_PADDING = 4


@dataclass(frozen=True)
class GallerySortInputResult:
    consumed_click: bool = False
    changed: bool = False


def handle_gallery_sort_input(
    state: "AppState",
    mouse_x: float,
    mouse_y: float,
    left_clicked: bool,
    gallery_height: int,
) -> GallerySortInputResult:
    """Handle sort control clicks while the gallery is visible."""
    if not _is_gallery_visible(state):
        state.gallery.sort_menu_open = False
        state.gallery.sort_menu_hover_index = -1
        return GallerySortInputResult()

    control = _control_rect(state, gallery_height)
    menu = _menu_rect(state, gallery_height)
    state.gallery.sort_menu_hover_index = _menu_item_at(mouse_x, mouse_y, menu) if state.gallery.sort_menu_open else -1

    if not left_clicked:
        return GallerySortInputResult()

    if state.gallery.sort_menu_open and state.gallery.sort_menu_hover_index >= 0:
        option = SORT_OPTIONS[state.gallery.sort_menu_hover_index]
        state.gallery.sort_key = option.key
        state.gallery.sort_menu_open = False
        state.gallery.sort_menu_hover_index = -1
        return GallerySortInputResult(consumed_click=True, changed=True)

    if _point_in_rect(mouse_x, mouse_y, _arrow_rect(control)):
        state.gallery.sort_desc = not state.gallery.sort_desc
        state.gallery.sort_menu_open = False
        state.gallery.sort_menu_hover_index = -1
        return GallerySortInputResult(consumed_click=True, changed=True)

    if _point_in_rect(mouse_x, mouse_y, _label_rect(control)):
        state.gallery.sort_menu_open = not state.gallery.sort_menu_open
        return GallerySortInputResult(consumed_click=True)

    if state.gallery.sort_menu_open:
        state.gallery.sort_menu_open = False
        state.gallery.sort_menu_hover_index = -1
        return GallerySortInputResult(consumed_click=True)

    return GallerySortInputResult()


def draw_gallery_sort_control(state: "AppState", gallery_height: int) -> None:
    """Draw the compact sort control and its optional menu."""
    if not _is_gallery_visible(state):
        return

    control = _control_rect(state, gallery_height)
    alpha = _gallery_alpha(state, gallery_height)
    bg_alpha = int(190 * alpha)
    border_alpha = int(180 * alpha)
    text_alpha = int(235 * alpha)

    x, y, w, h = control
    rl.DrawRectangle(x, y, w, h, RL_Color(20, 20, 20, bg_alpha))
    rl.DrawRectangleLines(x, y, w, h, RL_Color(220, 220, 220, border_alpha))

    arrow_x = x + CONTROL_LABEL_W
    rl.DrawLine(arrow_x, y + 4, arrow_x, y + h - 4, RL_Color(220, 220, 220, int(90 * alpha)))

    label = sort_label(state.gallery.sort_key)
    font_size = 16
    label_w = measure_text_width(state, label, font_size)
    label_x = x + max(6, (CONTROL_LABEL_W - label_w) // 2)
    draw_text_raw(state, label, label_x, y + 6, font_size, RL_Color(255, 255, 255, text_alpha))

    _draw_direction_icon(
        arrow_x + CONTROL_ARROW_W // 2,
        y + h // 2,
        state.gallery.sort_desc,
        RL_Color(255, 255, 255, text_alpha),
    )

    if state.gallery.sort_menu_open:
        _draw_sort_menu(state, gallery_height, alpha)


def _draw_sort_menu(state: "AppState", gallery_height: int, alpha: float) -> None:
    x, y, w, h = _menu_rect(state, gallery_height)
    rl.DrawRectangle(x + 3, y + 3, w, h, RL_Color(0, 0, 0, int(95 * alpha)))
    rl.DrawRectangle(x, y, w, h, RL_Color(28, 28, 28, int(230 * alpha)))
    rl.DrawRectangleLines(x, y, w, h, RL_Color(210, 210, 210, int(150 * alpha)))

    font_size = 15
    item_y = y + MENU_PADDING
    for idx, option in enumerate(SORT_OPTIONS):
        is_hover = idx == state.gallery.sort_menu_hover_index
        is_active = option.key == state.gallery.sort_key
        if is_hover:
            rl.DrawRectangle(x + 2, item_y, w - 4, MENU_ITEM_H, RL_Color(255, 255, 255, int(40 * alpha)))

        prefix = "*" if is_active else " "
        label = f"{prefix} {option.label}"
        color = RL_Color(255, 255, 255, int((245 if is_active else 205) * alpha))
        draw_text_raw(state, label, x + 8, item_y + 5, font_size, color)
        item_y += MENU_ITEM_H


def _draw_direction_icon(cx: int, cy: int, descending: bool, color) -> None:
    stem_top = cy - 7
    stem_bottom = cy + 7
    if descending:
        rl.DrawLineEx(RL_V2(cx, stem_top), RL_V2(cx, stem_bottom), 2.0, color)
        rl.DrawLineEx(RL_V2(cx, stem_bottom), RL_V2(cx - 5, stem_bottom - 5), 2.0, color)
        rl.DrawLineEx(RL_V2(cx, stem_bottom), RL_V2(cx + 5, stem_bottom - 5), 2.0, color)
    else:
        rl.DrawLineEx(RL_V2(cx, stem_bottom), RL_V2(cx, stem_top), 2.0, color)
        rl.DrawLineEx(RL_V2(cx, stem_top), RL_V2(cx - 5, stem_top + 5), 2.0, color)
        rl.DrawLineEx(RL_V2(cx, stem_top), RL_V2(cx + 5, stem_top + 5), 2.0, color)


def _control_rect(state: "AppState", gallery_height: int) -> tuple[int, int, int, int]:
    y_visible = state.screenH - gallery_height
    y_hidden = state.screenH
    y = int(clamp(state.gallery_y, y_visible, y_hidden)) + CONTROL_Y_MARGIN
    return CONTROL_X, y, CONTROL_W, CONTROL_H


def _label_rect(control: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x, y, _, h = control
    return x, y, CONTROL_LABEL_W, h


def _arrow_rect(control: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x, y, _, h = control
    return x + CONTROL_LABEL_W, y, CONTROL_ARROW_W, h


def _menu_rect(state: "AppState", gallery_height: int) -> tuple[int, int, int, int]:
    x, y, w, _ = _control_rect(state, gallery_height)
    menu_h = len(SORT_OPTIONS) * MENU_ITEM_H + MENU_PADDING * 2
    menu_y = max(5, y - menu_h - 6)
    return x, menu_y, w, menu_h


def _menu_item_at(mouse_x: float, mouse_y: float, menu: tuple[int, int, int, int]) -> int:
    x, y, w, h = menu
    if not _point_in_rect(mouse_x, mouse_y, menu):
        return -1
    item_y = y + MENU_PADDING
    for idx in range(len(SORT_OPTIONS)):
        if item_y <= mouse_y < item_y + MENU_ITEM_H:
            return idx
        item_y += MENU_ITEM_H
    return -1


def _point_in_rect(px: float, py: float, rect: tuple[int, int, int, int]) -> bool:
    x, y, w, h = rect
    return x <= px <= x + w and y <= py <= y + h


def _is_gallery_visible(state: "AppState") -> bool:
    return state.gallery_y < state.screenH


def _gallery_alpha(state: "AppState", gallery_height: int) -> float:
    y_visible = state.screenH - gallery_height
    y_hidden = state.screenH
    denom = y_hidden - y_visible
    return 1.0 - ((state.gallery_y - y_visible) / denom) if denom > 0 else 1.0
