#!/usr/bin/env python3
"""
Accumulation/Distribution Rating Loader — IBD-canonical methodology.

Computes per-symbol A/D rating from price_daily using the standard
"accumulation vs distribution volume" methodology (William J. O'Neil /
Investor's Business Daily):

  Window:        Last 65 trading days (~13 weeks, IBD standard)
  Up volume:     Sum of volume on days where close > prev close
  Down volume:   Sum of volume on days where close < prev close
  Net score:     (up_volume - down_volume) / (up_volume + down_volume)
                 -> ranges from -1 (pure distribution) to +1 (pure accumulation)

  Volume bias:   Each day's contribution weighted by its volume ratio to
                 50-day avg, so heavy-volume days dominate (institutional
                 footprint).

  Letter grade:  Cross-symbol percentile rank for the latest date:
                 A = top 10% (heavy accumulation)
                 B = next 20% (moderate accumulation)
                 C = middle 40% (neutral)
                 D = next 20% (moderate distribution)
                 E = bottom 10% (heavy distribution)

Persisted to positioning_metrics:
  ad_rating         NUMERIC(5,2)  — percentile rank 0-100
  ad_grade          VARCHAR(1)    — A / B / C / D / E
  ad_score_raw      NUMERIC(8,4)  — raw signed -1..+1
  ad_window_days    INTEGER       — actual lookback used (may be < 65 if young)

Run:
    python3 loadadrating.py
    python3 loadadrating.py --date 2026-05-01
    python3 loadadrating.py --symbols AAPL,NVDA  # subset for testing
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import date as _date
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("ad_rating")

DB = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


def ensure_schema(cur):
    """Add columns if missing — idempotent."""
    cur.execute(
        """
        ALTER TABLE positioning_metrics
            ADD COLUMN IF NOT EXISTS ad_grade VARCHAR(1),
            ADD COLUMN IF NOT EXISTS ad_score_raw NUMERIC(8, 4),
            ADD COLUMN IF NOT EXISTS ad_window_days INTEGER
        """
    )


def compute_ratings(cur, eval_date, symbol_filter=None):
    """SQL window-function computation across all symbols at once."""
    where_clauses = ["date <= %s", "date >= %s::date - INTERVAL '120 days'"]
    params = [eval_date, eval_date]
    if symbol_filter:
        placeholders = ",".join(["%s"] * len(symbol_filter))
        where_clauses.append(f"symbol IN ({placeholders})")
        params.extend(symbol_filter)
    where = " AND ".join(where_clauses)

    sql = f"""
    WITH px AS (
        SELECT
            symbol,
            date,
            close,
            volume,
            LAG(close) OVER (PARTITION BY symbol ORDER BY date) AS prev_close,
            AVG(volume) OVER (
                PARTITION BY symbol ORDER BY date
                ROWS BETWEEN 49 PRECEDING AND 1 PRECEDING
            ) AS avg_vol_50d,
            ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn_desc
        FROM price_daily
        WHERE {where}
    ),
    weighted AS (
        SELECT
            symbol, date, close, volume, prev_close, avg_vol_50d, rn_desc,
            CASE
                WHEN avg_vol_50d IS NULL OR avg_vol_50d = 0 THEN 1.0
                ELSE LEAST(3.0, GREATEST(0.5, volume::numeric / avg_vol_50d))
            END AS vol_weight,
            CASE
                WHEN prev_close IS NULL OR close IS NULL THEN NULL
                WHEN close > prev_close THEN 1
                WHEN close < prev_close THEN -1
                ELSE 0
            END AS direction
        FROM px
    ),
    -- Last 65 trading days per symbol (IBD 13-week window)
    last_65 AS (
        SELECT * FROM weighted WHERE rn_desc <= 65 AND direction IS NOT NULL
    ),
    score AS (
        SELECT
            symbol,
            COUNT(*) AS window_days,
            SUM(volume * vol_weight) FILTER (WHERE direction = 1) AS up_vol_w,
            SUM(volume * vol_weight) FILTER (WHERE direction = -1) AS down_vol_w
        FROM last_65
        GROUP BY symbol
        HAVING COUNT(*) >= 20  -- need at least 20 trading days for meaningful rating
    ),
    raw_score AS (
        SELECT
            symbol,
            window_days,
            COALESCE(up_vol_w, 0) AS up_vol,
            COALESCE(down_vol_w, 0) AS down_vol,
            CASE
                WHEN COALESCE(up_vol_w, 0) + COALESCE(down_vol_w, 0) = 0 THEN 0
                ELSE (COALESCE(up_vol_w, 0) - COALESCE(down_vol_w, 0))
                     / (COALESCE(up_vol_w, 0) + COALESCE(down_vol_w, 0))
            END AS net_score
        FROM score
    ),
    ranked AS (
        SELECT
            symbol,
            window_days,
            net_score,
            (PERCENT_RANK() OVER (ORDER BY net_score) * 100)::numeric(5, 2) AS pct_rank
        FROM raw_score
    )
    SELECT
        symbol,
        net_score::numeric(8, 4) AS ad_score_raw,
        pct_rank AS ad_rating,
        CASE
            WHEN pct_rank >= 90 THEN 'A'
            WHEN pct_rank >= 70 THEN 'B'
            WHEN pct_rank >= 30 THEN 'C'
            WHEN pct_rank >= 10 THEN 'D'
            ELSE 'E'
        END AS ad_grade,
        window_days
    FROM ranked
    """
    cur.execute(sql, params)
    return cur.fetchall()


def upsert(cur, rows, eval_date):
    """Upsert ratings into positioning_metrics. Uses (symbol, date) as key."""
    if not rows:
        return 0

    cur.executemany(
        """
        INSERT INTO positioning_metrics
            (symbol, date, ad_score_raw, ad_rating, ad_grade, ad_window_days, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (symbol, date) DO UPDATE SET
            ad_score_raw   = EXCLUDED.ad_score_raw,
            ad_rating      = EXCLUDED.ad_rating,
            ad_grade       = EXCLUDED.ad_grade,
            ad_window_days = EXCLUDED.ad_window_days,
            updated_at     = CURRENT_TIMESTAMP
        """,
        [(r[0], eval_date, r[1], r[2], r[3], r[4]) for r in rows],
    )
    return len(rows)


def run(eval_date=None, symbol_filter=None):
    if eval_date is None:
        eval_date = _date.today()
    elif isinstance(eval_date, str):
        eval_date = _date.fromisoformat(eval_date)

    started = time.time()
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()

    # Use the latest trading day in price_daily not later than eval_date
    cur.execute(
        "SELECT MAX(date) FROM price_daily WHERE symbol = 'SPY' AND date <= %s",
        (eval_date,),
    )
    actual_date = cur.fetchone()[0]
    if actual_date is None:
        log.error(f"No price_daily rows <= {eval_date}; aborting.")
        return
    if actual_date != eval_date:
        log.info(f"Snapping eval_date {eval_date} -> latest trading day {actual_date}")
        eval_date = actual_date

    ensure_schema(cur)

    # Make sure positioning_metrics has a (symbol, date) unique constraint or
    # promote it via CREATE UNIQUE INDEX so ON CONFLICT works.
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 'public'
                  AND tablename  = 'positioning_metrics'
                  AND indexname  = 'positioning_metrics_symbol_date_uniq'
            ) THEN
                CREATE UNIQUE INDEX positioning_metrics_symbol_date_uniq
                    ON positioning_metrics (symbol, date);
            END IF;
        END $$;
        """
    )
    conn.commit()

    log.info(f"Computing A/D ratings for eval_date={eval_date}")
    rows = compute_ratings(cur, eval_date, symbol_filter)
    log.info(f"  computed {len(rows)} symbol ratings")

    inserted = upsert(cur, rows, eval_date)
    conn.commit()
    elapsed = time.time() - started

    # Distribution summary
    grades = {}
    for r in rows:
        g = r[3]
        grades[g] = grades.get(g, 0) + 1
    log.info(f"\nGrade distribution (n={len(rows)}):")
    for g in ['A', 'B', 'C', 'D', 'E']:
        n = grades.get(g, 0)
        bar = '#' * int(n / max(1, max(grades.values())) * 30)
        log.info(f"  {g}: {n:>5}  {bar}")

    log.info(f"\nPersisted {inserted} rows in {elapsed:.1f}s")
    cur.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="A/D rating loader (IBD-canonical)")
    parser.add_argument("--date", type=str, default=None,
                        help="Eval date YYYY-MM-DD. Default = today (snapped to latest trading day).")
    parser.add_argument("--symbols", type=str, default=None,
                        help="Comma-separated subset (testing).")
    args = parser.parse_args()
    syms = args.symbols.split(",") if args.symbols else None
    run(eval_date=args.date, symbol_filter=syms)
