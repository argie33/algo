#!/usr/bin/env python3
"""AuditManager - position monitoring audit logging."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import psycopg2

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class AuditManager:
    """Handles audit logging for position monitoring decisions."""

    def __init__(self, config: Any = None) -> None:
        """Initialize audit manager with config.

        Args:
            config: Algorithm configuration

        Raises:
            ValueError: If config is None (audit logging requires configuration)
        """
        if config is None:
            raise ValueError(
                "AuditManager requires explicit config parameter. "
                "Silent fallback to empty dict would log audit entries without configuration validation. "
                "Cannot execute audit logging without required config parameters. "
                "Pass config from orchestrator or provide explicit configuration."
            )
        self.config = config

    def get_position_history(self, symbol: str, lookback_days: int = 30, cur: Any = None) -> list[dict[str, Any]]:
        """Retrieve recent position review history.

        Args:
            symbol: Ticker symbol
            lookback_days: How many days back to query
            cur: Database cursor (optional, creates if not provided)

        Returns:
            List of audit entries

        Raises:
            RuntimeError: If position history cannot be retrieved
        """
        try:
            if cur is None:
                with DatabaseContext("read") as cursor:
                    return self._fetch_history(symbol, lookback_days, cursor)
            else:
                return self._fetch_history(symbol, lookback_days, cur)
        except Exception as e:
            raise RuntimeError(f"Cannot retrieve position history for {symbol}: {e}") from e

    def _fetch_history(self, symbol: str, lookback_days: int, cur: Any) -> list[dict[str, Any]]:
        cur.execute(
            """
            SELECT review_date, data FROM position_monitor_audit
            WHERE symbol = %s AND review_date > NOW() - INTERVAL '%s days'
            ORDER BY review_date DESC
            LIMIT %s
            """,
            (symbol, lookback_days, 100),
        )
        rows = cur.fetchall()
        return [
            {
                "date": str(row[0]),
                "data": json.loads(row[1]) if isinstance(row[1], str) else row[1],
            }
            for row in rows
        ]

    def log_trade(self, trade: dict[str, Any]) -> None:
        """Log a trade action.

        Args:
            trade: Trade dict with symbol, action, quantity, price, etc.
        """
        logger.info(f"Trade logged: {trade}")

    def log_halt(self, reason: str) -> None:
        """Log a halt event.

        Args:
            reason: Reason for halt
        """
        logger.info(f"Halt logged: {reason}")

    def get_history(self) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "AuditManager.get_history() requires explicit parameters. "
            "Use get_position_history(symbol, lookback_days, cur) instead to retrieve position review history. "
            "This prevents silent empty-list fallback that could mask audit trail gaps."
        )
