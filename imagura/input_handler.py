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
)
from .config import (
    ZOOM_STEP_KEYS, ZOOM_STEP_WHEEL,
    ANIM_SWITCH_KEYS_MS, ANIM_SWITCH_GALLERY_MS,
    GALLERY_HEIGHT_FRAC, GALLERY_TRIGGER_FRAC,
    CLOSE_BTN_RADIUS, CLOSE_BTN_MARGIN,
)
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
