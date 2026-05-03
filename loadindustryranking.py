#!/usr/bin/env python3
"""
loadindustryranking.py — Compute industry_ranking from constituent stock returns

Computes 4-week momentum per industry by averaging 4-week returns of all
stocks in that industry. Ranks all 197+ industries.

Pure SQL — uses company_profile.industry to group, price_daily for returns.
Run after loadpricedaily.py and loaddailycompanydata.py.

USAGE:
  python3 loadindustryranking.py
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


def load_industry_ranking():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    start = datetime.now()

    print(f"\n{'='*70}\nLOADING INDUSTRY RANKING\n{'='*70}")

    cur.execute("SELECT MAX(date) FROM price_daily WHERE symbol = 'SPY'")
    latest_date = cur.fetchone()[0]
    if not latest_date:
        print("  ERROR: no SPY data")
        return

    print(f"  Computing for date: {latest_date}")

    # Compute average 4-week return per industry, weighted by liquidity (volume)
    cur.execute("""
        WITH stock_returns AS (
            SELECT
                cp.industry,
                pd.symbol,
                pd.close AS today_close,
                pd.volume,
                LAG(pd.close, 20) OVER (PARTITION BY pd.symbol ORDER BY pd.date) AS close_4w,
                LAG(pd.close, 5)  OVER (PARTITION BY pd.symbol ORDER BY pd.date) AS close_1w,
                LAG(pd.close, 60) OVER (PARTITION BY pd.symbol ORDER BY pd.date) AS close_12w,
                ROW_NUMBER() OVER (PARTITION BY pd.symbol ORDER BY pd.date DESC) AS rn
            FROM price_daily pd
            JOIN company_profile cp ON cp.ticker = pd.symbol
            WHERE pd.date >= %s::date - INTERVAL '90 days'
              AND pd.date <= %s
              AND cp.industry IS NOT NULL AND cp.industry <> ''
              AND pd.close > 5
        ),
        latest AS (
            SELECT industry, symbol, today_close, volume,
                   close_1w, close_4w, close_12w
            FROM stock_returns WHERE rn = 1
        ),
        industry_avg AS (
            SELECT
                industry,
                COUNT(*) AS n_constituents,
                AVG(CASE WHEN close_1w > 0 THEN (today_close - close_1w) / close_1w * 100 END) AS ret_1w,
                AVG(CASE WHEN close_4w > 0 THEN (today_close - close_4w) / close_4w * 100 END) AS ret_4w,
                AVG(CASE WHEN close_12w > 0 THEN (today_close - close_12w) / close_12w * 100 END) AS ret_12w,
                AVG(today_close * volume) AS avg_dollar_vol
            FROM latest
            GROUP BY industry
            HAVING COUNT(*) >= 3  -- need at least 3 stocks for stable average
        ),
        ranked AS (
            SELECT
                industry,
                n_constituents,
                ret_1w, ret_4w, ret_12w,
                avg_dollar_vol,
                -- Strength score: 4w weighted heavily (swing window), with breadth bonus
                COALESCE(ret_4w, 0) * 0.5 + COALESCE(ret_12w, 0) * 0.3 + COALESCE(ret_1w, 0) * 0.2 AS strength,
                ROW_NUMBER() OVER (
                    ORDER BY
                        COALESCE(ret_4w, 0) * 0.5 + COALESCE(ret_12w, 0) * 0.3 + COALESCE(ret_1w, 0) * 0.2
                        DESC NULLS LAST
                ) AS current_rank
            FROM industry_avg
        )
        SELECT industry, current_rank, strength, ret_1w, ret_4w, ret_12w, n_constituents
        FROM ranked
        ORDER BY current_rank
    """, (latest_date, latest_date))

    rows = cur.fetchall()
    print(f"  Computed ranks for {len(rows)} industries")

    # Get prior ranks
    rank_lookback = {}
    for lookback in (5, 20, 60):
        cur.execute(f"""
            SELECT industry, current_rank
            FROM industry_ranking
            WHERE date_recorded = (
                SELECT MAX(date_recorded) FROM industry_ranking
                WHERE date_recorded <= %s::date - INTERVAL '{lookback} days'
            )
        """, (latest_date,))
        rank_lookback[lookback] = dict(cur.fetchall())

    # Persist
    for industry, rank, strength, r1, r4, r12, n in rows:
        cur.execute("""
            INSERT INTO industry_ranking
                (industry, date_recorded, current_rank, daily_strength_score,
                 rank_1w_ago, rank_4w_ago, rank_12w_ago, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
        """, (
            industry, latest_date, rank, float(strength or 0),
            rank_lookback[5].get(industry),
            rank_lookback[20].get(industry),
            rank_lookback[60].get(industry),
        ))

    conn.commit()
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n  Persisted {len(rows)} industries")
    print(f"\n  Top 15 industries by 4w momentum:")
    for i, (ind, rank, strength, r1, r4, r12, n) in enumerate(rows[:15], 1):
        print(f"  {rank:>3} {ind[:40]:<40s} strength={strength:+6.2f} ret_4w={float(r4 or 0):+5.2f}% n={n}")

    print(f"\n{'='*70}\nCOMPLETE — {elapsed:.1f}s\n{'='*70}\n")

    cur.close()
    conn.close()


if __name__ == "__main__":
    load_industry_ranking()
