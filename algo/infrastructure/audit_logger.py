#!/usr/bin/env python3
"""
Trade Audit Logger - Comprehensive logging for every trade decision.

Tracks:
- Why each position was sized (drawdown multiplier, exposure tier, phase mult, VIX mult)
- Why stop loss was chosen (MA, swing, ATR, base-type)
- All multipliers applied in cascade
- Entry quality scores (all 6 tiers)
"""

import logging
from datetime import date as _date
from datetime import datetime, timezone
from typing import Any

import psycopg2

from utils.db import DatabaseContext

logger = logging.getLogger(__name__)


class TradeAuditLogger:
    """Log every trade decision with full reasoning."""

    def log_position_sizing_audit(
        self,
        symbol: str,
        signal_date: _date,
        entry_price: float,
        stop_loss_price: float,
        base_shares: int,
        final_shares: int,
        position_size_pct: float,
        multipliers: dict[str, float],
        reasons: dict[str, str],
    ) -> None:
        """Log complete position sizing decision with all multipliers.

        Args:
            symbol: Stock symbol
            signal_date: Date signal was generated
            entry_price: Entry price per share
            stop_loss_price: Stop loss price
            base_shares: Shares before multipliers
            final_shares: Shares after all multipliers
            position_size_pct: Final position size as % of portfolio
            multipliers: Dict of multiplier names and values
                {
                    'base_risk_pct': 0.75,
                    'drawdown_adjustment': 0.5,
                    'exposure_tier_multiplier': 0.75,
                    'vix_caution_multiplier': 0.75,
                    'phase_multiplier': 0.5,
                }
            reasons: Dict of multiplier reasons
                {
                    'drawdown_adjustment': 'At -10% drawdown',
                    'exposure_tier_multiplier': 'CAUTION tier (high losses)',
                    'vix_caution_multiplier': 'VIX 28 (caution zone 25-35)',
                    'phase_multiplier': 'Late Stage 2 phase',
                }
        """
        try:
            # Calculate cascade effect
            cascade = 1.0
            cascade_str = "1.0 (baseline)"
            multiplier_list = []

            for key in [
                "base_risk_pct",
                "drawdown_adjustment",
                "exposure_tier_multiplier",
                "vix_caution_multiplier",
                "phase_multiplier",
            ]:
                mult = multipliers.get(key, 1.0)
                if mult != 1.0:
                    cascade *= mult
                    reason = reasons.get(key, "")
                    multiplier_list.append(f"{key}={mult:.2f}x ({reason})")

            cascade_str = f"{cascade:.2f}x cascade"

            audit_msg = (
                f"[POSITION SIZING] {symbol}: "
                f"${entry_price:.2f}/${stop_loss_price:.2f} (1R={entry_price - stop_loss_price:.2f}) | "
                f"{base_shares} shares → {final_shares} shares ({cascade_str}) | "
                f"Position {position_size_pct:.1f}% of portfolio | "
                f"Multipliers: {', '.join(multiplier_list)}"
            )
            logger.info(audit_msg)

            # Persist to database for dashboard visibility
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO algo_position_sizing_audit (
                        symbol, signal_date, entry_price, stop_loss_price,
                        base_shares, final_shares, position_size_pct,
                        cascade_multiplier, multipliers_json, reasons_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        symbol,
                        signal_date,
                        entry_price,
                        stop_loss_price,
                        base_shares,
                        final_shares,
                        position_size_pct,
                        cascade,
                        str(multipliers),
                        str(reasons),
                        datetime.now(timezone.utc),
                    ),
                )

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"Position sizing audit log failed - cannot record sizing (safety gate failed): {e}"
            ) from e

    def log_stop_loss_calculation(
        self,
        symbol: str,
        signal_date: _date,
        entry_price: float,
        stop_loss_price: float,
        stop_method: str,
        stop_reasoning: str,
        candidates: dict[str, float | None],
    ) -> None:
        """Log why stop loss was calculated as it was.

        Args:
            symbol: Stock symbol
            signal_date: Date signal was generated
            entry_price: Entry price
            stop_loss_price: Chosen stop loss
            stop_method: Method used ('base_type', 'best_of_ma_swing_atr', 'none', etc.)
            stop_reasoning: Human-readable reasoning
            candidates: Dict of candidate stops evaluated
                {
                    'sma_50': 142.50,
                    'swing_low_10d': 141.80,
                    'atr_2x': 143.00,
                    'base_type_cup_handle': None,
                    'floor_stop_8pct': 140.00,
                }
        """
        try:
            if entry_price is None or stop_loss_price is None:
                return  # Cannot compute distance without valid prices
            distance_pct = ((entry_price - stop_loss_price) / entry_price) * 100

            # Build candidate list for logging
            candidates_str = " | ".join([f"{k}=${v:.2f}" for k, v in candidates.items() if v is not None])

            audit_msg = (
                f"[STOP LOSS] {symbol}: Entry ${entry_price:.2f} → Stop ${stop_loss_price:.2f} "
                f"({distance_pct:.2f}% risk) | "
                f"Method: {stop_method} | "
                f"Reason: {stop_reasoning} | "
                f"Candidates: {candidates_str}"
            )
            logger.info(audit_msg)

            # Persist to database
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO algo_stop_loss_audit (
                        symbol, signal_date, entry_price, stop_loss_price,
                        distance_pct, stop_method, stop_reasoning,
                        candidates_json, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        symbol,
                        signal_date,
                        entry_price,
                        stop_loss_price,
                        distance_pct,
                        stop_method,
                        stop_reasoning,
                        str(candidates),
                        datetime.now(timezone.utc),
                    ),
                )

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Stop loss audit log failed - cannot record stop loss (safety gate failed): {e}") from e

    def log_exit_execution(
        self,
        symbol: str,
        position_id: str,
        exit_reason: str,
        exit_rule: str,
        entry_price: float,
        exit_price: float,
        pnl_dollars: float,
        pnl_pct: float,
        r_multiple: float,
    ) -> None:
        """Log exit execution with rule that triggered.

        Args:
            symbol: Stock symbol
            position_id: Position ID
            exit_reason: Human-readable reason
            exit_rule: Which rule triggered (STOP, T1, T2, T3, TIME, MINERVINI_BREAK, etc.)
            entry_price: Entry price
            exit_price: Exit price
            pnl_dollars: P&L in dollars
            pnl_pct: P&L as %
            r_multiple: Profit in R-multiples
        """
        try:
            audit_msg = (
                f"[EXIT] {symbol}: {exit_rule} | "
                f"${entry_price:.2f} → ${exit_price:.2f} | "
                f"P&L ${pnl_dollars:+.2f} ({pnl_pct:+.2f}%) ({r_multiple:+.2f}R) | "
                f"{exit_reason}"
            )
            logger.info(audit_msg)

            # Track exit rule distribution
            with DatabaseContext("write") as cur:
                cur.execute(
                    """
                    INSERT INTO algo_exit_rules_distribution (
                        symbol, position_id, exit_rule, exit_reason,
                        entry_price, exit_price, pnl_dollars, pnl_pct, r_multiple,
                        created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        symbol,
                        position_id,
                        exit_rule,
                        exit_reason,
                        entry_price,
                        exit_price,
                        pnl_dollars,
                        pnl_pct,
                        r_multiple,
                        datetime.now(timezone.utc),
                    ),
                )

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Exit execution audit log failed - cannot record exit (safety gate failed): {e}") from e

    def get_position_sizing_summary(self, days: int = 30) -> dict[str, Any]:
        """Get position sizing statistics for dashboard."""
        try:
            with DatabaseContext("read") as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as total_trades,
                        AVG(cascade_multiplier) as avg_cascade_mult,
                        MIN(cascade_multiplier) as min_cascade_mult,
                        MAX(cascade_multiplier) as max_cascade_mult,
                        AVG(position_size_pct) as avg_position_size_pct
                    FROM algo_position_sizing_audit
                    WHERE created_at >= NOW() - INTERVAL '%d days'
                """
                    % days
                )

                row = cur.fetchone()
                if row:
                    return {
                        "total_trades": row[0],
                        "avg_cascade_multiplier": float(row[1]) if row[1] is not None else 1.0,
                        "min_cascade_multiplier": float(row[2]) if row[2] is not None else 1.0,
                        "max_cascade_multiplier": float(row[3]) if row[3] is not None else 1.0,
                        "avg_position_size_pct": float(row[4]) if row[4] is not None else None,
                    }
            raise RuntimeError("No position sizing data available")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Position sizing summary query failed: {e}") from e

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
                        action_type, symbol, actor, details
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        "PORTFOLIO_SNAPSHOT",
                        str(snapshot_date),
                        "reconciliation",
                        audit_msg,
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
                        action_type, symbol, actor, details
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        "POSITION_RECONCILIATION",
                        symbol,
                        "reconciliation",
                        audit_msg,
                    ),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"Position reconciliation audit log failed - cannot record reconciliation (safety gate failed): {e}"
            ) from e
