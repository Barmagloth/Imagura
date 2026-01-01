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
class TextEditState:
    """State for a text input field with full editing support."""
    text: str = ""
    cursor_pos: int = 0  # Position of cursor in text
    selection_start: int = -1  # -1 means no selection
    selection_end: int = -1

    def has_selection(self) -> bool:
        """Check if there's active text selection."""
        return self.selection_start >= 0 and self.selection_end >= 0 and self.selection_start != self.selection_end

    def get_selection_range(self) -> Tuple[int, int]:
        """Get normalized selection range (start, end) where start <= end."""
        if not self.has_selection():
            return (self.cursor_pos, self.cursor_pos)
        return (min(self.selection_start, self.selection_end),
                max(self.selection_start, self.selection_end))

    def get_selected_text(self) -> str:
        """Get selected text."""
        if not self.has_selection():
            return ""
        start, end = self.get_selection_range()
        return self.text[start:end]

    def delete_selection(self) -> None:
        """Delete selected text."""
        if not self.has_selection():
            return
        start, end = self.get_selection_range()
        self.text = self.text[:start] + self.text[end:]
        self.cursor_pos = start
        self.clear_selection()

    def clear_selection(self) -> None:
        """Clear text selection."""
        self.selection_start = -1
        self.selection_end = -1

    def select_all(self) -> None:
        """Select all text."""
        self.selection_start = 0
        self.selection_end = len(self.text)
        self.cursor_pos = len(self.text)

    def insert_text(self, text: str) -> None:
        """Insert text at cursor, replacing selection if any."""
        if self.has_selection():
            self.delete_selection()
        self.text = self.text[:self.cursor_pos] + text + self.text[self.cursor_pos:]
        self.cursor_pos += len(text)

    def delete_char_before(self) -> None:
        """Delete character before cursor (backspace)."""
        if self.has_selection():
            self.delete_selection()
        elif self.cursor_pos > 0:
            self.text = self.text[:self.cursor_pos - 1] + self.text[self.cursor_pos:]
            self.cursor_pos -= 1

    def delete_char_after(self) -> None:
        """Delete character after cursor (delete key)."""
        if self.has_selection():
            self.delete_selection()
        elif self.cursor_pos < len(self.text):
            self.text = self.text[:self.cursor_pos] + self.text[self.cursor_pos + 1:]

    def move_cursor_left(self, select: bool = False) -> None:
        """Move cursor left, optionally extending selection."""
        if select:
            if self.selection_start < 0:
                self.selection_start = self.cursor_pos
                self.selection_end = self.cursor_pos
            if self.cursor_pos > 0:
                self.cursor_pos -= 1
                self.selection_end = self.cursor_pos
        else:
            if self.has_selection():
                self.cursor_pos = min(self.selection_start, self.selection_end)
                self.clear_selection()
            elif self.cursor_pos > 0:
                self.cursor_pos -= 1

    def move_cursor_right(self, select: bool = False) -> None:
        """Move cursor right, optionally extending selection."""
        if select:
            if self.selection_start < 0:
                self.selection_start = self.cursor_pos
                self.selection_end = self.cursor_pos
            if self.cursor_pos < len(self.text):
                self.cursor_pos += 1
                self.selection_end = self.cursor_pos
        else:
            if self.has_selection():
                self.cursor_pos = max(self.selection_start, self.selection_end)
                self.clear_selection()
            elif self.cursor_pos < len(self.text):
                self.cursor_pos += 1

    def move_cursor_home(self, select: bool = False) -> None:
        """Move cursor to start of text."""
        if select:
            if self.selection_start < 0:
                self.selection_start = self.cursor_pos
                self.selection_end = self.cursor_pos
            self.cursor_pos = 0
            self.selection_end = 0
        else:
            self.clear_selection()
            self.cursor_pos = 0

    def move_cursor_end(self, select: bool = False) -> None:
        """Move cursor to end of text."""
        if select:
            if self.selection_start < 0:
                self.selection_start = self.cursor_pos
                self.selection_end = self.cursor_pos
            self.cursor_pos = len(self.text)
            self.selection_end = len(self.text)
        else:
            self.clear_selection()
            self.cursor_pos = len(self.text)

    def set_text(self, text: str) -> None:
        """Set text and position cursor at end."""
        self.text = text
        self.cursor_pos = len(text)
        self.clear_selection()

    def reset(self) -> None:
        """Reset to empty state."""
        self.text = ""
        self.cursor_pos = 0
        self.clear_selection()


@dataclass
class SettingsState:
    """State for settings window."""
    visible: bool = False
    scroll_offset: int = 0
    hover_item: int = -1
    editing_item: int = -1
    edit_state: TextEditState = field(default_factory=TextEditState)
    active_tab: int = 0  # Currently active tab index

    # Legacy property for compatibility
    @property
    def edit_value(self) -> str:
        return self.edit_state.text

    @edit_value.setter
    def edit_value(self, value: str) -> None:
        self.edit_state.set_text(value)

    def show(self) -> None:
        """Show settings window."""
        self.visible = True
        self.scroll_offset = 0
        self.hover_item = -1
        self.editing_item = -1
        self.edit_state.reset()
        self.active_tab = 0

    def hide(self) -> None:
        """Hide settings window."""
        self.visible = False
        self.editing_item = -1
        self.edit_state.reset()


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
