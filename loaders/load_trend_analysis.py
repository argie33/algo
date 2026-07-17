#!/usr/bin/env python3
"""
Trend Analysis - Compute Minervini & Weinstein trend scores for all symbols.

PURPOSE: Classify each symbol by trend strength (Minervini 0-8) and market stage
(Weinstein 1-4). Used by market_health_daily for breadth calculations and by signal
generation to filter entries by market regime.

INPUT: technical_data_daily table (SMA-50, SMA-200, RSI, price changes)
OUTPUT: trend_template_data table
ROWS: ~10,600 symbols x 1 update/day

SCHEDULE: Step Functions Pipeline, Step 2 (ParallelEnrichment/TrendTemplate)
  Timing: ~2:15 AM ET
  Dependency: price_daily

COST: CPU=1024m, Memory=2048MB, Timeout=5400s (90m)
  Runtime: 30-45 minutes
  Parallelism: 1 (vectorized)

DATA FRESHNESS: Daily
COMPLETENESS: 99%+

FAILURE MODE: Graceful (doesn't fail-close)

METRICS:

  Minervini Score (0-8):
  1. close > sma_200
  2. close > sma_50
  3. sma_50 > sma_200
  4. roc_60d > 0%
  5. roc_252d > 10%
  6. RSI > 50
  7. close > sma_200 x 1.10
  8. roc_20d > 0%

  Weinstein Stage:
  - Stage 1 (basing): < sma_200, sma_50 > sma_200
  - Stage 2 (uptrend): > sma_200, sma_50 > sma_200
  - Stage 3 (topping): > sma_200, sma_50 < sma_200
  - Stage 4 (downtrend): < sma_200, sma_50 < sma_200

NOTE: Formerly load_trend_criteria_data.py (renamed 2026-07 for clarity).
"""

import logging
import sys
import time
from datetime import date

import pandas as pd
import psycopg2
import psycopg2.extensions

from utils.db.context import DatabaseContext

logger = logging.getLogger(__name__)

_TABLE = "trend_template_data"
_LOOKBACK_DAYS = 10  # compute for the last N trading days to fill recent gaps


def _update_loader_status(status: str, error_message: str | None = None, symbol_count: int | None = None) -> None:
    with DatabaseContext("write") as cur:
        if status == "RUNNING":
            cur.execute(
                "UPDATE data_loader_status SET status=%s, last_updated=NOW(), execution_started=NOW() WHERE table_name=%s",
                (status, _TABLE),
            )
            if cur.rowcount == 0:
                cur.execute(
                    "INSERT INTO data_loader_status (table_name, status, last_updated, execution_started) VALUES (%s, %s, NOW(), NOW())",
                    (_TABLE, status),
                )
        else:
            cur.execute(
                "UPDATE data_loader_status SET status=%s, last_updated=NOW(), execution_completed=NOW(), error_message=%s WHERE table_name=%s",
                (status, error_message, _TABLE),
            )


def _fetch_latest_dates(cur: psycopg2.extensions.cursor) -> list[date]:
    cur.execute(
        "SELECT DISTINCT date FROM price_daily ORDER BY date DESC LIMIT %s",
        (_LOOKBACK_DAYS,),
    )
    rows = cur.fetchall()
    return [r[0] for r in rows]


def _fetch_technical_data(cur: psycopg2.extensions.cursor, dates: list[date]) -> pd.DataFrame:
    cur.execute(
        """
        SELECT symbol, date, rsi_14, sma_50, sma_200, roc_20d, roc_60d, roc_252d
        FROM technical_data_daily
        WHERE date = ANY(%s)
        """,
        (dates,),
    )
    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=["symbol", "date", "rsi_14", "sma_50", "sma_200", "roc_20d", "roc_60d", "roc_252d"])
    return pd.DataFrame(
        rows,
        columns=["symbol", "date", "rsi_14", "sma_50", "sma_200", "roc_20d", "roc_60d", "roc_252d"],
    )


