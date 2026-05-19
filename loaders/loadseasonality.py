#!/usr/bin/env python3
"""Seasonality Loader — computes day-of-week and monthly return stats from SPY price history.

No external API needed — reads price_daily locally.
Tables: seasonality_day_of_week, seasonality_monthly_stats

Run: python3 loaders/loadseasonality.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date, timedelta

import pandas as pd

from config.env_loader import load_env

log = logging.getLogger(__name__)

DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
MONTH_NAMES = ["January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December"]


def run() -> int:
    from utils.db_connection import get_db_connection

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            start = date.today() - timedelta(days=20 * 365)
            cur.execute(
                "SELECT date, open, close FROM price_daily WHERE symbol='SPY' AND date >= %s AND close IS NOT NULL AND open IS NOT NULL AND open != 0 ORDER BY date",
                (start,),
            )
            rows = cur.fetchall()

        if len(rows) < 252:
            log.error("Not enough SPY price data (%d rows)", len(rows))
            return 1

        df = pd.DataFrame(rows, columns=["date", "open", "close"])
        df["date"] = pd.to_datetime(df["date"])
        df["open"] = df["open"].astype(float)
        df["close"] = df["close"].astype(float)
        df["daily_return"] = (df["close"] - df["open"]) / df["open"] * 100

        # Day-of-week stats (0=Monday ... 6=Sunday in pandas, but EXTRACT(DOW) uses 0=Sunday)
        dof_df = df[df["date"] >= pd.Timestamp(date.today() - timedelta(days=5 * 365))].copy()
        dof_df["dow"] = dof_df["date"].dt.dayofweek  # 0=Monday ... 4=Friday

        with conn.cursor() as cur:
            cur.execute("TRUNCATE seasonality_day_of_week")
            for dow in range(5):  # Mon=0 ... Fri=4
                sub = dof_df[dof_df["dow"] == dow]["daily_return"]
                if len(sub) < 10:
                    continue
                # pandas dow: 0=Monday -> map to day names starting Monday
                day_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][dow]
                cur.execute(
                    """INSERT INTO seasonality_day_of_week
                       (day, day_num, avg_return, win_rate, days_counted)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (
                        day_name,
                        dow + 1,  # 1=Monday for display
                        round(float(sub.mean()), 4),
                        round(float((sub > 0).mean()), 4),
                        len(sub),
                    ),
                )
            log.info("Inserted day-of-week seasonality")

            # Monthly stats (last 20 years)
            df["year"] = df["date"].dt.year
            df["month"] = df["date"].dt.month
            monthly = df.groupby(["year", "month"])["daily_return"].sum().reset_index()
            monthly.columns = ["year", "month", "monthly_return"]

            cur.execute("TRUNCATE seasonality_monthly_stats")
            for m in range(1, 13):
                sub = monthly[monthly["month"] == m]["monthly_return"]
                if len(sub) < 5:
                    continue
                wins = int((sub > 0).sum())
                losses = int((sub <= 0).sum())
                cur.execute(
                    """INSERT INTO seasonality_monthly_stats
                       (month, month_name, avg_return, best_return, worst_return,
                        years_counted, winning_years, losing_years)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        m,
                        MONTH_NAMES[m - 1],
                        round(float(sub.mean()), 4),
                        round(float(sub.max()), 4),
                        round(float(sub.min()), 4),
                        len(sub),
                        wins,
                        losses,
                    ),
                )
            log.info("Inserted monthly seasonality stats")

        conn.commit()
        log.info("Seasonality complete")
        return 0

    except Exception as e:
        log.error("Seasonality loader error: %s", e, exc_info=True)
        conn.rollback()
        return 1
    finally:
        conn.close()


def main() -> int:
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run()


if __name__ == "__main__":
    sys.exit(main())
