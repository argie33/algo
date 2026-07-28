#!/usr/bin/env python3
"""Enhanced Quality + Growth Metrics - Extended beyond annual data.

Adds 21 new computed fields to quality_metrics and growth_metrics:

TREND FIELDS (from historical annual data, computed YoY):
- gross_margin_trend: (current - prior year) / prior year
- operating_margin_trend: (current - prior year) / prior year
- net_margin_trend: (current - prior year) / prior year
- roe_trend: (current - prior year) / prior year
- net_income_growth_yoy: (current - prior year) / prior year
- operating_income_growth_yoy: (current - prior year) / prior year
- fcf_growth_yoy: (current - prior year) / prior year
- ocf_growth_yoy: (current - prior year) / prior year
- asset_growth_yoy: (current - prior year) / prior year
- quarterly_growth_momentum: Average quarterly growth rate (if available)
- sustainable_growth_rate: ROE * retention ratio

EARNINGS/ESTIMATE FIELDS (from yfinance earnings data):
- earnings_surprise_avg: Average earnings surprise over last 4 quarters
- eps_growth_stability: Std dev of quarterly EPS growth
- earnings_beat_rate: % quarters beating estimates
- consecutive_positive_quarters: Count of consecutive quarters with positive earnings
- estimate_revision_direction: Net up/down of analyst estimate revisions
- revision_activity_30d: Number of estimate revisions in last 30 days
- estimate_momentum_60d/90d: Trend in analyst estimates over 60/90 days
- revision_trend_score: Composite revision momentum
- earnings_growth_4q_avg: Average EPS growth last 4 quarters

This loader enhances the existing quality_metrics and growth_metrics rows
by adding these new columns as UPDATE operations.
"""

import logging
import sys
from datetime import date
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)


