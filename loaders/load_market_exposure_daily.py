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
- Runs independently of orchestrator to guarantee availability

Time: ~2-5 seconds (vectorized computation, minimal DB load)
"""

import logging
import sys

import psycopg2

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    """Compute and persist market_exposure_daily for latest trading date."""
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

        # Determine the latest trading date from price_daily
        latest_date = None
        with DatabaseContext("read") as cur:
            cur.execute("SELECT date FROM price_daily WHERE symbol='SPY' ORDER BY date DESC LIMIT 1")
            result = cur.fetchone()
            if result:
                latest_date = result[0]

        if not latest_date:
            logger.error("No price data available for SPY — cannot compute market exposure")
            with DatabaseContext("write") as cur:
                cur.execute(
                    "UPDATE data_loader_status SET status = %s, last_updated = NOW(), error_message = %s WHERE table_name = %s",
                    ("FAILED", "No price data available for SPY", table_name),
                )
            return 1

        logger.info(f"Computing market exposure for {latest_date}")

        # Compute market exposure (this persists to DB automatically)
        me = MarketExposure()
        result = me.compute(latest_date, force_recompute=True)

        if result.get("success") is False:
            logger.error(f"Market exposure computation failed: {result.get('error')}")
            with DatabaseContext("write") as cur:
                cur.execute(
                    "UPDATE data_loader_status SET status = %s, last_updated = NOW(), error_message = %s WHERE table_name = %s",
                    ("FAILED", result.get("error"), table_name),
                )
            return 1

        logger.info("✓ Market exposure computed:")
        logger.info(f"  Regime: {result.get('regime')}")
        logger.info(f"  Exposure: {result.get('exposure_pct')}%")
        logger.info(f"  Raw score: {result.get('raw_score')}")

        if result.get("halt_reasons"):
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
        logger.error(f"Market exposure loader failed (database error): {e}", exc_info=True)
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    "UPDATE data_loader_status SET status = %s, last_updated = NOW(), error_message = %s WHERE table_name = %s",
                    ("FAILED", str(e)[:200], table_name),
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as db_err:
            logger.error(f"Failed to update loader status: {db_err}")
        return 1
    except Exception as e:
        logger.error(f"Market exposure loader failed ({type(e).__name__}): {e}", exc_info=True)
        try:
            with DatabaseContext("write") as cur:
                cur.execute(
                    "UPDATE data_loader_status SET status = %s, last_updated = NOW(), error_message = %s WHERE table_name = %s",
                    ("FAILED", f"{type(e).__name__}: {str(e)[:180]}", table_name),
                )
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
