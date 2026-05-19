#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

"""
Seasonality Stats Loader.

Computes day-of-week and monthly seasonality statistics from SPY price_daily
data and stores results in seasonality_day_of_week and seasonality_monthly_stats.

No external API needed — reads from local price_daily table.
Run weekly (data changes slowly).

Run:
    python3 loadseasonality.py
"""

import logging
from calendar import month_abbr
from datetime import date

from config.env_loader import load_env
from utils.db_connection import get_db_connection

log = logging.getLogger(__name__)

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def compute_day_of_week(cur) -> list:
    """Compute average return and win rate by day of week using SPY daily returns."""
    cur.execute("""
        SELECT
            EXTRACT(DOW FROM date)::int AS day_num,
            (close - open) / NULLIF(open, 0) * 100 AS daily_return
        FROM price_daily
        WHERE symbol = 'SPY'
          AND date >= CURRENT_DATE - INTERVAL '5 years'
          AND close IS NOT NULL AND open IS NOT NULL AND open != 0
        ORDER BY date
    """)
    rows = cur.fetchall()

    buckets: dict = {}
    for row in rows:
        dn = row["day_num"]  # 0=Sunday in PostgreSQL EXTRACT(DOW)
        ret = float(row["daily_return"])
        if dn not in buckets:
            buckets[dn] = []
        buckets[dn].append(ret)

    results = []
    for dn, returns in buckets.items():
        n = len(returns)
        if n == 0:
            continue
        avg = sum(returns) / n
        wins = sum(1 for r in returns if r > 0)
        # Map PostgreSQL DOW (0=Sun) to name
        day_name = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][dn]
        results.append({
            "day": day_name,
            "day_num": dn,
            "avg_return": round(avg, 4),
            "win_rate": round(wins / n * 100, 4),
            "days_counted": n,
        })
    return results


def compute_monthly(cur) -> list:
    """Compute monthly return stats using SPY monthly close-to-close returns."""
    cur.execute("""
        SELECT
            EXTRACT(MONTH FROM date)::int AS month,
            EXTRACT(YEAR FROM date)::int AS year,
            MAX(close) FILTER (WHERE date = (
                SELECT MAX(d2.date) FROM price_daily d2
                WHERE d2.symbol = 'SPY'
                  AND EXTRACT(MONTH FROM d2.date) = EXTRACT(MONTH FROM price_daily.date)
                  AND EXTRACT(YEAR FROM d2.date) = EXTRACT(YEAR FROM price_daily.date)
            )) AS month_close
        FROM price_daily
        WHERE symbol = 'SPY'
          AND date >= CURRENT_DATE - INTERVAL '20 years'
          AND close IS NOT NULL
        GROUP BY month, year
        ORDER BY year, month
    """)
    rows = cur.fetchall()

    # Build dict {(year, month): close}
    closes = {}
    for row in rows:
        if row["month_close"] is not None:
            closes[(int(row["year"]), int(row["month"]))] = float(row["month_close"])

    # Compute month-over-month returns
    sorted_keys = sorted(closes.keys())
    monthly_returns: dict = {}
    for i in range(1, len(sorted_keys)):
        prev_key = sorted_keys[i - 1]
        curr_key = sorted_keys[i]
        prev_c = closes[prev_key]
        curr_c = closes[curr_key]
        if prev_c == 0:
            continue
        ret = (curr_c - prev_c) / prev_c * 100
        month = curr_key[1]
        if month not in monthly_returns:
            monthly_returns[month] = []
        monthly_returns[month].append(ret)

    results = []
    for month, returns in monthly_returns.items():
        n = len(returns)
        if n == 0:
            continue
        avg = sum(returns) / n
        wins = sum(1 for r in returns if r > 0)
        results.append({
            "month": month,
            "month_name": month_abbr[month],
            "avg_return": round(avg, 4),
            "best_return": round(max(returns), 4),
            "worst_return": round(min(returns), 4),
            "years_counted": n,
            "winning_years": wins,
            "losing_years": n - wins,
        })
    return results


def upsert_all(conn, dow_rows: list, monthly_rows: list) -> tuple:
    cur = conn.cursor()
    try:
        # Truncate and reload (small tables, no incremental needed)
        cur.execute("TRUNCATE TABLE seasonality_day_of_week")
        for row in dow_rows:
            cur.execute(
                """
                INSERT INTO seasonality_day_of_week
                    (day, day_num, avg_return, win_rate, days_counted)
                VALUES (%(day)s, %(day_num)s, %(avg_return)s, %(win_rate)s, %(days_counted)s)
                """,
                row,
            )

        cur.execute("TRUNCATE TABLE seasonality_monthly_stats")
        for row in monthly_rows:
            cur.execute(
                """
                INSERT INTO seasonality_monthly_stats
                    (month, month_name, avg_return, best_return, worst_return,
                     years_counted, winning_years, losing_years)
                VALUES (%(month)s, %(month_name)s, %(avg_return)s, %(best_return)s,
                        %(worst_return)s, %(years_counted)s, %(winning_years)s, %(losing_years)s)
                """,
                row,
            )
        conn.commit()
        return len(dow_rows), len(monthly_rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        dow_rows = compute_day_of_week(cur)
        monthly_rows = compute_monthly(cur)
    finally:
        cur.close()

    if not dow_rows and not monthly_rows:
        log.warning("No SPY price data found — run price loader first")
        conn.close()
        return 0

    n_dow, n_monthly = upsert_all(conn, dow_rows, monthly_rows)
    conn.close()
    log.info("Seasonality: %d day-of-week rows, %d monthly rows", n_dow, n_monthly)
    return 0


if __name__ == "__main__":
    sys.exit(main())
