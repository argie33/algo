"""Helper functions for the main multi-factor stock scores listing endpoint.

Extracted out of stock_scores.py's single dominant `_get_stock_scores` function (2026-09)
purely to keep that file under the file-size ratchet's new-file cap - each function below
is a behavior-preserving, mechanical extraction of one phase of that function's body (query
construction, row/factor-input transformation, summary-metric computation). No logic,
computation, query, or control flow was changed in the process - see stock_scores.py for
the orchestration that calls these in the same sequence the inline code used to run in.
"""

from __future__ import annotations

import logging
from typing import Any

from algo.infrastructure.config.sql_intervals import get_interval_sql

from .stock_details_history import _derive_mom_12_1

logger = logging.getLogger(__name__)


def _build_stock_scores_query(where_clause: str, market_cap_join: str, sort_col: str, sort_direction: str) -> str:
    """Build the paginated stock-scores listing query.

    PERFORMANCE: filter/sort/limit to the target page FIRST in a CTE, then run the
    per-symbol LATERAL lookups (price_daily/technical_data_daily) only against that
    small row set. Previously the LATERAL joins ran against every row of stock_scores
    BEFORE the WHERE clause was applied, so a page of 50 rows still paid for thousands
    of per-symbol index scans - this was the root cause of the endpoint's 7+ second
    latency (and the dashboard's 3s client timeout hiding it as "no data").
    """
    interval_52w = get_interval_sql("52w")
    query = f"""
            WITH max_price_date AS (
                SELECT MAX(date) AS max_date FROM price_daily
            ),
            filtered_scores AS (
                SELECT sc.*, ss.security_name, ss.is_sp500
                FROM stock_scores sc
                JOIN stock_symbols ss ON ss.symbol = sc.symbol
                {market_cap_join}
                {where_clause}
                ORDER BY sc.{sort_col} {sort_direction}
                LIMIT %s OFFSET %s
            )
            SELECT
                fs.symbol,
                COALESCE(fs.security_name, fs.symbol) AS company_name,
                cp.sector,
                cp.industry,
                fs.composite_score, fs.momentum_score, fs.quality_score,
                fs.value_score, fs.growth_score, fs.risk_score,
                fs.rs_percentile, fs.data_completeness,
                fs.updated_at AS last_updated,
                pl.close AS current_price,
                pl.close AS price,
                (pl.close IS NULL) AS _is_fallback,
                (qm.symbol IS NULL OR qm.data_unavailable = TRUE OR (qm.roe IS NULL AND qm.operating_margin IS NULL AND qm.net_margin IS NULL)) AS _financial_data_unavailable,
                (vm.symbol IS NULL OR vm.data_unavailable = TRUE) AS _value_data_unavailable,
                (fs.growth_score IS NULL) AS _growth_data_unavailable,
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
            FROM filtered_scores fs
            LEFT JOIN company_profile cp ON cp.symbol = fs.symbol
            LEFT JOIN value_metrics vm ON vm.symbol = fs.symbol
            LEFT JOIN quality_metrics qm ON qm.symbol = fs.symbol
            LEFT JOIN growth_metrics gm ON gm.symbol = fs.symbol
            LEFT JOIN stability_metrics sm ON sm.symbol = fs.symbol
            LEFT JOIN positioning_metrics pm ON pm.symbol = fs.symbol
            LEFT JOIN institutional_holdings_13f ih ON ih.symbol = fs.symbol
            LEFT JOIN momentum_metrics mm ON mm.symbol = fs.symbol
            LEFT JOIN sec_segment_metrics segm ON segm.symbol = fs.symbol
            LEFT JOIN LATERAL (
                SELECT close, date
                FROM price_daily
                WHERE symbol = fs.symbol
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
                    WHERE symbol = fs.symbol
                      AND COALESCE(data_unavailable, false) = false
                      AND volume IS NOT NULL AND close IS NOT NULL
                    ORDER BY date DESC
                    LIMIT 20
                ) recent20
            ) liq ON true
            LEFT JOIN LATERAL (
                SELECT close
                FROM price_daily
                WHERE symbol = fs.symbol
                  AND date < (SELECT max_date FROM max_price_date)
                ORDER BY date DESC
                LIMIT 1
            ) pp ON true
            LEFT JOIN LATERAL (
                SELECT rsi_14, macd, sma_50, sma_200,
                       roc_20d, roc_60d, roc_120d, roc_252d, date
                FROM technical_data_daily
                WHERE symbol = fs.symbol
                ORDER BY date DESC
                LIMIT 1
            ) tl ON true
            LEFT JOIN LATERAL (
                -- See matching comment in _get_stock_details.
                SELECT COUNT(*) AS n
                FROM (
                    SELECT 1 FROM price_daily
                    WHERE symbol = fs.symbol
                    ORDER BY date DESC
                    LIMIT 253
                ) recent
            ) phist ON true
            LEFT JOIN LATERAL (
                SELECT MAX(high) AS high_52w
                FROM price_daily
                WHERE symbol = fs.symbol
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
                WHERE acf_curr.symbol = fs.symbol
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
                WHERE ais.symbol = fs.symbol
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
                WHERE acf_curr.symbol = fs.symbol
                ORDER BY acf_curr.fiscal_year DESC
                LIMIT 1
            ) fcf_calc ON true
            ORDER BY fs.{sort_col} {sort_direction}
        """
    return query