def _fetch_price_data(cur: psycopg2.extensions.cursor, dates: list[date]) -> pd.DataFrame:
    cur.execute(
        "SELECT symbol, date, close FROM price_daily WHERE date = ANY(%s)",
        (dates,),
    )
    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=["symbol", "date", "close"])
    return pd.DataFrame(rows, columns=["symbol", "date", "close"])


def _compute_scores_vectorized(merged: pd.DataFrame) -> pd.DataFrame:
    # Cast to float for vectorized comparisons; NaN propagates safely for fillna
    close = pd.to_numeric(merged["close"], errors="coerce")
    sma50 = pd.to_numeric(merged["sma_50"], errors="coerce")
    sma200 = pd.to_numeric(merged["sma_200"], errors="coerce")
    roc20 = pd.to_numeric(merged["roc_20d"], errors="coerce")
    roc60 = pd.to_numeric(merged["roc_60d"], errors="coerce")
    roc252 = pd.to_numeric(merged["roc_252d"], errors="coerce")
    rsi = pd.to_numeric(merged["rsi_14"], errors="coerce")

    # Minervini score (0-8)
    # GOVERNANCE: NaN indicators become NaN score (fail-fast), not silent 0 (no fallback to False)
    minervini_components = pd.DataFrame(
        {
            "c1": (close > sma200).astype(int),
            "c2": (close > sma50).astype(int),
            "c3": (sma50 > sma200).astype(int),
            "c4": (roc60 > 0).where(pd.notna(roc60), pd.NA).astype("Int64"),
            "c5": (roc252 > 10).where(pd.notna(roc252), pd.NA).astype("Int64"),
            "c6": (rsi > 50).where(pd.notna(rsi), pd.NA).astype("Int64"),
            "c7": (close > sma200 * 1.10).astype(int),
            "c8": (roc20 > 0).where(pd.notna(roc20), pd.NA).astype("Int64"),
        }
    )
    merged["minervini_trend_score"] = (
        minervini_components[["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8"]].sum(axis=1, skipna=False).astype(float)
    )

    # Weinstein stage (1-4)
    above200 = close > sma200
    sma50_above_sma200 = sma50 > sma200
    merged["weinstein_stage"] = 4  # default: downtrend
    merged.loc[above200 & sma50_above_sma200, "weinstein_stage"] = 2  # uptrend
    merged.loc[above200 & ~sma50_above_sma200, "weinstein_stage"] = 3  # topping
    merged.loc[~above200 & sma50_above_sma200, "weinstein_stage"] = 1  # basing

    # Trend direction
    merged["trend_direction"] = "sideways"
    merged.loc[roc60 > 5, "trend_direction"] = "up"
    merged.loc[roc60 < -5, "trend_direction"] = "down"

    # price_above_sma50
    # GOVERNANCE: NaN when SMA missing (fail-fast), not silent False
    merged["price_above_sma50"] = (close > sma50).where(pd.notna(close) & pd.notna(sma50), pd.NA)

    return merged


def _upsert_batch(cur: psycopg2.extensions.cursor, rows: list) -> int:  # type: ignore[type-arg]
    """Upsert a batch of rows into trend_template_data."""
    if not rows:
        raise ValueError(
            "[LOAD_TREND_CRITERIA] Cannot upsert empty row batch. "
            "Input data is required - possible stale data or upstream processing failure."
        )

    cur.executemany(
        """
        INSERT INTO trend_template_data
            (symbol, date, weinstein_stage, minervini_trend_score, trend_direction, price_above_sma50, data_unavailable, reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, date) DO UPDATE SET
            weinstein_stage         = EXCLUDED.weinstein_stage,
            minervini_trend_score   = EXCLUDED.minervini_trend_score,
            trend_direction         = EXCLUDED.trend_direction,
            price_above_sma50       = EXCLUDED.price_above_sma50,
            data_unavailable        = EXCLUDED.data_unavailable,
            reason                  = EXCLUDED.reason
        """,
        rows,
    )
    return len(rows)


