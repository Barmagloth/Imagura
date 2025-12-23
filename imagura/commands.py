"""Command Pattern for input handling.

Commands encapsulate actions that can be triggered by various inputs.
Each command has an execute() method and optional can_execute() for guards.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from .state import AppState

from .types import ViewParams
from .logging import log


class Command(ABC):
    """Base class for all commands."""

    @abstractmethod
    def execute(self, state: "AppState") -> bool:
        """Execute the command. Returns True if action was taken."""
        pass

    def can_execute(self, state: "AppState") -> bool:
        """Check if command can be executed. Override for guards."""
        return True


# ═══════════════════════════════════════════════════════════════════════════
# Navigation Commands
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class NavigateNext(Command):
    """Navigate to next image."""
    animate: bool = True
    duration_ms: int = 700

    def can_execute(self, state: "AppState") -> bool:
        return (state.images.has_next and
                not state.anim.open_active)

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        # Actual switch_to is called from imagura2.py
        log(f"[CMD] NavigateNext: {state.index} -> {state.index + 1}")
        return True


@dataclass
class NavigatePrev(Command):
    """Navigate to previous image."""
    animate: bool = True
    duration_ms: int = 700

    def can_execute(self, state: "AppState") -> bool:
        return (state.images.has_prev and
                not state.anim.open_active)

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        log(f"[CMD] NavigatePrev: {state.index} -> {state.index - 1}")
        return True


@dataclass
class NavigateToIndex(Command):
    """Navigate to specific index (e.g., from gallery click)."""
    target_index: int
    animate: bool = True
    duration_ms: int = 700

    def can_execute(self, state: "AppState") -> bool:
        return (0 <= self.target_index < state.images.count and
                self.target_index != state.index and
                not state.anim.open_active)

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        log(f"[CMD] NavigateToIndex: {state.index} -> {self.target_index}")
        return True


# ═══════════════════════════════════════════════════════════════════════════
# Zoom Commands
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ZoomIn(Command):
    """Zoom in by step amount."""
    step: float = 0.05
    anchor: Tuple[int, int] = (0, 0)

    def can_execute(self, state: "AppState") -> bool:
        return (state.cache.curr is not None and
                not state.anim.open_active and
                not state.anim.toggle_zoom_active)

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        log(f"[CMD] ZoomIn: step={self.step} anchor={self.anchor}")
        return True


@dataclass
class ZoomOut(Command):
    """Zoom out by step amount."""
    step: float = 0.05
    anchor: Tuple[int, int] = (0, 0)

    def can_execute(self, state: "AppState") -> bool:
        return (state.cache.curr is not None and
                not state.anim.open_active and
                not state.anim.toggle_zoom_active)

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        log(f"[CMD] ZoomOut: step={self.step} anchor={self.anchor}")
        return True


@dataclass
class WheelZoom(Command):
    """Zoom with mouse wheel."""
    delta: float  # Positive = zoom in, negative = zoom out
    anchor: Tuple[int, int] = (0, 0)
    step_multiplier: float = 0.15

    def can_execute(self, state: "AppState") -> bool:
        return (state.cache.curr is not None and
                not state.anim.open_active and
                not state.anim.toggle_zoom_active)

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        log(f"[CMD] WheelZoom: delta={self.delta} anchor={self.anchor}")
        return True


class ToggleZoom(Command):
    """Cycle through zoom states: Fit -> 1:1 -> User -> Fit."""

    def can_execute(self, state: "AppState") -> bool:
        return (state.cache.curr is not None and
                not state.anim.toggle_zoom_active)

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        log(f"[CMD] ToggleZoom: current_state={state.zoom_state_cycle}")
        return True


# ═══════════════════════════════════════════════════════════════════════════
# Pan Commands
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class StartPan(Command):
    """Start panning operation."""
    mouse_x: float
    mouse_y: float

    def can_execute(self, state: "AppState") -> bool:
        return (state.cache.curr is not None and
                state.is_zoomed and
                not state.anim.open_active and
                not state.anim.toggle_zoom_active and
                not state.input.is_panning)

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        state.input.start_pan(
            self.mouse_x, self.mouse_y,
            state.view.offx, state.view.offy
        )
        log(f"[CMD] StartPan: pos=({self.mouse_x:.0f}, {self.mouse_y:.0f})")
        return True


@dataclass
class UpdatePan(Command):
    """Update pan position during drag."""
    mouse_x: float
    mouse_y: float

    def can_execute(self, state: "AppState") -> bool:
        return state.input.is_panning

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        # View update happens in imagura2.py with clamp_pan
        return True


class EndPan(Command):
    """End panning operation."""

    def can_execute(self, state: "AppState") -> bool:
        return state.input.is_panning

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        state.input.end_pan()
        log(f"[CMD] EndPan")
        return True


# ═══════════════════════════════════════════════════════════════════════════
# UI Toggle Commands
# ═══════════════════════════════════════════════════════════════════════════

class ToggleHUD(Command):
    """Toggle HUD display."""

    def execute(self, state: "AppState") -> bool:
        state.ui.toggle_hud()
        log(f"[CMD] ToggleHUD: now={state.show_hud}")
        return True


class ToggleFilename(Command):
    """Toggle filename display."""

    def execute(self, state: "AppState") -> bool:
        state.ui.toggle_filename()
        log(f"[CMD] ToggleFilename: now={state.show_filename}")
        return True


class CycleBackground(Command):
    """Cycle through background modes."""

    def execute(self, state: "AppState") -> bool:
        old_mode = state.bg_mode_index
        state.ui.cycle_bg_mode()
        log(f"[CMD] CycleBackground: {old_mode} -> {state.bg_mode_index}")
        return True


# ═══════════════════════════════════════════════════════════════════════════
# Gallery Commands
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class GalleryScroll(Command):
    """Scroll gallery with wheel."""
    delta: float  # Positive = scroll left, negative = scroll right

    def execute(self, state: "AppState") -> bool:
        n = state.images.count
        if n == 0:
            return False

        base = state.gallery.target_index if state.gallery.has_pending_target else state.index
        if self.delta > 0:
            target = max(0, int(base) - 1)
        else:
            target = min(n - 1, int(base) + 1)

        state.gallery.target_index = target
        log(f"[CMD] GalleryScroll: target={target}")
        return True


@dataclass
class GalleryClick(Command):
    """Click on gallery thumbnail."""
    target_index: int

    def can_execute(self, state: "AppState") -> bool:
        return (0 <= self.target_index < state.images.count and
                self.target_index != state.index)

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        log(f"[CMD] GalleryClick: index={self.target_index}")
        return True


# ═══════════════════════════════════════════════════════════════════════════
# Image Transformation Commands
# ═══════════════════════════════════════════════════════════════════════════

class RotateClockwise(Command):
    """Rotate current image 90 degrees clockwise."""

    def can_execute(self, state: "AppState") -> bool:
        return state.cache.curr is not None

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        log(f"[CMD] RotateClockwise")
        return True


class RotateCounterClockwise(Command):
    """Rotate current image 90 degrees counter-clockwise."""

    def can_execute(self, state: "AppState") -> bool:
        return state.cache.curr is not None

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        log(f"[CMD] RotateCounterClockwise")
        return True


class FlipHorizontal(Command):
    """Flip current image horizontally."""

    def can_execute(self, state: "AppState") -> bool:
        return state.cache.curr is not None

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        log(f"[CMD] FlipHorizontal")
        return True


class CopyToClipboard(Command):
    """Copy current image to clipboard."""

    def can_execute(self, state: "AppState") -> bool:
        return (state.cache.curr is not None and
                state.index < len(state.current_dir_images))

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        log(f"[CMD] CopyToClipboard")
        return True


# ═══════════════════════════════════════════════════════════════════════════
# Context Menu Commands
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ShowContextMenu(Command):
    """Show context menu at position."""
    x: int
    y: int

    def execute(self, state: "AppState") -> bool:
        state.ui.context_menu.show(self.x, self.y)
        log(f"[CMD] ShowContextMenu at ({self.x}, {self.y})")
        return True


class HideContextMenu(Command):
    """Hide context menu."""

    def execute(self, state: "AppState") -> bool:
        state.ui.context_menu.hide()
        log(f"[CMD] HideContextMenu")
        return True


@dataclass
class ContextMenuClick(Command):
    """Click on context menu item."""
    item_index: int

    def can_execute(self, state: "AppState") -> bool:
        menu = state.ui.context_menu
        return menu.visible and 0 <= self.item_index < len(menu.items)

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        item = state.ui.context_menu.items[self.item_index]
        log(f"[CMD] ContextMenuClick: {item.label}")
        state.ui.context_menu.hide()
        return True


# ═══════════════════════════════════════════════════════════════════════════
# Toolbar Commands
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ToolbarButtonClick(Command):
    """Click on toolbar button."""
    button_index: int

    def can_execute(self, state: "AppState") -> bool:
        toolbar = state.ui.toolbar
        return 0 <= self.button_index < len(toolbar.buttons)

    def execute(self, state: "AppState") -> bool:
        if not self.can_execute(state):
            return False
        button = state.ui.toolbar.buttons[self.button_index]
        log(f"[CMD] ToolbarButtonClick: {button.tooltip}")
        return True


# ═══════════════════════════════════════════════════════════════════════════
# App Control Commands
# ═══════════════════════════════════════════════════════════════════════════

class CloseApp(Command):
    """Close the application."""

    def execute(self, state: "AppState") -> bool:
        log(f"[CMD] CloseApp")
        return True


# ═══════════════════════════════════════════════════════════════════════════
# Command Queue (optional, for undo/redo support)
# ═══════════════════════════════════════════════════════════════════════════

class CommandQueue:
    """Queue for executing commands with optional history tracking."""

    def __init__(self, max_history: int = 100):
        self._history: list = []
        self._max_history = max_history

    def execute(self, command: Command, state: "AppState") -> bool:
        """Execute a command and optionally track it."""
        if not command.can_execute(state):
            return False

        result = command.execute(state)
        if result and self._max_history > 0:
            self._history.append(command)
            if len(self._history) > self._max_history:
                self._history.pop(0)

        return result

    @property
    def history(self) -> list:
        """Get command history."""
        return self._history.copy()

    def clear_history(self) -> None:
        """Clear command history."""
        self._history.clear()
