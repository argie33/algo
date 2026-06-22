#!/usr/bin/env python3
"""Centralized VIX data accessor - eliminates duplication across loaders and APIs.

VIX fetching logic was previously scattered across:
- loaders/load_market_health_daily.py::_fetch_vix_data()
- loaders/market_health_fetchers.py::_fetch_vix_data()
- lambda/api/routes/economic.py::_get_vix()
- lambda/api/routes/sentiment.py::_get_vix_data()
- loaders/compute_circuit_breakers.py::_compute_vix_level()

This module consolidates all VIX access patterns into a single source of truth,
reducing Shotgun Surgery when VIX schema or fetch logic changes.
"""

import logging
from typing import Any

from utils.loaders import execute_query, fetch_latest

logger = logging.getLogger(__name__)


class VIXAccessor:
    """Centralized accessor for VIX data from market_health_daily table."""

    @staticmethod
    def get_latest_vix(timeout: int = 30) -> dict[str, Any] | None:
        """Get latest VIX level from market_health_daily.

        Used by:
        - Orchestration phase: CB4 circuit breaker check
        - Risk calculations: VIX-based position sizing
        - API sentiment endpoint: Market fear/greed signal

        Returns:
            Dict with vix_level and date, or None if unavailable
        """
        row = fetch_latest("market_health_daily", "date", timeout=timeout)
        if row and row.get("vix_level") is not None:
            return {
                "date": row.get("date"),
                "vix_level": float(row["vix_level"]),
            }
        return None

    @staticmethod
    def get_vix_history(days: int = 100, timeout: int = 30) -> list[dict[str, Any]]:
        """Get historical VIX data from market_health_daily.

        Used by:
        - Economic API endpoint: /api/economic/vix
        - Dashboard VIX charts
        - Risk analysis and reporting

        Args:
            days: Number of days of history to fetch (default 100)
            timeout: Database query timeout in seconds

        Returns:
            List of dicts with date and vix_level
        """
        rows = execute_query(
            """
            SELECT date, vix_level, put_call_ratio, market_trend, market_stage
            FROM market_health_daily
            WHERE vix_level IS NOT NULL
            ORDER BY date DESC
            LIMIT %s
        """,
            (days,),
            timeout=timeout,
        )
        return [
            {
                "date": r.get("date"),
                "vix_level": float(r["vix_level"]) if r.get("vix_level") else None,
                "put_call_ratio": float(r["put_call_ratio"]) if r.get("put_call_ratio") else None,
                "market_trend": r.get("market_trend"),
                "market_stage": r.get("market_stage"),
            }
            for r in rows
            if r
        ]

    @staticmethod
    def compute_market_signal(vix_level: float) -> str:
        """Compute market sentiment signal from VIX level.

        Consolidated from duplicate logic in sentiment.py and multiple risk modules.

        Args:
            vix_level: Current VIX value

        Returns:
            Signal string: "fear" (VIX > 25), "neutral" (15-25), "greed" (< 15)
        """
        if vix_level > 25:
            return "fear"
        elif vix_level > 15:
            return "neutral"
        else:
            return "greed"

    @staticmethod
    def get_vix_with_signal(timeout: int = 30) -> dict[str, Any] | None:
        """Get latest VIX + computed market sentiment signal.

        Used by:
        - Sentiment API: /api/sentiment/vix
        - Dashboard market gauge

        Returns:
            Dict with latest VIX data and computed signal
        """
        latest = VIXAccessor.get_latest_vix(timeout=timeout)
        if not latest or latest.get("vix_level") is None:
            return None

        vix = latest["vix_level"]
        return {
            "date": latest.get("date"),
            "vix_level": vix,
            "signal": VIXAccessor.compute_market_signal(vix),
        }
