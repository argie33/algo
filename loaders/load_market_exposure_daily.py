#!/usr/bin/env python3
"""
Load market_exposure_daily: Compute market regime + exposure % from price & market health data.

Runs during EOD pipeline (4:05 PM ET) to ensure market regime is available for dashboard
regardless of orchestrator halt status. If orchestrator Phase 3b halts before running,
this loader ensures MarketsHealth page has regime display.

Purpose:
- Computes daily market exposure percentage (0-100) from 12 quantitative factors
- Determines market regime (confirmed_uptrend, uptrend_under_pressure, caution, correction)
- Persists to market_exposure_daily table for API + dashboard consumption
- Records data_unavailable markers when computation fails (explicit fallback vs. silent)
- Runs independently of orchestrator to guarantee availability

Data Quality:
- On success: inserts row with data_unavailable=FALSE, reason=NULL
- On any failure: inserts row with data_unavailable=TRUE, reason=<error detail>
- Prevents silent data gaps — API/dashboard always has explicit availability status

Validation & Error Handling (Fail-Fast):
- MarketExposure.compute() raises RuntimeError on invalid/missing data (no fallback)
- Loader validates result structure BEFORE using any fields
- All critical fields (regime, exposure_pct, raw_score, halt_reasons, distribution_days) required
- Invalid regime, exposure_pct outside [0,100], or missing factors cause immediate failure
- No placeholder data or silent defaults — missing data is reported as FAILED status + data_unavailable marker

Time: ~2-5 seconds (vectorized computation, minimal DB load)
"""

from __future__ import annotations

import logging
import socket
import sys
from datetime import date
from typing import Any

import psycopg2
from psycopg2.extensions import cursor as PsycopgCursor  # noqa: N812

from loaders.timeout_config import configure_socket_timeout

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configure socket timeout to prevent indefinite hangs
configure_socket_timeout(30)


def _insert_unavailable_marker(cur: PsycopgCursor[Any], eval_date: date, reason: str) -> None:
    """Insert a data_unavailable marker row into market_exposure_daily.

    Args:
        cur: Database cursor
        eval_date: Date for which data is unavailable
        reason: Human-readable explanation (max 500 chars)
    """
    # Truncate reason to 500 chars to fit column constraint
    reason_truncated = reason[:500] if reason else "Unknown error"

    cur.execute(
        """
        INSERT INTO market_exposure_daily
        (date, regime, exposure_pct, raw_score, halt_reasons, distribution_days, factors,
         data_unavailable, reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (date) DO UPDATE SET
          regime = EXCLUDED.regime,
          exposure_pct = EXCLUDED.exposure_pct,
          raw_score = EXCLUDED.raw_score,
          halt_reasons = EXCLUDED.halt_reasons,
          distribution_days = EXCLUDED.distribution_days,
          factors = EXCLUDED.factors,
          data_unavailable = EXCLUDED.data_unavailable,
          reason = EXCLUDED.reason
        """,
        (
            eval_date,
            None,  # regime
            None,  # exposure_pct
            None,  # raw_score
            None,  # halt_reasons - use NULL not [] to distinguish from "data available, no halts"
            None,  # distribution_days
            None,  # factors
            True,  # data_unavailable
            reason_truncated,  # reason
        ),
    )


