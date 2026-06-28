"""Watch mode state containers."""

from typing import Any


class LoadState:
    """Thread-safe state container for data loading and display."""

    def __init__(self) -> None:
        self.result: dict[str, Any] | None = None
        self.elapsed: float = 0.0


class WatchState:
    """Thread-safe state container for watch mode with frame tracking."""

    def __init__(self) -> None:
        self.result: dict[str, Any] | None = None
        self.elapsed: float = 0.0
        self.loading: bool = True
        self.last_load: float = 0.0
        self.frame: int = 0
        self.error: str | None = None
