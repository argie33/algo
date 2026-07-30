"""Route: scores"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    error_response,
    execute_with_timeout,
    extract_param,
    handle_db_error,
    json_response,
    safe_limit,
    safe_offset,
)

from algo.infrastructure.config.sql_intervals import get_interval_sql

logger = logging.getLogger(__name__)


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, str] | None,
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/scores/* and /api/algo/scores/* endpoints."""
    try:
        if path in [
            "/api/scores",
            "/api/scores/stockscores",
            "/api/algo/scores",
            "/api/algo/scores/stockscores",
        ] or path.startswith(
            ("/api/scores?", "/api/scores/stockscores?", "/api/algo/scores?", "/api/algo/scores/stockscores?")
        ):
            limit = safe_limit(extract_param(params, "limit"), max_val=1000, default=1000)
            offset = safe_offset(extract_param(params, "offset") or "0")
            sort_by = extract_param(params, "sortBy") or "composite_score"
            sort_order = extract_param(params, "sortOrder") or "desc"
            sp500_only = extract_param(params, "sp500Only") or "false"
            symbol = extract_param(params, "symbol")

            allowed_sorts = [
                "composite_score",
                "momentum_score",
                "quality_score",
                "value_score",
                "growth_score",
                "positioning_score",
                "stability_score",
                "symbol",
            ]
            if sort_by not in allowed_sorts:
                return error_response(
                    400,
                    "bad_request",
                    f"Sort must be one of: {', '.join(allowed_sorts)}",
                )
            if sort_order not in ["asc", "desc"]:
                return error_response(400, "bad_request", 'Sort order must be "asc" or "desc"')

            return _get_stock_scores(cur, limit, offset, sort_by, sort_order, sp500_only == "true", symbol)
        else:
            return error_response(404, "not_found", f"No scores handler for {path}")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle scores")
        return error_response(code, error_type, message)


