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

    def log_position_review(
        self,
        symbol: str,
        review_data: dict[str, Any],
        current_date: Any,
        cur: Any,
    ) -> None:
        """Log position review to audit table.

        Args:
            symbol: Ticker symbol
            review_data: Review result dict with scores, flags, recommendation
            current_date: Current date
            cur: Database cursor

        Raises:
            RuntimeError: If audit logging fails (audit trail is critical for compliance)
        """
        # Explicit handling of optional enrichment fields
        flags = review_data.get("flags")
        if flags is None:
            logger.debug(f"[AUDIT_MANAGER] {symbol}: flags field missing from review_data (optional enrichment)")
            flags = {}

        audit_entry = {
            "symbol": symbol,
            "review_date": str(current_date),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "health_score": review_data.get("health_score"),
            "recommendation": review_data.get("recommendation"),
            "flags": flags,
            "stop_price": review_data.get("stop_price"),
        }

        try:
            cur.execute(
                """
                INSERT INTO position_monitor_audit
                (symbol, review_date, data, created_at)
                VALUES (%s, %s, %s, NOW())
                """,
                (symbol, current_date, json.dumps(audit_entry)),
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"CRITICAL: Audit log failed for {symbol} position review. "
                f"Audit trail is required for compliance and risk tracking. "
                f"Database error: {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"CRITICAL: Audit log failed for {symbol} position review: {e}") from e

    def log_stop_adjustment(
        self,
        symbol: str,
        old_stop: float,
        new_stop: float,
        reason: str,
        current_date: Any,
        cur: Any,
    ) -> None:
        """Log stop loss adjustment to audit table.

        Args:
            symbol: Ticker symbol
            old_stop: Previous stop price
            new_stop: New stop price
            reason: Reason for adjustment
            current_date: Current date
            cur: Database cursor

        Raises:
            RuntimeError: If audit logging fails (risk management audit trail is critical)
        """
        try:
            cur.execute(
                """
                INSERT INTO position_stop_adjustments
                (symbol, adjustment_date, old_stop, new_stop, reason, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                (symbol, current_date, old_stop, new_stop, reason),
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"CRITICAL: Audit log failed for {symbol} stop adjustment "
                f"(${old_stop:.2f} -> ${new_stop:.2f}). "
                f"Risk management requires audit trail. "
                f"Database error: {e}"
            ) from e
        except Exception as e:
            raise RuntimeError(f"CRITICAL: Audit log failed for {symbol} stop adjustment: {e}") from e

    def log_exit_recommendation(
        self,
        symbol: str,
        reason: str,
        recommendation: str,
        current_date: Any,
        cur: Any,
    ) -> None:
        """Log early exit recommendation to audit table.

        Args:
            symbol: Ticker symbol
            reason: Reason for recommendation
            recommendation: Exit recommendation (HOLD, MONITOR_CLOSELY, CONSIDER_EXIT)
            current_date: Current date
            cur: Database cursor

        Raises:
            RuntimeError: If audit logging fails (exit decisions require audit trail)
        """
        if recommendation == "CONSIDER_EXIT":
            try:
                cur.execute(
                    """
                    INSERT INTO position_exit_recommendations
                    (symbol, recommendation_date, reason, created_at)
                    VALUES (%s, %s, %s, NOW())
                    """,
                    (symbol, current_date, reason),
                )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                raise RuntimeError(
                    f"CRITICAL: Audit log failed for {symbol} exit recommendation. "
                    f"Exit decision audit trail is required. "
                    f"Database error: {e}"
                ) from e
            except Exception as e:
                raise RuntimeError(f"CRITICAL: Audit log failed for {symbol} exit recommendation: {e}") from e

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
        """Helper to fetch history from cursor."""
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
        """Get audit history.

        Returns:
            List of audit entries
        """
        return []
