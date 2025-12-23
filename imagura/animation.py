"""Animation system - unified non-blocking animations."""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Any
from enum import Enum, auto

from .types import ViewParams
from .math_utils import lerp, ease_out_quad, ease_in_out_cubic
from .logging import now, log


class AnimationType(Enum):
    """Types of animations for priority handling."""
    OPEN = auto()      # App opening animation
    SWITCH = auto()    # Image switching animation
    ZOOM = auto()      # Zoom level change
    TOGGLE_ZOOM = auto()  # Cycle zoom state (F key / double-click)
    BG_FADE = auto()   # Background opacity fade


@dataclass
class Animation(ABC):
    """Base class for all animations."""
    start_time: float = field(default_factory=now)
    duration_ms: float = 0.0
    finished: bool = False

    @property
    def progress(self) -> float:
        """Get animation progress (0.0 to 1.0)."""
        if self.duration_ms <= 0:
            return 1.0
        elapsed = (now() - self.start_time) * 1000.0
        return min(1.0, elapsed / self.duration_ms)

    @property
    def is_complete(self) -> bool:
        """Check if animation has completed."""
        return self.progress >= 1.0 or self.finished

    @abstractmethod
    def get_type(self) -> AnimationType:
        """Get the type of this animation."""
        pass

    def finish(self) -> None:
        """Mark animation as finished."""
        self.finished = True


@dataclass
class OpenAnimation(Animation):
    """Animation for app opening - scale and fade in."""
    from_scale: float = 0.6
    to_scale: float = 0.95
    from_alpha: float = 0.4
    to_alpha: float = 1.0
    from_bg_opacity: float = 0.0
    to_bg_opacity: float = 0.5

    def get_type(self) -> AnimationType:
        return AnimationType.OPEN

    def get_current_scale_factor(self) -> float:
        """Get current scale factor (relative to fit scale)."""
        t = ease_out_quad(self.progress)
        return lerp(self.from_scale, self.to_scale, t)

    def get_current_alpha(self) -> float:
        """Get current image alpha."""
        t = ease_out_quad(self.progress)
        return lerp(self.from_alpha, self.to_alpha, t)

    def get_current_bg_opacity(self) -> float:
        """Get current background opacity."""
        t = ease_out_quad(self.progress)
        return lerp(self.from_bg_opacity, self.to_bg_opacity, t)


@dataclass
class SwitchAnimation(Animation):
    """Animation for switching between images - slide transition."""
    direction: int = 1  # 1 = right, -1 = left
    prev_view: ViewParams = field(default_factory=ViewParams)
    curr_view: ViewParams = field(default_factory=ViewParams)

    def get_type(self) -> AnimationType:
        return AnimationType.SWITCH

    def get_offset_progress(self) -> float:
        """Get eased progress for offset calculation."""
        return ease_in_out_cubic(self.progress)

    def get_prev_alpha(self) -> float:
        """Get alpha for previous image (fading out)."""
        return 1.0 - ease_in_out_cubic(self.progress)

    def get_curr_alpha(self) -> float:
        """Get alpha for current image (fading in)."""
        return ease_in_out_cubic(self.progress)


@dataclass
class ZoomAnimation(Animation):
    """Animation for smooth zoom changes."""
    from_view: ViewParams = field(default_factory=ViewParams)
    to_view: ViewParams = field(default_factory=ViewParams)

    def get_type(self) -> AnimationType:
        return AnimationType.ZOOM

    def get_current_view(self) -> ViewParams:
        """Get interpolated view parameters."""
        t = ease_out_quad(self.progress)
        return ViewParams(
            scale=lerp(self.from_view.scale, self.to_view.scale, t),
            offx=lerp(self.from_view.offx, self.to_view.offx, t),
            offy=lerp(self.from_view.offy, self.to_view.offy, t),
        )


@dataclass
class ToggleZoomAnimation(Animation):
    """Animation for cycling zoom states (Fit -> 1:1 -> User)."""
    from_view: ViewParams = field(default_factory=ViewParams)
    to_view: ViewParams = field(default_factory=ViewParams)
    target_state: int = 0  # 0=1:1, 1=fit, 2=user

    def get_type(self) -> AnimationType:
        return AnimationType.TOGGLE_ZOOM

    def get_current_view(self) -> ViewParams:
        """Get interpolated view parameters."""
        t = ease_in_out_cubic(self.progress)
        return ViewParams(
            scale=lerp(self.from_view.scale, self.to_view.scale, t),
            offx=lerp(self.from_view.offx, self.to_view.offx, t),
            offy=lerp(self.from_view.offy, self.to_view.offy, t),
        )


