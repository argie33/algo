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
    """Compute derived economic metrics daily.

    CRITICAL METRICS (must be present):
    - CPI YoY: Year-over-year CPI change (required for inflation environment assessment)
    - Yield curve slope: 10Y - 2Y spread (required for market regime detection)
    - SPY price change: Daily SPY performance for market regime assessment

    NOTE: All metrics above are REQUIRED. No fallback sources are implemented.
    If any metric unavailable, entire loader fails (no partial/degraded mode).
    Dashboard does NOT implement fallback computation from price_daily.
    """

    table_name = "economic_metrics_daily"
    primary_key = ("report_date",)
    watermark_field = "report_date"

    # Allow multiple updates per day
    allow_multiple_updates_per_day = True

    def fetch_global(self, since: date | None) -> list[dict[str, Any]] | None:
        """Compute daily economic metrics from source data.

        All metrics are CRITICAL—function raises RuntimeError if any metric unavailable.
        No partial/degraded mode, no silent returns.

        Metrics (REQUIRED):
        - cpi_yoy_pct: Year-over-year CPI change (%)
        - spy_price_change_pct: SPY daily price change (%)
        - yield_curve_slope_10y2y: 10Y - 2Y yield spread
        """
        try:
            now_et = datetime.now(ET)
            report_date = now_et.date()

            with DatabaseContext("read") as cur:
                # 1. Compute CPI YoY (CRITICAL: inflation environment)
                cpi_yoy = self._compute_cpi_yoy(cur)

                # 2. Compute SPY daily price change (CRITICAL: market regime)
                spy_price_change = self._compute_spy_price_change(cur)

                # 3. Compute yield curve slope (CRITICAL: market regime)
                ycs_10y2y = self._compute_yield_curve_slope(cur)

                result = {
                    "report_date": report_date,
                    "cpi_yoy_pct": cpi_yoy,
                    "spy_price_change_pct": spy_price_change,
                    "yield_curve_slope_10y2y": ycs_10y2y,
                    "updated_at": datetime.now(ET),
                }

                logger.info(
                    f"Economic metrics: CPI_YoY={cpi_yoy}% SPY_chg={spy_price_change}% YCS={ycs_10y2y}"
                )

                return [result]

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(
                f"[ECONOMIC_METRICS] Failed to compute daily metrics: {e}. Cannot proceed without macro indicators."
            ) from e

    def _compute_cpi_yoy(self, cur: Any) -> float:
        """Compute CPI year-over-year percentage change (CRITICAL metric).

        Raises RuntimeError if CPI data unavailable—this is a critical market regime indicator.
        """
        try:
            # Get current CPI value
            cur.execute("""
                SELECT value FROM economic_data
                WHERE series_id = 'CPIAUCSL'
                ORDER BY date DESC LIMIT 1
            """)
            cpi_cur_row = cur.fetchone()
            if cpi_cur_row is None:
                raise RuntimeError(
                    "[ECONOMIC_METRICS] Current CPI data not found. "
                    "Ensure CPIAUCSL series is loaded in economic_data table."
                )

            # Validate row structure and extract value
            if "value" not in cpi_cur_row:
                raise RuntimeError(
                    "[ECONOMIC_METRICS] CPI row missing 'value' column from economic_data query."
                )
            cpi_cur_val = cpi_cur_row["value"]
            if cpi_cur_val is None:
                raise RuntimeError(
                    "[ECONOMIC_METRICS] Current CPI value is NULL in database."
                )
            cpi_cur = float(cpi_cur_val)

            # Get CPI from 1 year ago
            cur.execute("""
                SELECT value FROM economic_data
                WHERE series_id = 'CPIAUCSL'
                  AND date <= CURRENT_DATE - 365
                ORDER BY date DESC LIMIT 1
            """)
            cpi_prev_row = cur.fetchone()
            if cpi_prev_row is None:
                raise RuntimeError(
                    "[ECONOMIC_METRICS] Historical CPI data (1 year ago) not found. "
                    "Insufficient price history for YoY calculation."
                )

            # Validate row structure and extract value
            if "value" not in cpi_prev_row:
                raise RuntimeError(
                    "[ECONOMIC_METRICS] Historical CPI row missing 'value' column."
                )
            cpi_prev_val = cpi_prev_row["value"]
            if cpi_prev_val is None:
                raise RuntimeError(
                    "[ECONOMIC_METRICS] Historical CPI value is NULL in database."
                )
            cpi_prev = float(cpi_prev_val)

            # Validate divisor
            if cpi_prev <= 0:
                raise RuntimeError(
                    f"[ECONOMIC_METRICS] Invalid historical CPI value for YoY calc: {cpi_prev}. "
                    "CPI values must be positive."
                )

            return round((cpi_cur - cpi_prev) / cpi_prev * 100, 2)

        except (ValueError, TypeError) as e:
            raise RuntimeError(
                f"[ECONOMIC_METRICS] CPI YoY calculation failed: {e}. "
                "Ensure CPI values are numeric in economic_data table."
            ) from e

    def _compute_spy_price_change(self, cur: Any) -> float:
        """Compute SPY daily price change percentage (CRITICAL metric).

        Requires 2 most recent trading days. Raises RuntimeError if unavailable.
        """
        try:
            cur.execute("""
                SELECT close, date FROM price_daily
                WHERE symbol = 'SPY'
                ORDER BY date DESC LIMIT 2
            """)
            spy_rows = cur.fetchall()

            if spy_rows is None or len(spy_rows) < 2:
                raise RuntimeError(
                    f"[ECONOMIC_METRICS] Insufficient SPY price data. "
                    f"Need 2 days, found {len(spy_rows) if spy_rows else 0}. "
                    "Ensure SPY is loaded in price_daily before computing economic metrics."
                )

            # Validate row structure for most recent close
            if "close" not in spy_rows[0]:
                raise RuntimeError(
                    "[ECONOMIC_METRICS] SPY row missing 'close' column from price_daily query."
                )
            cur_close = spy_rows[0]["close"]
            if cur_close is None:
                raise RuntimeError(
                    "[ECONOMIC_METRICS] Current SPY close price is NULL in database."
                )

            # Validate row structure for previous close
            if "close" not in spy_rows[1]:
                raise RuntimeError(
                    "[ECONOMIC_METRICS] SPY historical row missing 'close' column."
                )
            prev_close = spy_rows[1]["close"]
            if prev_close is None:
                raise RuntimeError(
                    "[ECONOMIC_METRICS] Previous SPY close price is NULL in database."
                )

            # Convert and validate
            cur_price = float(cur_close)
            prev_price = float(prev_close)

            if prev_price <= 0:
                raise RuntimeError(
                    f"[ECONOMIC_METRICS] Invalid previous SPY price: {prev_price}. "
                    "SPY prices must be positive."
                )

            return round((cur_price - prev_price) / prev_price * 100, 2)

        except (ValueError, TypeError) as e:
            raise RuntimeError(
                f"[ECONOMIC_METRICS] SPY price change calculation failed: {e}. "
                "Ensure SPY prices are numeric in price_daily table."
            ) from e

    def _compute_yield_curve_slope(self, cur: Any) -> float:
        """Compute yield curve slope: 10Y - 2Y spread (CRITICAL metric).

        Raises RuntimeError if either yield rate unavailable.
        """
        try:
            cur.execute("""
                SELECT DISTINCT ON (series_id) series_id, value FROM economic_data
                WHERE series_id IN ('DGS10', 'DGS2')
                ORDER BY series_id, date DESC
            """)
            ycs_rows = cur.fetchall()

            if ycs_rows is None:
                raise RuntimeError(
                    "[ECONOMIC_METRICS] Yield curve query returned None—database error or connection lost."
                )

            # Extract yields by series_id
            dgs10 = None
            dgs2 = None
            for row in ycs_rows:
                # Validate row structure
                if "series_id" not in row or "value" not in row:
                    raise RuntimeError(
                        "[ECONOMIC_METRICS] Yield curve row missing 'series_id' or 'value' columns."
                    )

                series_id = row["series_id"]
                val = row["value"]

                if val is None:
                    raise RuntimeError(
                        f"[ECONOMIC_METRICS] Yield curve value for {series_id} is NULL in database."
                    )

                try:
                    val_float = float(val)
                except (ValueError, TypeError) as e:
                    raise RuntimeError(
                        f"[ECONOMIC_METRICS] Invalid yield value for {series_id}: {val}. "
                        "Yield values must be numeric."
                    ) from e

                if series_id == "DGS10":
                    dgs10 = val_float
                elif series_id == "DGS2":
                    dgs2 = val_float

            # Validate both yields present
            if dgs10 is None:
                raise RuntimeError(
                    "[ECONOMIC_METRICS] 10-year yield (DGS10) not found in economic_data. "
                    "Ensure DGS10 series is loaded."
                )
            if dgs2 is None:
                raise RuntimeError(
                    "[ECONOMIC_METRICS] 2-year yield (DGS2) not found in economic_data. "
                    "Ensure DGS2 series is loaded."
                )

            return round(dgs10 - dgs2, 3)

        except (ValueError, TypeError) as e:
            raise RuntimeError(
                f"[ECONOMIC_METRICS] Yield curve slope calculation failed: {e}. "
                "Ensure yield values are numeric in economic_data table."
            ) from e


if __name__ == "__main__":
    sys.exit(run_loader(EconomicMetricsDailyLoader, global_mode=True))