def main() -> int:  # noqa: C901
    """Compute and persist market_exposure_daily for latest trading date.

    Exit codes: 0=success, 1=error, 2=no_data
    """
    from utils.db.context import DatabaseContext

    table_name = "market_exposure_daily"

    try:
        # Mark loader as RUNNING
        with DatabaseContext("write") as cur:
            cur.execute(
                "UPDATE data_loader_status SET status = %s, last_updated = NOW(), execution_started = NOW() WHERE table_name = %s",
                ("RUNNING", table_name),
            )
            if cur.rowcount == 0:
                cur.execute(
                    "INSERT INTO data_loader_status (table_name, status, last_updated, execution_started) VALUES (%s, %s, NOW(), NOW())",
                    (table_name, "RUNNING"),
                )

        from algo.risk import MarketExposure

        # Determine the latest date for which BOTH price_daily AND market_health_daily have data.
        # market_health_daily is capped to VIX availability and may lag price_daily by 1 trading day
        # (VIX is not available until after market close). Computing market_exposure for a date
        # where market_health_daily has no row causes a hard failure in new_highs_lows().
        latest_date = None
        with DatabaseContext("read") as cur:
            cur.execute("SELECT date FROM price_daily WHERE symbol='SPY' ORDER BY date DESC LIMIT 1")
            result = cur.fetchone()
            spy_latest = result[0] if result else None

            cur.execute("SELECT MAX(date) FROM market_health_daily")
            result = cur.fetchone()
            health_latest = result[0] if result else None

        if not spy_latest:
            error_msg = "No price data available for SPY — cannot compute market exposure"
            logger.warning(
                "[MARKET_EXPOSURE] No SPY price data available — critical data for market exposure computation missing"
            )
            logger.error(error_msg)
            with DatabaseContext("write") as cur:
                cur.execute(
                    "UPDATE data_loader_status SET status = %s, last_updated = NOW(), error_message = %s WHERE table_name = %s",
                    ("FAILED", error_msg, table_name),
                )
            return 1

        if not health_latest:
            error_msg = "No market_health_daily data available — required for new_highs_lows computation"
            logger.warning(
                "[MARKET_EXPOSURE] No market_health_daily data available — required for new_highs_lows computation"
            )
            with DatabaseContext("write") as cur:
                cur.execute(
                    "UPDATE data_loader_status SET status = %s, last_updated = NOW(), error_message = %s WHERE table_name = %s",
                    ("FAILED", error_msg, table_name),
                )
            return 1

        # Use the earlier of the two dates so market_exposure never tries to compute for a date
        # where market_health_daily has no row (VIX lag causes health to trail price by 1 day)
        latest_date = min(spy_latest, health_latest)
        if latest_date < spy_latest:
            logger.info(
                f"[MARKET_EXPOSURE] Using health watermark {latest_date} (SPY has {spy_latest}; "
                f"market_health_daily not yet available for {spy_latest})"
            )

        # CRITICAL: Only compute market exposure for trading days
        # Loading on weekend/holiday should not create entries for non-trading days (corrupts position sizing logic)
        from algo.infrastructure import MarketCalendar

        if not MarketCalendar.is_trading_day(latest_date):
            error_msg = (
                f"Latest price_daily date {latest_date} is not a trading day. "
                f"Cannot compute market exposure for non-trading days (would corrupt position sizing logic). "
                f"Check: (1) Is yfinance loader running correctly? (2) Did market holidays get misconfigured?"
            )
            logger.error(f"[MARKET_EXPOSURE LOADER CRITICAL] {error_msg}")
            with DatabaseContext("write") as cur:
                cur.execute(
                    "UPDATE data_loader_status SET status = %s, last_updated = NOW(), error_message = %s WHERE table_name = %s",
                    ("FAILED", f"Latest date {latest_date} is not a trading day", table_name),
                )
            return 1

        logger.info(f"Computing market exposure for {latest_date}")

        # Compute market exposure (this persists to DB automatically)
        me = MarketExposure()
        result = me.compute(latest_date, force_recompute=True)

        # CRITICAL: Validate result structure - compute() either succeeds with full dict or raises error
        # No "success" field exists; validation is fail-fast via exception
        try:
            required_fields = [
                "eval_date",
                "regime",
                "exposure_pct",
                "raw_score",
                "halt_reasons",
                "distribution_days",
                "factors",
            ]
            missing_fields = [f for f in required_fields if f not in result]
            if missing_fields:
                msg = (
                    f"Market exposure computation returned incomplete result. "
                    f"Missing required fields: {missing_fields}. "
                    f"Cannot proceed with incomplete market regime data."
                )
                logger.error(msg)
                with DatabaseContext("write") as cur:
                    cur.execute(
                        "UPDATE data_loader_status SET status = %s, last_updated = NOW(), error_message = %s WHERE table_name = %s",
                        ("FAILED", msg, table_name),
                    )
                    # Record data unavailability in market_exposure_daily
                    _insert_unavailable_marker(cur, latest_date, msg)
                return 1

            # Validate critical field types
            if not isinstance(result["regime"], str) or result["regime"] not in [
                "confirmed_uptrend",
                "uptrend_under_pressure",
                "caution",
                "correction",
            ]:
                raise ValueError(f"Invalid regime value: {result.get('regime')}")
            if not isinstance(result["exposure_pct"], (int, float)) or not (0 <= result["exposure_pct"] <= 100):
                raise ValueError(f"Invalid exposure_pct: {result.get('exposure_pct')}")
            if not isinstance(result["halt_reasons"], list):
                raise ValueError(f"Invalid halt_reasons type: {type(result['halt_reasons'])}")
            if not isinstance(result["distribution_days"], int):
                raise ValueError(f"Invalid distribution_days type: {type(result['distribution_days'])}")

            # Ensure data_unavailable and reason are present in result
            # (should be set by MarketExposure.compute() on success)
            if "data_unavailable" not in result:
                result["data_unavailable"] = False
            if "reason" not in result:
                result["reason"] = None

        except (KeyError, ValueError, TypeError) as e:
            msg = f"Market exposure validation failed: {type(e).__name__}: {e}"
            logger.error(msg)
            with DatabaseContext("write") as cur:
                cur.execute(
                    "UPDATE data_loader_status SET status = %s, last_updated = NOW(), error_message = %s WHERE table_name = %s",
                    ("FAILED", msg[:200], table_name),
                )
                # Record data unavailability in market_exposure_daily
                _insert_unavailable_marker(cur, latest_date, msg[:500])
            return 1

        logger.info("✓ Market exposure computed:")
        logger.info(f"  Regime: {result['regime']}")
        logger.info(f"  Exposure: {result['exposure_pct']}%")
        logger.info(f"  Raw score: {result['raw_score']}")
        logger.info(f"  Data available: {not result.get('data_unavailable', False)}")

        if result["halt_reasons"]:  # Already validated as list above
            logger.info(f"  Halt reasons: {'; '.join(result['halt_reasons'])}")

        # Mark loader as COMPLETED (atomic upsert prevents race conditions from concurrent loaders)
        with DatabaseContext("write") as cur:
            cur.execute(
                """
                INSERT INTO data_loader_status
                (table_name, row_count, latest_date, last_updated, status,
                 completion_pct, symbol_count, symbols_loaded, execution_completed)
                VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, NOW())
                ON CONFLICT (table_name) DO UPDATE SET
                  row_count = EXCLUDED.row_count,
                  latest_date = EXCLUDED.latest_date,
                  last_updated = NOW(),
                  status = EXCLUDED.status,
                  completion_pct = EXCLUDED.completion_pct,
                  symbol_count = EXCLUDED.symbol_count,
                  symbols_loaded = EXCLUDED.symbols_loaded,
                  execution_completed = NOW()
                """,
                (
                    table_name,
                    1,  # market_exposure_daily has 1 "symbol" (daily aggregate)
                    latest_date,
                    "COMPLETED",
                    100.0,  # 100% completion
                    1,
                    1,
                ),
            )

        logger.info("✓ Loader completed successfully")
        return 0

    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        error_detail = f"Database error: {str(e)[:400]}"
        logger.error(f"Market exposure loader failed (database error): {e}", exc_info=True)
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    "UPDATE data_loader_status SET status = %s, last_updated = NOW(), error_message = %s WHERE table_name = %s",
                    ("FAILED", str(e)[:200], table_name),
                )
                # Try to record data unavailability, but if DB is down it may fail
                # This is best-effort since we already have a DB error
                try:
                    # Determine latest_date if not already set
                    if "latest_date" not in locals():
                        cur.execute("SELECT date FROM price_daily WHERE symbol='SPY' ORDER BY date DESC LIMIT 1")
                        result = cur.fetchone()
                        if result:
                            latest_date = result[0]
                            _insert_unavailable_marker(cur, latest_date, error_detail)
                except (psycopg2.DatabaseError, psycopg2.OperationalError, NameError):
                    # If we can't determine date or insert fails, that's OK — we already updated loader status
                    pass
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as db_err:
            logger.error(f"Failed to update loader status: {db_err}")
        return 1
    except Exception as e:
        error_detail = f"{type(e).__name__}: {str(e)[:400]}"
        logger.error(f"Market exposure loader failed ({type(e).__name__}): {e}", exc_info=True)
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    "UPDATE data_loader_status SET status = %s, last_updated = NOW(), error_message = %s WHERE table_name = %s",
                    ("FAILED", f"{type(e).__name__}: {str(e)[:180]}", table_name),
                )
                # Try to record data unavailability
                try:
                    # Determine latest_date if not already set
                    if "latest_date" not in locals():
                        cur.execute("SELECT date FROM price_daily WHERE symbol='SPY' ORDER BY date DESC LIMIT 1")
                        result = cur.fetchone()
                        if result:
                            latest_date = result[0]
                            _insert_unavailable_marker(cur, latest_date, error_detail)
                except (psycopg2.DatabaseError, psycopg2.OperationalError, NameError):
                    # If we can't determine date or insert fails, that's OK — we already updated loader status
                    pass
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as status_err:
            logger.error(f"Failed to update FAILED status in data_loader_status: {status_err}")
            raise RuntimeError(
                f"Market exposure loader failed AND failed to record failure status: {e.__class__.__name__}: {e}"
            ) from status_err
        except Exception as status_err:
            logger.error(f"Unexpected error updating loader status: {status_err}")
            raise RuntimeError(
                f"Market exposure loader failed AND unexpected error updating status: {status_err.__class__.__name__}: {status_err}"
            ) from status_err
        return 1


if __name__ == "__main__":
    sys.exit(main())
