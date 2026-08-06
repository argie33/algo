"""Specialized data integrity checks for orchestrator safety."""

import logging
from datetime import datetime
from typing import Any

import psycopg2

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)


class DataIntegrityChecker:
    """Check and repair data integrity issues that could halt the orchestrator."""

    @staticmethod
    def check_orphaned_positions() -> dict[str, Any]:
        """Detect and clean up positions with NULL or empty trade_ids_arr."""
        try:
            with DatabaseContext("write") as cur:
                # Find positions with orphaned trade references
                cur.execute("""
                SELECT COUNT(*) as count, STRING_AGG(DISTINCT symbol, ', ') as symbols
                FROM algo_positions
                WHERE status = 'open'
                  AND (trade_ids_arr IS NULL OR ARRAY_LENGTH(trade_ids_arr, 1) IS NULL)
                """)

                result = cur.fetchone()
                orphaned_count = result[0] if result else 0
                symbols = result[1] if result and len(result) > 1 else ""

                if orphaned_count > 0:
                    logger.critical(
                        f"[DATA_PATROL] Found {orphaned_count} positions with empty trade_ids_arr: {symbols}. "
                        "These positions are orphaned (not linked to trades) and will be closed for data safety."
                    )

                    # Close orphaned positions to prevent circuit breaker halt
                    cur.execute("""
                    UPDATE algo_positions
                    SET status = 'closed',
                        exit_reason = 'DATA_PATROL_orphaned_no_trade_ids',
                        closed_at = CURRENT_TIMESTAMP
                    WHERE status = 'open'
                      AND (trade_ids_arr IS NULL OR ARRAY_LENGTH(trade_ids_arr, 1) IS NULL)
                    """)

                    cleaned = cur.rowcount
                    logger.warning(f"[DATA_PATROL] Closed {cleaned} orphaned positions")
                    return {
                        "check": "orphaned_positions",
                        "status": "fixed",
                        "found": orphaned_count,
                        "cleaned": cleaned,
                        "symbols": symbols,
                    }

                return {
                    "check": "orphaned_positions",
                    "status": "ok",
                    "found": 0,
                }
        except Exception as e:
            logger.error(f"[DATA_PATROL] Orphaned position check failed: {e}")
            return {
                "check": "orphaned_positions",
                "status": "error",
                "error": str(e),
            }

    @staticmethod
    def check_dead_trade_references() -> dict[str, Any]:
        """Detect and clean up positions referencing non-existent trades."""
        try:
            with DatabaseContext("write") as cur:
                # Find positions with dead trade references (trade_ids_arr points to non-existent trades)
                # CRITICAL FIX: Use INNER JOIN to find positions where NO trades in their trade_ids_arr exist
                cur.execute("""
                SELECT DISTINCT p.position_id, p.symbol
                FROM algo_positions p
                WHERE p.status = 'open'
                  AND NOT EXISTS (
                    SELECT 1 FROM algo_trades t
                    WHERE t.trade_id::text = ANY(p.trade_ids_arr::text[])
                  )
                """)

                dead_refs = cur.fetchall()

                if dead_refs:
                    symbols_list = [row[1] for row in dead_refs]
                    logger.critical(
                        f"[DATA_PATROL] Found {len(dead_refs)} positions with dead trade references: "
                        f"{', '.join(symbols_list)}. "
                        "These positions reference trades that don't exist and will be closed."
                    )

                    # Close all positions with dead references
                    cur.execute("""
                    UPDATE algo_positions
                    SET status = 'closed',
                        exit_reason = 'DATA_PATROL_dead_trade_refs',
                        closed_at = CURRENT_TIMESTAMP
                    WHERE status = 'open'
                      AND NOT EXISTS (
                        SELECT 1 FROM algo_trades t
                        WHERE t.trade_id::text = ANY(algo_positions.trade_ids_arr::text[])
                      )
                    """)

                    cleaned = cur.rowcount
                    logger.warning(f"[DATA_PATROL] Closed {cleaned} positions with dead trade references")

                    return {
                        "check": "dead_trade_references",
                        "status": "fixed",
                        "positions_closed": cleaned,
                        "symbols": ", ".join(symbols_list),
                    }

                return {
                    "check": "dead_trade_references",
                    "status": "ok",
                    "positions_closed": 0,
                }
        except Exception as e:
            logger.error(f"[DATA_PATROL] Dead trade reference check failed: {e}")
            return {
                "check": "dead_trade_references",
                "status": "error",
                "error": str(e),
            }

    @staticmethod
    def check_incomplete_position_data() -> dict[str, Any]:
        """Detect and close positions with incomplete critical fields."""
        try:
            with DatabaseContext("write") as cur:
                # Check for positions missing required fields
                cur.execute("""
                SELECT position_id, symbol,
                       entry_price IS NULL as missing_entry,
                       current_stop_price IS NULL as missing_stop,
                       quantity IS NULL OR quantity = 0 as bad_qty
                FROM algo_positions
                WHERE status = 'open'
                  AND (entry_price IS NULL
                       OR current_stop_price IS NULL
                       OR quantity IS NULL
                       OR quantity = 0)
                """)

                incomplete = cur.fetchall()

                if incomplete:
                    logger.critical(
                        f"[DATA_PATROL] Found {len(incomplete)} positions with incomplete data. "
                        "Missing critical fields (entry_price, stop_loss_price, or quantity). "
                        "These positions cannot be safely managed and will be closed."
                    )

                    # Close positions with incomplete data
                    for pos_id, symbol, missing_entry, missing_stop, bad_qty in incomplete:
                        reasons = []
                        if missing_entry:
                            reasons.append("no_entry_price")
                        if missing_stop:
                            reasons.append("no_stop_loss")
                        if bad_qty:
                            reasons.append("bad_quantity")

                        reason_str = ", ".join(reasons)
                        logger.warning(f"[DATA_PATROL] Closing {symbol}: {reason_str}")

                        cur.execute("""
                        UPDATE algo_positions
                        SET status = 'closed',
                            exit_reason = %s,
                            closed_at = CURRENT_TIMESTAMP
                        WHERE position_id = %s
                        """, (f"DATA_PATROL_incomplete_{reason_str}", pos_id))

                    return {
                        "check": "incomplete_position_data",
                        "status": "fixed",
                        "positions_closed": len(incomplete),
                        "symbols": ", ".join([row[1] for row in incomplete]),
                    }

                return {
                    "check": "incomplete_position_data",
                    "status": "ok",
                    "positions_closed": 0,
                }
        except Exception as e:
            logger.error(f"[DATA_PATROL] Incomplete position data check failed: {e}")
            return {
                "check": "incomplete_position_data",
                "status": "error",
                "error": str(e),
            }

    @staticmethod
    def check_incomplete_trade_data() -> dict[str, Any]:
        """Detect open trades with incomplete critical fields."""
        try:
            with DatabaseContext("write") as cur:
                # Check for incomplete trades
                cur.execute("""
                SELECT trade_id, symbol, COUNT(*) as missing_fields
                FROM (
                    SELECT trade_id, symbol,
                           CASE WHEN entry_price IS NULL THEN 'entry_price' END,
                           CASE WHEN stop_loss_price IS NULL THEN 'stop_loss_price' END,
                           CASE WHEN entry_quantity IS NULL AND quantity IS NULL THEN 'quantity' END
                    FROM algo_trades
                    WHERE status NOT IN ('exited', 'closed')
                      AND (entry_price IS NULL
                           OR stop_loss_price IS NULL
                           OR (entry_quantity IS NULL AND quantity IS NULL))
                ) sub
                WHERE sub IS NOT NULL
                GROUP BY trade_id, symbol
                """)

                incomplete_trades = cur.fetchall()

                if incomplete_trades:
                    logger.warning(
                        f"[DATA_PATROL] Found {len(incomplete_trades)} trades with incomplete data: "
                        f"{', '.join([row[1] for row in incomplete_trades])}. "
                        "These trades should be marked as closed to prevent risk calculation errors."
                    )

                    return {
                        "check": "incomplete_trade_data",
                        "status": "warning",
                        "trades_affected": len(incomplete_trades),
                        "symbols": ", ".join([row[1] for row in incomplete_trades]),
                    }

                return {
                    "check": "incomplete_trade_data",
                    "status": "ok",
                    "trades_affected": 0,
                }
        except Exception as e:
            logger.error(f"[DATA_PATROL] Incomplete trade data check failed: {e}")
            return {
                "check": "incomplete_trade_data",
                "status": "error",
                "error": str(e),
            }

    @staticmethod
    def verify_circuit_breaker_readiness() -> dict[str, Any]:
        """Run the same checks as circuit breaker to ensure we pass pre-execution."""
        try:
            with DatabaseContext("read") as cur:
                # Check 1: All open positions have stops
                cur.execute("""
                SELECT COUNT(*) FROM algo_positions
                WHERE status = 'open' AND current_stop_price IS NULL
                """)
                missing_stops = cur.fetchone()[0]

                # Check 2: Open positions count matches trade_ids_arr join
                cur.execute("""
                SELECT COUNT(*) FROM algo_positions p
                JOIN algo_trades t ON t.trade_id::text = ANY(p.trade_ids_arr::text[])
                WHERE p.status = 'open'
                """)
                positions_with_trades = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
                total_open = cur.fetchone()[0]

                orphaned = total_open - positions_with_trades

                if missing_stops > 0:
                    logger.critical(f"[DATA_PATROL] {missing_stops} open positions missing current_stop_price")
                    return {
                        "check": "circuit_breaker_readiness",
                        "status": "critical",
                        "missing_stops": missing_stops,
                        "ready": False,
                    }

                if orphaned > 0:
                    logger.critical(f"[DATA_PATROL] {orphaned} open positions orphaned (no trade join)")
                    return {
                        "check": "circuit_breaker_readiness",
                        "status": "critical",
                        "orphaned_positions": orphaned,
                        "ready": False,
                    }

                return {
                    "check": "circuit_breaker_readiness",
                    "status": "ok",
                    "total_open": total_open,
                    "ready": True,
                }
        except Exception as e:
            logger.error(f"[DATA_PATROL] Circuit breaker readiness check failed: {e}")
            return {
                "check": "circuit_breaker_readiness",
                "status": "error",
                "error": str(e),
                "ready": False,
            }

    @staticmethod
    def clear_stale_halt_flag() -> dict[str, Any]:
        """Clear halt flag if the underlying condition has been resolved."""
        try:
            with DatabaseContext("write") as cur:
                # First check if there's an active halt flag
                cur.execute("""
                SELECT halt_reason FROM algo_orchestrator_state
                WHERE key = 'halt_flag_active'
                LIMIT 1
                """)

                halt_row = cur.fetchone()
                if not halt_row:
                    return {
                        "check": "halt_flag_status",
                        "status": "ok",
                        "halt_active": False,
                    }

                halt_reason = halt_row[0] if halt_row else None

                # Check if the halt reason was about orphaned positions
                if halt_reason and "orphaned trade_ids_arr" in halt_reason:
                    # Re-verify if orphaned positions still exist
                    cur.execute("""
                    SELECT COUNT(*) FROM algo_positions p
                    WHERE p.status = 'open'
                      AND NOT EXISTS (
                        SELECT 1 FROM algo_trades t
                        WHERE t.trade_id::text = ANY(p.trade_ids_arr::text[])
                      )
                    """)

                    orphaned_count = cur.fetchone()[0]

                    if orphaned_count == 0:
                        # Halt reason no longer valid - clear the flag
                        logger.warning(
                            f"[DATA_PATROL] Clearing stale halt flag: '{halt_reason}'. "
                            "Underlying condition (orphaned positions) has been resolved."
                        )
                        cur.execute("""
                        DELETE FROM algo_orchestrator_state
                        WHERE key = 'halt_flag_active'
                        """)
                        return {
                            "check": "halt_flag_status",
                            "status": "cleared",
                            "reason_cleared": halt_reason,
                        }
                    else:
                        logger.critical(
                            f"[DATA_PATROL] Halt flag still valid: {orphaned_count} orphaned positions detected"
                        )
                        return {
                            "check": "halt_flag_status",
                            "status": "active",
                            "orphaned_count": orphaned_count,
                        }

                return {
                    "check": "halt_flag_status",
                    "status": "ok",
                    "halt_active": True,
                    "reason": halt_reason,
                }
        except Exception as e:
            logger.error(f"[DATA_PATROL] Halt flag check failed: {e}")
            return {
                "check": "halt_flag_status",
                "status": "error",
                "error": str(e),
            }

    @classmethod
    def run_all_checks(cls) -> dict[str, Any]:
        """Run all data integrity checks and return comprehensive report."""
        logger.info("[DATA_PATROL] Running comprehensive data integrity checks...")

        results = {
            "timestamp": datetime.now().isoformat(),
            "checks": {},
            "summary": {
                "total_issues_found": 0,
                "total_fixed": 0,
                "total_errors": 0,
            },
        }

        checks = [
            cls.check_orphaned_positions,
            cls.check_dead_trade_references,
            cls.check_incomplete_position_data,
            cls.check_incomplete_trade_data,
            cls.verify_circuit_breaker_readiness,
            cls.clear_stale_halt_flag,  # Must run AFTER fixing data issues
        ]

        for check_func in checks:
            result = check_func()
            check_name = result.get("check", check_func.__name__)
            results["checks"][check_name] = result

            if result.get("status") == "fixed":
                results["summary"]["total_fixed"] += result.get("found") or result.get("positions_closed") or 0
            elif result.get("status") == "error":
                results["summary"]["total_errors"] += 1

            if result.get("found") or result.get("positions_closed"):
                results["summary"]["total_issues_found"] += result.get("found") or result.get("positions_closed") or 0

        logger.info(f"[DATA_PATROL] Checks complete: {results['summary']['total_issues_found']} issues found, "
                   f"{results['summary']['total_fixed']} fixed, {results['summary']['total_errors']} errors")

        return results
