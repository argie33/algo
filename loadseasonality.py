#!/usr/bin/env python3
"""
Seasonality Loader — computes S&P 500 (SPY) monthly and day-of-week return
statistics from the price_daily table and writes them into
seasonality_monthly_stats and seasonality_day_of_week.

The API reads these tables without a symbol filter, so these are market-level
aggregates rather than per-symbol rows.

Run:
    python3 loadseasonality.py
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None
credential_manager = get_credential_manager()

import logging
import math
import os
import sys
from collections import defaultdict

from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("loadseasonality")

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}
DOW_NAMES = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday"}


def _connect():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        user=os.getenv("DB_USER", "stocks"),
        password=credential_manager.get_db_credentials()["password"],
        database=os.getenv("DB_NAME", "stocks"),
    )


def _fetch_spy_prices(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT date, close FROM price_daily WHERE symbol = 'SPY' AND close IS NOT NULL ORDER BY date ASC"
        )
        return cur.fetchall()


def _compute_monthly_stats(rows):
    """
    Group SPY daily closes by (year, month). For each month compute the
    monthly return: (last_close / first_close_prev_month - 1) * 100.
    Returns dict keyed by month 1-12.
    """
    from datetime import date as dtdate

    # Build sorted (date, close) list
    prices = [(r[0], float(r[1])) for r in rows]
    if len(prices) < 22:
        return {}

    # Compute month-end returns: group by year+month, keep first+last
    monthly = defaultdict(list)
    for d, c in prices:
        monthly[(d.year, d.month)].append(c)

    sorted_months = sorted(monthly.keys())
    monthly_returns = []  # list of (year, month, return_pct)
    for i in range(1, len(sorted_months)):
        prev_ym = sorted_months[i - 1]
        curr_ym = sorted_months[i]
        prev_last = monthly[prev_ym][-1]
        curr_last = monthly[curr_ym][-1]
        if prev_last > 0:
            ret = (curr_last / prev_last - 1) * 100
            monthly_returns.append((curr_ym[0], curr_ym[1], ret))

    # Aggregate by calendar month
    by_month = defaultdict(list)
    for year, month, ret in monthly_returns:
        by_month[month].append((year, ret))

    stats = {}
    for month in range(1, 13):
        observations = by_month.get(month, [])
        if not observations:
            continue
        rets = [r for _, r in observations]
        avg = sum(rets) / len(rets)
        best = max(rets)
        worst = min(rets)
        winning = sum(1 for r in rets if r > 0)
        stats[month] = {
            "month": month,
            "month_name": MONTH_NAMES[month],
            "avg_return": round(avg, 4),
            "best_return": round(best, 4),
            "worst_return": round(worst, 4),
            "years_counted": len(rets),
            "winning_years": winning,
            "losing_years": len(rets) - winning,
        }
    return stats


def _compute_dow_stats(rows):
    """
    Group SPY daily closes by day-of-week (0=Mon, 4=Fri).
    Day return = (close / prev_close - 1) * 100.
    """
    prices = [(r[0], float(r[1])) for r in rows]
    if len(prices) < 5:
        return {}

    by_dow = defaultdict(list)
    for i in range(1, len(prices)):
        d, c = prices[i]
        prev_c = prices[i - 1][1]
        if prev_c > 0:
            ret = (c / prev_c - 1) * 100
            by_dow[d.weekday()].append(ret)

    stats = {}
    for dow in range(5):
        rets = by_dow.get(dow, [])
        if not rets:
            continue
        avg = sum(rets) / len(rets)
        win_rate = sum(1 for r in rets if r > 0) / len(rets) * 100
        stats[dow] = {
            "day": DOW_NAMES[dow],
            "day_num": dow + 1,
            "avg_return": round(avg, 4),
            "win_rate": round(win_rate, 2),
            "days_counted": len(rets),
        }
    return stats


def _upsert_monthly(conn, stats):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM seasonality_monthly_stats")
        for row in stats.values():
            cur.execute(
                """INSERT INTO seasonality_monthly_stats
                   (month, month_name, avg_return, best_return, worst_return,
                    years_counted, winning_years, losing_years)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (row["month"], row["month_name"], row["avg_return"],
                 row["best_return"], row["worst_return"], row["years_counted"],
                 row["winning_years"], row["losing_years"]),
            )
    conn.commit()
    log.info("Wrote %d monthly seasonality rows", len(stats))


def _upsert_dow(conn, stats):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM seasonality_day_of_week")
        for row in stats.values():
            cur.execute(
                """INSERT INTO seasonality_day_of_week
                   (day, day_num, avg_return, win_rate, days_counted)
                   VALUES (%s, %s, %s, %s, %s)""",
                (row["day"], row["day_num"], row["avg_return"],
                 row["win_rate"], row["days_counted"]),
            )
    conn.commit()
    log.info("Wrote %d day-of-week seasonality rows", len(stats))


def main():
    conn = _connect()
    try:
        rows = _fetch_spy_prices(conn)
        if not rows:
            log.error("No SPY price data found in price_daily — nothing to compute")
            return 1
        log.info("Loaded %d SPY price rows", len(rows))

        monthly = _compute_monthly_stats(rows)
        dow = _compute_dow_stats(rows)

        if not monthly:
            log.warning("Insufficient SPY history for monthly stats")
        else:
            _upsert_monthly(conn, monthly)

        if not dow:
            log.warning("Insufficient SPY history for day-of-week stats")
        else:
            _upsert_dow(conn, dow)

        return 0
    except Exception as e:
        log.error("Seasonality computation failed: %s", e)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
