"""UI state - HUD, buttons, background."""

from __future__ import annotations
from dataclasses import dataclass

from ..config import BG_MODES


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
