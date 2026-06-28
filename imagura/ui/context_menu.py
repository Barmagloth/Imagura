"""Right-click context menu hit-testing, input update, and drawing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from .. import config as cfg
from ..config import KEY_CLOSE, MENU_BG_ALPHA, MENU_HOVER_ALPHA, MENU_ITEM_HEIGHT, MENU_ITEM_WIDTH, MENU_PADDING
from ..rl_compat import make_color as RL_Color
from ..rl_compat import rl
from ..i18n import tr
from ..state.ui import MenuItem
from .text_overlays import draw_text_raw

if TYPE_CHECKING:
    from ..state import AppState


@dataclass(frozen=True)
class ContextMenuInputResult:
    consumed_click: bool = False
    clicked_item: Optional[MenuItem] = None


def handle_context_menu_input(state: "AppState", mouse, settings_active: bool) -> ContextMenuInputResult:
    """Update menu hover/visibility and return a clicked item when selected."""
    menu = state.ui.context_menu

    if settings_active:
        return ContextMenuInputResult(consumed_click=True)

    consumed_click = False
    clicked_item = None

    if menu.visible:
        menu.hover_index = get_context_menu_item_at(state, mouse.x, mouse.y)

        if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT):
            consumed_click = True
            if menu.hover_index >= 0:
                clicked_item = menu.items[menu.hover_index]
            menu.hide()

        if rl.IsKeyPressed(KEY_CLOSE):
            menu.hide()

    if rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_RIGHT) and not menu.visible and not state.ui.settings.visible:
        menu.show(int(mouse.x), int(mouse.y))

    return ContextMenuInputResult(consumed_click=consumed_click, clicked_item=clicked_item)


def get_context_menu_item_at(state: "AppState", mx: float, my: float) -> int:
    """Return context menu item index at pointer position, or `-1`."""
    menu = state.ui.context_menu
    if not menu.visible:
        return -1

    n_items = len(menu.items)
    menu_w = MENU_ITEM_WIDTH
    menu_h = n_items * MENU_ITEM_HEIGHT + MENU_PADDING * 2
    x, y = _clamped_menu_position(state, menu_w, menu_h)

    if not (x <= mx <= x + menu_w):
        return -1

    item_start_y = y + MENU_PADDING
    for i in range(n_items):
        item_y = item_start_y + i * MENU_ITEM_HEIGHT
        if item_y <= my < item_y + MENU_ITEM_HEIGHT:
            return i
    return -1


def draw_context_menu(state: "AppState") -> None:
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
    x, y = _clamped_menu_position(state, menu_w, menu_h)

    rl.DrawRectangle(x + 4, y + 4, menu_w, menu_h, RL_Color(0, 0, 0, 100))
    rl.DrawRectangle(x, y, menu_w, menu_h, RL_Color(40, 40, 40, int(255 * MENU_BG_ALPHA)))
    rl.DrawRectangleLines(x, y, menu_w, menu_h, RL_Color(80, 80, 80, 255))

    item_y = y + MENU_PADDING
    for i, item in enumerate(menu.items):
        is_hover = i == menu.hover_index

        if is_hover:
            rl.DrawRectangle(
                x + 2,
                item_y,
                menu_w - 4,
                MENU_ITEM_HEIGHT,
                RL_Color(255, 255, 255, int(255 * MENU_HOVER_ALPHA)),
            )

        text_color = RL_Color(255, 255, 255, 255) if is_hover else RL_Color(200, 200, 200, 255)
        text_x = x + MENU_PADDING + 8
        text_y = item_y + (MENU_ITEM_HEIGHT - font_size) // 2
        draw_text_raw(state, tr(item.label), text_x, text_y, font_size, text_color)
        item_y += MENU_ITEM_HEIGHT


def _clamped_menu_position(state: "AppState", menu_w: int, menu_h: int) -> tuple[int, int]:
    menu = state.ui.context_menu
    x = min(menu.x, state.screenW - menu_w - 5)
    y = min(menu.y, state.screenH - menu_h - 5)
    return max(5, x), max(5, y)
