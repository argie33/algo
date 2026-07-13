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
from typing import Any

import psycopg2

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class TradeAuditLogger:
    """Log every trade decision with full reasoning."""

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