def _build_stock_score_factor_inputs(d: dict[str, Any]) -> None:
    """Build factor input objects from flat response fields.

    Maps API field names to schema keys for UI display. Adds objects:
    - quality_inputs: ROE, margins, debt ratios, growth metrics
    - momentum_inputs: price momentum, technical indicators
    - value_inputs: valuation ratios (PE, PB, PS, etc.)
    - growth_inputs: revenue/EPS growth rates
    - positioning_inputs: institutional/insider ownership, short interest
    - risk_inputs: volatility, beta
    """
    # Quality Inputs: ROE, ROA, ROIC, margins, debt, ratios
    d["quality_inputs"] = {
        "return_on_equity_pct": d.get("roe_pct"),
        "return_on_equity_pct_unavailable_reason": d.get("roe_unavailable_reason"),
        "return_on_assets_pct": d.get("roa_val"),
        "return_on_assets_pct_unavailable_reason": d.get("roa_unavailable_reason"),
        "return_on_invested_capital_pct": d.get("roic_pct"),
        "return_on_invested_capital_pct_unavailable_reason": d.get("roic_pct_unavailable_reason"),
        "return_on_capital_employed_pct": d.get("roce_pct"),
        "return_on_capital_employed_pct_unavailable_reason": d.get("roce_pct_unavailable_reason"),
        "fcf_margin_pct": d.get("fcf_margin"),
        "fcf_margin_pct_unavailable_reason": d.get("fcf_margin_unavailable_reason"),
        "asset_turnover_pct": d.get("asset_turnover"),
        "asset_turnover_pct_unavailable_reason": d.get("asset_turnover_unavailable_reason"),
        "gross_profitability_pct": d.get("gross_profitability"),
        "gross_profitability_pct_unavailable_reason": d.get("gross_profitability_unavailable_reason"),
        "operating_profitability_pct": d.get("operating_profitability"),
        "operating_profitability_pct_unavailable_reason": d.get("operating_profitability_unavailable_reason"),
        "accruals_ratio_pct": d.get("accruals_ratio"),
        "accruals_ratio_pct_unavailable_reason": d.get("accruals_ratio_unavailable_reason"),
        "margin_volatility": d.get("margin_volatility"),
        "margin_volatility_unavailable_reason": d.get("margin_volatility_unavailable_reason"),
        "gross_margin_pct": d.get("gross_margin_pct"),
        "gross_margin_pct_unavailable_reason": d.get("gross_margin_unavailable_reason"),
        "operating_margin_pct": d.get("operating_margin_val"),
        "operating_margin_pct_unavailable_reason": d.get("operating_margin_unavailable_reason"),
        "profit_margin_pct": d.get("net_margin_val"),
        "profit_margin_pct_unavailable_reason": d.get("net_margin_unavailable_reason"),
        "ebitda_margin_pct": d.get("ebitda_margin_pct"),
        "ebitda_margin_pct_unavailable_reason": d.get("ebitda_margin_unavailable_reason"),
        "fcf_to_net_income": d.get("fcf_to_net_income"),
        "fcf_to_net_income_unavailable_reason": d.get("fcf_to_net_income_unavailable_reason"),
        "operating_cf_to_net_income": d.get("operating_cf_to_net_income"),
        "operating_cf_to_net_income_unavailable_reason": d.get("ocf_to_net_income_unavailable_reason"),
        "debt_to_equity": d.get("debt_to_equity"),
        "debt_to_equity_unavailable_reason": d.get("debt_to_equity_unavailable_reason"),
        "current_ratio": d.get("current_ratio_val"),
        "current_ratio_unavailable_reason": d.get("current_ratio_unavailable_reason"),
        "quick_ratio": d.get("quick_ratio_val"),
        "quick_ratio_unavailable_reason": d.get("quick_ratio_unavailable_reason"),
        "interest_coverage": d.get("interest_coverage_val"),
        "interest_coverage_unavailable_reason": d.get("interest_coverage_unavailable_reason"),
        "debt_to_assets": d.get("debt_to_assets_val"),
        "debt_to_assets_unavailable_reason": d.get("debt_to_assets_unavailable_reason"),
        "earnings_surprise_avg": d.get("earnings_surprise_avg"),
        "earnings_surprise_avg_unavailable_reason": d.get("earnings_surprise_avg_unavailable_reason"),
        "eps_growth_stability": d.get("eps_growth_stability"),
        "eps_growth_stability_unavailable_reason": d.get("eps_growth_stability_unavailable_reason"),
        "earnings_beat_rate": d.get("earnings_beat_rate"),
        "earnings_beat_rate_unavailable_reason": d.get("earnings_beat_rate_unavailable_reason"),
        "consecutive_positive_quarters": d.get("consecutive_positive_quarters"),
        "consecutive_positive_quarters_unavailable_reason": d.get("consecutive_positive_quarters_unavailable_reason"),
        "estimate_revision_direction": d.get("estimate_revision_direction"),
        "estimate_revision_direction_unavailable_reason": d.get("estimate_revision_direction_unavailable_reason"),
        "revision_activity_30d": d.get("revision_activity_30d"),
        "revision_activity_30d_unavailable_reason": d.get("revision_activity_30d_unavailable_reason"),
        "estimate_momentum_60d": d.get("estimate_momentum_60d"),
        "estimate_momentum_60d_unavailable_reason": d.get("estimate_momentum_60d_unavailable_reason"),
        "estimate_momentum_90d": d.get("estimate_momentum_90d"),
        "estimate_momentum_90d_unavailable_reason": d.get("estimate_momentum_90d_unavailable_reason"),
        "revision_trend_score": d.get("revision_trend_score"),
        "revision_trend_score_unavailable_reason": d.get("revision_trend_score_unavailable_reason"),
        "payout_ratio": d.get("payout_ratio"),
        "payout_ratio_unavailable_reason": d.get("payout_ratio_unavailable_reason"),
        "free_cashflow": d.get("free_cashflow"),
        "free_cashflow_unavailable_reason": d.get("free_cash_flow_unavailable_reason"),
        "operating_cashflow": d.get("operating_cashflow"),
        "operating_cashflow_unavailable_reason": d.get("operating_cash_flow_unavailable_reason"),
        "total_debt": d.get("total_debt"),
        "total_debt_unavailable_reason": d.get("total_debt_unavailable_reason"),
        "total_cash": d.get("total_cash"),
        "total_cash_unavailable_reason": d.get("total_cash_unavailable_reason"),
        "cash_per_share": d.get("cash_per_share"),
        "cash_per_share_unavailable_reason": d.get("cash_per_share_unavailable_reason"),
        "earnings_growth_pct": d.get("earnings_growth"),
        "earnings_growth_yoy_unavailable_reason": d.get("earnings_growth_yoy_unavailable_reason"),
        "revenue_growth_pct": d.get("revenue_growth"),
        "revenue_growth_yoy_unavailable_reason": d.get("revenue_growth_yoy_unavailable_reason"),
        "earnings_growth_4q_avg": d.get("earnings_growth_4q_avg"),
        "earnings_growth_4q_avg_unavailable_reason": d.get("earnings_growth_4q_avg_unavailable_reason"),
    }

    # Momentum Inputs: Price momentum, technical indicators
    # See matching comment in _get_stock_details for why the *_unavailable_reason
    # fields below are derived from price_history_days rather than a stored column.
    _phist_days = d.get("price_history_days") or 0
    d["momentum_inputs"] = {
        "current_price": d.get("current_price"),
        "price_vs_52w_high": d.get("price_vs_52w_high_val"),
        "price_vs_sma_50": d.get("price_vs_sma_50"),
        "price_vs_sma_200": d.get("price_vs_sma_200"),
        "price_vs_sma_200_unavailable_reason": (
            "insufficient_history" if d.get("price_vs_sma_200") is None and _phist_days < 200 else None
        ),
        "momentum_1m": d.get("momentum_1m_val"),
        "momentum_1m_unavailable_reason": (
            "insufficient_history" if d.get("momentum_1m_val") is None and _phist_days < 22 else None
        ),
        "momentum_3m": d.get("momentum_3m_val"),
        "momentum_3m_unavailable_reason": (
            "insufficient_history" if d.get("momentum_3m_val") is None and _phist_days < 63 else None
        ),
        "momentum_6m": d.get("momentum_6m_val"),
        "momentum_6m_unavailable_reason": (
            "insufficient_history" if d.get("momentum_6m_val") is None and _phist_days < 126 else None
        ),
        "momentum_12_3": d.get("momentum_12m_val"),
        "momentum_12_3_unavailable_reason": (
            "insufficient_history" if d.get("momentum_12m_val") is None and _phist_days < 252 else None
        ),
        "momentum_12_1": _derive_mom_12_1(d.get("momentum_12m_val"), d.get("momentum_1m_val")),
        "momentum_12_1_unavailable_reason": (
            "insufficient_history"
            if _derive_mom_12_1(d.get("momentum_12m_val"), d.get("momentum_1m_val")) is None and _phist_days < 252
            else None
        ),
        "rsi": d.get("tdd_rsi"),
        "macd": d.get("tdd_macd"),
        "roc_20d": d.get("tdd_roc_20d"),
        "roc_60d": d.get("tdd_roc_60d"),
        "roc_120d": d.get("tdd_roc_120d"),
        "roc_252d": d.get("tdd_roc_252d"),
    }

    # Value Inputs: Valuation ratios
    d["value_inputs"] = {
        "market_cap": d.get("market_cap"),
        "market_cap_unavailable_reason": d.get("market_cap_unavailable_reason"),
        "stock_pe": d.get("trailing_pe"),
        "stock_pe_unavailable_reason": d.get("pe_ratio_unavailable_reason"),
        "stock_forward_pe": d.get("forward_pe"),
        "stock_forward_pe_unavailable_reason": d.get("forward_pe_unavailable_reason"),
        "stock_pb": d.get("price_to_book"),
        "stock_pb_unavailable_reason": d.get("pb_ratio_unavailable_reason"),
        "stock_ps": d.get("ps_ratio_val"),
        "stock_ps_unavailable_reason": d.get("ps_ratio_unavailable_reason"),
        "peg_ratio": d.get("peg_ratio_val"),
        "peg_ratio_unavailable_reason": d.get("peg_ratio_unavailable_reason"),
        "stock_ev_ebitda": d.get("ev_ebitda"),
        "stock_ev_ebitda_unavailable_reason": d.get("ev_ebitda_unavailable_reason"),
        "stock_ev_revenue": d.get("ev_revenue"),
        "stock_ev_revenue_unavailable_reason": d.get("ev_revenue_unavailable_reason"),
        "fcf_yield": d.get("fcf_yield_val"),
        "fcf_yield_unavailable_reason": d.get("fcf_yield_unavailable_reason"),
        "stock_dividend_yield": d.get("dividend_yield"),
        "stock_dividend_yield_unavailable_reason": d.get("dividend_yield_unavailable_reason"),
        "net_payout_yield": d.get("net_payout_yield"),
        "stock_intrinsic_value": d.get("intrinsic_value_per_share"),
        "stock_intrinsic_value_unavailable_reason": d.get("intrinsic_value_unavailable_reason"),
        "stock_margin_of_safety": d.get("margin_of_safety_pct"),
        "stock_margin_of_safety_unavailable_reason": d.get("margin_of_safety_unavailable_reason"),
    }

    # Growth Inputs: Revenue and EPS growth
    # Reason keys use the frontend's <schema-key>_unavailable_reason convention (see
    # matching comment on the details-endpoint copy of this block above).
    d["growth_inputs"] = {
        "revenue_growth_1y_pct": d.get("rev_growth_1y_val"),
        "revenue_growth_1y_pct_unavailable_reason": d.get("revenue_growth_1y_unavailable_reason"),
        "eps_growth_1y_pct": d.get("eps_growth_1y_val"),
        "eps_growth_1y_pct_unavailable_reason": d.get("eps_growth_1y_unavailable_reason"),
        "revenue_growth_3y_cagr": d.get("rev_growth_3y_val"),
        "revenue_growth_3y_cagr_unavailable_reason": d.get("revenue_growth_3y_unavailable_reason"),
        "eps_growth_3y_cagr": d.get("eps_growth_3y_val"),
        "eps_growth_3y_cagr_unavailable_reason": d.get("eps_growth_3y_unavailable_reason"),
        "revenue_growth_5y_cagr": d.get("rev_growth_5y_val"),
        "revenue_growth_5y_cagr_unavailable_reason": d.get("revenue_growth_5y_unavailable_reason"),
        "eps_growth_5y_cagr": d.get("eps_growth_5y_val"),
        "eps_growth_5y_cagr_unavailable_reason": d.get("eps_growth_5y_unavailable_reason"),
        "book_value_growth_pct": d.get("book_value_growth_val"),
        "book_value_growth_pct_unavailable_reason": d.get("book_value_growth_unavailable_reason"),
        "net_income_growth_yoy": d.get("net_income_growth_yoy"),
        "net_income_growth_yoy_unavailable_reason": d.get("net_income_growth_yoy_unavailable_reason"),
        "operating_income_growth_yoy": d.get("operating_income_growth_yoy"),
        "operating_income_growth_yoy_unavailable_reason": d.get("operating_income_growth_yoy_unavailable_reason"),
        "gross_margin_trend": d.get("gross_margin_trend"),
        "gross_margin_trend_unavailable_reason": d.get("gross_margin_trend_unavailable_reason"),
        "operating_margin_trend": d.get("operating_margin_trend"),
        "operating_margin_trend_unavailable_reason": d.get("operating_margin_trend_unavailable_reason"),
        "net_margin_trend": d.get("net_margin_trend"),
        "net_margin_trend_unavailable_reason": d.get("net_margin_trend_unavailable_reason"),
        "roe_trend": d.get("roe_trend"),
        "roe_trend_unavailable_reason": d.get("roe_trend_unavailable_reason"),
        "sustainable_growth_rate": d.get("sustainable_growth_rate"),
        "sustainable_growth_rate_unavailable_reason": d.get("sustainable_growth_rate_unavailable_reason"),
        "quarterly_growth_momentum": d.get("quarterly_growth_momentum"),
        "quarterly_growth_momentum_unavailable_reason": d.get("quarterly_growth_momentum_unavailable_reason"),
        "fcf_growth_yoy": d.get("fcf_growth_yoy"),
        "fcf_growth_yoy_unavailable_reason": d.get("fcf_growth_yoy_unavailable_reason"),
        "ocf_growth_yoy": d.get("ocf_growth_yoy"),
        "ocf_growth_yoy_unavailable_reason": d.get("ocf_growth_yoy_unavailable_reason"),
        "asset_growth_yoy": d.get("asset_growth_yoy"),
        "asset_growth_yoy_unavailable_reason": d.get("asset_growth_yoy_unavailable_reason"),
        "earnings_growth_4q_avg": d.get("earnings_growth_4q_avg"),
        "earnings_growth_4q_avg_unavailable_reason": d.get("earnings_growth_4q_avg_unavailable_reason"),
        "forward_eps_growth_current_fy": d.get("forward_eps_growth_current_fy"),
        "forward_eps_growth_current_fy_unavailable_reason": d.get("forward_eps_growth_current_fy_unavailable_reason"),
        "forward_eps_growth_next_fy": d.get("forward_eps_growth_next_fy"),
        "forward_eps_growth_next_fy_unavailable_reason": d.get("forward_eps_growth_next_fy_unavailable_reason"),
        "forward_revenue_growth_next_fy": d.get("forward_revenue_growth_next_fy"),
        "forward_revenue_growth_next_fy_unavailable_reason": d.get("forward_revenue_growth_next_fy_unavailable_reason"),
        "eps_estimate_revision_90d_pct": d.get("eps_estimate_revision_90d_pct"),
        "eps_estimate_revision_90d_pct_unavailable_reason": d.get("eps_estimate_revision_90d_pct_unavailable_reason"),
        # ADDED 2026-08-31 (see matching comment on the details-endpoint copy above).
        "eps_growth_stability": d.get("eps_growth_stability"),
        "eps_growth_stability_unavailable_reason": d.get("eps_growth_stability_unavailable_reason"),
    }

    # Positioning Inputs: Ownership and short interest
    d["positioning_inputs"] = {
        "institutional_ownership_pct": d.get("inst_own_val"),
        # See matching comment in _get_stock_details - frontend looks up
        # institutional_ownership_pct_unavailable_reason/short_interest_pct_...,
        # the missing "_pct" meant a real null value here rendered as a bare
        # "No data" instead of the actual reason.
        "institutional_ownership_pct_unavailable_reason": d.get("institutional_ownership_unavailable_reason"),
        "top_10_institutions_pct": d.get("top_10_institutions_pct"),
        "top_10_institutions_pct_unavailable_reason": d.get("top_10_institutions_pct_unavailable_reason"),
        "institutional_holders_count": d.get("institutional_holders_count"),
        "institutional_holders_count_unavailable_reason": d.get("institutional_holders_count_unavailable_reason"),
        "short_interest_pct": d.get("short_pct_val"),
        "short_interest_pct_unavailable_reason": d.get("short_interest_unavailable_reason"),
        "short_percent_of_float": d.get("short_pct_float"),
        "short_percent_of_float_unavailable_reason": d.get("short_percent_of_float_unavailable_reason"),
        "short_interest_pct_change": d.get("short_interest_pct_change_val"),
        "short_interest_pct_change_unavailable_reason": d.get("short_interest_pct_change_unavailable_reason"),
        "shares_short_prior_month": d.get("shares_short_prior_month_val"),
        "shares_short_prior_month_unavailable_reason": d.get("shares_short_prior_month_unavailable_reason"),
        "short_ratio": d.get("days_to_cover"),
        "short_ratio_unavailable_reason": d.get("short_ratio_unavailable_reason"),
        "ad_rating": d.get("ad_rating"),
        "ad_rating_unavailable_reason": d.get("ad_rating_unavailable_reason"),
    }

    # Risk Inputs: Volatility, beta, financial stability
    d["risk_inputs"] = {
        "volatility_12m": d.get("volatility_12m_val"),
        "volatility_12m_unavailable_reason": d.get("volatility_12m_unavailable_reason"),
        "volatility_60d": d.get("volatility_60d_val"),
        "volatility_60d_unavailable_reason": d.get("volatility_60d_unavailable_reason"),
        "volatility_30d": d.get("volatility_30d_val"),
        "volatility_30d_unavailable_reason": d.get("volatility_30d_unavailable_reason"),
        "downside_volatility_30d": d.get("downside_volatility_30d"),
        "downside_volatility_30d_unavailable_reason": d.get("downside_volatility_30d_unavailable_reason"),
        "downside_volatility_60d": d.get("downside_volatility_60d"),
        "downside_volatility_60d_unavailable_reason": d.get("downside_volatility_60d_unavailable_reason"),
        "downside_volatility_252d": d.get("downside_volatility_252d"),
        "downside_volatility_252d_unavailable_reason": d.get("downside_volatility_252d_unavailable_reason"),
        "max_drawdown_1y": d.get("max_drawdown_1y"),
        "max_drawdown_1y_unavailable_reason": d.get("max_drawdown_1y_unavailable_reason"),
        "avg_dollar_volume_20d": d.get("avg_dollar_volume_20d"),
        "beta": d.get("beta_val"),
        "beta_unavailable_reason": d.get("beta_unavailable_reason"),
        # debt_to_assets briefly RESTORED HERE 2026-08-30, then REMOVED AGAIN the same
        # day (user directive) - see the other risk_inputs block above.
        # CLEANUP 2026-08-16: same "moved to Quality" cleanup as the other
        # risk_inputs block above - see that comment for details.
        "segment_count": d.get("segment_count"),
        "largest_segment_revenue_pct": d.get("largest_segment_revenue_pct"),
        "is_diversified": d.get("is_diversified"),
        "segment_count_unavailable_reason": (
            d.get("segment_unavailable_reason") if d.get("segment_count") is None else None
        ),
        "largest_segment_revenue_pct_unavailable_reason": (
            d.get("segment_unavailable_reason") if d.get("largest_segment_revenue_pct") is None else None
        ),
        "is_diversified_unavailable_reason": (
            d.get("segment_unavailable_reason") if d.get("is_diversified") is None else None
        ),
    }


