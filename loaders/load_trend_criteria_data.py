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
        return pd.DataFrame(
            columns=["symbol", "date", "rsi_14", "sma_50", "sma_200", "roc_20d", "roc_60d", "roc_252d"]
        )
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


def _compute_minervini_score(row: pd.Series) -> int:
    """Return integer Minervini trend score (0-8) from a merged row."""
    close = row.get("close")
    sma50 = row.get("sma_50")
    sma200 = row.get("sma_200")
    roc20 = row.get("roc_20d")
    roc60 = row.get("roc_60d")
    roc252 = row.get("roc_252d")
    rsi = row.get("rsi_14")

    if close is None or sma50 is None or sma200 is None:
        return 0

    score = 0
    try:
        close_f = float(close)
        sma50_f = float(sma50)
        sma200_f = float(sma200)

        if sma200_f > 0:
            if close_f > sma200_f:
                score += 1
            if sma50_f > sma200_f:
                score += 1
            if close_f > sma200_f * 1.10:
                score += 1

        if sma50_f > 0 and close_f > sma50_f:
            score += 1

        if roc60 is not None and not pd.isna(roc60) and float(roc60) > 0:
            score += 1
        if roc252 is not None and not pd.isna(roc252) and float(roc252) > 10:
            score += 1
        if rsi is not None and not pd.isna(rsi) and float(rsi) > 50:
            score += 1
        if roc20 is not None and not pd.isna(roc20) and float(roc20) > 0:
            score += 1

    except (TypeError, ValueError, ZeroDivisionError):
        return 0

    return score


def _compute_weinstein_stage(row: pd.Series) -> int:
    """Return Weinstein stage (1-4) from a merged row."""
    close = row.get("close")
    sma50 = row.get("sma_50")
    sma200 = row.get("sma_200")

    if close is None or sma50 is None or sma200 is None:
        return 4  # default to downtrend when data missing (conservative)

    try:
        close_f = float(close)
        sma50_f = float(sma50)
        sma200_f = float(sma200)

        above200 = close_f > sma200_f
        sma50_above_sma200 = sma50_f > sma200_f

        if above200 and sma50_above_sma200:
            return 2  # uptrend
        elif not above200 and not sma50_above_sma200:
            return 4  # downtrend
        elif above200 and not sma50_above_sma200:
            return 3  # topping
        else:
            return 1  # basing
    except (TypeError, ValueError):
        return 4


def _compute_trend_direction(row: pd.Series) -> str:
    """Return 'up', 'down', or 'sideways' based on roc_60d."""
    roc60 = row.get("roc_60d")
    if roc60 is None or pd.isna(roc60):
        return "sideways"
    try:
        r = float(roc60)
        if r > 5:
            return "up"
        elif r < -5:
            return "down"
        else:
            return "sideways"
    except (TypeError, ValueError):
        return "sideways"


def _upsert_batch(cur: psycopg2.extensions.cursor, rows: list[tuple]) -> int:
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


def run() -> dict:
    """Compute and persist trend template data for recent trading dates."""
    _update_loader_status("RUNNING")
    start = time.time()

    try:
        with DatabaseContext("read") as read_cur:
            dates = _fetch_latest_dates(read_cur)
            if not dates:
                raise RuntimeError("[TREND] No dates found in price_daily — cannot compute trend data")

            logger.info(f"[TREND] Computing trend template data for {len(dates)} dates: {dates[-1]} → {dates[0]}")

            tech_df = _fetch_technical_data(read_cur, dates)
            price_df = _fetch_price_data(read_cur, dates)

        if tech_df.empty or price_df.empty:
            raise RuntimeError("[TREND] No technical or price data available — check upstream loaders")

        # Merge on symbol + date
        merged = price_df.merge(tech_df, on=["symbol", "date"], how="inner")
        if merged.empty:
            raise RuntimeError("[TREND] No matching rows after price/technical join")

        logger.info(f"[TREND] Computing scores for {len(merged)} symbol-date pairs")

        rows = []
        for _, row in merged.iterrows():
            symbol = row["symbol"]
            dt = row["date"]
            minervini = _compute_minervini_score(row)
            weinstein = _compute_weinstein_stage(row)
            direction = _compute_trend_direction(row)
            price_above_sma50 = (
                bool(float(row["close"]) > float(row["sma_50"]))
                if row.get("close") is not None and row.get("sma_50") is not None
                else False
            )
            rows.append((symbol, dt, weinstein, float(minervini), direction, price_above_sma50))

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
        print(f"Result: {result}")
        sys.exit(0)
    except Exception as exc:
        logger.error(f"Trend criteria loader failed: {exc}")
        sys.exit(1)
