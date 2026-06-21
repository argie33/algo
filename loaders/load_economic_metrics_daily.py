#!/usr/bin/env python3
"""Economic Metrics Daily Loader - Pre-compute derived economic indicators.

MEDIUM-SEVERITY ISSUE: CPI YoY, SPY price change calculated in dashboard.

Pre-computes daily economic metrics for dashboard consumption:
- cpi_yoy_pct: CPI year-over-year percentage change
- spy_price_change_pct: SPY daily price change percentage
- yield_curve_slope: 10Y - 2Y yield spread
"""

import logging
import sys
from datetime import date, datetime
from typing import Any

import psycopg2

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.infrastructure.timezone import EASTERN_TZ
from utils.optimal_loader import OptimalLoader


logger = logging.getLogger(__name__)
ET = EASTERN_TZ


class EconomicMetricsDailyLoader(OptimalLoader):
    """Compute derived economic metrics daily."""

    table_name = "economic_metrics_daily"
    primary_key = ("report_date",)
    watermark_field = "report_date"

    # Allow multiple updates per day
    allow_multiple_updates_per_day = True

    def fetch_global(self, since: date | None) -> list[dict] | None:
        """Compute daily economic metrics from source data.

        Metrics:
        - cpi_yoy_pct: Year-over-year CPI change (%)
        - spy_price_change_pct: SPY daily price change (%)
        - yield_curve_slope_10y2y: 10Y - 2Y yield spread
        """
        try:
            now_et = datetime.now(ET)
            report_date = now_et.date()

            with DatabaseContext("read") as cur:
                # 1. Compute CPI YoY
                cpi_yoy = None
                cpi_error = None
                try:
                    cur.execute("""
                        SELECT value FROM economic_data
                        WHERE series_id='CPIAUCSL'
                        ORDER BY date DESC LIMIT 1
                    """)
                    cpi_cur_row = cur.fetchone()
                    if cpi_cur_row is None:
                        cpi_error = "no_current_cpi_data"
                        cpi_cur = None
                    else:
                        cpi_val = cpi_cur_row.get("value")
                        cpi_cur = float(cpi_val) if cpi_val is not None else None

                    if cpi_cur is not None:
                        # Get CPI from 1 year ago
                        cur.execute("""
                            SELECT value FROM economic_data
                            WHERE series_id='CPIAUCSL'
                              AND date <= CURRENT_DATE - 365
                            ORDER BY date DESC LIMIT 1
                        """)
                        cpi_yoy_row = cur.fetchone()
                        if cpi_yoy_row is None:
                            cpi_error = "no_historical_cpi_data"
                            cpi_prev = None
                        else:
                            cpi_prev_val = cpi_yoy_row.get("value")
                            cpi_prev = float(cpi_prev_val) if cpi_prev_val is not None else None

                        if cpi_prev is not None and cpi_prev > 0:
                            cpi_yoy = round((cpi_cur - cpi_prev) / cpi_prev * 100, 2)
                        elif cpi_prev == 0:
                            cpi_error = "prev_cpi_zero"
                    else:
                        cpi_error = "no_current_cpi"
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    cpi_error = f"cpi_error:{type(e).__name__}"
                    logger.warning(f"Failed to compute CPI YoY: {e}")

                # 2. Compute SPY daily price change
                spy_price_change = None
                spy_error = None
                try:
                    cur.execute("""
                        SELECT close, date FROM price_daily
                        WHERE symbol='SPY'
                        ORDER BY date DESC LIMIT 2
                    """)
                    spy_rows = cur.fetchall()
                    if spy_rows is None:
                        spy_rows = []

                    if len(spy_rows) >= 2:
                        cur_price = (
                            float(spy_rows[0].get("close"))
                            if spy_rows[0].get("close") is not None
                            else None
                        )
                        prev_price = (
                            float(spy_rows[1].get("close"))
                            if spy_rows[1].get("close") is not None
                            else None
                        )

                        if (
                            cur_price is not None
                            and prev_price is not None
                            and prev_price > 0
                        ):
                            spy_price_change = round(
                                (cur_price - prev_price) / prev_price * 100, 2
                            )
                        elif prev_price == 0:
                            spy_error = "prev_price_zero"
                    else:
                        spy_error = f"insufficient_data:{len(spy_rows)}"
                except (ValueError, ZeroDivisionError, TypeError) as e:
                    spy_error = f"spy_error:{type(e).__name__}"
                    logger.warning(f"Failed to compute SPY price change: {e}")

                # 3. Compute yield curve slope (10Y - 2Y)
                ycs_10y2y = None
                ycs_error = None
                try:
                    cur.execute("""
                        SELECT DISTINCT ON (series_id) series_id, value FROM economic_data
                        WHERE series_id IN ('DGS10', 'DGS2')
                        ORDER BY series_id, date DESC
                    """)
                    ycs_rows = cur.fetchall() or []

                    # Each series_id appears once (most recent date)
                    dgs10 = None
                    dgs2 = None
                    for row in ycs_rows:
                        if row.get("series_id") == "DGS10":
                            dgs10 = (
                                float(row.get("value"), default=0.0)
                                if row.get("value") is not None
                                else None
                            )
                        elif row.get("series_id") == "DGS2":
                            dgs2 = (
                                float(row.get("value"), default=0.0)
                                if row.get("value") is not None
                                else None
                            )

                    if dgs10 is not None and dgs2 is not None:
                        ycs_10y2y = round(dgs10 - dgs2, 3)
                    else:
                        ycs_error = f"missing_data:DGS10={dgs10},DGS2={dgs2}"
                except (ValueError, ZeroDivisionError, TypeError) as e:
                    ycs_error = f"ycs_error:{type(e).__name__}"
                    logger.warning(f"Failed to compute yield curve slope: {e}")

                if cpi_yoy is None and spy_price_change is None and ycs_10y2y is None:
                    raise RuntimeError(
                        f"[ECONOMIC_METRICS] All metrics failed: CPI({cpi_error}), "
                        f"SPY({spy_error}), YCS({ycs_error}). Cannot proceed without at least one metric."
                    )

                result = {
                    "report_date": report_date,
                    "cpi_yoy_pct": cpi_yoy,
                    "cpi_yoy_error": cpi_error,
                    "spy_price_change_pct": spy_price_change,
                    "spy_price_change_error": spy_error,
                    "yield_curve_slope_10y2y": ycs_10y2y,
                    "yield_curve_slope_error": ycs_error,
                    "updated_at": datetime.now(ET),
                }

                logger.info(
                    f"Economic metrics: CPI_YoY={cpi_yoy}% SPY_chg={spy_price_change}% YCS={ycs_10y2y}"
                )

                return [result]

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[ECONOMIC_METRICS] Failed to compute daily metrics: {e}. "
                "Cannot proceed without macro indicators."
            )



if __name__ == "__main__":
    sys.exit(run_loader(EconomicMetricsDailyLoader, global_mode=True))