def _build_stock_score_items(scores: Any) -> list[dict[str, Any]]:
    """Turn the raw query rows into the response `items` list.

    Applies the data-unavailable score-nulling rules, builds each row's factor input
    objects, and flags rows with no current price - the exact per-row transformation the
    inline loop in _get_stock_scores used to do.
    """
    items: list[dict[str, Any]] = []
    for row in scores:
        d = dict(row)
        # CRITICAL FIX: Explicit data_unavailable flags for each metric
        # If a score metric is marked unavailable, include it as None (not synthetic value)
        # Dashboard will see explicit unavailability markers
        if d.get("_growth_data_unavailable"):
            d["growth_score"] = None
        # positioning_score REMOVED from the API contract 2026-08-27 (Positioning retired
        # as a composite pillar - see loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS).
        if d.get("_risk_data_unavailable"):
            d["risk_score"] = None
        if d.get("_financial_data_unavailable"):
            d["quality_score"] = None
        if d.get("_value_data_unavailable"):
            d["value_score"] = None
        # size_score REMOVED from the API contract 2026-08-28 (Size retired as a composite
        # pillar - see loaders/load_stock_scores.py's BASE_PILLAR_WEIGHTS). market_cap
        # itself is still available via the Value pillar's inputs.

        # Build factor input objects for UI display (Session 302+ fix)
        _build_stock_score_factor_inputs(d)

        # TRANSPARENCY FIX (2026-08-05): Add data completeness and reason to top-level response
        # Traders need to see: (1) how complete is this score? (2) why is data missing?
        # Include these fields so dashboard can display data quality to users
        completeness = d.get("data_completeness")
        reason = d.get("reason")
        unavailable = d.get("data_unavailable")

        # Ensure these are in the response
        d["data_completeness"] = completeness if completeness is not None else 0.0
        d["data_unavailable_reason"] = (
            reason if reason else ("Data completeness below 70% threshold" if unavailable else None)
        )

        # CRITICAL FIX: If current price is missing, mark data unavailable
        # For trading, current price is REQUIRED to calculate entry/exit risk
        # Don't silently include incomplete scores - that masks data quality issues
        if d.get("current_price") is None:
            d["_data_unavailable"] = True
            d["_data_unavailable_reason"] = "current_price missing from price_daily - cannot calculate position risk"

        items.append(d)

    return items


