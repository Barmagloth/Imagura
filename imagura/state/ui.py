"""UI state - HUD, buttons, background, toolbar, context menu."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Callable
from enum import IntEnum

from ..config import BG_MODES


class MenuItemId(IntEnum):
    """Identifiers for context menu items."""
    COPY = 1
    # Future items can be added here


@dataclass
class MenuItem:
    """A single context menu item."""
    id: MenuItemId
    label: str
    icon: Optional[str] = None  # Icon identifier


# Default menu items
DEFAULT_MENU_ITEMS: List[MenuItem] = [
    MenuItem(MenuItemId.COPY, "Копировать"),
]


@dataclass
class ContextMenuState:
    """State for right-click context menu."""
    visible: bool = False
    x: int = 0
    y: int = 0
    items: List[MenuItem] = field(default_factory=lambda: list(DEFAULT_MENU_ITEMS))
    hover_index: int = -1

    def show(self, x: int, y: int) -> None:
        """Show menu at position."""
        self.visible = True
        self.x = x
        self.y = y
        self.hover_index = -1

    def hide(self) -> None:
        """Hide the menu."""
        self.visible = False
        self.hover_index = -1

    def get_hovered_item(self) -> Optional[MenuItem]:
        """Get currently hovered item or None."""
        if 0 <= self.hover_index < len(self.items):
            return self.items[self.hover_index]
        return None


class ToolbarButtonId(IntEnum):
    """Identifiers for toolbar buttons."""
    SETTINGS = 0       # Settings (gear icon)
    ROTATE_CW = 1      # Rotate clockwise
    ROTATE_CCW = 2     # Rotate counter-clockwise
    FLIP_H = 3         # Flip horizontal


@dataclass
class ToolbarButton:
    """A toolbar button."""
    id: ToolbarButtonId
    tooltip: str
    separator_after: bool = False  # Draw separator after this button


# Default toolbar buttons (settings first with separator, then image tools)
DEFAULT_TOOLBAR_BUTTONS: List[ToolbarButton] = [
    ToolbarButton(ToolbarButtonId.SETTINGS, "Настройки", separator_after=True),
    ToolbarButton(ToolbarButtonId.ROTATE_CCW, "Повернуть влево"),
    ToolbarButton(ToolbarButtonId.ROTATE_CW, "Повернуть вправо"),
    ToolbarButton(ToolbarButtonId.FLIP_H, "Отразить"),
]


@dataclass
class ToolbarState:
    """State for top toolbar."""
    alpha: float = 0.0  # Current visibility (0-1)
    target_alpha: float = 0.0  # Target visibility
    buttons: List[ToolbarButton] = field(default_factory=lambda: list(DEFAULT_TOOLBAR_BUTTONS))
    hover_index: int = -1  # -1 = no hover

    def get_hovered_button(self) -> Optional[ToolbarButton]:
        """Get currently hovered button or None."""
        if 0 <= self.hover_index < len(self.buttons):
            return self.buttons[self.hover_index]
        return None


@dataclass
class SettingsState:
    """State for settings window."""
    visible: bool = False
    scroll_offset: int = 0
    hover_item: int = -1
    editing_item: int = -1
    edit_value: str = ""

    def show(self) -> None:
        """Show settings window."""
        self.visible = True
        self.scroll_offset = 0
        self.hover_item = -1
        self.editing_item = -1

    def hide(self) -> None:
        """Hide settings window."""
        self.visible = False
        self.editing_item = -1


@dataclass
class UIState:
    """State for UI elements."""
    show_hud: bool = False
    show_filename: bool = False
    nav_left_alpha: float = 0.0
    nav_right_alpha: float = 0.0
    close_btn_alpha: float = 0.0
    bg_mode_index: int = 0
    bg_current_opacity: float = BG_MODES[0]["opacity"]
    bg_target_opacity: float = BG_MODES[0]["opacity"]

    # Toolbar, context menu, settings
    toolbar: ToolbarState = field(default_factory=ToolbarState)
    context_menu: ContextMenuState = field(default_factory=ContextMenuState)
    settings: SettingsState = field(default_factory=SettingsState)

    @property
    def current_bg_mode(self) -> dict:
        """Get current background mode settings."""
        return BG_MODES[self.bg_mode_index]

    @property
    def bg_blur_enabled(self) -> bool:
        """Check if blur is enabled for current mode."""
        return self.current_bg_mode["blur"]

    @property
    def bg_color(self) -> tuple:
        """Get background color for current mode."""
        return self.current_bg_mode["color"]

    def cycle_bg_mode(self) -> None:
        """Cycle to next background mode."""
        self.bg_mode_index = (self.bg_mode_index + 1) % len(BG_MODES)
        self.bg_target_opacity = BG_MODES[self.bg_mode_index]["opacity"]

    def toggle_hud(self) -> None:
        """Toggle HUD visibility."""
        self.show_hud = not self.show_hud

    def toggle_filename(self) -> None:
        """Toggle filename display."""
        self.show_filename = not self.show_filename