@dataclass
class BgFadeAnimation(Animation):
    """Animation for background opacity changes."""
    from_opacity: float = 0.0
    to_opacity: float = 1.0

    def get_type(self) -> AnimationType:
        return AnimationType.BG_FADE

    def get_current_opacity(self) -> float:
        """Get current opacity value."""
        t = ease_out_quad(self.progress)
        return lerp(self.from_opacity, self.to_opacity, t)


class AnimationController:
    """Manages all active animations."""

    def __init__(self):
        self._animations: List[Animation] = []
        self._on_complete_callbacks: dict = {}

    @property
    def has_animations(self) -> bool:
        """Check if any animations are running."""
        return len(self._animations) > 0

    def get_animation(self, anim_type: AnimationType) -> Optional[Animation]:
        """Get currently running animation of specified type."""
        for anim in self._animations:
            if anim.get_type() == anim_type:
                return anim
        return None

    def is_running(self, anim_type: AnimationType) -> bool:
        """Check if an animation of the specified type is running."""
        return self.get_animation(anim_type) is not None

    def start(self, animation: Animation, on_complete: Optional[Callable] = None) -> None:
        """Start a new animation, replacing any existing of same type."""
        anim_type = animation.get_type()

        # Remove existing animation of same type
        self._animations = [a for a in self._animations if a.get_type() != anim_type]

        # Add new animation
        self._animations.append(animation)

        if on_complete:
            self._on_complete_callbacks[anim_type] = on_complete

        log(f"[ANIM] Started {anim_type.name} duration={animation.duration_ms}ms")

    def cancel(self, anim_type: AnimationType) -> None:
        """Cancel animation of specified type."""
        self._animations = [a for a in self._animations if a.get_type() != anim_type]
        self._on_complete_callbacks.pop(anim_type, None)
        log(f"[ANIM] Cancelled {anim_type.name}")

    def cancel_all(self) -> None:
        """Cancel all running animations."""
        self._animations.clear()
        self._on_complete_callbacks.clear()

    def update(self) -> List[Animation]:
        """Update all animations and return list of completed ones."""
        completed = []
        still_running = []

        for anim in self._animations:
            if anim.is_complete:
                completed.append(anim)
                anim_type = anim.get_type()
                callback = self._on_complete_callbacks.pop(anim_type, None)
                if callback:
                    try:
                        callback(anim)
                    except Exception as e:
                        log(f"[ANIM][ERR] Callback failed for {anim_type.name}: {e!r}")
                log(f"[ANIM] Completed {anim_type.name}")
            else:
                still_running.append(anim)

        self._animations = still_running
        return completed


# Convenience functions for creating common animations

def create_open_animation(
    duration_ms: float,
    from_scale: float = 0.6,
    to_scale: float = 0.95,
    target_bg_opacity: float = 0.5
) -> OpenAnimation:
    """Create an opening animation."""
    return OpenAnimation(
        duration_ms=duration_ms,
        from_scale=from_scale,
        to_scale=to_scale,
        to_bg_opacity=target_bg_opacity,
    )


def create_switch_animation(
    duration_ms: float,
    direction: int,
    prev_view: ViewParams,
    curr_view: ViewParams
) -> SwitchAnimation:
    """Create a switch animation."""
    return SwitchAnimation(
        duration_ms=duration_ms,
        direction=direction,
        prev_view=prev_view.copy() if hasattr(prev_view, 'copy') else ViewParams(prev_view.scale, prev_view.offx, prev_view.offy),
        curr_view=curr_view.copy() if hasattr(curr_view, 'copy') else ViewParams(curr_view.scale, curr_view.offx, curr_view.offy),
    )


def create_zoom_animation(
    duration_ms: float,
    from_view: ViewParams,
    to_view: ViewParams
) -> ZoomAnimation:
    """Create a zoom animation."""
    return ZoomAnimation(
        duration_ms=duration_ms,
        from_view=from_view.copy() if hasattr(from_view, 'copy') else ViewParams(from_view.scale, from_view.offx, from_view.offy),
        to_view=to_view.copy() if hasattr(to_view, 'copy') else ViewParams(to_view.scale, to_view.offx, to_view.offy),
    )


def create_toggle_zoom_animation(
    duration_ms: float,
    from_view: ViewParams,
    to_view: ViewParams,
    target_state: int
) -> ToggleZoomAnimation:
    """Create a toggle zoom animation (F key / double-click)."""
    return ToggleZoomAnimation(
        duration_ms=duration_ms,
        from_view=from_view.copy() if hasattr(from_view, 'copy') else ViewParams(from_view.scale, from_view.offx, from_view.offy),
        to_view=to_view.copy() if hasattr(to_view, 'copy') else ViewParams(to_view.scale, to_view.offx, to_view.offy),
        target_state=target_state,
    )
