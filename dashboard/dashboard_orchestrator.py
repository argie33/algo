"""Dashboard event loop orchestration separated from rendering."""

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class DashboardOrchestrator:
    """Manages event loop, state, input handling, and display updates.

    Separates orchestration from rendering logic.
    """

    def __init__(self, compact: bool, data_source: str = "AWS"):
        self.compact = compact
        self.data_source = data_source
        self.frame = 0
        self.view_mode = "normal"
        self.watch_interval: int | None = None
        self.last_load_time: float | None = None
        self.refreshing = False
        self.elapsed = 0.0
        self._state_lock = threading.Lock()

    def update_frame(self) -> None:
        """Increment frame counter for animation."""
        with self._state_lock:
            self.frame += 1
            if self.frame > 1_000_000:
                self.frame = 0

    def update_view_mode(self, key: str) -> None:
        """Update view mode based on keyboard input."""
        key_map = {
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
        with self._state_lock:
            if key in key_map:
                target = key_map[key]
                self.view_mode = "normal" if self.view_mode == target else target

    def get_snapshot(self) -> dict[str, Any]:
        """Get thread-safe snapshot of state."""
        with self._state_lock:
            return {
                "frame": self.frame,
                "view_mode": self.view_mode,
                "watch_interval": self.watch_interval,
                "last_load_time": self.last_load_time,
                "refreshing": self.refreshing,
                "elapsed": self.elapsed,
                "compact": self.compact,
                "data_source": self.data_source,
            }

    def set_state(self, **kwargs: Any) -> None:
        """Set state values thread-safely."""
        with self._state_lock:
            for key, value in kwargs.items():
                if hasattr(self, key):
                    setattr(self, key, value)
