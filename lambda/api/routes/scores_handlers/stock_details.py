"""Score route handlers: single-symbol details endpoint.

_derive_mom_12_1/_get_score_history moved out to stock_details_history.py (2026-09) purely
to keep this file under the file-size ratchet's new-file cap - no behavior change.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    error_response,
    execute_with_timeout,
    handle_db_error,
    json_response,
)

from algo.infrastructure.config.sql_intervals import get_interval_sql

from .stock_details_history import _derive_mom_12_1

logger = logging.getLogger(__name__)


def _get_stock_details(cur: cursor, symbol: str) -> Any:
    """Get detailed factor inputs for a single stock symbol."""
    try:
        # Build the same comprehensive query as _get_stock_scores but for a single symbol
        interval_52w = get_interval_sql("52w")
        query = f"""
                WITH max_price_date AS (
                    SELECT MAX(date) AS max_date FROM price_daily
                )
                SELECT
                    sc.symbol,
                    COALESCE(ss.security_name, sc.symbol) AS company_name,
                    cp.sector,
                    cp.industry,
                    sc.composite_score, sc.momentum_score, sc.quality_score,
                    sc.value_score, sc.growth_score, sc.risk_score,
                    sc.rs_percentile, sc.data_completeness,
                    sc.updated_at AS last_updated,
                    pl.close AS current_price,
                    pl.close AS price,
                    (pl.close IS NULL) AS _is_fallback,
                    (qm.symbol IS NULL OR qm.data_unavailable = TRUE OR (qm.roe IS NULL AND qm.operating_margin IS NULL AND qm.net_margin IS NULL)) AS _financial_data_unavailable,
                    (vm.symbol IS NULL OR vm.data_unavailable = TRUE) AS _value_data_unavailable,
                    (sc.growth_score IS NULL) AS _growth_data_unavailable,
                    (pm.symbol IS NULL OR pm.data_unavailable = TRUE) AS _positioning_data_unavailable,
                    (sm.symbol IS NULL OR sm.data_unavailable = TRUE) AS _risk_data_unavailable,
                    ROUND(CASE
                        WHEN pp.close IS NOT NULL THEN ((pl.close - pp.close) / NULLIF(pp.close, 0)) * 100
                        ELSE NULL
                    END, 2) AS change_percent,
                    vm.pe_ratio AS trailing_pe,
                    vm.pe_ratio_unavailable_reason,
                    vm.forward_pe,
                    vm.forward_pe_unavailable_reason,
                    vm.pb_ratio AS price_to_book,
                    vm.pb_ratio_unavailable_reason,
                    vm.ps_ratio AS ps_ratio_val,
                    vm.ps_ratio_unavailable_reason,
                    vm.peg_ratio AS peg_ratio_val,
                    vm.peg_ratio_unavailable_reason,
                    vm.dividend_yield,
                    vm.dividend_yield_unavailable_reason,
                    vm.net_payout_yield,
                    vm.fcf_yield AS fcf_yield_val,
                    vm.fcf_yield_unavailable_reason,
                    vm.enterprise_value,
                    vm.ev_ebitda,
                    vm.ev_ebitda_unavailable_reason,
                    vm.ev_revenue,
                    vm.market_cap,
                    vm.market_cap_unavailable_reason,
                    vm.intrinsic_value_per_share,
                    vm.intrinsic_value_unavailable_reason,
                    vm.margin_of_safety_pct,
                    vm.margin_of_safety_unavailable_reason,
                    vm.held_percent_institutions AS vm_held_institutions,
                    qm.roe AS roe_pct,
                    qm.roe_unavailable_reason,
                    qm.roa AS roa_val,
                    qm.roa_unavailable_reason,
                    qm.roic_pct,
                    qm.roic_pct_unavailable_reason,
                    qm.roce_pct,
                    qm.roce_pct_unavailable_reason,
                    qm.fcf_margin,
                    qm.fcf_margin_unavailable_reason,
                    qm.asset_turnover,
                    qm.asset_turnover_unavailable_reason,
                    qm.gross_profitability,
                    qm.gross_profitability_unavailable_reason,
                    qm.operating_profitability,
                    qm.operating_profitability_unavailable_reason,
                    qm.accruals_ratio,
                    qm.accruals_ratio_unavailable_reason,
                    qm.margin_volatility,
                    qm.margin_volatility_unavailable_reason,
                    COALESCE(gm_calc.calculated_gross_margin, qm.gross_margin) AS gross_margin_pct,
                    qm.gross_margin_unavailable_reason,
                    qm.ebitda_margin AS ebitda_margin_pct,
                    qm.ebitda_margin_unavailable_reason,
                    qm.debt_to_equity,
                    qm.debt_to_equity_unavailable_reason,
                    qm.current_ratio AS current_ratio_val,
                    qm.current_ratio_unavailable_reason,
                    qm.quick_ratio AS quick_ratio_val,
                    qm.quick_ratio_unavailable_reason,
                    qm.operating_margin AS operating_margin_val,
                    qm.operating_margin_unavailable_reason,
                    qm.net_margin AS net_margin_val,
                    qm.net_margin_unavailable_reason,
                    qm.interest_coverage AS interest_coverage_val,
                    qm.interest_coverage_unavailable_reason,
                    qm.debt_to_assets AS debt_to_assets_val,
                    qm.debt_to_assets_unavailable_reason,
                    qm.fcf_to_net_income,
                    qm.fcf_to_net_income_unavailable_reason,
                    qm.ocf_to_net_income AS operating_cf_to_net_income,
                    qm.ocf_to_net_income_unavailable_reason,
                    qm.payout_ratio,
                    qm.payout_ratio_unavailable_reason,
                    qm.free_cash_flow AS free_cashflow,
                    qm.free_cash_flow_unavailable_reason,
                    qm.operating_cash_flow AS operating_cashflow,
                    qm.operating_cash_flow_unavailable_reason,
                    qm.total_debt,
                    qm.total_debt_unavailable_reason,
                    qm.total_cash,
                    qm.total_cash_unavailable_reason,
                    qm.cash_per_share,
                    qm.cash_per_share_unavailable_reason,
                    qm.ebitda,
                    qm.ebitda_unavailable_reason,
                    qm.earnings_growth_yoy AS earnings_growth,
                    qm.earnings_growth_yoy_unavailable_reason,
                    qm.revenue_growth_yoy AS revenue_growth,
                    qm.revenue_growth_yoy_unavailable_reason,
                    qm.earnings_surprise_avg,
                    qm.earnings_surprise_avg_unavailable_reason,
                    qm.eps_growth_stability,
                    qm.eps_growth_stability_unavailable_reason,
                    qm.earnings_beat_rate,
                    qm.earnings_beat_rate_unavailable_reason,
                    qm.consecutive_positive_quarters,
                    qm.consecutive_positive_quarters_unavailable_reason,
                    qm.estimate_revision_direction,
                    qm.estimate_revision_direction_unavailable_reason,
                    qm.revision_activity_30d,
                    qm.revision_activity_30d_unavailable_reason,
                    qm.estimate_momentum_60d,
                    qm.estimate_momentum_60d_unavailable_reason,
                    qm.estimate_momentum_90d,
                    qm.estimate_momentum_90d_unavailable_reason,
                    qm.revision_trend_score,
                    qm.revision_trend_score_unavailable_reason,
                    qm.earnings_growth_4q_avg,
                    qm.earnings_growth_4q_avg_unavailable_reason,
                    qm.quarterly_growth_momentum,
                    qm.quarterly_growth_momentum_unavailable_reason,
                    gm.net_income_growth_yoy,
                    gm.net_income_growth_yoy_unavailable_reason,
                    gm.operating_income_growth_yoy,
                    gm.operating_income_growth_yoy_unavailable_reason,
                    gm.gross_margin_trend,
                    gm.gross_margin_trend_unavailable_reason,
                    gm.operating_margin_trend,
                    gm.operating_margin_trend_unavailable_reason,
                    gm.net_margin_trend,
                    gm.net_margin_trend_unavailable_reason,
                    gm.roe_trend,
                    gm.roe_trend_unavailable_reason,
                    gm.sustainable_growth_rate,
                    gm.sustainable_growth_rate_unavailable_reason,
                    COALESCE(fcf_calc.calculated_fcf_growth, gm.fcf_growth_yoy) AS fcf_growth_yoy,
                    gm.fcf_growth_yoy_unavailable_reason,
                    COALESCE(ocf_calc.calculated_ocf_growth, gm.ocf_growth_yoy) AS ocf_growth_yoy,
                    gm.ocf_growth_yoy_unavailable_reason,
                    gm.asset_growth_yoy,
                    gm.asset_growth_yoy_unavailable_reason,
                    gm.revenue_growth_1y AS rev_growth_1y_val,
                    gm.revenue_growth_1y_unavailable_reason,
                    gm.eps_growth_1y AS eps_growth_1y_val,
                    gm.eps_growth_1y_unavailable_reason,
                    gm.revenue_growth_3y AS rev_growth_3y_val,
                    gm.revenue_growth_3y_unavailable_reason,
                    gm.eps_growth_3y AS eps_growth_3y_val,
                    gm.eps_growth_3y_unavailable_reason,
                    gm.revenue_growth_5y AS rev_growth_5y_val,
                    gm.revenue_growth_5y_unavailable_reason,
                    gm.eps_growth_5y AS eps_growth_5y_val,
                    gm.eps_growth_5y_unavailable_reason,
                    gm.book_value_growth AS book_value_growth_val,
                    gm.book_value_growth_unavailable_reason,
                    gm.forward_eps_growth_current_fy,
                    gm.forward_eps_growth_current_fy_unavailable_reason,
                    gm.forward_eps_growth_next_fy,
                    gm.forward_eps_growth_next_fy_unavailable_reason,
                    gm.forward_revenue_growth_next_fy,
                    gm.forward_revenue_growth_next_fy_unavailable_reason,
                    gm.eps_estimate_revision_90d_pct,
                    gm.eps_estimate_revision_90d_pct_unavailable_reason,
                    sm.beta AS beta_val,
                    sm.beta_unavailable_reason,
                    sm.volatility_252d AS volatility_12m_val,
                    sm.volatility_252d_unavailable_reason AS volatility_12m_unavailable_reason,
                    sm.volatility_30d AS volatility_30d_val,
                    sm.volatility_30d_unavailable_reason,
                    sm.volatility_60d AS volatility_60d_val,
                    sm.volatility_60d_unavailable_reason,
                    sm.downside_volatility_30d,
                    sm.downside_volatility_30d_unavailable_reason,
                    sm.downside_volatility_60d,
                    sm.downside_volatility_60d_unavailable_reason,
                    sm.downside_volatility_252d,
                    sm.downside_volatility_252d_unavailable_reason,
                    sm.max_drawdown_1y,
                    sm.max_drawdown_1y_unavailable_reason,
                    liq.avg_dollar_volume_20d,
                    pm.institutional_ownership_pct AS inst_own_val,
                    pm.institutional_ownership_pct_unavailable_reason AS institutional_ownership_unavailable_reason,
                    pm.short_interest_pct AS short_pct_val,
                    pm.short_interest_pct_unavailable_reason AS short_interest_unavailable_reason,
                    pm.shares_short_prior_month AS shares_short_prior_month_val,
                    pm.shares_short_prior_month_unavailable_reason,
                    pm.short_interest_pct_change AS short_interest_pct_change_val,
                    pm.short_interest_pct_change_unavailable_reason,
                    pm.top_10_institutions_pct,
                    pm.top_10_institutions_pct_unavailable_reason,
                    COALESCE(pm.institutional_holders_count, ih.number_of_institutional_holders) AS institutional_holders_count,
                    pm.institutional_holders_count_unavailable_reason,
                    pm.short_percent_of_float AS short_pct_float,
                    pm.short_percent_of_float_unavailable_reason,
                    pm.short_ratio AS days_to_cover,
                    pm.short_ratio_unavailable_reason,
                    pm.ad_rating,
                    pm.ad_rating_unavailable_reason,
                    tl.rsi_14 AS tdd_rsi,
                    tl.macd AS tdd_macd,
                    tl.roc_20d AS tdd_roc_20d,
                    tl.roc_60d AS tdd_roc_60d,
                    tl.roc_120d AS tdd_roc_120d,
                    tl.roc_252d AS tdd_roc_252d,
                    ROUND(CASE WHEN tl.sma_50 IS NOT NULL AND tl.sma_50 > 0 THEN ((pl.close - tl.sma_50) / tl.sma_50 * 100) ELSE NULL END, 2) AS price_vs_sma_50,
                    ROUND(CASE WHEN tl.sma_200 IS NOT NULL AND tl.sma_200 > 0 THEN ((pl.close - tl.sma_200) / tl.sma_200 * 100) ELSE NULL END, 2) AS price_vs_sma_200,
                    p52.high_52w AS high_52w_val,
                    ROUND(CASE WHEN p52.high_52w > 0 THEN ((pl.close - p52.high_52w) / p52.high_52w * 100) END, 2) AS price_vs_52w_high_val,
                    mm.momentum_1m AS momentum_1m_val,
                    mm.momentum_3m AS momentum_3m_val,
                    mm.momentum_6m AS momentum_6m_val,
                    mm.momentum_12m AS momentum_12m_val,
                    (mm.symbol IS NULL OR mm.data_unavailable = TRUE) AS _momentum_data_unavailable,
                    phist.n AS price_history_days,
                    segm.revenue_concentration_hhi AS segment_revenue_concentration_hhi,
                    segm.segment_count,
                    segm.largest_segment_revenue_pct,
                    segm.is_diversified,
                    segm.reason AS segment_unavailable_reason,
                    (segm.symbol IS NULL OR segm.data_unavailable = TRUE) AS _segment_data_unavailable
                FROM stock_scores sc
                JOIN stock_symbols ss ON ss.symbol = sc.symbol
                LEFT JOIN company_profile cp ON cp.symbol = sc.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
                LEFT JOIN stability_metrics sm ON sm.symbol = sc.symbol
                LEFT JOIN positioning_metrics pm ON pm.symbol = sc.symbol
                LEFT JOIN institutional_holdings_13f ih ON ih.symbol = sc.symbol
                LEFT JOIN momentum_metrics mm ON mm.symbol = sc.symbol
                LEFT JOIN sec_segment_metrics segm ON segm.symbol = sc.symbol
                LEFT JOIN LATERAL (
                    SELECT close, date
                    FROM price_daily
                    WHERE symbol = sc.symbol
                    ORDER BY date DESC
                    LIMIT 1
                ) pl ON true
                LEFT JOIN LATERAL (
                    -- Same 20-trading-day average(volume*close) definition
                    -- algo/risk/liquidity_checks.py's _check_dollar_volume and
                    -- loaders/load_stock_scores.py's Risk-pillar liquidity input both use -
                    -- see _score_risk's docstring for why this is now a scored Risk component
                    -- (2026-09-01 Liquidity reweight), not just a display-only field.
                    SELECT AVG(volume * close) AS avg_dollar_volume_20d
                    FROM (
                        SELECT volume, close FROM price_daily
                        WHERE symbol = sc.symbol
                          AND COALESCE(data_unavailable, false) = false
                          AND volume IS NOT NULL AND close IS NOT NULL
                        ORDER BY date DESC
                        LIMIT 20
                    ) recent20
                ) liq ON true
                LEFT JOIN LATERAL (
                    SELECT close
                    FROM price_daily
                    WHERE symbol = sc.symbol
                      AND date < (SELECT max_date FROM max_price_date)
                    ORDER BY date DESC
                    LIMIT 1
                ) pp ON true
                LEFT JOIN LATERAL (
                    SELECT rsi_14, macd, sma_50, sma_200,
                           roc_20d, roc_60d, roc_120d, roc_252d, date
                    FROM technical_data_daily
                    WHERE symbol = sc.symbol
                    ORDER BY date DESC
                    LIMIT 1
                ) tl ON true
                LEFT JOIN LATERAL (
                    -- Same LIMIT 253 window loaders/load_risk_metrics_daily.py reads to compute
                    -- momentum - mirrors its row-count thresholds (22/63/126/252 days) so recently-
                    -- listed symbols with too little history show "Insufficient history" instead of
                    -- an unexplained "No data" for momentum_6m/12m/price_vs_sma_200.
                    SELECT COUNT(*) AS n
                    FROM (
                        SELECT 1 FROM price_daily
                        WHERE symbol = sc.symbol
                        ORDER BY date DESC
                        LIMIT 253
                    ) recent
                ) phist ON true
                LEFT JOIN LATERAL (
                    SELECT MAX(high) AS high_52w
                    FROM price_daily
                    WHERE symbol = sc.symbol
                      AND date >= CURRENT_DATE - {interval_52w}
                ) p52 ON true
                LEFT JOIN LATERAL (
                    SELECT ROUND(
                        CASE
                            WHEN acf_curr.operating_cash_flow IS NOT NULL
                                 AND acf_prior.operating_cash_flow IS NOT NULL
                                 AND acf_prior.operating_cash_flow != 0
                            THEN ((acf_curr.operating_cash_flow - acf_prior.operating_cash_flow)
                                  / ABS(acf_prior.operating_cash_flow)) * 100
                            ELSE NULL
                        END, 2) AS calculated_ocf_growth
                    FROM annual_cash_flow acf_curr
                    LEFT JOIN annual_cash_flow acf_prior
                        ON acf_curr.symbol = acf_prior.symbol
                        AND acf_prior.fiscal_year = acf_curr.fiscal_year - 1
                    WHERE acf_curr.symbol = sc.symbol
                    ORDER BY acf_curr.fiscal_year DESC
                    LIMIT 1
                ) ocf_calc ON true
                LEFT JOIN LATERAL (
                    SELECT ROUND(
                        CASE
                            WHEN ais.gross_profit IS NOT NULL AND ais.revenue IS NOT NULL AND ais.revenue > 0
                            THEN (ais.gross_profit / ais.revenue) * 100
                            ELSE NULL
                        END, 2) AS calculated_gross_margin
                    FROM annual_income_statement ais
                    WHERE ais.symbol = sc.symbol
                    ORDER BY ais.fiscal_year DESC
                    LIMIT 1
                ) gm_calc ON true
                LEFT JOIN LATERAL (
                    SELECT ROUND(
                        CASE
                            WHEN acf_curr.free_cash_flow IS NOT NULL
                                 AND acf_prior.free_cash_flow IS NOT NULL
                                 AND acf_prior.free_cash_flow != 0
                            THEN ((acf_curr.free_cash_flow - acf_prior.free_cash_flow)
                                  / ABS(acf_prior.free_cash_flow)) * 100
                            ELSE NULL
                        END, 2) AS calculated_fcf_growth
                    FROM annual_cash_flow acf_curr
                    LEFT JOIN annual_cash_flow acf_prior
                        ON acf_curr.symbol = acf_prior.symbol
                        AND acf_prior.fiscal_year = acf_curr.fiscal_year - 1
                    WHERE acf_curr.symbol = sc.symbol
                    ORDER BY acf_curr.fiscal_year DESC
                    LIMIT 1
                ) fcf_calc ON true
                WHERE sc.symbol = %s
            """

        try:
            rows = execute_with_timeout(cur, query, [symbol], timeout_sec=20, max_attempts=1)
        except psycopg2.errors.UndefinedColumn as e:
            if "data_unavailable" in str(e):
                logger.critical(
                    f"[SCORES_DETAILS_API] Schema validation failed: data_unavailable columns missing. "
                    f"Database migration (0046) may not have been applied. "
                    f"Error: {e}"
                )
                return error_response(
                    503,
                    "schema_mismatch",
                    "Score validation unavailable: database schema missing required data_unavailable columns.",
                )
            else:
                raise

        if not rows:
            return error_response(404, "not_found", f"No score data for symbol {symbol}")

        row = rows[0]
        d = dict(row)

        # Apply data unavailable flags to scores
        if d.get("_growth_data_unavailable"):
            d["growth_score"] = None
        # positioning_score REMOVED from the API contract 2026-08-27: Positioning retired as a
        # composite pillar (see loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS for the full
        # evidence trail) - no longer a real key on this response at all, not a null placeholder.
        # A/D rating/institutional ownership/short interest are still available, informationally,
        # via positioning_inputs below.
        if d.get("_risk_data_unavailable"):
            d["risk_score"] = None
        if d.get("_financial_data_unavailable"):
            d["quality_score"] = None
        if d.get("_value_data_unavailable"):
            d["value_score"] = None
        # size_score REMOVED from the API contract 2026-08-28 (Size retired as a composite
        # pillar - see loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS). market_cap itself
        # is still available via the Value pillar's inputs.

        # Build factor input objects
        def _build_factor_inputs(data: dict[str, Any]) -> None:
            """Build factor input objects from flat response fields."""
            # Quality Inputs
            data["quality_inputs"] = {
                "return_on_equity_pct": data.get("roe_pct"),
                "return_on_equity_pct_unavailable_reason": data.get("roe_unavailable_reason"),
                "return_on_assets_pct": data.get("roa_val"),
                "return_on_assets_pct_unavailable_reason": data.get("roa_unavailable_reason"),
                "return_on_invested_capital_pct": data.get("roic_pct"),
                "return_on_invested_capital_pct_unavailable_reason": data.get("roic_pct_unavailable_reason"),
                "return_on_capital_employed_pct": data.get("roce_pct"),
                "return_on_capital_employed_pct_unavailable_reason": data.get("roce_pct_unavailable_reason"),
                "fcf_margin_pct": data.get("fcf_margin"),
                "fcf_margin_pct_unavailable_reason": data.get("fcf_margin_unavailable_reason"),
                "asset_turnover_pct": data.get("asset_turnover"),
                "asset_turnover_pct_unavailable_reason": data.get("asset_turnover_unavailable_reason"),
                "gross_profitability_pct": data.get("gross_profitability"),
                "gross_profitability_pct_unavailable_reason": data.get("gross_profitability_unavailable_reason"),
                "operating_profitability_pct": data.get("operating_profitability"),
                "operating_profitability_pct_unavailable_reason": data.get(
                    "operating_profitability_unavailable_reason"
                ),
                "accruals_ratio_pct": data.get("accruals_ratio"),
                "accruals_ratio_pct_unavailable_reason": data.get("accruals_ratio_unavailable_reason"),
                "margin_volatility": data.get("margin_volatility"),
                "margin_volatility_unavailable_reason": data.get("margin_volatility_unavailable_reason"),
                "gross_margin_pct": data.get("gross_margin_pct"),
                "gross_margin_pct_unavailable_reason": data.get("gross_margin_unavailable_reason"),
                "operating_margin_pct": data.get("operating_margin_val"),
                "operating_margin_pct_unavailable_reason": data.get("operating_margin_unavailable_reason"),
                "profit_margin_pct": data.get("net_margin_val"),
                "profit_margin_pct_unavailable_reason": data.get("net_margin_unavailable_reason"),
                "ebitda_margin_pct": data.get("ebitda_margin_pct"),
                "ebitda_margin_pct_unavailable_reason": data.get("ebitda_margin_unavailable_reason"),
                "fcf_to_net_income": data.get("fcf_to_net_income"),
                "fcf_to_net_income_unavailable_reason": data.get("fcf_to_net_income_unavailable_reason"),
                "operating_cf_to_net_income": data.get("operating_cf_to_net_income"),
                "operating_cf_to_net_income_unavailable_reason": data.get("ocf_to_net_income_unavailable_reason"),
                "debt_to_equity": data.get("debt_to_equity"),
                "debt_to_equity_unavailable_reason": data.get("debt_to_equity_unavailable_reason"),
                "current_ratio": data.get("current_ratio_val"),
                "current_ratio_unavailable_reason": data.get("current_ratio_unavailable_reason"),
                "quick_ratio": data.get("quick_ratio_val"),
                "quick_ratio_unavailable_reason": data.get("quick_ratio_unavailable_reason"),
                "interest_coverage": data.get("interest_coverage_val"),
                "interest_coverage_unavailable_reason": data.get("interest_coverage_unavailable_reason"),
                "debt_to_assets": data.get("debt_to_assets_val"),
                "debt_to_assets_unavailable_reason": data.get("debt_to_assets_unavailable_reason"),
                "earnings_surprise_avg": data.get("earnings_surprise_avg"),
                "earnings_surprise_avg_unavailable_reason": data.get("earnings_surprise_avg_unavailable_reason"),
                "eps_growth_stability": data.get("eps_growth_stability"),
                "eps_growth_stability_unavailable_reason": data.get("eps_growth_stability_unavailable_reason"),
                "earnings_beat_rate": data.get("earnings_beat_rate"),
                "earnings_beat_rate_unavailable_reason": data.get("earnings_beat_rate_unavailable_reason"),
                "consecutive_positive_quarters": data.get("consecutive_positive_quarters"),
                "consecutive_positive_quarters_unavailable_reason": data.get(
                    "consecutive_positive_quarters_unavailable_reason"
                ),
                "estimate_revision_direction": data.get("estimate_revision_direction"),
                "estimate_revision_direction_unavailable_reason": data.get(
                    "estimate_revision_direction_unavailable_reason"
                ),
                "revision_activity_30d": data.get("revision_activity_30d"),
                "revision_activity_30d_unavailable_reason": data.get("revision_activity_30d_unavailable_reason"),
                "estimate_momentum_60d": data.get("estimate_momentum_60d"),
                "estimate_momentum_60d_unavailable_reason": data.get("estimate_momentum_60d_unavailable_reason"),
                "estimate_momentum_90d": data.get("estimate_momentum_90d"),
                "estimate_momentum_90d_unavailable_reason": data.get("estimate_momentum_90d_unavailable_reason"),
                "revision_trend_score": data.get("revision_trend_score"),
                "revision_trend_score_unavailable_reason": data.get("revision_trend_score_unavailable_reason"),
                "payout_ratio": data.get("payout_ratio"),
                "payout_ratio_unavailable_reason": data.get("payout_ratio_unavailable_reason"),
                "free_cashflow": data.get("free_cashflow"),
                "free_cashflow_unavailable_reason": data.get("free_cash_flow_unavailable_reason"),
                "operating_cashflow": data.get("operating_cashflow"),
                "operating_cashflow_unavailable_reason": data.get("operating_cash_flow_unavailable_reason"),
                "total_debt": data.get("total_debt"),
                "total_debt_unavailable_reason": data.get("total_debt_unavailable_reason"),
                "total_cash": data.get("total_cash"),
                "total_cash_unavailable_reason": data.get("total_cash_unavailable_reason"),
                "cash_per_share": data.get("cash_per_share"),
                "cash_per_share_unavailable_reason": data.get("cash_per_share_unavailable_reason"),
                "earnings_growth_pct": data.get("earnings_growth"),
                "earnings_growth_yoy_unavailable_reason": data.get("earnings_growth_yoy_unavailable_reason"),
                "revenue_growth_pct": data.get("revenue_growth"),
                "revenue_growth_yoy_unavailable_reason": data.get("revenue_growth_yoy_unavailable_reason"),
                "earnings_growth_4q_avg": data.get("earnings_growth_4q_avg"),
                "earnings_growth_4q_avg_unavailable_reason": data.get("earnings_growth_4q_avg_unavailable_reason"),
            }

            # Momentum Inputs
            # loaders/load_risk_metrics_daily.py computes each momentum window from the row-count
            # of price history it can read (22/63/126/252 days for 1m/3m/6m/12m) but only records a
            # row-level `reason` when EVERY window fails - a symbol with 1m/3m but not 6m/12m (e.g.
            # a recent IPO) gets reason=None, so the missing window rendered as an unexplained bare
            # "No data" instead of "Insufficient history". price_history_days (phist LATERAL join
            # above) mirrors those same thresholds to backfill the reason for display purposes only.
            _phist_days = data.get("price_history_days") or 0
            data["momentum_inputs"] = {
                "current_price": data.get("current_price"),
                "price_vs_52w_high": data.get("price_vs_52w_high_val"),
                "price_vs_sma_50": data.get("price_vs_sma_50"),
                "price_vs_sma_200": data.get("price_vs_sma_200"),
                "price_vs_sma_200_unavailable_reason": (
                    "insufficient_history" if data.get("price_vs_sma_200") is None and _phist_days < 200 else None
                ),
                "momentum_1m": data.get("momentum_1m_val"),
                "momentum_1m_unavailable_reason": (
                    "insufficient_history" if data.get("momentum_1m_val") is None and _phist_days < 22 else None
                ),
                "momentum_3m": data.get("momentum_3m_val"),
                "momentum_3m_unavailable_reason": (
                    "insufficient_history" if data.get("momentum_3m_val") is None and _phist_days < 63 else None
                ),
                "momentum_6m": data.get("momentum_6m_val"),
                "momentum_6m_unavailable_reason": (
                    "insufficient_history" if data.get("momentum_6m_val") is None and _phist_days < 126 else None
                ),
                "momentum_12_3": data.get("momentum_12m_val"),
                "momentum_12_3_unavailable_reason": (
                    "insufficient_history" if data.get("momentum_12m_val") is None and _phist_days < 252 else None
                ),
                "momentum_12_1": _derive_mom_12_1(data.get("momentum_12m_val"), data.get("momentum_1m_val")),
                "momentum_12_1_unavailable_reason": (
                    "insufficient_history"
                    if _derive_mom_12_1(data.get("momentum_12m_val"), data.get("momentum_1m_val")) is None
                    and _phist_days < 252
                    else None
                ),
                "rsi": data.get("tdd_rsi"),
                "macd": data.get("tdd_macd"),
                "roc_20d": data.get("tdd_roc_20d"),
                "roc_60d": data.get("tdd_roc_60d"),
                "roc_120d": data.get("tdd_roc_120d"),
                "roc_252d": data.get("tdd_roc_252d"),
            }

            # Value Inputs
            data["value_inputs"] = {
                "market_cap": data.get("market_cap"),
                "market_cap_unavailable_reason": data.get("market_cap_unavailable_reason"),
                "stock_pe": data.get("trailing_pe"),
                "stock_pe_unavailable_reason": data.get("pe_ratio_unavailable_reason"),
                "stock_forward_pe": data.get("forward_pe"),
                "stock_forward_pe_unavailable_reason": data.get("forward_pe_unavailable_reason"),
                "stock_pb": data.get("price_to_book"),
                "stock_pb_unavailable_reason": data.get("pb_ratio_unavailable_reason"),
                "stock_ps": data.get("ps_ratio_val"),
                "stock_ps_unavailable_reason": data.get("ps_ratio_unavailable_reason"),
                "peg_ratio": data.get("peg_ratio_val"),
                "peg_ratio_unavailable_reason": data.get("peg_ratio_unavailable_reason"),
                "stock_ev_ebitda": data.get("ev_ebitda"),
                "stock_ev_ebitda_unavailable_reason": data.get("ev_ebitda_unavailable_reason"),
                "stock_ev_revenue": data.get("ev_revenue"),
                "stock_ev_revenue_unavailable_reason": data.get("ev_revenue_unavailable_reason"),
                "fcf_yield": data.get("fcf_yield_val"),
                "fcf_yield_unavailable_reason": data.get("fcf_yield_unavailable_reason"),
                "stock_dividend_yield": data.get("dividend_yield"),
                "stock_dividend_yield_unavailable_reason": data.get("dividend_yield_unavailable_reason"),
                "net_payout_yield": data.get("net_payout_yield"),
                "stock_intrinsic_value": data.get("intrinsic_value_per_share"),
                "stock_intrinsic_value_unavailable_reason": data.get("intrinsic_value_unavailable_reason"),
                "stock_margin_of_safety": data.get("margin_of_safety_pct"),
                "stock_margin_of_safety_unavailable_reason": data.get("margin_of_safety_unavailable_reason"),
            }

            # Growth Inputs
            # Reason keys use the frontend's <schema-key>_unavailable_reason convention
            # (schema keys are revenue_growth_1y_pct/revenue_growth_3y_cagr/etc, not the
            # bare revenue_growth_1y/revenue_growth_3y used elsewhere) - StockScoreAccordion's
            # InputRow looks up `${row.key}_unavailable_reason` verbatim, so a mismatched
            # suffix here means it silently falls through to the generic "No data" label
            # instead of the real reason (e.g. "insufficient_history") even though the
            # reason was already computed and available in `data`.
            data["growth_inputs"] = {
                "revenue_growth_1y_pct": data.get("rev_growth_1y_val"),
                "revenue_growth_1y_pct_unavailable_reason": data.get("revenue_growth_1y_unavailable_reason"),
                "eps_growth_1y_pct": data.get("eps_growth_1y_val"),
                "eps_growth_1y_pct_unavailable_reason": data.get("eps_growth_1y_unavailable_reason"),
                "revenue_growth_3y_cagr": data.get("rev_growth_3y_val"),
                "revenue_growth_3y_cagr_unavailable_reason": data.get("revenue_growth_3y_unavailable_reason"),
                "eps_growth_3y_cagr": data.get("eps_growth_3y_val"),
                "eps_growth_3y_cagr_unavailable_reason": data.get("eps_growth_3y_unavailable_reason"),
                "revenue_growth_5y_cagr": data.get("rev_growth_5y_val"),
                "revenue_growth_5y_cagr_unavailable_reason": data.get("revenue_growth_5y_unavailable_reason"),
                "eps_growth_5y_cagr": data.get("eps_growth_5y_val"),
                "eps_growth_5y_cagr_unavailable_reason": data.get("eps_growth_5y_unavailable_reason"),
                "book_value_growth_pct": data.get("book_value_growth_val"),
                "book_value_growth_pct_unavailable_reason": data.get("book_value_growth_unavailable_reason"),
                "net_income_growth_yoy": data.get("net_income_growth_yoy"),
                "net_income_growth_yoy_unavailable_reason": data.get("net_income_growth_yoy_unavailable_reason"),
                "operating_income_growth_yoy": data.get("operating_income_growth_yoy"),
                "operating_income_growth_yoy_unavailable_reason": data.get(
                    "operating_income_growth_yoy_unavailable_reason"
                ),
                "gross_margin_trend": data.get("gross_margin_trend"),
                "gross_margin_trend_unavailable_reason": data.get("gross_margin_trend_unavailable_reason"),
                "operating_margin_trend": data.get("operating_margin_trend"),
                "operating_margin_trend_unavailable_reason": data.get("operating_margin_trend_unavailable_reason"),
                "net_margin_trend": data.get("net_margin_trend"),
                "net_margin_trend_unavailable_reason": data.get("net_margin_trend_unavailable_reason"),
                "roe_trend": data.get("roe_trend"),
                "roe_trend_unavailable_reason": data.get("roe_trend_unavailable_reason"),
                "sustainable_growth_rate": data.get("sustainable_growth_rate"),
                "sustainable_growth_rate_unavailable_reason": data.get("sustainable_growth_rate_unavailable_reason"),
                "quarterly_growth_momentum": data.get("quarterly_growth_momentum"),
                "quarterly_growth_momentum_unavailable_reason": data.get(
                    "quarterly_growth_momentum_unavailable_reason"
                ),
                "earnings_growth_4q_avg": data.get("earnings_growth_4q_avg"),
                "earnings_growth_4q_avg_unavailable_reason": data.get("earnings_growth_4q_avg_unavailable_reason"),
                "fcf_growth_yoy": data.get("fcf_growth_yoy"),
                "fcf_growth_yoy_unavailable_reason": data.get("fcf_growth_yoy_unavailable_reason"),
                "ocf_growth_yoy": data.get("ocf_growth_yoy"),
                "ocf_growth_yoy_unavailable_reason": data.get("ocf_growth_yoy_unavailable_reason"),
                "asset_growth_yoy": data.get("asset_growth_yoy"),
                "asset_growth_yoy_unavailable_reason": data.get("asset_growth_yoy_unavailable_reason"),
                "forward_eps_growth_current_fy": data.get("forward_eps_growth_current_fy"),
                "forward_eps_growth_current_fy_unavailable_reason": data.get(
                    "forward_eps_growth_current_fy_unavailable_reason"
                ),
                "forward_eps_growth_next_fy": data.get("forward_eps_growth_next_fy"),
                "forward_eps_growth_next_fy_unavailable_reason": data.get(
                    "forward_eps_growth_next_fy_unavailable_reason"
                ),
                "forward_revenue_growth_next_fy": data.get("forward_revenue_growth_next_fy"),
                "forward_revenue_growth_next_fy_unavailable_reason": data.get(
                    "forward_revenue_growth_next_fy_unavailable_reason"
                ),
                "eps_estimate_revision_90d_pct": data.get("eps_estimate_revision_90d_pct"),
                "eps_estimate_revision_90d_pct_unavailable_reason": data.get(
                    "eps_estimate_revision_90d_pct_unavailable_reason"
                ),
                # ADDED 2026-08-31: eps_growth_stability is now a scored GROWTH_SCORE_FIELDS
                # candidate (see loaders/load_stock_scores.py) - was already fetched into `data`
                # for quality_inputs above, reused here under the growth_inputs section too.
                "eps_growth_stability": data.get("eps_growth_stability"),
                "eps_growth_stability_unavailable_reason": data.get("eps_growth_stability_unavailable_reason"),
            }

            # Positioning Inputs
            data["positioning_inputs"] = {
                "institutional_ownership_pct": data.get("inst_own_val"),
                # Frontend schema key is institutional_ownership_pct, so FactorInputs looks up
                # institutional_ownership_pct_unavailable_reason - the missing "_pct" here meant
                # this reason was computed but never actually reached the UI; a real null value
                # rendered as a bare "No data" instead of the actual reason underneath it.
                "institutional_ownership_pct_unavailable_reason": data.get(
                    "institutional_ownership_unavailable_reason"
                ),
                "top_10_institutions_pct": data.get("top_10_institutions_pct"),
                "top_10_institutions_pct_unavailable_reason": data.get("top_10_institutions_pct_unavailable_reason"),
                "institutional_holders_count": data.get("institutional_holders_count"),
                "institutional_holders_count_unavailable_reason": data.get(
                    "institutional_holders_count_unavailable_reason"
                ),
                "short_interest_pct": data.get("short_pct_val"),
                "short_interest_pct_unavailable_reason": data.get("short_interest_unavailable_reason"),
                "short_percent_of_float": data.get("short_pct_float"),
                "short_percent_of_float_unavailable_reason": data.get("short_percent_of_float_unavailable_reason"),
                "short_interest_pct_change": data.get("short_interest_pct_change_val"),
                "short_interest_pct_change_unavailable_reason": data.get(
                    "short_interest_pct_change_unavailable_reason"
                ),
                "shares_short_prior_month": data.get("shares_short_prior_month_val"),
                "shares_short_prior_month_unavailable_reason": data.get("shares_short_prior_month_unavailable_reason"),
                "short_ratio": data.get("days_to_cover"),
                "short_ratio_unavailable_reason": data.get("short_ratio_unavailable_reason"),
                "ad_rating": data.get("ad_rating"),
                "ad_rating_unavailable_reason": data.get("ad_rating_unavailable_reason"),
            }

            # Risk Inputs
            data["risk_inputs"] = {
                "volatility_12m": data.get("volatility_12m_val"),
                "volatility_12m_unavailable_reason": data.get("volatility_12m_unavailable_reason"),
                "volatility_60d": data.get("volatility_60d_val"),
                "volatility_60d_unavailable_reason": data.get("volatility_60d_unavailable_reason"),
                "volatility_30d": data.get("volatility_30d_val"),
                "volatility_30d_unavailable_reason": data.get("volatility_30d_unavailable_reason"),
                "downside_volatility_30d": data.get("downside_volatility_30d"),
                "downside_volatility_30d_unavailable_reason": data.get("downside_volatility_30d_unavailable_reason"),
                "downside_volatility_60d": data.get("downside_volatility_60d"),
                "downside_volatility_60d_unavailable_reason": data.get("downside_volatility_60d_unavailable_reason"),
                "downside_volatility_252d": data.get("downside_volatility_252d"),
                "downside_volatility_252d_unavailable_reason": data.get("downside_volatility_252d_unavailable_reason"),
                "max_drawdown_1y": data.get("max_drawdown_1y"),
                "max_drawdown_1y_unavailable_reason": data.get("max_drawdown_1y_unavailable_reason"),
                "avg_dollar_volume_20d": data.get("avg_dollar_volume_20d"),
                "beta": data.get("beta_val"),
                "beta_unavailable_reason": data.get("beta_unavailable_reason"),
                # debt_to_assets briefly RESTORED HERE 2026-08-30, then REMOVED AGAIN the same
                # day (user directive) - a balance-sheet solvency ratio doesn't fit this
                # pillar's price-volatility/risk-of-loss character, same CLEANUP 2026-08-16
                # reasoning below. Still available via quality_inputs (debt_to_assets_val).
                # current_ratio/quick_ratio/cash_per_share (Financial Stability) and
                # revenue_concentration_hhi (Business Diversification) remain out - CLEANUP
                # 2026-08-16, not scored under Risk (see loaders/load_stock_scores.py
                # _score_risk). segment_count/largest_segment_revenue_pct/is_diversified below
                # were always unweighted reference fields, kept as-is.
                "segment_count": data.get("segment_count"),
                "largest_segment_revenue_pct": data.get("largest_segment_revenue_pct"),
                "is_diversified": data.get("is_diversified"),
                "segment_count_unavailable_reason": (
                    data.get("segment_unavailable_reason") if data.get("segment_count") is None else None
                ),
                "largest_segment_revenue_pct_unavailable_reason": (
                    data.get("segment_unavailable_reason") if data.get("largest_segment_revenue_pct") is None else None
                ),
                "is_diversified_unavailable_reason": (
                    data.get("segment_unavailable_reason") if data.get("is_diversified") is None else None
                ),
            }

        _build_factor_inputs(d)

        # Check data freshness
        freshness = check_data_freshness(cur, "stock_scores", "updated_at", warning_days=7)

        return json_response(200, d, data_freshness=freshness)

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "get stock details")
        return error_response(code, error_type, message)
