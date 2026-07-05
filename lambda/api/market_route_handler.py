#!/usr/bin/env python3
"""Market Route Handler - Polymorphic market route handlers (eliminates switch statements)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class MarketHandlerStrategy(ABC):
    """Base strategy for market route handlers."""

    @abstractmethod
    def handle(self, cur: Any) -> dict[str, Any]:
        """Handle request and return response."""
        ...


class MarketStatusHandler(MarketHandlerStrategy):
    """Handle /api/market/status endpoint."""

    def handle(self, cur: Any) -> dict[str, Any]:
        """Fetch and return current market status."""
        cur.execute("""
            SELECT date, market_trend, market_stage, vix_level, put_call_ratio
            FROM market_health_daily ORDER BY date DESC LIMIT 1
        """)
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                "Market health data unavailable: no rows in market_health_daily table. "
                "Cannot return market status without valid daily market health data."
            )
        return {"status": 200, "data": dict(row)}


class MarketBreadthHandler(MarketHandlerStrategy):
    """Handle /api/market/breadth endpoint."""

    def handle(self, cur: Any) -> dict[str, Any]:
        """Fetch and return market breadth data."""
        cur.execute("""
            SELECT date, advances, declines, unchanged
            FROM breadth_daily ORDER BY date DESC LIMIT 12
        """)
        return {"status": 200, "data": [dict(row) for row in cur.fetchall()]}


class MarketHandlerFactory:
    """Factory for creating market route handlers."""

    _handlers = {
        "status": MarketStatusHandler(),
        "breadth": MarketBreadthHandler(),
    }

    @classmethod
    def get_handler(cls, endpoint: str) -> MarketHandlerStrategy:
        """Get handler for market endpoint."""
        return cls._handlers.get(endpoint.lower(), cls._handlers["status"])
