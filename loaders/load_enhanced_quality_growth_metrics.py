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
from typing import Any, Iterable

import psycopg2

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.loaders.status_manager import LoaderStatusManager
from utils.optimal_loader import OptimalLoader
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)

# Guards against a near-zero EPS-estimate base blowing up a percentage-change calculation
# into a value that overflows this table's NUMERIC(10,4) revision columns (max magnitude
# 999,999.9999) - same class of guard as load_value_quality_growth_metrics.py's
# MAX_TREND_PERCENTAGE_POINTS, applied here to estimate_momentum_60d/90d and
# revision_trend_score.
MAX_TREND_PERCENTAGE_POINTS = 100_000.0

# CRITICAL FIX 2026-08-09: same near-zero-revenue-denominator bound as commits 12063b32a/
# 5ceda9952 (which bounded gross_margin/ebitda_margin/roic_pct/operating_margin/net_margin
# in load_value_quality_growth_metrics.py at |ratio| <= 1000). This loader recomputes
# gross/operating/net margin independently from raw annual_income_statement rows to derive
# *_margin_trend/roe_trend, using the same revenue-denominator division pattern, but never
# inherited the bound - a garbage current-year or prior-year margin (e.g. near-zero revenue)
# was flowing straight into a trend value in the thousands of percentage points.
MAX_MARGIN_ABS_PCT = 1000.0