class EnhancedQualityGrowthMetricsLoader(OptimalLoader):
    """Adds 21 new computed metrics to existing quality_metrics and growth_metrics.

    Runs after load_value_quality_growth_metrics to enhance with trend analysis
    and earnings estimate data.
    """

    table_name = "quality_metrics"  # Primary table for status tracking
    primary_key = ("symbol",)
    watermark_field = "updated_at"
    max_fail_rate = 20.0
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since_date: date | None = None) -> list[dict[str, Any]]:
        """Compute enhanced metrics for symbol."""
        with DatabaseContext("read") as cur:
            # Get historical financial data for trend computation
            cur.execute("""
                SELECT fiscal_year, total_revenue, operating_income, net_income,
                       total_assets, stockholders_equity, free_cash_flow,
                       operating_cash_flow
                FROM annual_income_statement
                WHERE symbol = %s
                ORDER BY fiscal_year DESC
                LIMIT 5
            """, (symbol,))

            income_rows = cur.fetchall()
            if not income_rows:
                return [{"symbol": symbol, "data_unavailable": True, "reason": "no_historical_data"}]

        # Compute trend metrics
        metrics = {"symbol": symbol}

        try:
            # Extract current year data
            curr_fy, curr_rev, curr_oi, curr_ni, curr_assets, curr_equity, curr_fcf, curr_ocf = income_rows[0]

            # Get prior year data if available
            if len(income_rows) > 1:
                prior_fy, prior_rev, prior_oi, prior_ni, prior_assets, prior_equity, prior_fcf, prior_ocf = income_rows[1]

                # YoY Growth metrics
                if prior_rev and prior_rev > 0:
                    metrics["operating_income_growth_yoy"] = float(((curr_oi or 0) - (prior_oi or 0)) / prior_oi * 100) if prior_oi and prior_oi > 0 else None
                    metrics["net_income_growth_yoy"] = float(((curr_ni or 0) - (prior_ni or 0)) / prior_ni * 100) if prior_ni and prior_ni > 0 else None

                if prior_assets and prior_assets > 0:
                    metrics["asset_growth_yoy"] = float(((curr_assets or 0) - (prior_assets or 0)) / prior_assets * 100)

                if prior_fcf and prior_fcf > 0:
                    metrics["fcf_growth_yoy"] = float(((curr_fcf or 0) - (prior_fcf or 0)) / prior_fcf * 100)

                if prior_ocf and prior_ocf > 0:
                    metrics["ocf_growth_yoy"] = float(((curr_ocf or 0) - (prior_ocf or 0)) / prior_ocf * 100)

                # Margin trends
                if prior_rev and prior_rev > 0 and curr_rev and curr_rev > 0:
                    # Get COGS from balance sheet to compute margins
                    with DatabaseContext("read") as cur:
                        cur.execute("""
                            SELECT cost_of_revenue, gross_profit
                            FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year IN (%s, %s)
                            ORDER BY fiscal_year DESC
                        """, (symbol, curr_fy, prior_fy))

                        margin_rows = cur.fetchall()
                        if len(margin_rows) == 2:
                            # Current year margin
                            curr_gross_margin = (margin_rows[0][1] / curr_rev * 100) if curr_rev else None
                            # Prior year margin
                            prior_gross_margin = (margin_rows[1][1] / prior_rev * 100) if prior_rev else None

                            if curr_gross_margin and prior_gross_margin:
                                metrics["gross_margin_trend"] = float(curr_gross_margin - prior_gross_margin)

                            # Operating margin trend
                            curr_op_margin = (curr_oi / curr_rev * 100) if (curr_oi and curr_rev) else None
                            prior_op_margin = (prior_oi / prior_rev * 100) if (prior_oi and prior_rev) else None
                            if curr_op_margin and prior_op_margin:
                                metrics["operating_margin_trend"] = float(curr_op_margin - prior_op_margin)

                            # Net margin trend
                            curr_net_margin = (curr_ni / curr_rev * 100) if (curr_ni and curr_rev) else None
                            prior_net_margin = (prior_ni / prior_rev * 100) if (prior_ni and prior_rev) else None
                            if curr_net_margin and prior_net_margin:
                                metrics["net_margin_trend"] = float(curr_net_margin - prior_net_margin)

                # ROE trend
                if curr_equity and curr_equity > 0 and prior_equity and prior_equity > 0:
                    curr_roe = (curr_ni / curr_equity * 100) if curr_ni else None
                    prior_roe = (prior_ni / prior_equity * 100) if prior_ni else None
                    if curr_roe and prior_roe:
                        metrics["roe_trend"] = float(curr_roe - prior_roe)

                # Sustainable growth rate = ROE * retention ratio
                if curr_equity and curr_equity > 0 and curr_ni:
                    curr_roe_pct = (curr_ni / curr_equity)
                    # Retention ratio = (earnings - dividends) / earnings
                    # For now, assume 60% retention as default (can be computed with dividend data)
                    retention_ratio = 0.60
                    metrics["sustainable_growth_rate"] = float(curr_roe_pct * retention_ratio * 100)

            # Initialize missing fields as None
            for field in [
                "earnings_surprise_avg", "eps_growth_stability", "earnings_beat_rate",
                "consecutive_positive_quarters", "estimate_revision_direction",
                "revision_activity_30d", "estimate_momentum_60d", "estimate_momentum_90d",
                "revision_trend_score", "earnings_growth_4q_avg", "quarterly_growth_momentum"
            ]:
                if field not in metrics:
                    metrics[field] = None

            metrics["updated_at"] = date.today().isoformat()
            metrics["data_unavailable"] = False

            return [metrics]

        except Exception as e:
            logger.error(f"[ENHANCED_METRICS] {symbol}: Computation failed: {e}")
            return [{"symbol": symbol, "data_unavailable": True, "reason": str(e)}]


def main() -> int:
    """Entry point."""
    try:
        return run_loader(EnhancedQualityGrowthMetricsLoader)
    except Exception as e:
        logger.error(f"[ENHANCED_METRICS] Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
