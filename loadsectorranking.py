#!/usr/bin/env python3
"""
loadsectorranking.py — Compute sector_ranking from sector ETF returns

Ranks all 11 GICS sectors by 1-week / 4-week / 12-week price momentum.
Uses sector ETFs (XLE, XLK, XLF, XLU, XLP, XLV, XLY, XLI, XLB, XLRE, XLC)
as proxies for sector performance.

Replaces the previous loader (deleted from disk). Pure SQL — fast.
Run after loadetfpricedaily.py.

USAGE:
  python3 loadsectorranking.py
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

# Sector → ETF mapping (canonical SPDR sector ETFs)
SECTORS = [
    ('Technology', 'XLK'),
    ('Healthcare', 'XLV'),
    ('Financial Services', 'XLF'),
    ('Consumer Cyclical', 'XLY'),
    ('Consumer Defensive', 'XLP'),
    ('Industrials', 'XLI'),
    ('Energy', 'XLE'),
    ('Utilities', 'XLU'),
    ('Basic Materials', 'XLB'),
    ('Real Estate', 'XLRE'),
    ('Communication Services', 'XLC'),
]


def load_sector_ranking():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    start = datetime.now()

    print(f"\n{'='*70}\nLOADING SECTOR RANKING\n{'='*70}")

    # If we have sector ETF prices, use them. Otherwise fall back to
    # computing sector returns from constituents (slower but doesn't need ETF prices).
    cur.execute("""
        SELECT symbol FROM price_daily
        WHERE symbol IN %s AND date >= CURRENT_DATE - INTERVAL '90 days'
        GROUP BY symbol HAVING COUNT(*) >= 30
    """, (tuple(s[1] for s in SECTORS),))
    available_etfs = {row[0] for row in cur.fetchall()}
    print(f"  ETF coverage: {len(available_etfs)}/{len(SECTORS)}")

    # Get the latest trading date
    cur.execute("SELECT MAX(date) FROM price_daily WHERE symbol = 'SPY'")
    latest_date = cur.fetchone()[0]
    if not latest_date:
        print("  ERROR: No SPY data, can't compute SPY-relative ranks")
        return
    print(f"  Computing for date: {latest_date}")

    # Compute returns per sector (try ETF first, fall back to constituent average)
    sector_returns = []
    for sector_name, etf in SECTORS:
        if etf in available_etfs:
            # Use ETF prices
            cur.execute("""
                WITH bracket AS (
                    SELECT close, ROW_NUMBER() OVER (ORDER BY date DESC) AS rn
                    FROM price_daily
                    WHERE symbol = %s AND date <= %s
                    ORDER BY date DESC LIMIT 70
                )
                SELECT
                    (SELECT close FROM bracket WHERE rn = 1) AS today,
                    (SELECT close FROM bracket WHERE rn = 5) AS w1,
                    (SELECT close FROM bracket WHERE rn = 20) AS w4,
                    (SELECT close FROM bracket WHERE rn = 60) AS w12
            """, (etf, latest_date))
            row = cur.fetchone()
            if not row or not row[0]:
                continue
            today = float(row[0])
            r1 = ((today - float(row[1])) / float(row[1]) * 100) if row[1] else 0
            r4 = ((today - float(row[2])) / float(row[2]) * 100) if row[2] else 0
            r12 = ((today - float(row[3])) / float(row[3]) * 100) if row[3] else 0
            source = 'etf'
        else:
            # Fall back: average return of all stocks in this sector
            cur.execute("""
                WITH constituents AS (
                    SELECT ticker FROM company_profile WHERE sector = %s LIMIT 100
                ),
                returns AS (
                    SELECT
                        AVG((today.close - w1.close) / NULLIF(w1.close, 0) * 100) AS r1,
                        AVG((today.close - w4.close) / NULLIF(w4.close, 0) * 100) AS r4,
                        AVG((today.close - w12.close) / NULLIF(w12.close, 0) * 100) AS r12
                    FROM constituents c
                    JOIN price_daily today ON today.symbol = c.ticker AND today.date = %s
                    LEFT JOIN price_daily w1 ON w1.symbol = c.ticker
                        AND w1.date = (SELECT MAX(date) FROM price_daily WHERE symbol = c.ticker AND date <= %s::date - INTERVAL '5 days')
                    LEFT JOIN price_daily w4 ON w4.symbol = c.ticker
                        AND w4.date = (SELECT MAX(date) FROM price_daily WHERE symbol = c.ticker AND date <= %s::date - INTERVAL '20 days')
                    LEFT JOIN price_daily w12 ON w12.symbol = c.ticker
                        AND w12.date = (SELECT MAX(date) FROM price_daily WHERE symbol = c.ticker AND date <= %s::date - INTERVAL '60 days')
                )
                SELECT r1, r4, r12 FROM returns
            """, (sector_name, latest_date, latest_date, latest_date, latest_date))
            row = cur.fetchone()
            r1 = float(row[0] or 0)
            r4 = float(row[1] or 0)
            r12 = float(row[2] or 0)
            source = 'constituents'

        # Momentum score: weighted blend (weighted toward 4w as primary swing window)
        momentum = (r1 * 0.2) + (r4 * 0.5) + (r12 * 0.3)
        sector_returns.append((sector_name, etf, r1, r4, r12, momentum, source))

    # Sort by momentum descending; assign ranks
    sector_returns.sort(key=lambda x: x[5], reverse=True)

    print(f"\n  Sector momentum (latest):")
    print(f"  {'#':>3} {'Sector':<25} {'ETF':<5} {'1w':>7} {'4w':>7} {'12w':>7} {'Mom':>7} {'Src':<10}")
    for i, (sec, etf, r1, r4, r12, mom, src) in enumerate(sector_returns, 1):
        print(f"  {i:>3} {sec:<25} {etf:<5} {r1:+7.2f} {r4:+7.2f} {r12:+7.2f} {mom:+7.2f} {src:<10}")

    # Get prior ranks (1w, 4w, 12w ago) for each sector
    rank_lookback = {}
    for lookback in (5, 20, 60):
        cur.execute(f"""
            SELECT sector_name, current_rank
            FROM sector_ranking
            WHERE date_recorded = (
                SELECT MAX(date_recorded) FROM sector_ranking
                WHERE date_recorded <= %s::date - INTERVAL '{lookback} days'
            )
        """, (latest_date,))
        rank_lookback[lookback] = dict(cur.fetchall())

    # Persist
    for i, (sec, etf, r1, r4, r12, mom, src) in enumerate(sector_returns, 1):
        cur.execute("""
            INSERT INTO sector_ranking
                (sector_name, date_recorded, current_rank, momentum_score,
                 rank_1w_ago, rank_4w_ago, rank_12w_ago, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT DO NOTHING
        """, (
            sec, latest_date, i, mom,
            rank_lookback[5].get(sec),
            rank_lookback[20].get(sec),
            rank_lookback[60].get(sec),
        ))

    conn.commit()
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n  Persisted {len(sector_returns)} sectors")
    print(f"\n{'='*70}\nCOMPLETE — {elapsed:.1f}s\n{'='*70}\n")

    cur.close()
    conn.close()


if __name__ == "__main__":
    load_sector_ranking()
