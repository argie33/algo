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

    def run(self, symbols: list[str], since_date: date | None = None, parallelism: int | None = None) -> dict[str, Any]:
        """Override run() to write trend metrics to BOTH quality_metrics and growth_metrics."""
        from utils.loaders.config import get_default_parallelism

        symbols_succeeded = 0
        symbols_failed = 0
        parallelism = parallelism or get_default_parallelism("quality_metrics")

        try:
            with DatabaseContext("write") as cur:
                for table in ["quality_metrics", "growth_metrics"]:
                    cur.execute(
                        "UPDATE data_loader_status SET status = %s, last_updated = NOW(), execution_started = NOW() WHERE table_name = %s",
                        ("loading", table),
                    )
                    if cur.rowcount == 0:
                        cur.execute(
                            "INSERT INTO data_loader_status (table_name, status, last_updated, execution_started) VALUES (%s, %s, NOW(), NOW())",
                            (table, "loading"),
                        )

            for symbol in symbols:
                try:
                    metrics = self.fetch_incremental(symbol, since_date)
                    if not metrics:
                        logger.error(f"[ENHANCED] {symbol}: fetch_incremental returned empty list")
                        symbols_failed += 1
                        continue

                    metric_dict = metrics[0]

                    with DatabaseContext("write") as cur:
                        growth_fields = [
                            "gross_margin_trend", "operating_margin_trend", "net_margin_trend",
                            "roe_trend", "sustainable_growth_rate", "fcf_growth_yoy", "ocf_growth_yoy",
                            "asset_growth_yoy", "quarterly_growth_momentum", "net_income_growth_yoy",
                            "operating_income_growth_yoy"
                        ]

                        update_fields = []
                        values = []
                        for key in growth_fields:
                            if key in metric_dict and metric_dict[key] is not None:
                                update_fields.append(f"{key} = %s")
                                values.append(metric_dict[key])

                        if update_fields:
                            update_fields.append("updated_at = CURRENT_DATE")
                            cur.execute(
                                f"UPDATE growth_metrics SET {', '.join(update_fields)} WHERE symbol = %s",
                                values + [symbol]
                            )

                        quality_fields = [
                            "roic_pct",
                            "earnings_surprise_avg", "eps_growth_stability", "earnings_beat_rate",
                            "consecutive_positive_quarters", "estimate_revision_direction",
                            "revision_activity_30d", "estimate_momentum_60d", "estimate_momentum_90d",
                            "revision_trend_score", "earnings_growth_4q_avg"
                        ]

                        update_fields = []
                        values = []
                        for key in quality_fields:
                            if key in metric_dict and metric_dict[key] is not None:
                                update_fields.append(f"{key} = %s")
                                values.append(metric_dict[key])

                        if update_fields:
                            update_fields.append("updated_at = CURRENT_DATE")
                            cur.execute(
                                f"UPDATE quality_metrics SET {', '.join(update_fields)} WHERE symbol = %s",
                                values + [symbol]
                            )

                    symbols_succeeded += 1

                except Exception as e:
                    logger.error(f"[ENHANCED] {symbol}: {e}")
                    symbols_failed += 1

            success = symbols_succeeded > 0
            fail_rate = (symbols_failed / max(symbols_succeeded + symbols_failed, 1)) * 100

            with DatabaseContext("write") as cur:
                for table in ["quality_metrics", "growth_metrics"]:
                    status = "healthy" if success and fail_rate <= self.max_fail_rate else "failed"
                    cur.execute(
                        "UPDATE data_loader_status SET status = %s, last_updated = NOW() WHERE table_name = %s",
                        (status, table),
                    )

            return {
                "symbols_succeeded": symbols_succeeded,
                "symbols_failed": symbols_failed,
                "success": success
            }

        except Exception as e:
            logger.error(f"[ENHANCED] Fatal error: {e}")
            return {"success": False, "error": str(e)}

    def fetch_incremental(self, symbol: str, since_date: date | None = None) -> list[dict[str, Any]]:
        """Compute enhanced metrics for symbol."""
        with DatabaseContext("read") as cur:
            # Get historical financial data for trend computation
            cur.execute("""
                SELECT i.fiscal_year, i.revenue, i.operating_income, i.net_income,
                       b.total_assets, b.stockholders_equity, b.current_liabilities,
                       c.operating_cash_flow, c.financing_cash_flow
                FROM annual_income_statement i
                LEFT JOIN annual_balance_sheet b ON b.symbol = i.symbol AND b.fiscal_year = i.fiscal_year
                LEFT JOIN annual_cash_flow c ON c.symbol = i.symbol AND c.fiscal_year = i.fiscal_year
                WHERE i.symbol = %s
                ORDER BY i.fiscal_year DESC
                LIMIT 5
            """, (symbol,))

            income_rows = cur.fetchall()
            if not income_rows:
                return [{"symbol": symbol, "data_unavailable": True, "reason": "no_historical_data"}]

        # Compute trend metrics
        metrics = {"symbol": symbol}

        try:
            # Extract current year data
            curr_fy, curr_rev, curr_oi, curr_ni, curr_assets, curr_equity, curr_curr_liab, curr_fcf, curr_ocf = income_rows[0]

            # Convert all to float early to avoid Decimal type issues
            curr_rev_f = safe_float(curr_rev, 'revenue')
            curr_oi_f = safe_float(curr_oi, 'operating_income')
            curr_ni_f = safe_float(curr_ni, 'net_income')
            curr_assets_f = safe_float(curr_assets, 'assets')
            curr_equity_f = safe_float(curr_equity, 'equity')
            curr_curr_liab_f = safe_float(curr_curr_liab, 'current_liabilities')
            curr_fcf_f = safe_float(curr_fcf, 'fcf')
            curr_ocf_f = safe_float(curr_ocf, 'ocf')

            # Compute ROIC = Operating Income / (Total Assets - Current Liabilities)
            if curr_oi_f is not None and curr_assets_f is not None and curr_curr_liab_f is not None:
                invested_capital = curr_assets_f - curr_curr_liab_f
                if invested_capital > 0:
                    metrics["roic_pct"] = float((curr_oi_f / invested_capital) * 100)

            # Get prior year data if available
            if len(income_rows) > 1:
                prior_fy, prior_rev, prior_oi, prior_ni, prior_assets, prior_equity, prior_curr_liab, prior_fcf, prior_ocf = income_rows[1]

                # Convert prior year values too
                prior_rev_f = safe_float(prior_rev, 'revenue')
                prior_oi_f = safe_float(prior_oi, 'operating_income')
                prior_ni_f = safe_float(prior_ni, 'net_income')
                prior_assets_f = safe_float(prior_assets, 'assets')
                prior_equity_f = safe_float(prior_equity, 'equity')
                prior_curr_liab_f = safe_float(prior_curr_liab, 'current_liabilities')
                prior_fcf_f = safe_float(prior_fcf, 'fcf')
                prior_ocf_f = safe_float(prior_ocf, 'ocf')

                # YoY Growth metrics - only compute if both current and prior values exist and prior > 0
                if prior_oi_f and prior_oi_f > 0 and curr_oi_f is not None:
                    metrics["operating_income_growth_yoy"] = float(((curr_oi_f or 0) - (prior_oi_f or 0)) / prior_oi_f * 100)
                if prior_ni_f and prior_ni_f > 0 and curr_ni_f is not None:
                    metrics["net_income_growth_yoy"] = float(((curr_ni_f or 0) - (prior_ni_f or 0)) / prior_ni_f * 100)

                if prior_assets_f and prior_assets_f > 0 and curr_assets_f is not None:
                    metrics["asset_growth_yoy"] = float(((curr_assets_f or 0) - (prior_assets_f or 0)) / prior_assets_f * 100)

                if prior_fcf_f and prior_fcf_f > 0 and curr_fcf_f is not None:
                    metrics["fcf_growth_yoy"] = float(((curr_fcf_f or 0) - (prior_fcf_f or 0)) / prior_fcf_f * 100)

                if prior_ocf_f and prior_ocf_f > 0 and curr_ocf_f is not None:
                    metrics["ocf_growth_yoy"] = float(((curr_ocf_f or 0) - (prior_ocf_f or 0)) / prior_ocf_f * 100)

                # Margin trends
                if prior_rev_f and prior_rev_f > 0 and curr_rev_f and curr_rev_f > 0:
                    # Get COGS from income statement to compute margins
                    with DatabaseContext("read") as cur:
                        cur.execute("""
                            SELECT fiscal_year, cost_of_revenue, gross_profit
                            FROM annual_income_statement
                            WHERE symbol = %s AND fiscal_year IN (%s, %s)
                            ORDER BY fiscal_year DESC
                        """, (symbol, curr_fy, prior_fy))

                        margin_rows = cur.fetchall()
                        if len(margin_rows) == 2:
                            # Current year margin (using gross_profit / revenue)
                            curr_gross_profit = safe_float(margin_rows[0][2], 'gross_profit')
                            prior_gross_profit = safe_float(margin_rows[1][2], 'gross_profit')

                            if curr_gross_profit is not None and curr_rev_f > 0:
                                curr_gross_margin = (curr_gross_profit / curr_rev_f * 100)
                            else:
                                curr_gross_margin = None
                            # Prior year margin
                            if prior_gross_profit is not None and prior_rev_f > 0:
                                prior_gross_margin = (prior_gross_profit / prior_rev_f * 100)
                            else:
                                prior_gross_margin = None

                            if curr_gross_margin is not None and prior_gross_margin is not None:
                                metrics["gross_margin_trend"] = float(curr_gross_margin - prior_gross_margin)

                            # Operating margin trend
                            if curr_oi_f is not None and curr_rev_f > 0:
                                curr_op_margin = (curr_oi_f / curr_rev_f * 100)
                            else:
                                curr_op_margin = None
                            if prior_oi_f is not None and prior_rev_f > 0:
                                prior_op_margin = (prior_oi_f / prior_rev_f * 100)
                            else:
                                prior_op_margin = None
                            if curr_op_margin is not None and prior_op_margin is not None:
                                metrics["operating_margin_trend"] = float(curr_op_margin - prior_op_margin)

                            # Net margin trend
                            if curr_ni_f is not None and curr_rev_f > 0:
                                curr_net_margin = (curr_ni_f / curr_rev_f * 100)
                            else:
                                curr_net_margin = None
                            if prior_ni_f is not None and prior_rev_f > 0:
                                prior_net_margin = (prior_ni_f / prior_rev_f * 100)
                            else:
                                prior_net_margin = None
                            if curr_net_margin is not None and prior_net_margin is not None:
                                metrics["net_margin_trend"] = float(curr_net_margin - prior_net_margin)

                # ROE trend
                if curr_equity_f and curr_equity_f > 0 and prior_equity_f and prior_equity_f > 0:
                    curr_roe = (curr_ni_f / curr_equity_f * 100) if curr_ni_f else None
                    prior_roe = (prior_ni_f / prior_equity_f * 100) if prior_ni_f else None
                    if curr_roe and prior_roe:
                        metrics["roe_trend"] = float(curr_roe - prior_roe)

                # Sustainable growth rate = ROE * retention ratio
                if curr_equity_f and curr_equity_f > 0 and curr_ni_f:
                    curr_roe_pct = (curr_ni_f / curr_equity_f)
                    # Retention ratio = (earnings - dividends) / earnings
                    # For now, assume 60% retention as default (can be computed with dividend data)
                    retention_ratio = 0.60
                    metrics["sustainable_growth_rate"] = float(curr_roe_pct * retention_ratio * 100)

            # Compute quarterly earnings metrics
            self._compute_quarterly_metrics(symbol, metrics)

            # Initialize missing analyst estimate fields as None (not yet loaded by any loader)
            for field in [
                "earnings_surprise_avg", "eps_growth_stability", "earnings_beat_rate",
                "estimate_revision_direction", "revision_activity_30d",
                "estimate_momentum_60d", "estimate_momentum_90d", "revision_trend_score"
            ]:
                if field not in metrics:
                    metrics[field] = None

            metrics["updated_at"] = date.today().isoformat()
            metrics["data_unavailable"] = False

            return [metrics]

        except Exception as e:
            logger.error(f"[ENHANCED_METRICS] {symbol}: Computation failed: {e}")
            return [{"symbol": symbol, "data_unavailable": True, "reason": str(e)}]

    def _compute_quarterly_metrics(self, symbol: str, metrics: dict[str, Any]) -> None:
        """Compute metrics from quarterly earnings data."""
        with DatabaseContext("read") as cur:
            # Get last 8 quarters of earnings data
            cur.execute("""
                SELECT fiscal_year, fiscal_quarter, earnings_per_share, net_income
                FROM quarterly_income_statement
                WHERE symbol = %s AND data_unavailable IS NOT TRUE
                ORDER BY fiscal_year DESC, fiscal_quarter DESC
                LIMIT 8
            """, (symbol,))

            quarters = cur.fetchall()
            if not quarters or len(quarters) < 2:
                return

            # quarters is sorted newest first
            eps_values = [safe_float(q[2], 'earnings_per_share') for q in quarters]  # EPS
            ni_values = [safe_float(q[3], 'net_income') for q in quarters]   # Net Income
            valid_eps = [e for e in eps_values if e is not None]
            valid_ni = [n for n in ni_values if n is not None]

            # Compute consecutive positive quarters (from most recent going backwards)
            consecutive_positive = 0
            for ni in ni_values:
                if ni is not None and ni > 0:
                    consecutive_positive += 1
                else:
                    break
            if consecutive_positive > 0:
                metrics["consecutive_positive_quarters"] = float(consecutive_positive)

            # Compute EPS growth rates over last 4 quarters (if we have 5 quarters)
            if len(valid_eps) >= 5:
                eps_growth_rates = []
                for i in range(len(valid_eps) - 1):
                    if valid_eps[i + 1] is not None and valid_eps[i + 1] != 0:
                        growth = (valid_eps[i] - valid_eps[i + 1]) / abs(valid_eps[i + 1])
                        eps_growth_rates.append(growth)

                if eps_growth_rates:
                    # Average EPS growth (last 4 quarters)
                    if len(eps_growth_rates) >= 4:
                        avg_growth = sum(eps_growth_rates[:4]) / 4
                        metrics["earnings_growth_4q_avg"] = float(avg_growth * 100)

                    # EPS growth stability (standard deviation)
                    if len(eps_growth_rates) >= 2:
                        import statistics
                        try:
                            stdev = statistics.stdev(eps_growth_rates)
                            metrics["eps_growth_stability"] = float(stdev)
                        except (ValueError, statistics.StatisticsError):
                            pass

            # Compute quarterly growth momentum (average of recent quarterly growth rates)
            if len(valid_eps) >= 4:
                recent_growth = []
                for i in range(min(4, len(valid_eps) - 1)):
                    if valid_eps[i + 1] is not None and valid_eps[i + 1] != 0:
                        growth = (valid_eps[i] - valid_eps[i + 1]) / abs(valid_eps[i + 1]) * 100
                        recent_growth.append(growth)
                if recent_growth:
                    metrics["quarterly_growth_momentum"] = float(sum(recent_growth) / len(recent_growth))


def main() -> int:
    """Entry point."""
    try:
        return run_loader(EnhancedQualityGrowthMetricsLoader)
    except Exception as e:
        logger.error(f"[ENHANCED_METRICS] Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
