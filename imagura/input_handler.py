"""Input Handler - maps raylib input events to commands.

This module bridges the gap between raw raylib input and the command pattern.
It polls input each frame and returns a list of commands to execute.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Tuple, Callable
from enum import Enum, auto

if TYPE_CHECKING:
    from .state import AppState

from .rl_compat import rl
from .commands import (
    Command,
    NavigateNext, NavigatePrev, NavigateToIndex,
    ZoomIn, ZoomOut, WheelZoom, ToggleZoom,
    StartPan, UpdatePan, EndPan,
    ToggleHUD, ToggleFilename, CycleBackground,
    GalleryScroll, GalleryClick,
    CloseApp,
    ShowContextMenu, HideContextMenu, ContextMenuClick,
    ToolbarButtonClick,
    RotateClockwise, RotateCounterClockwise, FlipHorizontal, CopyToClipboard,
)
from .config import (
    ZOOM_STEP_KEYS, ZOOM_STEP_WHEEL,
    ANIM_SWITCH_KEYS_MS, ANIM_SWITCH_GALLERY_MS,
    GALLERY_HEIGHT_FRAC, GALLERY_TRIGGER_FRAC,
    CLOSE_BTN_RADIUS, CLOSE_BTN_MARGIN,
    TOOLBAR_TRIGGER_FRAC, TOOLBAR_HEIGHT, TOOLBAR_BTN_RADIUS, TOOLBAR_BTN_SPACING,
    MENU_ITEM_HEIGHT, MENU_ITEM_WIDTH, MENU_PADDING,
)
from .state.ui import MenuItemId, ToolbarButtonId
from .logging import now


class InputContext(Enum):
    """Context for input handling - affects which inputs are valid."""
    NORMAL = auto()
    GALLERY_HOVER = auto()
    ZOOMED = auto()
    ANIMATING = auto()


@dataclass
class MouseState:
    """Current mouse state snapshot."""
    x: float = 0.0
    y: float = 0.0
    left_pressed: bool = False
    left_released: bool = False
    left_down: bool = False
    right_pressed: bool = False
    right_released: bool = False
    wheel: float = 0.0


@dataclass
class InputHandler:
    """Handles input polling and command generation."""

    # Key bindings (can be customized)
    key_next: List[int] = field(default_factory=lambda: [rl.KEY_RIGHT, rl.KEY_D])
    key_prev: List[int] = field(default_factory=lambda: [rl.KEY_LEFT, rl.KEY_A])
    key_zoom_in: int = rl.KEY_UP
    key_zoom_out: int = rl.KEY_DOWN
    key_toggle_zoom: int = rl.KEY_F
    key_toggle_hud: int = rl.KEY_I
    key_toggle_filename: int = rl.KEY_N
    key_cycle_bg: int = rl.KEY_V
    key_close: int = rl.KEY_ESCAPE

    # Double-click tracking
    _last_click_time: float = 0.0
    _last_click_pos: Tuple[int, int] = (0, 0)
    _double_click_threshold_ms: float = 300.0
    _double_click_distance: int = 10

    def poll_mouse(self) -> MouseState:
        """Get current mouse state."""
        pos = rl.GetMousePosition()
        return MouseState(
            x=pos.x,
            y=pos.y,
            left_pressed=rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_LEFT),
            left_released=rl.IsMouseButtonReleased(rl.MOUSE_BUTTON_LEFT),
            left_down=rl.IsMouseButtonDown(rl.MOUSE_BUTTON_LEFT),
            right_pressed=rl.IsMouseButtonPressed(rl.MOUSE_BUTTON_RIGHT),
            right_released=rl.IsMouseButtonReleased(rl.MOUSE_BUTTON_RIGHT),
            wheel=rl.GetMouseWheelMove(),
        )

    def get_context(self, state: "AppState", mouse: MouseState) -> InputContext:
        """Determine current input context."""
        if state.anim.open_active or state.anim.toggle_zoom_active:
            return InputContext.ANIMATING

        # Check if over gallery
        gh = int(state.screenH * GALLERY_HEIGHT_FRAC)
        gallery_y = state.screenH - gh
        if mouse.y >= gallery_y and state.gallery.y_position < state.screenH:
            return InputContext.GALLERY_HOVER

        if state.is_zoomed:
            return InputContext.ZOOMED

        return InputContext.NORMAL

    def is_in_center_zone(self, state: "AppState", mouse: MouseState) -> bool:
        """Check if mouse is in center zone (for double-click toggle zoom)."""
        mid_left = state.screenW * 0.33
        mid_right = state.screenW * 0.66
        mid_top = state.screenH * 0.33
        mid_bot = state.screenH * 0.66
        return mid_left <= mouse.x <= mid_right and mid_top <= mouse.y <= mid_bot

    def is_on_close_button(self, state: "AppState", mouse: MouseState) -> bool:
        """Check if mouse is over close button."""
        dist = CLOSE_BTN_MARGIN + CLOSE_BTN_RADIUS
        cx = state.screenW - dist
        cy = dist
        dx = mouse.x - cx
        dy = mouse.y - cy
        return (dx * dx + dy * dy) <= (CLOSE_BTN_RADIUS * CLOSE_BTN_RADIUS)

    def is_on_edge(self, state: "AppState", mouse: MouseState) -> Optional[str]:
        """Check if mouse is on navigation edge. Returns 'left', 'right', or None."""
        if mouse.x <= state.screenW * 0.10:
            return 'left'
        if mouse.x >= state.screenW * 0.90:
            return 'right'
        return None

    def is_over_image(self, state: "AppState", mouse: MouseState) -> bool:
        """Check if mouse is over the current image."""
        if not state.cache.curr:
            return False
        v = state.view
        ti = state.cache.curr
        x1 = v.offx
        y1 = v.offy
        x2 = x1 + ti.w * v.scale
        y2 = y1 + ti.h * v.scale
        return x1 <= mouse.x <= x2 and y1 <= mouse.y <= y2

    def is_in_toolbar_zone(self, state: "AppState", mouse: MouseState) -> bool:
        """Check if mouse is in toolbar trigger zone (top 5% of screen)."""
        return mouse.y < state.screenH * TOOLBAR_TRIGGER_FRAC

    def get_toolbar_button_at(self, state: "AppState", mouse: MouseState) -> int:
        """Get toolbar button index at mouse position, or -1 if none."""
        toolbar = state.ui.toolbar
        if toolbar.alpha < 0.5:  # Only clickable when visible enough
            return -1

        n_buttons = len(toolbar.buttons)
        total_width = n_buttons * (TOOLBAR_BTN_RADIUS * 2) + (n_buttons - 1) * TOOLBAR_BTN_SPACING
        start_x = (state.screenW - total_width) // 2 + TOOLBAR_BTN_RADIUS
        cy = TOOLBAR_HEIGHT // 2

        for i in range(n_buttons):
            cx = start_x + i * (TOOLBAR_BTN_RADIUS * 2 + TOOLBAR_BTN_SPACING)
            dx = mouse.x - cx
            dy = mouse.y - cy
            if (dx * dx + dy * dy) <= (TOOLBAR_BTN_RADIUS * TOOLBAR_BTN_RADIUS):
                return i
        return -1

    def is_in_context_menu(self, state: "AppState", mouse: MouseState) -> bool:
        """Check if mouse is inside context menu."""
        menu = state.ui.context_menu
        if not menu.visible:
            return False

        n_items = len(menu.items)
        menu_w = MENU_ITEM_WIDTH
        menu_h = n_items * MENU_ITEM_HEIGHT + MENU_PADDING * 2

        # Use same clamping as renderer
        x = min(menu.x, state.screenW - menu_w - 5)
        y = min(menu.y, state.screenH - menu_h - 5)
        x = max(5, x)
        y = max(5, y)

        return x <= mouse.x <= x + menu_w and y <= mouse.y <= y + menu_h

    def get_context_menu_item_at(self, state: "AppState", mouse: MouseState) -> int:
        """Get context menu item index at mouse position, or -1 if none."""
        menu = state.ui.context_menu
        if not menu.visible:
            return -1

        n_items = len(menu.items)
        menu_w = MENU_ITEM_WIDTH
        menu_h = n_items * MENU_ITEM_HEIGHT + MENU_PADDING * 2

        # Use same clamping as renderer
        x = min(menu.x, state.screenW - menu_w - 5)
        y = min(menu.y, state.screenH - menu_h - 5)
        x = max(5, x)
        y = max(5, y)

        if not (x <= mouse.x <= x + menu_w):
            return -1

        # Check which item
        item_start_y = y + MENU_PADDING
        for i in range(n_items):
            item_y = item_start_y + i * MENU_ITEM_HEIGHT
            if item_y <= mouse.y < item_y + MENU_ITEM_HEIGHT:
                return i
        return -1

    def check_double_click(self, mouse: MouseState) -> bool:
        """Check for double-click. Updates internal state."""
        t = now()
        is_double = False

        if (t - self._last_click_time) < (self._double_click_threshold_ms / 1000.0):
            dx = abs(int(mouse.x) - self._last_click_pos[0])
            dy = abs(int(mouse.y) - self._last_click_pos[1])
            if dx < self._double_click_distance and dy < self._double_click_distance:
                is_double = True
                self._last_click_time = 0.0
                return True

        self._last_click_time = t
        self._last_click_pos = (int(mouse.x), int(mouse.y))
        return False

    def poll(self, state: "AppState") -> List[Command]:
        """Poll all inputs and return list of commands to execute."""
        commands: List[Command] = []
        mouse = self.poll_mouse()
        context = self.get_context(state, mouse)

        # ─── Context Menu Handling ───────────────────────────────────────────
        menu = state.ui.context_menu
        if menu.visible:
            # Update hover state
            menu.hover_index = self.get_context_menu_item_at(state, mouse)

            # Left click on menu item
            if mouse.left_pressed:
                if menu.hover_index >= 0:
                    item = menu.items[menu.hover_index]
                    commands.append(ContextMenuClick(item_index=menu.hover_index))
                    # Generate action command based on item
                    if item.id == MenuItemId.COPY:
                        commands.append(CopyToClipboard())
                    return commands
                else:
                    # Click outside menu - close it
                    commands.append(HideContextMenu())
                    return commands

            # Escape closes menu
            if rl.IsKeyPressed(rl.KEY_ESCAPE):
                commands.append(HideContextMenu())
                return commands

        # Right-click shows context menu (when no menu visible)
        if mouse.right_pressed and not menu.visible:
            commands.append(ShowContextMenu(x=int(mouse.x), y=int(mouse.y)))
            return commands

        # ─── Toolbar Handling ────────────────────────────────────────────────
        toolbar = state.ui.toolbar

        # Update toolbar visibility based on mouse position
        if self.is_in_toolbar_zone(state, mouse):
            toolbar.target_alpha = 1.0
        else:
            toolbar.target_alpha = 0.0

        # Update toolbar hover
        if toolbar.alpha > 0.1:
            toolbar.hover_index = self.get_toolbar_button_at(state, mouse)
        else:
            toolbar.hover_index = -1

        # Toolbar button click
        if mouse.left_pressed and toolbar.hover_index >= 0:
            btn = toolbar.buttons[toolbar.hover_index]
            commands.append(ToolbarButtonClick(button_index=toolbar.hover_index))
            # Generate action command based on button
            if btn.id == ToolbarButtonId.ROTATE_CW:
                commands.append(RotateClockwise())
            elif btn.id == ToolbarButtonId.ROTATE_CCW:
                commands.append(RotateCounterClockwise())
            elif btn.id == ToolbarButtonId.FLIP_H:
                commands.append(FlipHorizontal())
            return commands

        # ─── Regular Input Handling ──────────────────────────────────────────

        # Always check for close
        if rl.IsKeyPressed(self.key_close):
            commands.append(CloseApp())
            return commands

        # Close button click
        if mouse.left_pressed and self.is_on_close_button(state, mouse):
            commands.append(CloseApp())
            return commands

        # UI toggles (always available)
        if rl.IsKeyPressed(self.key_toggle_hud):
            commands.append(ToggleHUD())

        if rl.IsKeyPressed(self.key_toggle_filename):
            commands.append(ToggleFilename())

        if rl.IsKeyPressed(self.key_cycle_bg):
            commands.append(CycleBackground())

        # Context-specific handling
        if context == InputContext.ANIMATING:
            # Limited input during animations
            return commands

        if context == InputContext.GALLERY_HOVER:
            # Gallery wheel scroll
            if mouse.wheel != 0.0:
                commands.append(GalleryScroll(delta=mouse.wheel))
            # Gallery clicks are handled by render_gallery in main loop
            return commands

        # Navigation keys (not during open animation)
        if not state.anim.open_active:
            for key in self.key_next:
                if rl.IsKeyPressed(key):
                    commands.append(NavigateNext(
                        animate=True,
                        duration_ms=ANIM_SWITCH_KEYS_MS
                    ))
                    break

            for key in self.key_prev:
                if rl.IsKeyPressed(key):
                    commands.append(NavigatePrev(
                        animate=True,
                        duration_ms=ANIM_SWITCH_KEYS_MS
                    ))
                    break

        # Zoom keys (continuous)
        if state.cache.curr and not state.anim.open_active and not state.anim.toggle_zoom_active:
            if rl.IsKeyDown(self.key_zoom_in):
                commands.append(ZoomIn(
                    step=ZOOM_STEP_KEYS,
                    anchor=(int(mouse.x), int(mouse.y))
                ))

            if rl.IsKeyDown(self.key_zoom_out):
                commands.append(ZoomOut(
                    step=ZOOM_STEP_KEYS,
                    anchor=(int(mouse.x), int(mouse.y))
                ))

            # Wheel zoom (not over gallery)
            if mouse.wheel != 0.0:
                commands.append(WheelZoom(
                    delta=mouse.wheel,
                    anchor=(int(mouse.x), int(mouse.y)),
                    step_multiplier=ZOOM_STEP_WHEEL
                ))

        # Toggle zoom (F key)
        if rl.IsKeyPressed(self.key_toggle_zoom) and not state.anim.toggle_zoom_active:
            commands.append(ToggleZoom())

        # Double-click toggle zoom in center zone
        if mouse.left_pressed and self.is_in_center_zone(state, mouse):
            if not state.anim.toggle_zoom_active and self.check_double_click(mouse):
                commands.append(ToggleZoom())

        # Edge navigation (not zoomed, not over gallery)
        if context == InputContext.NORMAL:
            edge = self.is_on_edge(state, mouse)
            if mouse.left_pressed and edge:
                if edge == 'right':
                    commands.append(NavigateNext(
                        animate=True,
                        duration_ms=ANIM_SWITCH_KEYS_MS
                    ))
                elif edge == 'left':
                    commands.append(NavigatePrev(
                        animate=True,
                        duration_ms=ANIM_SWITCH_KEYS_MS
                    ))

        # Panning (zoomed mode)
        if context == InputContext.ZOOMED:
            if mouse.left_pressed:
                if (self.is_over_image(state, mouse) and
                    not self.is_on_close_button(state, mouse) and
                    not self.is_in_center_zone(state, mouse)):
                    commands.append(StartPan(mouse_x=mouse.x, mouse_y=mouse.y))

            if state.input.is_panning:
                if mouse.left_down:
                    commands.append(UpdatePan(mouse_x=mouse.x, mouse_y=mouse.y))
                elif mouse.left_released:
                    commands.append(EndPan())

        return commands


# Singleton instance for convenience
_default_handler: Optional[InputHandler] = None


def get_input_handler() -> InputHandler:
    """Get the default input handler instance."""
    global _default_handler
    if _default_handler is None:
        _default_handler = InputHandler()
    return _default_handler


def poll_commands(state: "AppState") -> List[Command]:
    """Convenience function to poll commands using default handler."""
    return get_input_handler().poll(state)
