"""Thread-safe stats tracking for data loaders."""

import threading
from typing import Any


class LoaderStats:
    """Thread-safe stats container for loader execution."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stats: dict[str, Any] = {
            "symbols_processed": 0,
            "symbols_skipped_by_watermark": 0,
            "symbols_failed": 0,
            "rows_fetched": 0,
            "rows_dedup_skipped": 0,
            "rows_quality_dropped": 0,
            "rows_inserted": 0,
            "duration_sec": 0.0,
            "source_distribution": {},
        }

    def increment(self, key: str, delta: int = 1) -> None:
        """Increment a counter stat."""
        with self._lock:
            if key in self._stats and isinstance(self._stats[key], int):
                self._stats[key] += delta
            else:
                self._stats[key] = delta

    def add_source(self, source: str, count: int = 1) -> None:
        """Add to source distribution."""
        with self._lock:
            self._stats["source_distribution"][source] = self._stats["source_distribution"].get(source, 0) + count

    def set(self, key: str, value: Any) -> None:
        """Set a stat value."""
        with self._lock:
            self._stats[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get a stat value."""
        with self._lock:
            return self._stats.get(key, default)

    def __getitem__(self, key: str) -> Any:
        with self._lock:
            return self._stats[key]

    def __setitem__(self, key: str, value: Any) -> None:
        with self._lock:
            self._stats[key] = value

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._stats

    def to_dict(self) -> dict[str, Any]:
        """Get a snapshot of all stats."""
        with self._lock:
            return dict(self._stats)
