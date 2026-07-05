"""Watch mode state containers."""

import threading
from typing import Any


class LoadState:
    """Thread-safe state container for data loading and display."""

    def __init__(self) -> None:
        self.result: dict[str, Any] | None = None
        self.elapsed: float = 0.0


class WatchState:
    """Thread-safe state container for watch mode with frame tracking.

    Uses mutex lock to prevent concurrent updates to result field from
    reload threads racing with render threads reading the same data.
    """

    def __init__(self) -> None:
        self._result: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self.elapsed: float = 0.0
        self.loading: bool = True
        self.last_load: float = 0.0
        self.frame: int = 0
        self.error: str | None = None

    @property
    def result(self) -> dict[str, Any] | None:
        """Get current result snapshot with lock protection."""
        with self._lock:
            return self._result

    @result.setter
    def result(self, value: dict[str, Any] | None) -> None:
        """Set result with lock protection."""
        with self._lock:
            self._result = value
