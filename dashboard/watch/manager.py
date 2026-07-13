"""Watch mode management and control."""

import threading
import time
from collections.abc import Callable
from typing import Any

from dashboard.utilities import logger


class ReloadManager:
    """Manages data reload operations and thread lifecycle."""

    def __init__(self, load_fn: Callable[[], dict[str, Any]]) -> None:
        self.load_fn = load_fn
        self.active_threads: list[threading.Thread] = []
        self.active_threads_lock = threading.Lock()
        self.shutdown = threading.Event()

    def cleanup_dead_threads(self) -> None:
        """Remove finished threads from active_threads list."""
        with self.active_threads_lock:
            threads_to_remove = []
            for thread in self.active_threads:
                if not thread.is_alive():
                    threads_to_remove.append(thread)
            for thread in threads_to_remove:
                self.active_threads.remove(thread)

    def spawn_reload(self, on_complete: Callable[[dict[str, Any]], None]) -> threading.Thread:
        """Spawn a reload thread."""

        def reload_task() -> None:
            try:
                t0 = time.monotonic()
                result = self.load_fn()
                elapsed = time.monotonic() - t0
                on_complete({"result": result, "elapsed": elapsed, "error": None})
            except Exception as e:
                logger.error(f"Reload thread error: {type(e).__name__}: {e}")
                on_complete({"result": None, "elapsed": 0.0, "error": f"{type(e).__name__}: {e}"})

        thread = threading.Thread(target=reload_task, daemon=False)
        thread.start()
        with self.active_threads_lock:
            self.active_threads.append(thread)
        return thread

    def shutdown_all(self, timeout: int = 60) -> None:
        """Gracefully shutdown all active threads."""
        self.shutdown.set()
        with self.active_threads_lock:
            threads_to_join = self.active_threads[:]
        for thread in threads_to_join:
            if thread:
                thread.join(timeout=timeout)
                if thread.is_alive():
                    logger.error(
                        "Thread abandoned after 60s timeout in watch mode (data load exceeded graceful shutdown window)"
                    )


class WatchModeController:
    """Controls watch mode interactions and view mode toggling."""

    def __init__(self) -> None:
        self.view_mode = "normal"
        self.key_map = {
            "p": "positions",
            "s": "signals",
            "h": "health",
            "r": "sectors",
            "t": "trades",
            "e": "economic",
            "f": "portfolio",
            "b": "circuit",
            "x": "exposure",
            "m": "market",
            "d": "errors",
        }

    def handle_keypress(self, key: str) -> None:
        """Handle keypress input for view mode changes."""
        if key in self.key_map:
            target = self.key_map[key]
            self.view_mode = "normal" if self.view_mode == target else target

    def get_view_mode(self) -> str:
        return self.view_mode

    def should_reload(self, last_load_time: float, interval: int, is_loading: bool) -> bool:
        """Determine if data should be reloaded."""
        if is_loading:
            return False
        return (time.monotonic() - last_load_time) >= interval
