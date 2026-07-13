#!/usr/bin/env python3
"""Request Router - Route API requests to appropriate handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class RequestRouter:
    """Routes incoming API requests to appropriate handlers."""

    def __init__(self) -> None:
        self.routes: dict[str, Callable[..., Any]] = {}

    def register(self, path: str, handler: Callable[..., Any]) -> None:
        """Register a route handler.

        Args:
            path: API path pattern
            handler: Handler function
        """
        self.routes[path] = handler

    def route(self, path: str, method: str, params: dict[str, Any]) -> Any:
        """Route request to appropriate handler.

        Args:
            path: API path
            method: HTTP method
            params: Request parameters

        Returns:
            Handler result
        """
        if path not in self.routes:
            return {"error": "not_found", "status": 404}

        handler = self.routes[path]
        return handler(method=method, params=params)