def _bounded_margin_pct(numerator: float | None, denominator: float | None) -> float | None:
    """(numerator / denominator * 100), or None if denominator missing/non-positive or the
    result exceeds MAX_MARGIN_ABS_PCT (near-zero-denominator garbage value)."""
    if numerator is None or denominator is None or denominator <= 0:
        return None
    margin = numerator / denominator * 100
    return None if abs(margin) > MAX_MARGIN_ABS_PCT else margin


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

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        """Override run() to write trend metrics to BOTH quality_metrics and growth_metrics.

        Args:
            symbols: Stock ticker symbols to process
            parallelism: Number of parallel workers (default 1)
            backfill_days: Number of days to backfill (passed to parent)
        """
        from utils.loaders.config import get_default_parallelism

        symbols_succeeded = 0
        symbols_failed = 0
        parallelism = parallelism or get_default_parallelism("quality_metrics")

        try:
            # Use LoaderStatusManager for centralized status updates (RACE CONDITION FIX)
            for table in ["quality_metrics", "growth_metrics"]:
                status_mgr = LoaderStatusManager(table)
                status_mgr.mark_running()

            # Apply backfill_days override if provided
            if backfill_days is not None:
                self._backfill_days = backfill_days

            for symbol in symbols:
                try:
                    # Calculate since_date from backfill_days (matching parent behavior)
                    from datetime import datetime, timedelta, timezone as tz

                    since_date = None
                    if self._backfill_days > 0:
                        since_date = datetime.now(tz.utc).date() - timedelta(days=self._backfill_days)
                    else:
                        # Use watermark for incremental loading
                        since_date = self._watermark.get_current_watermark(symbol=symbol)

                    metrics = self.fetch_incremental(symbol, since_date)
                    if not metrics:
                        logger.error(f"[ENHANCED] {symbol}: fetch_incremental returned empty list")
                        symbols_failed += 1
                        continue

                    metric_dict = metrics[0]

                    # FIX 2026-08-09: fetch_incremental() returns a truthy
                    # {"data_unavailable": True, "reason": ...} marker dict (not an empty list)
                    # when the symbol has no annual_income_statement history - the `if not
                    # metrics` check above only catches an empty list, not this marker. Without
                    # this check, the marker dict has none of the growth_fields/quality_fields
                    # keys, so both update_fields lists below stay empty, no UPDATE ever runs,
                    # and symbols_succeeded still increments - a symbol with zero real data
                    # written is silently counted as a success. Same bug class as
                    # earnings_calendar's fetch-failure placeholder rows fooling Phase 8 (see
                    # earnings_calendar_placeholder_false_rejection_fix_20260809).
                    if metric_dict.get("data_unavailable"):
                        symbols_failed += 1
                        continue

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
                            # roic_pct REMOVED 2026-08-03: found while fixing
                            # quality_metrics.roic_pct's real gap (was hardcoded unavailable in
                            # load_value_quality_growth_metrics.py, now computes real
                            # NOPAT/invested-capital ROIC using actual SEC-reported income tax
                            # data, migration 1178). This loader's own roic_pct formula
                            # (operating_income / (total_assets - current_liabilities), no tax
                            # adjustment, no debt/cash netting) is a strictly cruder duplicate.
                            #
                            # CORRECTION 2026-08-09: this comment used to also claim "this loader
                            # isn't wired into any active pipeline" as the reason the removal was
                            # only theoretical ("if this loader were ever scheduled..."). That was
                            # already false the day it was written - terraform/modules/pipeline/
                            # main.tf's EnhancedQualityGrowthMetrics Step Functions state and
                            # terraform/modules/loaders/main.tf's loader_file_map both schedule
                            # this loader in AWS production (a separate same-day 2026-08-03 fix
                            # enabled it), running after ValueQualityGrowthMetrics on the real
                            # quality_metrics/growth_metrics tables. It does NOT run in the local
                            # dev pipeline (scripts/local_loader_scheduler.py has zero references
                            # to it), so this file's behavior cannot be verified via a local
                            # orchestrator run - only in AWS. The roic_pct removal above was and
                            # is load-bearing in production, not a hypothetical.
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

                except (ValueError, KeyError) as e:
                    logger.error(f"[ENHANCED] {symbol}: Data structure error: {e}")
                    symbols_failed += 1
                except Exception as e:
                    logger.error(f"[ENHANCED] {symbol}: Unexpected error: {e}", exc_info=True)
                    symbols_failed += 1

            success = symbols_succeeded > 0
            fail_rate = (symbols_failed / max(symbols_succeeded + symbols_failed, 1)) * 100

            # Use LoaderStatusManager for final status (RACE CONDITION FIX)
            # FIX 2026-08-09: quality_metrics/growth_metrics are shared status rows also
            # written by load_value_quality_growth_metrics.py. A bare mark_completed() (no
            # current_run_* overrides) makes its internal <98%-completion safety check
            # re-read whatever symbol_count/symbols_loaded THAT OTHER loader last wrote,
            # instead of this run's own real counts - so this loader's actual completeness
            # was never actually verified by that safety check. Passing this run's own
            # symbols_succeeded/attempted counts closes that gap (same pattern as the
            # 2026-08-03 fix documented in LoaderStatusManager.mark_completed's docstring).
            for table in ["quality_metrics", "growth_metrics"]:
                status_mgr = LoaderStatusManager(table)
                if success and fail_rate <= self.max_fail_rate:
                    status_mgr.mark_completed(
                        current_run_symbols_loaded=symbols_succeeded,
                        current_run_symbol_count=symbols_succeeded + symbols_failed,
                    )
                else:
                    status_mgr.mark_failed(
                        error_message=f"Failed symbols: {symbols_failed}/{symbols_failed + symbols_succeeded}",
                        completion_pct=100.0 * symbols_succeeded / max(symbols_succeeded + symbols_failed, 1)
                    )

            return {
                "symbols_succeeded": symbols_succeeded,
                "symbols_failed": symbols_failed,
                "success": success
            }

        except (psycopg2.Error, ValueError) as e:
            logger.error(f"[ENHANCED] Fatal error: {type(e).__name__}: {e}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"[ENHANCED] Fatal unexpected error: {type(e).__name__}: {e}", exc_info=True)
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
        metrics: dict[str, Any] = {"symbol": symbol}

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

            # roic_pct computation REMOVED 2026-08-03 - see this loader's quality_fields list
            # comment above for why (confirmed-duplicate, cruder formula vs.
            # load_value_quality_growth_metrics.py's real tax-adjusted NOPAT computation).

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
                            curr_cogs = safe_float(margin_rows[0][1], 'cogs')
                            prior_gross_profit = safe_float(margin_rows[1][2], 'gross_profit')
                            prior_cogs = safe_float(margin_rows[1][1], 'cogs')

                            # Fallback: compute gross_profit from revenue - COGS if not directly available
                            if curr_gross_profit is None and curr_cogs is not None:
                                curr_gross_profit = curr_rev_f - curr_cogs
                            if prior_gross_profit is None and prior_cogs is not None:
                                prior_gross_profit = prior_rev_f - prior_cogs

                            curr_gross_margin = _bounded_margin_pct(curr_gross_profit, curr_rev_f)
                            prior_gross_margin = _bounded_margin_pct(prior_gross_profit, prior_rev_f)
                            if curr_gross_margin is not None and prior_gross_margin is not None:
                                metrics["gross_margin_trend"] = float(curr_gross_margin - prior_gross_margin)

                            # Operating margin trend
                            curr_op_margin = _bounded_margin_pct(curr_oi_f, curr_rev_f)
                            prior_op_margin = _bounded_margin_pct(prior_oi_f, prior_rev_f)
                            if curr_op_margin is not None and prior_op_margin is not None:
                                metrics["operating_margin_trend"] = float(curr_op_margin - prior_op_margin)

                            # Net margin trend
                            curr_net_margin = _bounded_margin_pct(curr_ni_f, curr_rev_f)
                            prior_net_margin = _bounded_margin_pct(prior_ni_f, prior_rev_f)
                            if curr_net_margin is not None and prior_net_margin is not None:
                                metrics["net_margin_trend"] = float(curr_net_margin - prior_net_margin)

                # ROE trend
                if curr_equity_f and curr_equity_f > 0 and prior_equity_f and prior_equity_f > 0:
                    curr_roe = _bounded_margin_pct(curr_ni_f, curr_equity_f)
                    prior_roe = _bounded_margin_pct(prior_ni_f, prior_equity_f)
                    if curr_roe and prior_roe:
                        metrics["roe_trend"] = float(curr_roe - prior_roe)

                # Sustainable growth rate = ROE * retention ratio. Left unset (not a fabricated
                # assumed retention ratio) because this loader's fetch_incremental() query never
                # selects dividends_paid, so a real retention ratio = (earnings - dividends) /
                # earnings can't be computed here. The sibling loader
                # load_value_quality_growth_metrics.py does fetch dividends_paid and computes
                # this field for real - that's the live path stock_scores actually reads from.

            # Compute quarterly earnings metrics (includes consecutive_positive_quarters, eps_growth_stability, etc.)
            self._compute_quarterly_metrics(symbol, metrics)

            # Log computed quarterly metrics for debugging
            quarterly_fields = [
                "consecutive_positive_quarters", "earnings_growth_4q_avg", "eps_growth_stability",
                "quarterly_growth_momentum"
            ]
            computed_quarterly = {k: v for k, v in metrics.items() if k in quarterly_fields and v is not None}
            if computed_quarterly:
                logger.info(f"[ENHANCED_METRICS] {symbol}: Computed quarterly metrics: {computed_quarterly}")
            else:
                logger.debug(f"[ENHANCED_METRICS] {symbol}: No quarterly metrics computed")

            # Compute earnings surprise and beat rate from yfinance
            self._compute_earnings_surprise_metrics(symbol, metrics)

            # Log computed surprise metrics for debugging
            surprise_fields = ["earnings_surprise_avg", "earnings_beat_rate"]
            computed_surprise = {k: v for k, v in metrics.items() if k in surprise_fields and v is not None}
            if computed_surprise:
                logger.info(f"[ENHANCED_METRICS] {symbol}: Computed surprise metrics: {computed_surprise}")

            # Compute estimate revision trend metrics from yfinance eps_trend/eps_revisions
            self._compute_estimate_revision_metrics(symbol, metrics)

            revision_fields = [
                "estimate_revision_direction", "revision_activity_30d",
                "estimate_momentum_60d", "estimate_momentum_90d", "revision_trend_score"
            ]
            computed_revision = {k: v for k, v in metrics.items() if k in revision_fields and v is not None}
            if computed_revision:
                logger.info(f"[ENHANCED_METRICS] {symbol}: Computed revision metrics: {computed_revision}")

            for field in revision_fields:
                if field not in metrics:
                    metrics[field] = None

            metrics["updated_at"] = date.today().isoformat()
            metrics["data_unavailable"] = False

            return [metrics]

        except Exception as e:
            logger.error(f"[ENHANCED_METRICS] {symbol}: Computation failed: {e}")
            return [{"symbol": symbol, "data_unavailable": True, "reason": str(e)}]

    def _compute_earnings_surprise_metrics(self, symbol: str, metrics: dict[str, Any]) -> None:
        """Compute earnings surprise and beat rate from yfinance earnings dates.

        Uses yfinance earnings_dates which provides:
        - EPS Estimate: Analyst consensus EPS estimate
        - Reported EPS: Actual reported EPS
        - Surprise(%): (Reported - Estimate) / Estimate * 100
        """
        try:
            import yfinance as yf
            from utils.loaders.retry_helper import retry_with_backoff
            ticker = yf.Ticker(symbol)

            # Get last 4 quarters of earnings data. Retried (2026-08-09) for the same reason
            # as _compute_estimate_revision_metrics's eps_trend/eps_revisions fetch - a single
            # transient yfinance failure here shouldn't be indistinguishable from real absence.
            earnings_dates = retry_with_backoff(
                lambda: ticker.earnings_dates, context=f"{symbol} earnings_dates", max_retries=2, backoff_seconds=1.0
            )
            if earnings_dates is None or earnings_dates.empty:
                logger.debug(f"[ENHANCED_METRICS] {symbol}: No earnings_dates from yfinance")
                return

            # Take most recent 4 reported earnings
            reported = earnings_dates[earnings_dates['Reported EPS'].notna()].head(4)
            if len(reported) < 2:
                logger.debug(f"[ENHANCED_METRICS] {symbol}: Only {len(reported)} quarters with reported EPS")
                return

            surprises = reported['Surprise(%)'].dropna()
            if len(surprises) > 0:
                # Average surprise over available quarters (guard against outlier earnings surprises)
                avg_surprise = float(surprises.mean())
                if abs(avg_surprise) < MAX_TREND_PERCENTAGE_POINTS:
                    metrics["earnings_surprise_avg"] = avg_surprise

                # Beat rate: % of quarters with positive surprise
                beat_count = (surprises > 0).sum()
                beat_rate = (beat_count / len(surprises)) * 100
                if beat_rate <= 100:  # Should always be <=100 but guard anyway
                    metrics["earnings_beat_rate"] = float(beat_rate)

                logger.info(f"[ENHANCED_METRICS] {symbol}: earnings_surprise_avg={metrics['earnings_surprise_avg']:.2f}%, earnings_beat_rate={metrics['earnings_beat_rate']:.2f}%")
            else:
                logger.debug(f"[ENHANCED_METRICS] {symbol}: No surprise data in earnings_dates")

        except ImportError:
            logger.debug(f"[ENHANCED_METRICS] {symbol}: yfinance not available")
        except Exception as e:
            logger.warning(
                f"[ENHANCED_METRICS] {symbol}: Could not fetch earnings surprise after retries: "
                f"{type(e).__name__}: {e}"
            )

    def _compute_estimate_revision_metrics(self, symbol: str, metrics: dict[str, Any]) -> None:
        """Compute analyst estimate revision trend metrics from yfinance eps_trend/eps_revisions.

        Live-verified 2026-08-04: yf.Ticker(symbol).eps_trend is a real DataFrame indexed by
        period ('0q'/'+1q'/'0y'/'+1y') with current/7daysAgo/30daysAgo/60daysAgo/90daysAgo
        consensus EPS columns; yf.Ticker(symbol).eps_revisions is a real DataFrame (same index)
        with upLast7days/upLast30days/downLast30days/downLast7Days analyst-revision counts.
        Uses the '0q' (current-quarter) row - the most immediately actionable estimate window,
        matching the same non-`.info` API family already used for forward_eps
        (utils/external/yfinance_analyst_ratings.py) and upgrades_downgrades.

        CONFIRMED 2026-08-09: on a full-universe run, this call transiently fails for many
        symbols that DO have real eps_trend/eps_revisions data (live-verified: CMS, D, TNDM all
        got a real earnings_surprise_avg from _compute_earnings_surprise_metrics on the same run,
        proving the symbol/loader/DB path works, yet estimate_momentum_60d/revision_activity_30d
        stayed NULL - re-fetching eps_trend for the same symbols moments later succeeded
        instantly). The bare `except Exception: logger.debug(...)` below used to swallow this
        indistinguishably from genuine "no analyst coverage", with no retry - explains most of
        the low (~7-8%) coverage on these fields despite real data being available. Now retries
        the fetch itself before giving up.
        """
        try:
            import yfinance as yf
            from utils.loaders.retry_helper import retry_with_backoff
            ticker = yf.Ticker(symbol)

            eps_trend = retry_with_backoff(
                lambda: ticker.eps_trend, context=f"{symbol} eps_trend", max_retries=2, backoff_seconds=1.0
            )
            eps_revisions = retry_with_backoff(
                lambda: ticker.eps_revisions, context=f"{symbol} eps_revisions", max_retries=2, backoff_seconds=1.0
            )

            if eps_trend is not None and not eps_trend.empty and "0q" in eps_trend.index:
                row = eps_trend.loc["0q"]
                current = row.get("current")
                ago_60 = row.get("60daysAgo")
                ago_90 = row.get("90daysAgo")

                if current is not None and ago_60 not in (None, 0):
                    momentum_60d = ((current - ago_60) / abs(ago_60)) * 100
                    if abs(momentum_60d) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["estimate_momentum_60d"] = float(round(momentum_60d, 2))

                if current is not None and ago_90 not in (None, 0):
                    momentum_90d = ((current - ago_90) / abs(ago_90)) * 100
                    if abs(momentum_90d) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["estimate_momentum_90d"] = float(round(momentum_90d, 2))

                momentum_values = [
                    v for v in (metrics.get("estimate_momentum_60d"), metrics.get("estimate_momentum_90d"))
                    if v is not None
                ]
                if momentum_values:
                    metrics["revision_trend_score"] = float(round(sum(momentum_values) / len(momentum_values), 2))
            else:
                logger.debug(f"[ENHANCED_METRICS] {symbol}: No eps_trend '0q' row from yfinance")

            if eps_revisions is not None and not eps_revisions.empty and "0q" in eps_revisions.index:
                row = eps_revisions.loc["0q"]
                up_30d = row.get("upLast30days")
                down_30d = row.get("downLast30days")

                if up_30d is not None and down_30d is not None:
                    metrics["revision_activity_30d"] = float(up_30d + down_30d)
                    metrics["estimate_revision_direction"] = float(up_30d - down_30d)
            else:
                logger.debug(f"[ENHANCED_METRICS] {symbol}: No eps_revisions '0q' row from yfinance")

        except ImportError:
            logger.debug(f"[ENHANCED_METRICS] {symbol}: yfinance not available")
        except Exception as e:
            # WARNING not DEBUG (2026-08-09): retries above already absorb transient blips;
            # a failure reaching here means 2 retries were exhausted, which is worth surfacing
            # instead of silently blending into "no coverage for this symbol".
            logger.warning(
                f"[ENHANCED_METRICS] {symbol}: Could not fetch estimate revisions after retries: "
                f"{type(e).__name__}: {e}"
            )

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
                        avg_growth_pct = avg_growth * 100
                        # Guard against overflow: EPS near-zero can cause huge percentage swings
                        if abs(avg_growth_pct) < MAX_TREND_PERCENTAGE_POINTS:
                            metrics["earnings_growth_4q_avg"] = float(avg_growth_pct)

                    # EPS growth stability (standard deviation)
                    if len(eps_growth_rates) >= 2:
                        import statistics
                        try:
                            stdev = statistics.stdev(eps_growth_rates)
                            # Cap stability metric too (same reason as growth rates)
                            if stdev < MAX_TREND_PERCENTAGE_POINTS:
                                metrics["eps_growth_stability"] = float(stdev)
                        except (ValueError, statistics.StatisticsError) as e:
                            # CRITICAL FIX 2026-08-02: Log failed calculations at WARNING level
                            # Silent pass hides data quality issues (insufficient data, invalid values)
                            logger.warning(
                                f"[{symbol}] Failed to calculate eps_growth_stability: {type(e).__name__}: {e}. "
                                f"Metric will be marked data_unavailable."
                            )

            # Compute quarterly growth momentum (average of recent quarterly growth rates)
            if len(valid_eps) >= 4:
                recent_growth = []
                for i in range(min(4, len(valid_eps) - 1)):
                    if valid_eps[i + 1] is not None and valid_eps[i + 1] != 0:
                        growth = (valid_eps[i] - valid_eps[i + 1]) / abs(valid_eps[i + 1]) * 100
                        recent_growth.append(growth)
                if recent_growth:
                    momentum = sum(recent_growth) / len(recent_growth)
                    # Guard against overflow: same near-zero EPS issue
                    if abs(momentum) < MAX_TREND_PERCENTAGE_POINTS:
                        metrics["quarterly_growth_momentum"] = float(momentum)


def main() -> int:
    """Entry point."""
    try:
        return run_loader(EnhancedQualityGrowthMetricsLoader)
    except Exception as e:
        logger.error(f"[ENHANCED_METRICS] Fatal error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
