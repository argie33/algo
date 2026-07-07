#!/usr/bin/env python3
"""Orchestrator diagnostics - surface root causes when trades don't execute.

CRITICAL: This module provides explicit fail-fast diagnostics for the orchestrator pipeline.
When trades are zero or signals are empty, operators need to know the EXACT root cause.

Used by Phase 7 (signal generation) and Phase 8 (entry execution) to log root causes
that prevent trading.
"""

import logging
from datetime import date as _date
from typing import Any

import psycopg2

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class OrchestratorDiagnostics:
    """Diagnose why orchestrator phases are not producing expected outputs."""

    @staticmethod
    def check_signal_generation_blockers(run_date: _date) -> dict[str, Any]:
        """Check if signal generation is blocked by missing upstream data.

        Returns dict with:
        - stock_scores: count of scores available
        - buy_sell_signals: count of BUY signals in lookback window
        - swing_scores: count of swing trader scores
        - circuit_breakers: whether entries are halted
        - data_completeness: highest data_completeness % in stock_scores
        """
        result = {
            "blocked": False,
            "blockers": [],
            "stock_scores": 0,
            "buy_sell_signals": 0,
            "swing_scores": 0,
            "circuit_breaker_halted": False,
            "data_completeness_min": 0.0,
            "data_completeness_avg": 0.0,
        }

        try:
            with DatabaseContext("read") as cur:
                # Count available stock scores
                cur.execute(
                    "SELECT COUNT(*) as total, AVG(data_completeness) as avg_comp FROM stock_scores WHERE composite_score > 0"
                )
                ss_row = cur.fetchone()
                result["stock_scores"] = ss_row[0] if ss_row else 0
                result["data_completeness_avg"] = float(ss_row[1]) if ss_row and ss_row[1] else 0.0

                if result["stock_scores"] == 0:
                    result["blockers"].append("No stock_scores with composite_score > 0")
                    result["blocked"] = True

                # Check for recent BUY signals
                cur.execute(
                    "SELECT COUNT(*) FROM buy_sell_daily WHERE signal = 'BUY' AND date >= %s - INTERVAL 7 AND date <= %s",
                    (run_date, run_date),
                )
                bs_row = cur.fetchone()
                result["buy_sell_signals"] = bs_row[0] if bs_row else 0

                if result["buy_sell_signals"] == 0:
                    result["blockers"].append("No BUY signals in last 7 days")
                    result["blocked"] = True

                # Check swing trader scores
                cur.execute(
                    "SELECT COUNT(*) FROM swing_trader_scores WHERE date <= %s AND score IS NOT NULL", (run_date,)
                )
                sw_row = cur.fetchone()
                result["swing_scores"] = sw_row[0] if sw_row else 0

                # Check circuit breaker status
                cur.execute(
                    "SELECT COUNT(*) FROM circuit_breaker_status WHERE status = 'TRIGGERED' AND check_date >= %s",
                    (run_date,),
                )
                cb_row = cur.fetchone()
                result["circuit_breaker_halted"] = (cb_row[0] if cb_row else 0) > 0

                if result["circuit_breaker_halted"]:
                    result["blockers"].append("Circuit breaker(s) triggered - entry execution halted")
                    result["blocked"] = True

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            result["blockers"].append(f"Database error checking signal generation: {e}")
            result["blocked"] = True

        return result

    @staticmethod
    def check_entry_execution_blockers(run_date: _date) -> dict[str, Any]:
        """Check if entry execution is blocked after signals are generated.

        Returns dict with:
        - signals_available: count of pending trade signals
        - max_positions: whether max position limit reached
        - insufficient_cash: whether cash prevents sizing
        - order_placement_errors: recent order errors
        """
        result = {
            "blocked": False,
            "blockers": [],
            "signals_available": 0,
            "max_positions_reached": False,
            "insufficient_cash": False,
            "order_placement_errors": 0,
        }

        try:
            with DatabaseContext("read") as cur:
                # Count pending trade signals
                cur.execute(
                    "SELECT COUNT(*) FROM algo_trades WHERE status = 'pending' AND created_at >= %s - INTERVAL 1 DAY",
                    (run_date,),
                )
                sig_row = cur.fetchone()
                result["signals_available"] = sig_row[0] if sig_row else 0

                # Check open positions count
                cur.execute("SELECT COUNT(*) FROM algo_positions WHERE is_open = TRUE")
                pos_row = cur.fetchone()
                open_positions = pos_row[0] if pos_row else 0

                # Assume max 10 positions (configurable per account)
                max_positions = 10
                if open_positions >= max_positions:
                    result["max_positions_reached"] = True
                    result["blockers"].append(f"Max positions reached ({open_positions}/{max_positions})")
                    result["blocked"] = True

                # Check cash availability
                cur.execute(
                    "SELECT total_cash FROM algo_portfolio_snapshots WHERE snapshot_date <= %s ORDER BY snapshot_date DESC LIMIT 1",
                    (run_date,),
                )
                cash_row = cur.fetchone()
                available_cash = float(cash_row[0]) if cash_row and cash_row[0] else 0.0

                if available_cash < 500:  # Minimum $500 per position
                    result["insufficient_cash"] = True
                    result["blockers"].append(
                        f"Insufficient cash (${available_cash:,.2f} available, need $500+ per position)"
                    )
                    result["blocked"] = True

                # Check for recent order placement errors
                cur.execute(
                    """
                    SELECT COUNT(*) FROM algo_audit_log
                    WHERE action_type = 'order_placement_error' AND action_date >= %s
                    """,
                    (run_date,),
                )
                err_row = cur.fetchone()
                result["order_placement_errors"] = err_row[0] if err_row else 0

                if result["order_placement_errors"] > 0:
                    result["blockers"].append(f"{result['order_placement_errors']} order placement errors in last 24h")

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            result["blockers"].append(f"Database error checking entry execution: {e}")
            result["blocked"] = True

        return result

    @staticmethod
    def check_growth_metrics_status() -> dict[str, Any]:
        """Check growth_metrics availability and data quality.

        Returns dict with:
        - total_stocks: count of stocks in growth_metrics
        - real_data_count: stocks with real growth data
        - unavailable_count: stocks marked data_unavailable
        - coverage_pct: percentage with real data
        - sample_unavailable: sample symbols lacking growth data
        """
        result = {
            "total_stocks": 0,
            "real_data_count": 0,
            "unavailable_count": 0,
            "coverage_pct": 0.0,
            "sample_unavailable": [],
            "healthy": False,
        }

        try:
            with DatabaseContext("read") as cur:
                # Get total count
                cur.execute("SELECT COUNT(*) FROM growth_metrics")
                total = cur.fetchone()[0] if cur.fetchone() else 0
                result["total_stocks"] = total

                if total == 0:
                    result["sample_unavailable"].append("growth_metrics table is EMPTY")
                    return result

                # Get real data count
                cur.execute(
                    "SELECT COUNT(*) FROM growth_metrics WHERE data_unavailable = FALSE OR data_unavailable IS NULL"
                )
                real = cur.fetchone()[0] if cur.fetchone() else 0
                result["real_data_count"] = real

                # Calculate coverage
                result["coverage_pct"] = (real / total * 100) if total > 0 else 0.0
                result["unavailable_count"] = total - real

                # Get sample of unavailable symbols
                cur.execute("SELECT DISTINCT symbol FROM growth_metrics WHERE data_unavailable = TRUE LIMIT 5")
                unavail_rows = cur.fetchall()
                result["sample_unavailable"] = [r[0] for r in unavail_rows] if unavail_rows else []

                # Health check
                result["healthy"] = result["coverage_pct"] >= 20.0  # Minimum 20% coverage

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            result["sample_unavailable"].append(f"Database error: {e}")

        return result

    @staticmethod
    def log_full_diagnostics(run_date: _date) -> None:
        """Log comprehensive diagnostics for troubleshooting."""
        logger.info("\n" + "=" * 80)
        logger.info("[ORCHESTRATOR DIAGNOSTICS] Comprehensive System Check")
        logger.info("=" * 80)

        # Signal generation blockers
        sig_blockers = OrchestratorDiagnostics.check_signal_generation_blockers(run_date)
        logger.info("\nSIGNAL GENERATION:")
        logger.info(f"  Stock Scores: {sig_blockers['stock_scores']} available")
        logger.info(f"  Data Completeness: avg {sig_blockers['data_completeness_avg']:.1f}%")
        logger.info(f"  BUY Signals: {sig_blockers['buy_sell_signals']} in last 7 days")
        logger.info(f"  Swing Scores: {sig_blockers['swing_scores']} available")
        logger.info(f"  Circuit Breaker Status: {'TRIGGERED' if sig_blockers['circuit_breaker_halted'] else 'OK'}")
        if sig_blockers["blockers"]:
            logger.warning(f"  BLOCKERS: {', '.join(sig_blockers['blockers'])}")

        # Entry execution blockers
        entry_blockers = OrchestratorDiagnostics.check_entry_execution_blockers(run_date)
        logger.info("\nENTRY EXECUTION:")
        logger.info(f"  Pending Signals: {entry_blockers['signals_available']}")
        logger.info(f"  Max Positions: {'REACHED' if entry_blockers['max_positions_reached'] else 'OK'}")
        logger.info(f"  Cash Availability: {'INSUFFICIENT' if entry_blockers['insufficient_cash'] else 'OK'}")
        logger.info(f"  Order Errors (24h): {entry_blockers['order_placement_errors']}")
        if entry_blockers["blockers"]:
            logger.warning(f"  BLOCKERS: {', '.join(entry_blockers['blockers'])}")

        # Growth metrics status
        gm_status = OrchestratorDiagnostics.check_growth_metrics_status()
        logger.info("\nGROWTH METRICS:")
        logger.info(f"  Total Stocks: {gm_status['total_stocks']}")
        logger.info(f"  Real Data: {gm_status['real_data_count']} ({gm_status['coverage_pct']:.1f}%)")
        logger.info(f"  Unavailable: {gm_status['unavailable_count']}")
        if gm_status["sample_unavailable"]:
            logger.warning(f"  Sample Unavailable: {', '.join(gm_status['sample_unavailable'][:5])}")

        logger.info("\n" + "=" * 80 + "\n")
