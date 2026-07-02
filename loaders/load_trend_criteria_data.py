#!/usr/bin/env python3
"""Trend Template Data Loader

Computes Minervini trend scores and Weinstein market stages for each symbol.
Results populate trend_template_data, which is used by:
  - swing_trader_scores (hard gate: minervini >= 5 AND weinstein_stage == 2)
  - market_health_daily (advance/decline breadth from price_above_sma50)

Minervini score (0-8, integer) — one point per criterion:
  1. close > sma_200
  2. close > sma_50
  3. sma_50 > sma_200
  4. roc_60d > 0
  5. roc_252d > 10 (annual return > 10%)
  6. rsi_14 > 50
  7. close > sma_200 * 1.10 (price 10%+ above 200-day)
  8. roc_20d > 0

Weinstein stage (1-4):
  Stage 2 (uptrend)   : close > sma_200 AND sma_50 > sma_200
  Stage 4 (downtrend) : close < sma_200 AND sma_50 < sma_200
  Stage 3 (topping)   : close > sma_200 AND sma_50 < sma_200
  Stage 1 (basing)    : close < sma_200 AND sma_50 > sma_200
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
    """Update data_loader_status for Phase 1 monitoring."""
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
    """Return the most recent N trading dates from price_daily."""
    cur.execute(
        "SELECT DISTINCT date FROM price_daily ORDER BY date DESC LIMIT %s",
        (_LOOKBACK_DAYS,),
    )
    rows = cur.fetchall()
    return [r[0] for r in rows]


def _fetch_technical_data(cur: psycopg2.extensions.cursor, dates: list[date]) -> pd.DataFrame:
    """Fetch technical indicators for the given dates (all symbols at once)."""
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
    """Fetch close prices for the given dates (all symbols at once)."""
    cur.execute(
        "SELECT symbol, date, close FROM price_daily WHERE date = ANY(%s)",
        (dates,),
    )
    rows = cur.fetchall()
    if not rows:
        return pd.DataFrame(columns=["symbol", "date", "close"])
    return pd.DataFrame(rows, columns=["symbol", "date", "close"])


def _compute_scores_vectorized(merged: pd.DataFrame) -> pd.DataFrame:
    """Compute Minervini scores, Weinstein stages, trend direction, and price_above_sma50 on the full DataFrame at once."""
    # Cast to float for vectorized comparisons; NaN propagates safely for fillna
    close = pd.to_numeric(merged["close"], errors="coerce")
    sma50 = pd.to_numeric(merged["sma_50"], errors="coerce")
    sma200 = pd.to_numeric(merged["sma_200"], errors="coerce")
    roc20 = pd.to_numeric(merged["roc_20d"], errors="coerce")
    roc60 = pd.to_numeric(merged["roc_60d"], errors="coerce")
    roc252 = pd.to_numeric(merged["roc_252d"], errors="coerce")
    rsi = pd.to_numeric(merged["rsi_14"], errors="coerce")

    # Minervini score (0-8)
    merged["minervini_trend_score"] = (
        (close > sma200).astype(int)
        + (close > sma50).astype(int)
        + (sma50 > sma200).astype(int)
        + (roc60 > 0).fillna(False).astype(int)
        + (roc252 > 10).fillna(False).astype(int)
        + (rsi > 50).fillna(False).astype(int)
        + (close > sma200 * 1.10).astype(int)
        + (roc20 > 0).fillna(False).astype(int)
    ).astype(float)

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
    merged["price_above_sma50"] = (close > sma50).fillna(False)

    return merged


def _upsert_batch(cur: psycopg2.extensions.cursor, rows: list) -> int:  # type: ignore[type-arg]
    """Upsert a batch of rows into trend_template_data."""
    if not rows:
        return 0
    cur.executemany(
        """
        INSERT INTO trend_template_data
            (symbol, date, weinstein_stage, minervini_trend_score, trend_direction, price_above_sma50)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (symbol, date) DO UPDATE SET
            weinstein_stage         = EXCLUDED.weinstein_stage,
            minervini_trend_score   = EXCLUDED.minervini_trend_score,
            trend_direction         = EXCLUDED.trend_direction,
            price_above_sma50       = EXCLUDED.price_above_sma50
        """,
        rows,
    )
    return len(rows)


def run() -> dict:  # type: ignore[type-arg]
    """Compute and persist trend template data for recent trading dates."""
    _update_loader_status("RUNNING")
    start = time.time()

    try:
        with DatabaseContext("read") as read_cur:
            dates = _fetch_latest_dates(read_cur)
            if not dates:
                raise RuntimeError("[TREND] No dates found in price_daily — cannot compute trend data")

            logger.info(f"[TREND] Computing trend template data for {len(dates)} dates: {dates[-1]} to {dates[0]}")

            tech_df = _fetch_technical_data(read_cur, dates)
            price_df = _fetch_price_data(read_cur, dates)

        if tech_df.empty or price_df.empty:
            raise RuntimeError("[TREND] No technical or price data available — check upstream loaders")

        merged = price_df.merge(tech_df, on=["symbol", "date"], how="inner")
        if merged.empty:
            raise RuntimeError("[TREND] No matching rows after price/technical join")

        logger.info(f"[TREND] Computing scores for {len(merged)} symbol-date pairs (vectorized)")

        merged = _compute_scores_vectorized(merged)

        rows = list(
            merged[
                ["symbol", "date", "weinstein_stage", "minervini_trend_score", "trend_direction", "price_above_sma50"]
            ].itertuples(index=False, name=None)
        )

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
        _update_loader_status("FAILED", error_message=str(e))
        raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    try:
        result = run()
        logger.info(f"Trend criteria loader completed: {result}")
        sys.exit(0)
    except Exception as exc:
        logger.error(f"Trend criteria loader failed: {exc}")
        sys.exit(1)
