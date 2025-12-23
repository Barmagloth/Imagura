"""Logging utilities with timing and frame tracking."""

from __future__ import annotations
import sys
import time
from typing import Optional


class Logger:
    """Application logger with timestamps and frame counts."""

    def __init__(self):
        self._start_time: float = time.perf_counter()
        self._frame: int = 0

    @property
    def frame(self) -> int:
        """Current frame number."""
        return self._frame

    @frame.setter
    def frame(self, value: int) -> None:
        """Set current frame number."""
        self._frame = value

    def increment_frame(self) -> None:
        """Increment frame counter."""
        self._frame += 1

    @property
    def elapsed(self) -> float:
        """Seconds since logger was created."""
        return time.perf_counter() - self._start_time

    def log(self, msg: str) -> None:
        """Log a message with timestamp and frame number."""
        line = f"[{self.elapsed:7.3f}s F{self._frame:06d}] {msg}\n"
        try:
            sys.stdout.write(line)
            sys.stdout.flush()
        except Exception:
            try:
                sys.stderr.write(line)
                sys.stderr.flush()
            except Exception:
                pass

    def __call__(self, msg: str) -> None:
        """Shorthand for log()."""
        self.log(msg)


# Global logger instance
_logger: Optional[Logger] = None


def get_logger() -> Logger:
    """Get or create the global logger instance."""
    global _logger
    if _logger is None:
        _logger = Logger()
    return _logger


def log(msg: str) -> None:
    """Log a message using the global logger."""
    get_logger().log(msg)


def get_frame() -> int:
    """Get current frame count."""
    return get_logger().frame


def set_frame(frame: int) -> None:
    """Set current frame count."""
    get_logger().frame = frame


def increment_frame() -> None:
    """Increment frame counter."""
    get_logger().increment_frame()


# Time utilities
def now() -> float:
    """Get current time in seconds (high precision)."""
    return time.perf_counter()