def _get_stock_scores(  # noqa: C901
    cur: cursor,
    limit: int = 5000,
    offset: int = 0,
    sort_by: str = "composite_score",
    sort_order: str = "desc",
    sp500_only: bool = False,
    symbol: str | None = None,
) -> Any:
    """Get stock scores with multi-factor ranking."""
    try:
        allowed_sorts = {
            "composite_score": "composite_score",
            "momentum_score": "momentum_score",
            "quality_score": "quality_score",
            "value_score": "value_score",
            "growth_score": "growth_score",
            "positioning_score": "positioning_score",
            "stability_score": "stability_score",
            "symbol": "symbol",
        }
        sort_col = allowed_sorts.get(sort_by, "composite_score")
        sort_direction = "DESC" if sort_order == "desc" else "ASC"

        # ETF FILTERING (GOVERNANCE compliance): Stock scores are for equity trading signals.
        # Exclude ETFs per GOVERNANCE.md: "financial data loaders and trading signals are stocks only".
        # Use etf_symbols table (definitive source). Note: ss.etf column does not exist in stock_scores.
        # This pattern is mirrored in /api/market/breadth and Phase 7 signal generation.
        where_clause = """
            WHERE sc.composite_score > 0
            AND ss.symbol NOT IN (SELECT symbol FROM etf_symbols)
            """
        params_list: list[Any] = []

        if sp500_only:
            where_clause += " AND ss.is_sp500 = TRUE"
        if symbol:
            # Validate symbol format (consistent with signals.py)
            import re

            if not re.match(r"^[A-Z0-9\-\^]{1,10}$", symbol.upper()):
                return error_response(400, "bad_request", "Invalid symbol format")
            where_clause += " AND sc.symbol = %s"
            params_list.append(symbol.upper())
        else:
            # Bulk queries: filter out degraded composite scores.
            # Only return scores with >= 70% metric completeness per GOVERNANCE.md line 62.
            # stock_scores computes at >=50% but API must gate to >=70% for downstream use.
            # This prevents clients from receiving degraded data without visibility into completeness %.
            where_clause += (
                " AND sc.data_completeness >= 70 AND (sc.data_unavailable = false OR sc.data_unavailable IS NULL)"
            )

        # PERFORMANCE: filter/sort/limit to the target page FIRST in a CTE, then run the
        # per-symbol LATERAL lookups (price_daily/technical_data_daily) only against that
        # small row set. Previously the LATERAL joins ran against every row of stock_scores
        # BEFORE the WHERE clause was applied, so a page of 50 rows still paid for thousands
        # of per-symbol index scans - this was the root cause of the endpoint's 7+ second
        # latency (and the dashboard's 3s client timeout hiding it as "no data").
        interval_52w = get_interval_sql("52w")
        query = f"""
                WITH max_price_date AS (
                    SELECT MAX(date) AS max_date FROM price_daily
                ),
                filtered_scores AS (
                    SELECT sc.*, ss.security_name, ss.is_sp500
                    FROM stock_scores sc
                    JOIN stock_symbols ss ON ss.symbol = sc.symbol
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
                    fs.value_score, fs.growth_score, fs.positioning_score, fs.stability_score,
                    fs.rs_percentile, fs.data_completeness,
                    fs.updated_at AS last_updated,
                    pl.close AS current_price,
                    pl.close AS price,
                    (pl.close IS NULL) AS _is_fallback,
                    (qm.symbol IS NULL OR qm.data_unavailable = TRUE OR (qm.roe IS NULL AND qm.operating_margin IS NULL AND qm.net_margin IS NULL)) AS _financial_data_unavailable,
                    (vm.symbol IS NULL OR vm.data_unavailable = TRUE) AS _value_data_unavailable,
                    (fs.growth_score IS NULL) AS _growth_data_unavailable,
                    (pm.symbol IS NULL OR pm.data_unavailable = TRUE) AS _positioning_data_unavailable,
                    (sm.symbol IS NULL OR sm.data_unavailable = TRUE) AS _stability_data_unavailable,
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
                    vm.fcf_yield AS fcf_yield_val,
                    vm.fcf_yield_unavailable_reason,
                    vm.enterprise_value,
                    vm.ev_ebitda,
                    vm.ev_ebitda_unavailable_reason,
                    vm.ev_revenue,
                    vm.held_percent_insiders AS vm_held_insiders,
                    vm.held_percent_institutions AS vm_held_institutions,
                    qm.roe AS roe_pct,
                    qm.roe_unavailable_reason,
                    qm.roa AS roa_val,
                    qm.roa_unavailable_reason,
                    qm.roic_pct,
                    qm.roic_pct_unavailable_reason,
                    qm.gross_margin AS gross_margin_pct,
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
                    qm.eps_growth_stability,
                    qm.earnings_beat_rate,
                    qm.consecutive_positive_quarters,
                    qm.estimate_revision_direction,
                    qm.revision_activity_30d,
                    qm.estimate_momentum_60d,
                    qm.estimate_momentum_90d,
                    qm.revision_trend_score,
                    qm.earnings_growth_4q_avg,
                    gm.net_income_growth_yoy,
                    gm.operating_income_growth_yoy,
                    gm.gross_margin_trend,
                    gm.operating_margin_trend,
                    gm.net_margin_trend,
                    gm.roe_trend,
                    gm.sustainable_growth_rate,
                    gm.quarterly_growth_momentum,
                    gm.fcf_growth_yoy,
                    gm.ocf_growth_yoy,
                    gm.asset_growth_yoy,
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
                    sm.beta AS beta_val,
                    sm.beta_unavailable_reason,
                    sm.volatility_252d AS volatility_12m_val,
                    sm.volatility_252d_unavailable_reason AS volatility_12m_unavailable_reason,
                    sm.volatility_30d AS volatility_30d_val,
                    sm.volatility_30d_unavailable_reason,
                    sm.volatility_60d AS volatility_60d_val,
                    sm.volatility_60d_unavailable_reason,
                    pm.institutional_ownership_pct AS inst_own_val,
                    pm.institutional_ownership_pct_unavailable_reason AS institutional_ownership_unavailable_reason,
                    pm.insider_ownership_pct AS insider_own_val,
                    pm.insider_ownership_pct_unavailable_reason AS insider_ownership_unavailable_reason,
                    pm.short_interest_pct AS short_pct_val,
                    pm.short_interest_pct_unavailable_reason AS short_interest_unavailable_reason,
                    pm.shares_short_prior_month AS shares_short_prior_month_val,
                    pm.shares_short_prior_month_unavailable_reason,
                    pm.short_interest_trend AS short_interest_trend_val,
                    pm.short_interest_trend_unavailable_reason,
                    pm.top_10_institutions_pct,
                    pm.top_10_institutions_pct_unavailable_reason,
                    pm.institutional_holders_count,
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
                    segm.revenue_concentration_hhi AS segment_revenue_concentration_hhi,
                    (segm.symbol IS NULL OR segm.data_unavailable = TRUE) AS _segment_data_unavailable
                FROM filtered_scores fs
                LEFT JOIN company_profile cp ON cp.symbol = fs.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = fs.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = fs.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = fs.symbol
                LEFT JOIN stability_metrics sm ON sm.symbol = fs.symbol
                LEFT JOIN positioning_metrics pm ON pm.symbol = fs.symbol
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
                    SELECT MAX(high) AS high_52w
                    FROM price_daily
                    WHERE symbol = fs.symbol
                      AND date >= CURRENT_DATE - {interval_52w}
                ) p52 ON true
                ORDER BY fs.{sort_col} {sort_direction}
            """
        params_list.extend([limit, offset])

        # Try with data_unavailable columns first (preferred)
        # timeout_sec=20 ensures DB cancels before Lambda's 25s timeout, allowing proper error response
        try:
            scores = execute_with_timeout(cur, query, params_list, timeout_sec=20, max_attempts=1)
        except psycopg2.errors.UndefinedColumn as e:
            # CRITICAL: Schema mismatch on data_unavailable columns indicates migration incomplete
            # FAIL-FAST: Do not silently degrade query validation
            if "data_unavailable" in str(e):
                logger.critical(
                    f"[SCORES_API] Schema validation failed: data_unavailable columns missing from metrics tables. "
                    f"This indicates database migration (0046) has not been applied. Cannot validate score completeness. "
                    f"Error: {e}"
                )
                return error_response(
                    503,
                    "schema_mismatch",
                    "Score validation unavailable: database schema missing required data_unavailable columns. "
                    "Database migration may not have completed.",
                )
            else:
                raise

        def _f(v: Any) -> float | None:
            return float(v) if v is not None else None

        def _build_factor_inputs(d: dict[str, Any]) -> None:
            """Build factor input objects from flat response fields.

            Maps API field names to schema keys for UI display. Adds objects:
            - quality_inputs: ROE, margins, debt ratios, growth metrics
            - momentum_inputs: price momentum, technical indicators
            - value_inputs: valuation ratios (PE, PB, PS, etc.)
            - growth_inputs: revenue/EPS growth rates
            - positioning_inputs: institutional/insider ownership, short interest
            - stability_inputs: volatility, beta
            """
            # Quality Inputs: ROE, ROA, ROIC, margins, debt, ratios
            d["quality_inputs"] = {
                "return_on_equity_pct": d.get("roe_pct"),
                "return_on_equity_pct_unavailable_reason": d.get("roe_unavailable_reason"),
                "return_on_assets_pct": d.get("roa_val"),
                "return_on_assets_pct_unavailable_reason": d.get("roa_unavailable_reason"),
                "return_on_invested_capital_pct": d.get("roic_pct"),
                "return_on_invested_capital_pct_unavailable_reason": d.get("roic_pct_unavailable_reason"),
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
                "eps_growth_stability": d.get("eps_growth_stability"),
                "earnings_beat_rate": d.get("earnings_beat_rate"),
                "consecutive_positive_quarters": d.get("consecutive_positive_quarters"),
                "estimate_revision_direction": d.get("estimate_revision_direction"),
                "revision_activity_30d": d.get("revision_activity_30d"),
                "estimate_momentum_60d": d.get("estimate_momentum_60d"),
                "estimate_momentum_90d": d.get("estimate_momentum_90d"),
                "revision_trend_score": d.get("revision_trend_score"),
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
                "net_income_growth_yoy": d.get("net_income_growth_yoy"),
                "operating_income_growth_yoy": d.get("operating_income_growth_yoy"),
                "gross_margin_trend": d.get("gross_margin_trend"),
                "operating_margin_trend": d.get("operating_margin_trend"),
                "net_margin_trend": d.get("net_margin_trend"),
                "roe_trend": d.get("roe_trend"),
                "sustainable_growth_rate": d.get("sustainable_growth_rate"),
                "quarterly_growth_momentum": d.get("quarterly_growth_momentum"),
            }

            # Momentum Inputs: Price momentum, technical indicators
            # Note: momentum_12_3 represents 12-minus-3-month momentum (Jegadeesh-Titman effect);
            # API returns individual period returns; may need computation for accuracy
            d["momentum_inputs"] = {
                "current_price": d.get("current_price"),
                "price_vs_52w_high": d.get("price_vs_52w_high_val"),
                "price_vs_sma_50": d.get("price_vs_sma_50"),
                "price_vs_sma_200": d.get("price_vs_sma_200"),
                "momentum_3m": d.get("momentum_3m_val"),  # 3-month return
                "momentum_6m": d.get("momentum_6m_val"),  # 6-month return
                "momentum_12_3": d.get("momentum_12m_val"),  # 12-month return (proxy for 12-3)
                "rsi": d.get("tdd_rsi"),
                "macd": d.get("tdd_macd"),
            }

            # Value Inputs: Valuation ratios
            d["value_inputs"] = {
                "stock_pe": d.get("trailing_pe"),
                "stock_pe_unavailable_reason": d.get("pe_ratio_unavailable_reason"),
                "stock_forward_pe": d.get("forward_pe"),  # May be None
                "stock_forward_pe_unavailable_reason": d.get("forward_pe_unavailable_reason"),
                "stock_pb": d.get("price_to_book"),
                "stock_pb_unavailable_reason": d.get("pb_ratio_unavailable_reason"),
                "stock_ps": d.get("ps_ratio_val"),
                "stock_ps_unavailable_reason": d.get("ps_ratio_unavailable_reason"),
                "peg_ratio": d.get("peg_ratio_val"),
                "peg_ratio_unavailable_reason": d.get("peg_ratio_unavailable_reason"),
                "stock_ev_ebitda": d.get("ev_ebitda"),  # May be None
                "stock_ev_ebitda_unavailable_reason": d.get("ev_ebitda_unavailable_reason"),
                "stock_ev_revenue": d.get("ev_revenue"),  # May be None
                "fcf_yield": d.get("fcf_yield_val"),
                "fcf_yield_unavailable_reason": d.get("fcf_yield_unavailable_reason"),
                "stock_dividend_yield": d.get("dividend_yield"),
                "stock_dividend_yield_unavailable_reason": d.get("dividend_yield_unavailable_reason"),
            }

            # Growth Inputs: Revenue and EPS growth
            d["growth_inputs"] = {
                "revenue_growth_1y_pct": d.get("rev_growth_1y_val"),
                "revenue_growth_1y_unavailable_reason": d.get("revenue_growth_1y_unavailable_reason"),
                "eps_growth_1y_pct": d.get("eps_growth_1y_val"),
                "eps_growth_1y_unavailable_reason": d.get("eps_growth_1y_unavailable_reason"),
                "revenue_growth_3y_cagr": d.get("rev_growth_3y_val"),
                "revenue_growth_3y_unavailable_reason": d.get("revenue_growth_3y_unavailable_reason"),
                "eps_growth_3y_cagr": d.get("eps_growth_3y_val"),
                "eps_growth_3y_unavailable_reason": d.get("eps_growth_3y_unavailable_reason"),
                "revenue_growth_5y_cagr": d.get("rev_growth_5y_val"),
                "revenue_growth_5y_unavailable_reason": d.get("revenue_growth_5y_unavailable_reason"),
                "eps_growth_5y_cagr": d.get("eps_growth_5y_val"),
                "eps_growth_5y_unavailable_reason": d.get("eps_growth_5y_unavailable_reason"),
                "net_income_growth_yoy": d.get("net_income_growth_yoy"),
                "operating_income_growth_yoy": d.get("operating_income_growth_yoy"),
                "gross_margin_trend": d.get("gross_margin_trend"),
                "operating_margin_trend": d.get("operating_margin_trend"),
                "net_margin_trend": d.get("net_margin_trend"),
                "roe_trend": d.get("roe_trend"),
                "sustainable_growth_rate": d.get("sustainable_growth_rate"),
                "quarterly_growth_momentum": d.get("quarterly_growth_momentum"),
                "fcf_growth_yoy": d.get("fcf_growth_yoy"),
                "ocf_growth_yoy": d.get("ocf_growth_yoy"),
                "asset_growth_yoy": d.get("asset_growth_yoy"),
            }

            # Positioning Inputs: Ownership and short interest
            d["positioning_inputs"] = {
                "institutional_ownership_pct": d.get("inst_own_val"),
                "institutional_ownership_unavailable_reason": d.get("institutional_ownership_unavailable_reason"),
                "top_10_institutions_pct": d.get("top_10_institutions_pct"),
                "top_10_institutions_pct_unavailable_reason": d.get("top_10_institutions_pct_unavailable_reason"),
                "institutional_holders_count": d.get("institutional_holders_count"),
                "institutional_holders_count_unavailable_reason": d.get("institutional_holders_count_unavailable_reason"),
                "insider_ownership_pct": d.get("insider_own_val"),
                "insider_ownership_unavailable_reason": d.get("insider_ownership_unavailable_reason"),
                "short_interest_pct": d.get("short_pct_val"),
                "short_interest_unavailable_reason": d.get("short_interest_unavailable_reason"),
                "short_percent_of_float": d.get("short_pct_float"),
                "short_percent_of_float_unavailable_reason": d.get("short_percent_of_float_unavailable_reason"),
                "short_interest_trend": d.get("short_interest_trend_val"),
                "short_interest_trend_unavailable_reason": d.get("short_interest_trend_unavailable_reason"),
                "shares_short_prior_month": d.get("shares_short_prior_month_val"),
                "shares_short_prior_month_unavailable_reason": d.get("shares_short_prior_month_unavailable_reason"),
                "short_ratio": d.get("days_to_cover"),
                "short_ratio_unavailable_reason": d.get("short_ratio_unavailable_reason"),
                "ad_rating": d.get("ad_rating"),
                "ad_rating_unavailable_reason": d.get("ad_rating_unavailable_reason"),
            }

            # Stability Inputs: Volatility, beta, financial stability, business diversification
            # NOTE: revenue_concentration_hhi comes from sec_segment_metrics (real XBRL segment
            # disclosures); the rest from load_risk_metrics_daily.py. (downside_volatility,
            # max_drawdown_52w, volume_consistency, etc. are not computed by any loader)
            d["stability_inputs"] = {
                "volatility_12m": d.get("volatility_12m_val"),
                "volatility_12m_unavailable_reason": d.get("volatility_12m_unavailable_reason"),
                "volatility_60d": d.get("volatility_60d_val"),
                "volatility_60d_unavailable_reason": d.get("volatility_60d_unavailable_reason"),
                "volatility_30d": d.get("volatility_30d_val"),
                "volatility_30d_unavailable_reason": d.get("volatility_30d_unavailable_reason"),
                "beta": d.get("beta_val"),
                "beta_unavailable_reason": d.get("beta_unavailable_reason"),
                "debt_to_assets": d.get("debt_to_assets_val"),
                "debt_to_assets_unavailable_reason": d.get("debt_to_assets_unavailable_reason"),
                "revenue_concentration_hhi": (
                    None if d.get("_segment_data_unavailable") else d.get("segment_revenue_concentration_hhi")
                ),
                "revenue_concentration_hhi_unavailable_reason": (
                    "no_segment_disclosure" if d.get("_segment_data_unavailable") else None
                ),
            }

        items: list[dict[str, Any]] = []
        prices_missing_count = 0
        for row in scores:
            d = dict(row)
            # CRITICAL FIX: Explicit data_unavailable flags for each metric
            # If a score metric is marked unavailable, include it as None (not synthetic value)
            # Dashboard will see explicit unavailability markers
            if d.get("_growth_data_unavailable"):
                d["growth_score"] = None
            if d.get("_positioning_data_unavailable"):
                d["positioning_score"] = None
            if d.get("_stability_data_unavailable"):
                d["stability_score"] = None
            if d.get("_financial_data_unavailable"):
                d["quality_score"] = None
            if d.get("_value_data_unavailable"):
                d["value_score"] = None

            # Build factor input objects for UI display (Session 302+ fix)
            _build_factor_inputs(d)

            # CRITICAL FIX: If current price is missing, mark data unavailable
            # For trading, current price is REQUIRED to calculate entry/exit risk
            # Don't silently include incomplete scores - that masks data quality issues
            if d.get("current_price") is None:
                d["_data_unavailable"] = True
                d["_data_unavailable_reason"] = "current_price missing from price_daily - cannot calculate position risk"

            items.append(d)

        # Check data freshness
        freshness = check_data_freshness(cur, "stock_scores", "updated_at", warning_days=7)

        # Audit: Count how many scores have missing prices (data quality indicator)
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

        # CRITICAL FIX: Return scores in standard paginated format
        # Dashboard/responseNormalizer expects {statusCode: 200, items: [...], pagination: {...}} format
        # This matches other paginated endpoints and works with frontend schema validation
        items_count = len(items) if items else 0
        # If we got fewer items than requested, we've hit the end of results
        # Otherwise, we estimate there might be more results
        is_last_page = items_count < limit
        estimated_total = offset + items_count if is_last_page else offset + limit + 1

        # Compute summary metrics over ALL scores (not just this page)
        # Dashboard summary line needs these metrics for the full universe
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
            # Using standard grading: A=80+, B=70-79, C=60-69, D=<60
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

        result = {
            "items": items,
            "pagination": {
                "total": estimated_total,
                "limit": limit,
                "offset": offset,
                "page": (offset // limit) + 1 if limit > 0 else 1,
                "totalPages": ((estimated_total - 1) // limit) + 1 if limit > 0 else 1,
            },
            "avg_composite": avg_composite,
            "grades": grades_summary if grades_summary else None,
        }
        return json_response(200, result, data_freshness=freshness)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle scores")
        return error_response(code, error_type, message)