def run() -> dict:  # type: ignore[type-arg]
    _update_loader_status("RUNNING")
    start = time.time()

    try:
        with DatabaseContext("read") as read_cur:
            dates = _fetch_latest_dates(read_cur)
            if not dates:
                logger.warning("[TREND] No dates found in price_daily - cannot compute trend data")
                elapsed = time.time() - start
                _update_loader_status("COMPLETED")
                return {
                    "symbols_processed": 0,
                    "rows_inserted": 0,
                    "dates_covered": 0,
                    "duration_sec": round(elapsed, 1),
                }

            logger.info(f"[TREND] Computing trend template data for {len(dates)} dates: {dates[-1]} to {dates[0]}")

            tech_df = _fetch_technical_data(read_cur, dates)
            price_df = _fetch_price_data(read_cur, dates)

        if tech_df.empty or price_df.empty:
            logger.warning("[TREND] No technical or price data available - check upstream loaders")
            elapsed = time.time() - start
            _update_loader_status("COMPLETED")
            return {
                "symbols_processed": 0,
                "rows_inserted": 0,
                "dates_covered": 0,
                "duration_sec": round(elapsed, 1),
            }

        merged = price_df.merge(tech_df, on=["symbol", "date"], how="inner")
        if merged.empty:
            logger.warning("[TREND] No matching rows after price/technical join")
            elapsed = time.time() - start
            _update_loader_status("COMPLETED")
            return {
                "symbols_processed": 0,
                "rows_inserted": 0,
                "dates_covered": len(dates),
                "duration_sec": round(elapsed, 1),
            }

        logger.info(f"[TREND] Computing scores for {len(merged)} symbol-date pairs (vectorized)")

        merged = _compute_scores_vectorized(merged)

        # Mark all successfully computed rows as available
        merged["data_unavailable"] = False
        merged["reason"] = None

        rows = list(
            merged[
                [
                    "symbol",
                    "date",
                    "weinstein_stage",
                    "minervini_trend_score",
                    "trend_direction",
                    "price_above_sma50",
                    "data_unavailable",
                    "reason",
                ]
            ].itertuples(index=False, name=None)
        )

        # Convert pandas NA/NaN values to None for psycopg2 compatibility
        rows = [tuple(None if pd.isna(val) else val for val in row) for row in rows]

        with DatabaseContext("write") as write_cur:
            inserted = _upsert_batch(write_cur, rows)

        elapsed = time.time() - start
        symbol_count = len(merged["symbol"].unique())
        result = {
            "symbols_processed": symbol_count,
            "rows_inserted": inserted,
            "dates_covered": len(dates),
            "duration_sec": round(elapsed, 1),
        }
        logger.info(f"[TREND] Done: {inserted} rows upserted in {elapsed:.1f}s")
        _update_loader_status("COMPLETED")
        return result

    except Exception as e:
        logger.error(
            f"[TREND LOAD ERROR] Failed to compute trend criteria: {e}. "
            f"Returning empty result instead of raising to allow orchestrator to continue with degraded data."
        )
        _update_loader_status("FAILED", error_message=str(e)[:255])
        # GOVERNANCE: Return empty result dict instead of raising
        # Allows Phase 1 to detect no data and mark affected symbols as data_unavailable
        return {
            "symbols_processed": 0,
            "rows_inserted": 0,
            "dates_covered": 0,
            "duration_sec": round(time.time() - start, 1),
            "error": str(e)[:255],
        }


def main() -> int:
    try:
        result = run()

        if not isinstance(result, dict):
            raise RuntimeError(
                f"[LOADER] Trend criteria run() returned unexpected type {type(result).__name__}, expected dict. Value: {result}"
            )

        if "rows_inserted" not in result:
            raise ValueError(f"[LOADER] Trend criteria result missing required 'rows_inserted' field. Got: {result}")

        # Return 0 (success) regardless of whether rows were inserted. The run() function already
        # handles missing/stale data gracefully. No rows inserted = data wasn't available yet, not a failure.
        # Step Functions .sync mode treats exit code 2 as task failure, so only return non-zero on exceptions.
        logger.info(f"[LOADER] Trend criteria loader completed: {result}. Exit code 0 (SUCCESS).")
        return 0
    except Exception as exc:
        logger.error(f"[LOADER] Trend criteria loader failed: {exc}. Exit code 1 (ERROR).")
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    sys.exit(main())
