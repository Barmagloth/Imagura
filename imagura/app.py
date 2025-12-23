"""Application - main loop orchestrator.

The Application class provides a clean, modular main loop that coordinates:
- Input handling (via InputHandler)
- Command execution
- State updates (animations, loading, etc.)
- Rendering (via Renderer)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Callable, List
import os
import sys
import atexit
import traceback

from .state import AppState
from .renderer import Renderer, get_renderer
from .input_handler import InputHandler, get_input_handler
from .commands import Command, CloseApp, NavigateNext, NavigatePrev, NavigateToIndex
from .commands import ZoomIn, ZoomOut, WheelZoom, ToggleZoom
from .commands import StartPan, UpdatePan, EndPan
from .commands import ToggleHUD, ToggleFilename, CycleBackground
from .commands import GalleryScroll
from .rl_compat import rl
from .config import TARGET_FPS, ANIM_SWITCH_KEYS_MS
from .logging import log, now, increment_frame, get_frame
from .types import ViewParams


@dataclass
class Application:
    """
    Main application orchestrator.

    Provides a clean separation between:
    - Input → Commands
    - Commands → State changes
    - State → Rendering

    Usage:
        app = Application()
        app.initialize(start_path)
        app.run()
    """

    state: AppState = field(default_factory=AppState)
    renderer: Renderer = field(default_factory=get_renderer)
    input_handler: InputHandler = field(default_factory=get_input_handler)
    running: bool = False

    # Callbacks for actions that require access to external functions
    # (These bridge to imagura2.py functions during transition period)
    on_switch_to: Optional[Callable[[int, bool, int], None]] = None
    on_start_zoom_animation: Optional[Callable[[ViewParams], None]] = None
    on_start_toggle_zoom: Optional[Callable[[], None]] = None
    on_preload_neighbors: Optional[Callable[[int, bool], None]] = None

    # Update functions (from imagura2.py)
    update_functions: List[Callable[[AppState], None]] = field(default_factory=list)

    def initialize(self, start_path: Optional[str] = None) -> bool:
        """
        Initialize the application.

        This sets up the window, loads initial images, etc.
        Returns True if initialization successful.
        """
        # Window initialization happens in imagura2.py for now
        # This method is for future use when we fully migrate
        log("[APP] Application initialized")
        return True

    def run(self) -> None:
        """
        Run the main loop.

        This is the clean main loop structure that can be used
        once all components are migrated.
        """
        self.running = True
        log("[APP] Starting main loop")

        try:
            while self.running:
                self._frame()
        except Exception as e:
            log(f"[APP][CRITICAL] Unhandled exception: {e!r}")
            log(f"[APP][CRITICAL] Traceback:\n{traceback.format_exc()}")
        finally:
            self._cleanup()

    def _frame(self) -> None:
        """Execute a single frame."""
        # Check for window close
        if rl.WindowShouldClose():
            self.running = False
            return

        # 1. Poll input and generate commands
        commands = self.input_handler.poll(self.state)

        # 2. Execute commands
        for cmd in commands:
            self._execute_command(cmd)
            if not self.running:
                return

        # 3. Update state (animations, loading, etc.)
        self._update()

        # 4. Render
        self.renderer.draw_frame(self.state)

        # 5. Frame bookkeeping
        increment_frame()

    def _execute_command(self, cmd: Command) -> None:
        """Execute a single command."""
        if isinstance(cmd, CloseApp):
            log("[APP] CloseApp command received")
            self.running = False
            return

        if isinstance(cmd, (NavigateNext, NavigatePrev)):
            if cmd.can_execute(self.state):
                if self.on_switch_to:
                    target = self.state.index + (1 if isinstance(cmd, NavigateNext) else -1)
                    self.on_switch_to(target, cmd.animate, cmd.duration_ms)
                cmd.execute(self.state)
            return

        if isinstance(cmd, NavigateToIndex):
            if cmd.can_execute(self.state) and self.on_switch_to:
                self.on_switch_to(cmd.target_index, cmd.animate, cmd.duration_ms)
                cmd.execute(self.state)
            return

        if isinstance(cmd, (ZoomIn, ZoomOut)):
            if cmd.can_execute(self.state) and self.on_start_zoom_animation:
                # Calculate new view and start animation
                from .view_math import recompute_view_anchor_zoom as anchor_zoom
                from .view_math import clamp_pan

                ti = self.state.cache.curr
                if ti:
                    step = cmd.step if isinstance(cmd, ZoomIn) else -cmd.step
                    new_scale = self.state.view.scale * (1.0 + step)
                    nv = anchor_zoom(
                        self.state.view, new_scale, cmd.anchor,
                        ti.w, ti.h
                    )
                    nv = clamp_pan(nv, ti.w, ti.h,
                                  self.state.screenW, self.state.screenH)
                    self.on_start_zoom_animation(nv)
                    self.state.is_zoomed = (nv.scale > self.state.last_fit_view.scale)
                    self.state.zoom_state_cycle = 2
                cmd.execute(self.state)
            return

        if isinstance(cmd, WheelZoom):
            if cmd.can_execute(self.state) and self.on_start_zoom_animation:
                from .view_math import recompute_view_anchor_zoom as anchor_zoom
                from .view_math import clamp_pan

                ti = self.state.cache.curr
                if ti:
                    new_scale = self.state.view.scale * (1.0 + cmd.delta * cmd.step_multiplier)
                    nv = anchor_zoom(
                        self.state.view, new_scale, cmd.anchor,
                        ti.w, ti.h
                    )
                    nv = clamp_pan(nv, ti.w, ti.h,
                                  self.state.screenW, self.state.screenH)
                    self.on_start_zoom_animation(nv)
                    self.state.is_zoomed = (nv.scale > self.state.last_fit_view.scale)
                    self.state.zoom_state_cycle = 2
                cmd.execute(self.state)
            return

        if isinstance(cmd, ToggleZoom):
            if cmd.can_execute(self.state) and self.on_start_toggle_zoom:
                self.on_start_toggle_zoom()
                cmd.execute(self.state)
            return

        if isinstance(cmd, StartPan):
            cmd.execute(self.state)
            return

        if isinstance(cmd, UpdatePan):
            if cmd.can_execute(self.state):
                # Update view based on pan
                from .view_math import clamp_pan
                ti = self.state.cache.curr
                if ti:
                    new_offx, new_offy = self.state.input.get_panned_offset(
                        cmd.mouse_x, cmd.mouse_y
                    )
                    nv = ViewParams(
                        scale=self.state.view.scale,
                        offx=new_offx,
                        offy=new_offy
                    )
                    self.state.view = clamp_pan(nv, ti.w, ti.h,
                                               self.state.screenW, self.state.screenH)
            return

        if isinstance(cmd, EndPan):
            if cmd.can_execute(self.state):
                cmd.execute(self.state)
                # Save view after pan
                if self.state.cache.curr and self.state.index < len(self.state.current_dir_images):
                    path = self.state.current_dir_images[self.state.index]
                    self.state.images.save_view(path, self.state.view)
                    self.state.images.save_user_zoom(path, self.state.view)
                    self.state.zoom_state_cycle = 2
            return

        if isinstance(cmd, (ToggleHUD, ToggleFilename, CycleBackground)):
            cmd.execute(self.state)
            return

        if isinstance(cmd, GalleryScroll):
            from .logging import now
            cmd.execute(self.state)
            self.state.gallery_last_wheel_time = now()
            return

        # Default: just execute
        cmd.execute(self.state)

    def _update(self) -> None:
        """Update all state (animations, loading, etc.)."""
        # Call registered update functions
        for update_fn in self.update_functions:
            try:
                update_fn(self.state)
            except Exception as e:
                log(f"[APP][UPDATE][ERR] {e!r}")

    def _cleanup(self) -> None:
        """Clean up resources."""
        log("[APP] Starting cleanup")

        # Shutdown async loader
        if self.state.async_loader:
            log("[APP] Shutting down async loader")
            self.state.async_loader.shutdown()

        # Unload textures
        for ti in (self.state.cache.prev, self.state.cache.curr, self.state.cache.next):
            try:
                if ti and getattr(ti.tex, 'id', 0):
                    rl.UnloadTexture(ti.tex)
            except Exception:
                pass

        # Unload thumbnails
        for bt in list(self.state.thumb_cache.values()):
            try:
                if bt.texture:
                    rl.UnloadTexture(bt.texture)
            except Exception:
                pass

        try:
            log("[APP] Closing window")
            rl.CloseWindow()
        except Exception:
            pass

        log("[APP] Cleanup complete")

    def stop(self) -> None:
        """Stop the main loop."""
        self.running = False

    def register_update(self, fn: Callable[[AppState], None]) -> None:
        """Register an update function to be called each frame."""
        self.update_functions.append(fn)

    def unregister_update(self, fn: Callable[[AppState], None]) -> None:
        """Unregister an update function."""
        if fn in self.update_functions:
            self.update_functions.remove(fn)


# Singleton instance
_app: Optional[Application] = None


def get_app() -> Application:
    """Get the application instance."""
    global _app
    if _app is None:
        _app = Application()
    return _app


def create_app(state: Optional[AppState] = None) -> Application:
    """Create a new application instance."""
    global _app
    _app = Application(state=state or AppState())
    return _app