def _log_stock_scores_price_quality(items: list[dict[str, Any]]) -> None:
    """Audit: Count how many scores have missing prices (data quality indicator)."""
    prices_missing_count = sum(1 for item in items if item.get("current_price") is None)
    if prices_missing_count > 0 and items:
        filter_rate = prices_missing_count / len(items) if len(items) > 0 else 0
        if filter_rate > 0.05:  # > 5% is degraded quality
            logger.error(
                f"Scores endpoint: {prices_missing_count}/{len(items)} scores ({filter_rate * 100:.1f}%) "
                f"have missing price data. Marked as data_unavailable to consumer. "
                f"Data quality is degraded - upstream price_daily loader may be incomplete."
            )
        else:
            logger.warning(
                f"Scores endpoint: {prices_missing_count} scores have missing price data ({filter_rate * 100:.1f}%). "
                f"Marked as data_unavailable to consumer."
            )


def _compute_stock_scores_summary(items: list[dict[str, Any]]) -> tuple[float | None, dict[str, int]]:
    """Compute average composite score and grade distribution (A/B/C/D) over ALL scores
    (not just this page) - the dashboard summary line needs these metrics for the full
    universe. Standard grading: A=80+, B=70-79, C=60-69, D=<60.
    """
    avg_composite: float | None = None
    grades_summary: dict[str, int] = {}

    if items:
        # Compute average composite score from returned items
        composite_scores: list[float] = []
        for item in items:
            score = item.get("composite_score")
            if score is not None:
                composite_scores.append(float(score))
        if composite_scores:
            avg_composite = sum(composite_scores) / len(composite_scores)

        # Count grade distribution (A/B/C/D) from composite scores
        for item in items:
            comp_score = item.get("composite_score")
            if comp_score is not None:
                if comp_score >= 80:
                    grades_summary["a"] = grades_summary.get("a", 0) + 1
                elif comp_score >= 70:
                    grades_summary["b"] = grades_summary.get("b", 0) + 1
                elif comp_score >= 60:
                    grades_summary["c"] = grades_summary.get("c", 0) + 1
                else:
                    grades_summary["d"] = grades_summary.get("d", 0) + 1

    return avg_composite, grades_summary


def _compute_stock_scores_completeness_health(items: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    """TRANSPARENCY ENHANCEMENT (2026-08-05): Data health metrics for the summary block -
    shows traders overall data quality of the scores being returned.
    """
    avg_completeness = None
    completeness_threshold_pct = None
    if items:
        completeness_values = [dc for d in items if (dc := d.get("data_completeness")) is not None and dc > 0]
        if completeness_values:
            avg_completeness = sum(completeness_values) / len(completeness_values)
            # Count how many meet trading gate (70%+ complete)
            trading_gate_count = sum(1 for c in completeness_values if c >= 70)
            completeness_threshold_pct = (
                100 * trading_gate_count / len(completeness_values) if completeness_values else 0
            )

    return avg_completeness, completeness_threshold_pct
