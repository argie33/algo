#!/usr/bin/env python3
"""
Trade Audit Logger - Comprehensive logging for every trade decision.

Tracks:
- Why each position was sized (drawdown multiplier, exposure tier, phase mult, VIX mult)
- Why stop loss was chosen (MA, swing, ATR, base-type)
- All multipliers applied in cascade
- Entry quality scores (all 6 tiers)
"""

import json
import logging
from datetime import date as _date
from datetime import datetime, timezone
from typing import Any

import psycopg2

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class TradeAuditLogger:
    """Log every trade decision with full reasoning."""

    def get_exit_rule_distribution(self, days: int = 30) -> dict[str, int]:
        """Get which exit rules fire most (diagnostic)."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT exit_rule, COUNT(*) as count
                    FROM algo_exit_rules_distribution
                    WHERE created_at >= NOW() - INTERVAL '%d days'
                    GROUP BY exit_rule
                    ORDER BY count DESC
                """
                    % days
                )

                result = {}
                for row in cur.fetchall():
                    result[row[0]] = row[1]
                return result
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"CRITICAL: Exit rule distribution failed due to database error: {e}")
            raise RuntimeError(
                f"Cannot compute exit rule distribution. Database error: {e}. "
                f"Check database connectivity and exit_rules table schema."
            ) from e

    def log_portfolio_snapshot_audit(
        self,
        snapshot_date: Any,
        total_portfolio_value: float,
        total_cash: float,
        position_count: int,
        unrealized_pnl_total: float,
        unrealized_pnl_pct: float,
    ) -> None:
        """Log portfolio snapshot to audit trail for traceability.

        Tracks: who created/updated snapshot, when, with what values.
        """
        try:
            audit_msg = (
                f"Portfolio snapshot: {snapshot_date} | "
                f"Value: ${total_portfolio_value:,.2f} | "
                f"Cash: ${total_cash:,.2f} | "
                f"Positions: {position_count} | "
                f"P&L: ${unrealized_pnl_total:,.2f} ({unrealized_pnl_pct:+.2f}%)"
            )
            logger.info(f"[AUDIT] {audit_msg}")

            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO algo_audit_log (
                        action_type, action_date, symbol, actor, details
                    ) VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        "PORTFOLIO_SNAPSHOT",
                        snapshot_date,
                        str(snapshot_date),
                        "reconciliation",
                        json.dumps({"message": audit_msg}),
                    ),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"Portfolio snapshot audit log failed - cannot record snapshot (safety gate failed): {e}"
            ) from e

    def log_position_reconciliation_audit(
        self,
        symbol: str,
        action: str,
        quantity_before: int,
        quantity_after: int,
        reason: str,
    ) -> None:
        """Log position reconciliation corrections for audit trail."""
        try:
            audit_msg = (
                f"Position {action}: {symbol} | Before: {quantity_before} | After: {quantity_after} | Reason: {reason}"
            )
            logger.info(f"[AUDIT] {audit_msg}")

            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO algo_audit_log (
                        action_type, action_date, symbol, actor, details
                    ) VALUES (%s, CURRENT_TIMESTAMP, %s, %s, %s)
                    """,
                    (
                        "POSITION_RECONCILIATION",
                        symbol,
                        "reconciliation",
                        json.dumps({"message": audit_msg}),
                    ),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"Position reconciliation audit log failed - cannot record reconciliation (safety gate failed): {e}"
            ) from e
