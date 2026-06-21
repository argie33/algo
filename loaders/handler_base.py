#!/usr/bin/env python3
"""Common interface for loader handlers.

All loader handlers follow the pattern:
- Initialize with a loader reference
- Execute via run() method
- Return structured results
"""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LoaderHandler(Protocol):
    """Protocol defining the interface all loader handlers must implement."""

    loader: Any
    """Reference to the parent loader for accessing config and utilities."""

    def run(self, *args: Any, **kwargs: Any) -> Any:
        """Execute handler logic.

        Returns structured data (list of dicts, dict, etc.) depending on handler.
        All handlers should be idempotent and handle missing/stale data gracefully.
        """
        ...
