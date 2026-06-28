"""Threaded CPU-side content loading.

The loader deliberately knows nothing about raylib textures. Worker threads load
CPU data only; callbacks are marshalled back to the UI thread with poll_ui_events.
"""

from __future__ import annotations

from collections import deque
from queue import Empty, PriorityQueue
from threading import Lock, Thread
from typing import Callable, Deque, List

from ..config import ASYNC_WORKERS, IDLE_THRESHOLD_SECONDS
from ..logging import log, now
from ..types import LoadPriority, LoadTask, UIEvent


class AsyncContentLoader:
    """Priority-based background loader with UI-thread callback delivery."""

    def __init__(self, loader_func: Callable[[str], object], workers: int = ASYNC_WORKERS):
        self.task_queue: PriorityQueue[LoadTask] = PriorityQueue()
        self.loader_func = loader_func
        self.running = True
        self.ui_events: Deque[UIEvent] = deque()
        self.ui_lock = Lock()
        self.workers: List[Thread] = []

        for _ in range(max(1, int(workers))):
            worker = Thread(target=self._worker_loop, daemon=True)
            worker.start()
            self.workers.append(worker)

    def _worker_loop(self) -> None:
        while self.running:
            try:
                task = self.task_queue.get(timeout=0.1)
            except Empty:
                continue

            result = None
            error = None

            try:
                result = self.loader_func(task.path)
            except Exception as exc:
                error = exc

            self.push_ui_event(task.callback, (task.path, result, error))
            self.task_queue.task_done()

    def push_ui_event(self, callback: Callable, args: tuple) -> None:
        """Queue a callback to run on the main/UI thread."""
        with self.ui_lock:
            self.ui_events.append(UIEvent(callback, args))

    # Compatibility for the old imagura2.py call site while it is being migrated.
    _push_ui_event = push_ui_event

    def poll_ui_events(self, max_events: int = 100) -> None:
        events_to_process = []
        with self.ui_lock:
            count = 0
            while self.ui_events and count < max_events:
                events_to_process.append(self.ui_events.popleft())
                count += 1

        for event in events_to_process:
            try:
                event.callback(*event.args)
            except Exception as exc:
                log(f"[UI_EVENT][ERR] {exc!r}")

    def submit(self, path: str, priority: LoadPriority, callback: Callable) -> None:
        self.task_queue.put(LoadTask(path, priority, callback, now()))

    def shutdown(self) -> None:
        self.running = False
        for worker in self.workers:
            worker.join(timeout=1.0)


class IdleDetector:
    """Small helper for UI elements that depend on recent input activity."""

    def __init__(self, threshold: float = IDLE_THRESHOLD_SECONDS):
        self.threshold = threshold
        self.last_activity = now()

    def mark_activity(self) -> None:
        self.last_activity = now()

    def is_idle(self) -> bool:
        return (now() - self.last_activity) >= self.threshold
