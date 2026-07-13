"""Watch mode state containers."""

import threading
from typing import Any


class LoadState:
    """Thread-safe state container for data loading and display.

    Uses mutex lock to protect concurrent access to result/elapsed from
    background load threads and main render thread.
    """

    def __init__(self) -> None:
        self._result: dict[str, Any] | None = None
        self._elapsed: float = 0.0
        self._lock = threading.Lock()

    @property
    def result(self) -> dict[str, Any] | None:
        with self._lock:
            return self._result

    @result.setter
    def result(self, value: dict[str, Any] | None) -> None:
        with self._lock:
            self._result = value

    @property
    def elapsed(self) -> float:
        with self._lock:
            return self._elapsed

    @elapsed.setter
    def elapsed(self, value: float) -> None:
        with self._lock:
            self._elapsed = value


class WatchState:
    """Thread-safe state container for watch mode with frame tracking.

    All fields use mutex lock to prevent concurrent updates from
    reload threads racing with render threads reading the same data.
    """

    def __init__(self) -> None:
        self._result: dict[str, Any] | None = None
        self._elapsed: float = 0.0
        self._loading: bool = True
        self._last_load: float = 0.0
        self._frame: int = 0
        self._error: str | None = None
        self._lock = threading.Lock()

    @property
    def result(self) -> dict[str, Any] | None:
        with self._lock:
            return self._result

    @result.setter
    def result(self, value: dict[str, Any] | None) -> None:
        with self._lock:
            self._result = value

    @property
    def elapsed(self) -> float:
        with self._lock:
            return self._elapsed

    @elapsed.setter
    def elapsed(self, value: float) -> None:
        with self._lock:
            self._elapsed = value

    @property
    def loading(self) -> bool:
        with self._lock:
            return self._loading

    @loading.setter
    def loading(self, value: bool) -> None:
        with self._lock:
            self._loading = value

    @property
    def last_load(self) -> float:
        with self._lock:
            return self._last_load

    @last_load.setter
    def last_load(self, value: float) -> None:
        with self._lock:
            self._last_load = value

    @property
    def frame(self) -> int:
        with self._lock:
            return self._frame

    @frame.setter
    def frame(self, value: int) -> None:
        with self._lock:
            self._frame = value

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    @error.setter
    def error(self, value: str | None) -> None:
        with self._lock:
            self._error = value
