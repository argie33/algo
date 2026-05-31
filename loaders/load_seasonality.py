#!/usr/bin/env python3
"""Seasonality Loader — SPY-based monthly and day-of-week seasonality statistics.

Reads SPY historical prices from price_daily and computes:
  - seasonality_monthly_stats: avg/best/worst return per calendar month
  - seasonality_day_of_week: avg return and win rate per day of week

Run: python3 load_seasonality.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from utils.database_context import DatabaseContext

logger = logging.getLogger(__name__)

MONTH_NAMES = {
    1: 'January', 2: 'February', 3: 'March', 4: 'April',
    5: 'May', 6: 'June', 7: 'July', 8: 'August',
    9: 'September', 10: 'October', 11: 'November', 12: 'December',
}
DAY_NAMES = {0: 'Monday', 1: 'Tuesday', 2: 'Wednesday', 3: 'Thursday', 4: 'Friday'}


def load_seasonality() -> int:
    """Compute and upsert seasonality stats from SPY price_daily history."""
    with DatabaseContext('write') as cur:
        # --- Monthly seasonality ---
        # Compute first and last close per calendar month per year, then monthly return.
        cur.execute("""
            WITH spy_monthly AS (
                SELECT
                    EXTRACT(YEAR  FROM date)::int AS yr,
                    EXTRACT(MONTH FROM date)::int AS mo,
                    FIRST_VALUE(close) OVER (
                        PARTITION BY EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date)
                        ORDER BY date ASC
                        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                    ) AS first_close,
                    LAST_VALUE(close) OVER (
                        PARTITION BY EXTRACT(YEAR FROM date), EXTRACT(MONTH FROM date)
                        ORDER BY date ASC
                        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                    ) AS last_close
                FROM price_daily
                WHERE symbol = 'SPY'
                  AND close > 0
            ),
            monthly_returns AS (
                SELECT DISTINCT
                    yr, mo,
                    ROUND(((last_close / NULLIF(first_close, 0)) - 1) * 100, 4) AS ret_pct
                FROM spy_monthly
            ),
            agg AS (
                SELECT
                    mo AS month,
                    ROUND(AVG(ret_pct)::numeric, 4)  AS avg_return,
                    ROUND(MAX(ret_pct)::numeric, 4)  AS best_return,
                    ROUND(MIN(ret_pct)::numeric, 4)  AS worst_return,
                    COUNT(*)                          AS years_counted,
                    COUNT(*) FILTER (WHERE ret_pct > 0) AS winning_years,
                    COUNT(*) FILTER (WHERE ret_pct < 0) AS losing_years
                FROM monthly_returns
                GROUP BY mo
            )
            SELECT * FROM agg ORDER BY month
        """)
        monthly_rows = cur.fetchall()

        cur.execute("TRUNCATE TABLE seasonality_monthly_stats")
        monthly_records = [
            (
                int(r['month']),
                MONTH_NAMES.get(int(r['month']), str(r['month'])),
                float(r['avg_return']) if r['avg_return'] is not None else None,
                float(r['best_return']) if r['best_return'] is not None else None,
                float(r['worst_return']) if r['worst_return'] is not None else None,
                int(r['years_counted']),
                int(r['winning_years']),
                int(r['losing_years']),
            )
            for r in monthly_rows
        ]
        cur.executemany("""
            INSERT INTO seasonality_monthly_stats
                (month, month_name, avg_return, best_return, worst_return,
                 years_counted, winning_years, losing_years)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, monthly_records)
        logger.info(f"Inserted {len(monthly_records)} monthly seasonality rows")

        # --- Day-of-week seasonality ---
        cur.execute("""
            WITH daily_returns AS (
                SELECT
                    date,
                    EXTRACT(DOW FROM date)::int AS dow,
                    ROUND(((close / NULLIF(LAG(close) OVER (ORDER BY date), 0)) - 1) * 100, 4) AS ret_pct
                FROM price_daily
                WHERE symbol = 'SPY'
                  AND close > 0
            ),
            agg AS (
                SELECT
                    dow,
                    ROUND(AVG(ret_pct)::numeric, 4) AS avg_return,
                    ROUND(COUNT(*) FILTER (WHERE ret_pct > 0)::numeric / NULLIF(COUNT(*), 0) * 100, 2) AS win_rate,
                    COUNT(*) AS days_counted
                FROM daily_returns
                WHERE dow BETWEEN 1 AND 5   -- Mon=1 … Fri=5 (PostgreSQL DOW: Sun=0)
                  AND ret_pct IS NOT NULL
                GROUP BY dow
            )
            SELECT * FROM agg ORDER BY dow
        """)
        dow_rows = cur.fetchall()

        # PostgreSQL DOW: 0=Sun, 1=Mon … 5=Fri, 6=Sat  →  day_num 0=Mon … 4=Fri
        DOW_PG_TO_DAY_NUM = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}
        DOW_PG_TO_NAME = {1: 'Monday', 2: 'Tuesday', 3: 'Wednesday', 4: 'Thursday', 5: 'Friday'}

        cur.execute("TRUNCATE TABLE seasonality_day_of_week")
        dow_records = [
            (
                DOW_PG_TO_NAME.get(int(r['dow']), str(r['dow'])),
                DOW_PG_TO_DAY_NUM.get(int(r['dow']), int(r['dow']) - 1),
                float(r['avg_return']) if r['avg_return'] is not None else None,
                float(r['win_rate']) if r['win_rate'] is not None else None,
                int(r['days_counted']),
            )
            for r in dow_rows
        ]
        cur.executemany("""
            INSERT INTO seasonality_day_of_week (day, day_num, avg_return, win_rate, days_counted)
            VALUES (%s, %s, %s, %s, %s)
        """, dow_records)
        logger.info(f"Inserted {len(dow_records)} day-of-week seasonality rows")

        return len(monthly_rows) + len(dow_rows)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        count = load_seasonality()
        logger.info(f"SUCCESS: {count} seasonality rows upserted")
        return 0
    except Exception as e:
        logger.error(f"Seasonality load failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
