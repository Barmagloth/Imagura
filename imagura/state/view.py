"""View state - current view parameters, zoom state."""

from __future__ import annotations
from dataclasses import dataclass, field

from ..types import ViewParams


@dataclass
class ViewState:
    """State for view/zoom parameters."""
    view: ViewParams = field(default_factory=ViewParams)
    last_fit_view: ViewParams = field(default_factory=ViewParams)
    zoom_state_cycle: int = 1  # 0=1:1, 1=fit, 2=user
    is_zoomed: bool = False

    @property
    def scale(self) -> float:
        """Current zoom scale."""
        return self.view.scale

    @property
    def offset(self) -> tuple[float, float]:
        """Current view offset."""
        return (self.view.offx, self.view.offy)

    def is_at_fit(self, tolerance: float = 0.01) -> bool:
        """Check if view is at fit scale."""
        return abs(self.view.scale - self.last_fit_view.scale) < tolerance

    def is_at_1to1(self, tolerance: float = 0.01) -> bool:
        """Check if view is at 1:1 scale."""
        return abs(self.view.scale - 1.0) < tolerance

    def update_zoom_state(self) -> None:
        """Update zoom state based on current scale."""
        self.is_zoomed = (self.view.scale > self.last_fit_view.scale)
        if self.is_at_1to1():
            self.zoom_state_cycle = 0
        elif self.is_at_fit():
            self.zoom_state_cycle = 1
        else:
            self.zoom_state_cycle = 2
