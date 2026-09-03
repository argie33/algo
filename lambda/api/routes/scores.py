"""Route: scores"""

from __future__ import annotations

import logging
import math
import re
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
    safe_days,
    safe_limit,
    safe_offset,
)

from algo.infrastructure.config.sql_intervals import get_interval_sql
from loaders.loader_registry import LOADER_TABLES, PSEUDO_LOADER_TABLES

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
        # Handle /api/scores/details/:symbol endpoint (new)
        if path.startswith("/api/scores/details/"):
            detail_symbol = path.split("/api/scores/details/")[-1].upper()
            if not detail_symbol or not detail_symbol.replace("-", "").replace("^", "").isalnum():
                return error_response(400, "bad_request", "Invalid symbol format")
            return _get_stock_details(cur, detail_symbol)

        # Handle /api/scores/history/:symbol endpoint - historical composite score/rank
        # movement, sourced from stock_scores_history (one snapshot per trading day,
        # written by load_stock_scores.py's post_run()).
        if path.startswith("/api/scores/history/"):
            history_symbol = path.split("/api/scores/history/")[-1].split("?")[0].upper()
            if not history_symbol or not history_symbol.replace("-", "").replace("^", "").isalnum():
                return error_response(400, "bad_request", "Invalid symbol format")
            days = safe_days(extract_param(params, "days"), max_val=365, default=90)
            return _get_score_history(cur, history_symbol, days)

        # Handle /api/scores/incomplete endpoint (new) - stocks with insufficient data
        if path in ["/api/scores/incomplete", "/api/algo/scores/incomplete"] or path.startswith(
            ("/api/scores/incomplete?", "/api/algo/scores/incomplete?")
        ):
            limit = safe_limit(extract_param(params, "limit"), max_val=1000, default=100)
            offset = safe_offset(extract_param(params, "offset") or "0")
            sort_by = extract_param(params, "sortBy") or "data_completeness"
            sort_order = (extract_param(params, "sortOrder") or "asc").lower()
            if sort_by not in ("data_completeness", "symbol"):
                sort_by = "data_completeness"
            if sort_order not in ("asc", "desc"):
                sort_order = "asc"

            return _get_incomplete_stocks(cur, limit, offset, sort_by, sort_order)

        # Handle /api/scores/coverage endpoint - factor-level aggregation of which
        # *_unavailable_reason columns are missing data, why, and how much. Mirrors
        # scripts/audit_unavailable_reasons.py's methodology (latest row per symbol,
        # deduplicated) but served live for the ServiceHealth "Scores Data Coverage" tab.
        #
        # FIXED 2026-09-01 (goal session: this single request ran ~100+ sequential
        # per-table queries in one HTTP call, taking 15-20s+ end to end - close enough to
        # the frontend axios client's 28s hard timeout (set deliberately below API
        # Gateway/Lambda's own 30s hard cutoff, see api.js) that it timed out in practice
        # under any real load, even though a one-off psql/script run of the same queries
        # "worked". Bumping the client timeout doesn't fix this: in production Lambda
        # kills the function at 30s regardless of what the client is willing to wait, so
        # the actual fix is to break the ~100+ queries into per-group chunks the frontend
        # fetches separately (ScoresDataCoverage.jsx), each cheap enough to finish well
        # under either limit. `?meta=1` returns just the group list (two fast
        # information_schema queries, no per-table scans) so the frontend knows what to
        # fetch; `?group=<name>` scopes the normal per-table loop to one group at a time.
        if path in ["/api/scores/coverage", "/api/algo/scores/coverage"]:
            if extract_param(params, "meta") == "1":
                return _get_scores_coverage(cur, meta_only=True)
            return _get_scores_coverage(cur, group_filter=extract_param(params, "group"))

        if path in [
            "/api/scores",
            "/api/scores/stockscores",
            "/api/algo/scores",
            "/api/algo/scores/stockscores",
        ] or path.startswith(
            ("/api/scores?", "/api/scores/stockscores?", "/api/algo/scores?", "/api/algo/scores/stockscores?")
        ):
            # max_val was 1000 - the real filtered universe is ~5000+ symbols (live-verified),
            # so any caller requesting the default/max page size silently got capped well
            # below the true universe size. Raised to match the other high-volume listing
            # endpoints (signals.py, algo.py use 10000).
            limit = safe_limit(extract_param(params, "limit"), max_val=10000, default=1000)
            offset = safe_offset(extract_param(params, "offset") or "0")
            sort_by = extract_param(params, "sortBy") or "composite_score"
            sort_order = (extract_param(params, "sortOrder") or "desc").lower()
            sp500_only = extract_param(params, "sp500Only") or "false"
            symbol = extract_param(params, "symbol")
            min_market_cap_param = extract_param(params, "minMarketCap")
            min_market_cap: float | None = None
            if min_market_cap_param:
                try:
                    min_market_cap = float(min_market_cap_param)
                except ValueError:
                    return error_response(400, "bad_request", "minMarketCap must be numeric")

            allowed_sorts = [
                "composite_score",
                "momentum_score",
                "quality_score",
                "value_score",
                "growth_score",
                "risk_score",
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

            return _get_stock_scores(
                cur, limit, offset, sort_by, sort_order, sp500_only == "true", symbol, min_market_cap
            )
        else:
            return error_response(404, "not_found", "Invalid scores endpoint requested")
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle scores")
        return error_response(code, error_type, message)


def _derive_mom_12_1(momentum_12m: float | None, momentum_1m: float | None) -> float | None:
    """12-1 skip-month momentum (Jegadeesh 1990 standard construction) - the actual quantity
    loaders/load_stock_scores.py's _score_momentum weights at 35% since 2026-08-25 (see that
    function's docstring RESOLVED note), replacing raw momentum_6m/momentum_12m. Not a stored
    field - derived here the identical way, so this page shows the real number driving the
    score instead of the raw momentum_12m value that no longer is the score input (same
    "computed but invisible" bug class this codebase has fixed before for
    vol_managed_multiplier/active_policy_tier - a scored quantity must be visible somewhere,
    not just its stale predecessor). Cumulative return from 12mo-ago to 1mo-ago is
    algebraically (1+momentum_12m/100)/(1+momentum_1m/100) - 1, converted back to the
    percentage-number convention this page's other momentum fields use.
    """
    if momentum_12m is None or momentum_1m is None:
        return None
    denom = 1.0 + float(momentum_1m) / 100.0
    if abs(denom) <= 1e-6:
        return None
    result = ((1.0 + float(momentum_12m) / 100.0) / denom - 1.0) * 100.0
    return result if math.isfinite(result) else None


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


def _get_score_history(cur: cursor, symbol: str, days: int) -> Any:
    """Historical composite score / rank movement for one symbol.

    Sourced from stock_scores_history - one snapshot per trading day, written by
    load_stock_scores.py's post_run() after RS percentiles are finalized for that run.
    A symbol new to scoring, or one that only recently started passing the completeness
    gate, will simply have fewer points than `days` - not an error.
    """
    try:
        query = """
            SELECT
                score_date, composite_score, composite_rank, rs_percentile,
                momentum_score, quality_score, growth_score, value_score,
                risk_score, data_completeness
            FROM stock_scores_history
            WHERE symbol = %s AND score_date >= CURRENT_DATE - %s::int
            ORDER BY score_date ASC
        """
        rows = execute_with_timeout(cur, query, [symbol, days], timeout_sec=20, max_attempts=1)

        points = [dict(row) for row in rows]
        for p in points:
            if p.get("score_date") is not None:
                p["score_date"] = p["score_date"].isoformat()

        movement: dict[str, Any] = {
            "score_change": None,
            "rank_change": None,
            "rs_percentile_change": None,
            "start_date": None,
            "end_date": None,
        }
        if len(points) >= 2:
            first, last = points[0], points[-1]
            movement["start_date"] = first["score_date"]
            movement["end_date"] = last["score_date"]
            if first.get("composite_score") is not None and last.get("composite_score") is not None:
                movement["score_change"] = round(float(last["composite_score"]) - float(first["composite_score"]), 2)
            if first.get("composite_rank") is not None and last.get("composite_rank") is not None:
                # Negative rank_change = improved (moved toward rank 1)
                movement["rank_change"] = int(first["composite_rank"]) - int(last["composite_rank"])
            if first.get("rs_percentile") is not None and last.get("rs_percentile") is not None:
                movement["rs_percentile_change"] = round(
                    float(last["rs_percentile"]) - float(first["rs_percentile"]), 2
                )

        result = {
            "symbol": symbol,
            "days": days,
            "points": points,
            "movement": movement,
        }

        freshness = check_data_freshness(cur, "stock_scores_history", "updated_at", warning_days=3)
        return json_response(200, result, data_freshness=freshness, preserve_arrays=True)

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "get score history")
        return error_response(code, error_type, message)


def _get_stock_scores(  # noqa: C901
    cur: cursor,
    limit: int = 5000,
    offset: int = 0,
    sort_by: str = "composite_score",
    sort_order: str = "desc",
    sp500_only: bool = False,
    symbol: str | None = None,
    min_market_cap: float | None = None,
) -> Any:
    """Get stock scores with multi-factor ranking."""
    try:
        allowed_sorts = {
            "composite_score": "composite_score",
            "momentum_score": "momentum_score",
            "quality_score": "quality_score",
            "value_score": "value_score",
            "growth_score": "growth_score",
            "risk_score": "risk_score",
            "symbol": "symbol",
        }
        sort_col = allowed_sorts.get(sort_by, "composite_score")
        sort_direction = "DESC" if sort_order == "desc" else "ASC"

        # ETF FILTERING (GOVERNANCE compliance): Stock scores are for equity trading signals.
        # Exclude ETFs per GOVERNANCE.md: "financial data loaders and trading signals are stocks only".
        # Use etf_symbols table (definitive source). Note: ss.etf column does not exist in stock_scores.
        # This pattern is mirrored in /api/market/breadth and Phase 7 signal generation.
        #
        # SPAC-SHELL/DERIVATIVE FILTERING (2026-08-03): pre-merger SPAC common shares
        # ("... Acquisition Corp[oration] - Class A Ordinary Shares") and their Rights/
        # Warrants derivatives have no operating business, so SEC EDGAR has no income
        # statement/balance sheet for them - loaders correctly mark them
        # 'no_annual_income_data_in_sec_edgar_reit_or_special_entity', which surfaced on
        # the scores page as "No SEC data" for ~5% of the universe (279/5455 symbols,
        # verified live 2026-08-03). That's not a loader gap to fix - there is nothing to
        # load - so exclude them the same way ETFs are excluded. The Rights/Warrants
        # pattern is end-anchored ('...Rights?/Warrants?$') to avoid matching ADS
        # boilerplate like "...American Depositary Shares (each representing the right to
        # receive...)" (e.g. AMX/RLX/WDH), which are real operating companies.
        #
        # SIC-CODE SPAC FILTERING (2026-08-03, follow-up): the name regex above was
        # verified live to still miss a real, non-trivial share of SPAC shells with
        # heterogeneous naming - "General Catalyst Global Resilience Merger Corp" (GCGR,
        # "Merger" not "Acquisition"), "Iron Dome Acquisition I Corp" / "Research Alliance
        # Corp III" / "Texas Ventures Acquisition IV Corp" (IDAC/RACC/RACD/TVIV, a roman
        # numeral or ordinal breaks the "Acquisition Corp" substring match), "Yorkville
        # International Capital Corp" (YICC, no "Acquisition"/"Merger" at all). Live-verified
        # against real SEC EDGAR submissions JSON: all 6 of the above report SIC code 6770
        # ("Blank Checks") - the SEC's own official classification for pre-merger SPAC
        # shells - while real operating companies with similar naming (AAPL, MSFT, FNWB) and
        # REITs/banks previously at false-positive risk from name regexes (NREF, OZK) do not.
        # `company_info_sec.sic_code` is already fetched from this same submissions endpoint
        # by loaders/load_company_info_sec.py, just never used for this filter before - a
        # strictly more reliable, name-independent signal than pattern matching heterogeneous
        # SPAC naming conventions.
        #
        # SIC-CODE ROYALTY TRUST FILTERING (2026-08-03, same follow-up): oil/gas royalty
        # trusts (CRT, MTR, PBT, SBR, SJT - ~5 symbols) have the identical "no operating
        # business, nothing for SEC EDGAR to report" problem as SPAC shells, but with their
        # own distinct, clean SIC code: 6792 ("Oil Royalty Traders"), live-verified for all 5.
        # No false-positive risk from real oil/gas producers - XOM/CVX (2911 Petroleum
        # Refining) and OXY (1311 Crude Petroleum & Natural Gas) live-confirmed as different
        # codes. Closed-end funds/investment trusts (~60+ symbols, the largest remaining
        # bucket) were also tested this same way and do NOT have a usable SIC signal - their
        # SIC field is blank/empty via this endpoint, identical to real operating companies
        # like OZK (Bank OZK) that were already a known false-positive risk for name-based
        # filtering. Solved instead via `has_annual_report_filing` below (migration 1193).
        #
        # SIC-CODE STRUCTURED-NOTE FILTERING (2026-08-03, same follow-up): trust-preferred/
        # structured-note certificates (GJH/GJO/GJP/GJR/GJS/GJT "STRATS", KTN "CorTS", PYT
        # "PPlus Trust" - a securitization wrapper around another company's bonds, no
        # operating business of its own) live-verified with their own distinct SIC code:
        # 6189 ("Asset-Backed Securities"), consistent across all 6 checked. Note:
        # ELC/EMP/ENJ/ENO ("Entergy First Mortgage Bonds") were checked too but their ticker
        # resolves to the PARENT operating utility's own CIK/SIC (real Entergy subsidiaries
        # with real SEC filings), not a separate securitization vehicle - those are a
        # different, not-yet-understood problem, NOT fixed by this filter and not added here.
        #
        # HAS_ANNUAL_REPORT_FILING FILTERING (2026-08-03, migration 1193): closed-end funds/
        # investment trusts (~60+ symbols, the LARGEST remaining "No SEC data" bucket - real
        # 40-Act funds like BlackRock/Eaton Vance/Gabelli/Invesco/Franklin CEFs) have no
        # usable SIC signal (blank sic_code, same as some real operating companies - see
        # comment above). Different, more direct signal: whether SEC EDGAR submissions.
        # filings.recent.form has EVER included 10-K/10-K-A (domestic annual report) or
        # 20-F/20-F-A (foreign private issuer annual report) - the two filing types this
        # pipeline's loaders actually parse for annual_income_statement/annual_balance_sheet.
        # Live-verified via loaders/load_company_info_sec.py: CEFs (BGT, GAB) file NEITHER -
        # only fund-specific forms (N-Q, NPORT-P, 40-17G, N-30B-2, DEF 14A) - while real
        # operating companies (AAPL, FNWB) have 10-K and foreign filers (IBN/ICICI Bank) have
        # 20-F, so this correctly leaves foreign 20-F filers unaffected (a separate, sparser-
        # coverage problem, not "no data at all"). `has_annual_report_filing IS NOT FALSE`
        # (not `= TRUE`) deliberately includes NULL (not yet checked for this symbol, or no
        # company_info_sec row at all) - only excludes symbols explicitly confirmed to have
        # neither filing type, same "fail open on unknown" posture as the ETF/SPAC filters
        # above.
        #
        # DEBT/PREFERRED-CERTIFICATE FILTERING (2026-08-03): subordinated debentures/mortgage
        # bonds (AFGB/AFGC/AFGD/AFGE - American Financial Group; ELC/EMP/ENJ/ENO/EAI - Entergy
        # utility subsidiaries) trade under their own ticker but share the parent operating
        # company's CIK, so they inherit real revenue/net_income data yet aren't common equity
        # and structurally have no separate balance sheet of their own to compute ROE/margins
        # from. Live-verified zero false-positive risk: `security_name ~*
        # '(Subordinated Debentures?|First Mortgage Bonds?|Collateral Trust Mortgage Bonds?)'`
        # matched exactly these 5 tickers across the ENTIRE active universe, nothing else.
        # Deliberately did NOT extend this to a broader "Trust N" pattern (e.g. for SCE$L "SCE
        # TRUST VI") - live-checked and found it collides with real closed-end funds (VLT
        # "Invesco High Income Trust II"), the same false-positive trap already documented for
        # CEF name-matching above.
        # PHYSICAL COMMODITY TRUST FILTERING (2026-08-10): grantor trusts that hold physical
        # bullion (GraniteShares Gold Trust "BAR" the live example - 279 more like it exist
        # for silver/platinum/palladium under other issuers) file real 10-Ks (so they pass
        # has_annual_report_filing) and aren't ETF-registered '40 Act funds (so etf_symbols
        # doesn't have them either) - they slipped through every filter above and ranked #1
        # in the entire universe on last live check. SIC 6221 ("Commodity Contracts Brokers &
        # Dealers") alone isn't a safe filter - live-verified it also covers real operating
        # companies (AIB "Data Centers Inc", ANTA "Antalpha Platform Holding", UROY "Uranium
        # Royalty Corp"), none of which have "Trust" in their name. Requiring both SIC 6221
        # AND a commodity-Trust name pattern together matched only BAR across the entire
        # scored universe, zero false positives against the SIC-6221 operating companies above.
        #
        # ETN FILTERING (goal: "scores still including ETFs", 2026-08-20): GRN ("iPath Series B
        # Carbon Exchange-Traded Notes") ranked in the score leaderboard despite every filter
        # above - not in etf_symbols (ETNs are debt notes, not '40 Act funds), sic_code=6029
        # ("Commercial Banks") not 6770/6792/6189, and has_annual_report_filing=TRUE, because
        # an ETN's SEC filer is the issuing BANK (Barclays Bank PLC here), which has its own
        # real filing history and SIC code unrelated to the note's actual structure. No usable
        # SIC/has_annual_report_filing signal exists for this case - same root cause as
        # utils/loaders/helpers.py::get_active_symbols(exclude_etfs=True), see that function's
        # 2026-08-20 comment for the live investigation. Name-based catch, verified against the
        # live active universe to match only GRN.
        where_clause = """
            WHERE sc.composite_score > 0
            AND ss.symbol NOT IN (SELECT symbol FROM etf_symbols)
            AND ss.symbol NOT IN (SELECT symbol FROM company_info_sec WHERE sic_code IN (6770, 6792, 6189))
            AND ss.symbol NOT IN (
                SELECT symbol FROM company_info_sec WHERE has_annual_report_filing = FALSE
            )
            AND NOT (
                ss.symbol IN (SELECT symbol FROM company_info_sec WHERE sic_code = 6221)
                AND ss.security_name ~* '(Gold|Silver|Platinum|Palladium|Bullion) Trust'
            )
            AND (ss.security_name IS NULL OR (
                ss.security_name !~* '(Rights?|Warrants?)$'
                AND ss.security_name NOT ILIKE '%%Acquisition Corp%%'
                AND ss.security_name !~* '(Subordinated Debentures?|First Mortgage Bonds?|Collateral Trust Mortgage Bonds?)'
                AND ss.security_name !~* '(ETNs?|Exchange[- ]Traded Notes?)'
            ))
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
            # Bulk queries: filter by data availability status computed by loader.
            # Loader marks data_unavailable=false for scores with 4+/6 metrics (sufficient diversity).
            # Loader marks data_unavailable=true for scores with <4/6 metrics or data_completeness < 70%.
            # API: Return all scores where loader marked available; dashboard filters on completeness %.
            # This gives traders full visibility: completeness % shown for all scores >= 50%.
            where_clause += " AND (sc.data_unavailable = false OR sc.data_unavailable IS NULL)"

        # MARKET-CAP ELIGIBILITY FLOOR (added 2026-08-31, /goal session - "make sure the
        # results make sense" investigation). This endpoint's default sort is composite_score
        # DESC with no investability screen of any kind - live-verified the top of that
        # ranking was dominated by nano/micro-caps (SOGP $37.6M mkt cap, COHN $19.6M, CPBI
        # $79.5M, several under $200K/day dollar volume), because Size was deliberately
        # retired as a scoring PILLAR (size_pillar_retired_entirely_20260828 in memory - not
        # being re-litigated here) with nothing left to offset small-cap-favoring percentile
        # scoring. A liquidity gate already exists for real trade EXECUTION
        # (algo/risk/liquidity_checks.py, min_adv_shares/min_adv_dollars config) but only
        # fires at Phase 8 entry time - invisible to anyone just browsing this "top stocks"
        # list, so untradeable names surface as if they were the best picks. Opt-in
        # (min_market_cap query param, no default) rather than a silent behavior change for
        # existing callers/tests - single-symbol lookups are deliberately exempt (you should
        # always be able to look up any specific symbol regardless of its size). Standard
        # index-provider practice (Russell/S&P/MSCI) applies exactly this kind of investability
        # screen separately from the factor scores themselves.
        market_cap_join = ""
        if min_market_cap is not None and not symbol:
            market_cap_join = "JOIN value_metrics mcf ON mcf.symbol = sc.symbol"
            where_clause += " AND mcf.market_cap >= %s"
            params_list.append(min_market_cap)

        # Real universe count (goal: dashboard/API were reporting "only ~1000 stocks
        # screened" - traced to `estimated_total` below being a page-size heuristic instead
        # of an actual count, compounded by this endpoint's limit being capped at 1000. The
        # true filtered universe is ~5000+ symbols (live-verified). Run against the same
        # where_clause/params_list as the page query, before LIMIT/OFFSET are appended to
        # params_list below, so this reflects the full filtered result set, not one page.
        count_query = f"""
            SELECT COUNT(*)
            FROM stock_scores sc
            JOIN stock_symbols ss ON ss.symbol = sc.symbol
            {market_cap_join}
            {where_clause}
        """
        cur.execute(count_query, params_list)
        real_total = cur.fetchone()[0]

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
                "consecutive_positive_quarters_unavailable_reason": d.get(
                    "consecutive_positive_quarters_unavailable_reason"
                ),
                "estimate_revision_direction": d.get("estimate_revision_direction"),
                "estimate_revision_direction_unavailable_reason": d.get(
                    "estimate_revision_direction_unavailable_reason"
                ),
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
                    if _derive_mom_12_1(d.get("momentum_12m_val"), d.get("momentum_1m_val")) is None
                    and _phist_days < 252
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
                "operating_income_growth_yoy_unavailable_reason": d.get(
                    "operating_income_growth_yoy_unavailable_reason"
                ),
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
                "forward_eps_growth_current_fy_unavailable_reason": d.get(
                    "forward_eps_growth_current_fy_unavailable_reason"
                ),
                "forward_eps_growth_next_fy": d.get("forward_eps_growth_next_fy"),
                "forward_eps_growth_next_fy_unavailable_reason": d.get("forward_eps_growth_next_fy_unavailable_reason"),
                "forward_revenue_growth_next_fy": d.get("forward_revenue_growth_next_fy"),
                "forward_revenue_growth_next_fy_unavailable_reason": d.get(
                    "forward_revenue_growth_next_fy_unavailable_reason"
                ),
                "eps_estimate_revision_90d_pct": d.get("eps_estimate_revision_90d_pct"),
                "eps_estimate_revision_90d_pct_unavailable_reason": d.get(
                    "eps_estimate_revision_90d_pct_unavailable_reason"
                ),
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
                "institutional_holders_count_unavailable_reason": d.get(
                    "institutional_holders_count_unavailable_reason"
                ),
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

        items: list[dict[str, Any]] = []
        prices_missing_count = 0
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
            _build_factor_inputs(d)

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
                d["_data_unavailable_reason"] = (
                    "current_price missing from price_daily - cannot calculate position risk"
                )

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
        # real_total comes from the COUNT(*) query above (same where_clause), not a
        # page-size estimate - see comment there for why the old estimate was wrong.
        estimated_total = real_total

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

        # TRANSPARENCY ENHANCEMENT (2026-08-05): Add data health metrics to summary
        # Shows traders overall data quality of the scores being returned
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
            "data_health": {
                "avg_completeness": round(avg_completeness, 2) if avg_completeness is not None else None,
                "meeting_trading_gate": f"{completeness_threshold_pct:.0f}%"
                if completeness_threshold_pct is not None
                else None,
                "note": "Completeness >= 70% passes trading entry gate; < 70% filtered per GOVERNANCE",
            },
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


def _get_incomplete_stocks(
    cur: cursor,
    limit: int,
    offset: int,
    sort_by: str = "data_completeness",
    sort_order: str = "asc",
) -> Any:
    """Get stocks with incomplete data (data_unavailable=True or data_completeness < 70%).

    Returns stocks that cannot be reliably scored due to missing data, with reason codes.
    Useful for understanding what data sources are still needed.
    """
    try:
        # Get count of incomplete stocks
        cur.execute("""
            SELECT COUNT(*)
            FROM stock_scores
            WHERE (data_unavailable = true OR data_completeness < 70)
        """)
        total_count = cur.fetchone()[0]

        # Sort by appropriate field. sort_order is interpolated below, so it must never
        # come from the raw query-param string - map it to a fixed SQL keyword first.
        sort_direction = "DESC" if sort_order == "desc" else "ASC"
        if sort_by == "symbol":
            sort_clause = f"ORDER BY symbol {sort_direction}"
        else:
            sort_clause = f"ORDER BY data_completeness {sort_direction}, symbol ASC"

        # Fetch incomplete stocks
        query = f"""
            SELECT
                symbol,
                composite_score,
                data_completeness,
                data_unavailable,
                reason,
                unavailable_metrics,
                updated_at
            FROM stock_scores
            WHERE (data_unavailable = true OR data_completeness < 70)
            {sort_clause}
            LIMIT %s OFFSET %s
        """

        rows = execute_with_timeout(cur, query, [limit, offset], timeout_sec=20, max_attempts=1)

        items = []
        for row in rows:
            d = dict(row)
            # Clean up unavailable_metrics for display
            if d.get("unavailable_metrics"):
                try:
                    if isinstance(d["unavailable_metrics"], str):
                        import json

                        d["unavailable_metrics"] = json.loads(d["unavailable_metrics"])
                except (TypeError, ValueError) as parse_err:
                    logger.warning(f"Could not parse unavailable_metrics, keeping raw value: {parse_err}")

            items.append(d)

        # Data freshness
        freshness = check_data_freshness(cur, "stock_scores", "updated_at", warning_days=1)

        result = {
            "items": items,
            "pagination": {
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "page": (offset // limit) + 1 if limit > 0 else 1,
                "totalPages": ((total_count - 1) // limit) + 1 if limit > 0 else 1,
            },
            "note": "Stocks with data_unavailable=true or completeness < 70%. These are SPACs, new listings, or stocks with insufficient SEC data.",
        }
        return json_response(200, result, data_freshness=freshness)

    except Exception as e:
        code, error_type, message = handle_db_error(e, "get incomplete stocks")
        return error_response(code, error_type, message)


# Root-cause buckets for /api/scores/coverage. Order is fixed (drives the fixed color
# assignment on the frontend) - every *_unavailable_reason value seen across the schema
# must resolve to exactly one of these via _categorize_reason(), falling back to
# "Other (errors / excluded)". Mirrors the categorization scripts/audit_unavailable_reasons.py
# output was manually bucketed into for the 2026-08-19 "Scores Data Coverage" report.
_COVERAGE_CATEGORY_RULES: list[tuple[str, set[str]]] = [
    (
        "Missing SEC/XBRL data",
        {
            "missing_sec_data",
            "missing_cash_flow_data",
            "no_revenue_reported",
            "total_debt_not_itemized",
            "interest_expense_not_itemized",
            "stockholders_equity_not_reported",
            "no_dividend_xbrl_concepts",
            "no_us_gaap_facts",
            "no_xbrl_filings",
            "cik_not_found",
            "depreciation_amortization_not_loaded",
            "ebitda_not_extracted",
            # FIXED 2026-08-19 (goal: "no SEC data" audit, same-day follow-up to the
            # bare_reason_tables extension above): reason strings from the newly-included
            # tables (sec_segment_info/metrics, sec_valuations, short_interest_finra) that
            # didn't exist in this map before because those tables were entirely invisible
            # to this report until now.
            "no_segment_dimension_contexts_in_xbrl_xml",
            "no_segment_revenue_in_xbrl_xml",
            "no_segment_disclosure",
            "no_computable_segment_metrics",
            "no_segment_data",
            "no_segment_count_facts_in_companyfacts",
            "income_statement_revenue_and_eps_null",
            "all_valuation_metrics_null",
            "no_income_statement",
            "finra_data_unavailable",
            # ADDED 2026-08-20 (goal session: coverage-categorization audit): these three
            # (load_sec_valuations.py, load_value_quality_growth_metrics.py) mean the
            # filer's own SEC filing section is incomplete/inconsistent (not merely
            # unset) - "the SEC data we have for this statement can't be trusted", the
            # same class as the other "Missing SEC/XBRL data" reasons above, not an
            # unexplained "Other" error. See load_sec_valuations.py's 2026-08-20
            # data_unavailable-filter fix for why these rows are excluded rather than fed
            # into ratios (113 live symbols were computing pe_ratio=1000+ from them before
            # that fix).
            "incomplete_sec_filing_income",
            "incomplete_sec_filing_balance",
            "incomplete_sec_filing_cashflow",
            # ADDED 2026-09-02 (goal session: SEC/XBRL missing-data sweep, financial-
            # statements post_run() flag-sync fix): same "the SEC data we have can't be
            # trusted/converted" class as incomplete_sec_filing_* above.
            # 'fpi_currency_data_rejected' is the new reason loaders/load_financial_
            # statements.py's post_run() now writes when it force-nulls a foreign private
            # issuer's stale home-currency values (see _reject_stale_fpi_currency_data).
            # 'raw_unconverted_currency_stale_value_20260829' is migration 1250's one-off
            # cleanup of the same bug class for BAK/BSAC/EDN/GGAL/HEPS/SUPV/TEO/TGS/TKC/TV -
            # both were falling through to "Other (errors / excluded)" for lack of a mapping.
            "fpi_currency_data_rejected",
            "raw_unconverted_currency_stale_value_20260829",
            # ADDED 2026-09-03 (same sweep, stranded-fix recovery): load_financial_statements.py's
            # _reject_stale_all_none_annual_row reason (Q1-mislabeled-as-annual force-null, e.g.
            # OFRM) - post_run()'s flag-sync previously hardcoded 'fpi_currency_data_rejected' for
            # every required-field force-null regardless of cause; now each rejection carries its
            # real reason (see that file's 2026-09-03 fix comment on _record_explicit_null_rejection).
            "no_usable_annual_duration_fact",
            # ADDED 2026-09-02 (same sweep): load_value_quality_growth_metrics.py's row-level
            # early-return reason when the symbol's annual_balance_sheet row itself is
            # unavailable/empty (see that file's ~line 4528) - was also unmapped, falling
            # through to "Other (errors / excluded)" for all 44 affected symbols across
            # every quality_metrics column derived from the balance sheet.
            "no_recent_balance_sheet_data_reported",
            # ADDED 2026-09-02 (same sweep): load_value_quality_growth_metrics.py's sibling
            # reason for fcf_yield/fcf_margin/fcf_to_net_income/free_cash_flow when the
            # symbol has no free cash flow reported across recent fiscal years (real OCF/
            # capex gap, not a computation error) - same unmapped-fallthrough bug as
            # no_recent_balance_sheet_data_reported above.
            "no_recent_free_cash_flow_reported",
            # ADDED 2026-09-02 (same sweep, ev_revenue/ps_ratio anchor-year trace): load_value_
            # quality_growth_metrics.py's reason when a symbol's SEC-selected anchor fiscal
            # year has no tagged revenue even though a real, nonzero revenue exists in an
            # earlier year (deliberately NOT computed from that stale figure - see
            # _get_revenue_absent_from_anchor_year_symbols()'s docstring) - same "the SEC data
            # we have can't be used for this specific period" class as the other reasons here.
            "revenue_absent_from_anchor_year",
            # ADDED 2026-09-02 (same sweep, quality_row_db anchor-year investigation):
            # net_income sibling of revenue_absent_from_anchor_year above - the balance-sheet
            # anchor fiscal year quality_row_db picks has no matching income-statement row,
            # even though the symbol has real net_income in a nearby fiscal year (live-
            # confirmed OBX/FTW/XLAB and 342 active-universe symbols total). Deliberately NOT
            # computed from the mismatched-year figure, same discipline as the revenue
            # sibling - see roe/roa/net_margin/sustainable_growth_rate's own reason blocks in
            # load_value_quality_growth_metrics.py.
            "net_income_absent_from_anchor_year",
            # ADDED 2026-09-02 (same sweep, quality_row_db anchor-year investigation):
            # operating_cash_flow/free_cash_flow siblings of net_income_absent_from_anchor_
            # year above - _get_no_recent_operating_cash_flow_symbols()/_get_no_recent_free_
            # cash_flow_symbols()'s own docstrings already documented this exact residual
            # ("the rest have OCF/FCF in an off-anchor year ... deliberately NOT fixed this
            # pass") but neither reason string existed until now. Affects
            # operating_cash_flow/free_cash_flow/accruals_ratio/fcf_to_net_income/
            # ocf_to_net_income_unavailable_reason in load_value_quality_growth_metrics.py.
            "operating_cash_flow_absent_from_anchor_year",
            "free_cash_flow_absent_from_anchor_year",
            # ADDED 2026-09-02 (same sweep, quality_row_db anchor-year investigation
            # follow-up): operating_income sibling of net_income/revenue/OCF/FCF's anchor-
            # year-mismatch reasons above - operating_margin/operating_profitability's
            # operating_income_for_margin only ever checked the anchor fiscal year (plus a
            # same-year EBIT approximation), never a different fiscal year, unlike its
            # net_income/revenue siblings. See
            # _get_operating_income_available_elsewhere_symbols()'s docstring in
            # load_value_quality_growth_metrics.py (39 active-universe symbols).
            "operating_income_absent_from_anchor_year",
            # ADDED 2026-09-02 (same sweep, static cross-check of every reason-string literal
            # in the SEC/XBRL loader files against this map - not just live DB counts, which
            # can't see a reason string that hasn't fired yet in the current data): 7 more
            # genuinely unmapped "the SEC data isn't there" facts found this way.
            # no_recent_operating_cash_flow_reported: sibling of no_recent_free_cash_flow_
            # reported above (both from load_value_quality_growth_metrics.py's OCF/FCF
            # windowed gates) - only the FCF one was ever added.
            "no_recent_operating_cash_flow_reported",
            # ADDED 2026-09-02 (static sweep continuation, quality_row_db anchor-year
            # investigation follow-up): total_cash/cash_per_share/ebitda_unavailable_reason's
            # own "sec_valuations has no row at all for this symbol" fact (see
            # load_value_quality_growth_metrics.py's ~line 6303/6316/6341, commits 1547b826c/
            # 37fc38252) - same "the SEC data we have can't be used" class as the other reasons
            # here. Never mapped despite landing 2026-09-02 08:20 CDT; caught by a full static
            # grep of every reason-string literal actually assigned in the loader's
            # `_unavailable_reason` ternary blocks vs this list, not live DB counts (which
            # currently show 0 live rows for this exact string - sec_valuations coverage may
            # have since improved for the originally-affected symbols - but the string is real,
            # reachable code, and must still resolve to a real category when it does fire).
            "no_sec_valuations_row",
            # ADDED 2026-09-02 (same sweep, restricted to load_sec_valuations.py):
            # invalid_shares_outstanding - _compute_valuations()'s final "no valid
            # shares_outstanding from any SEC/DEI-derived tier" fact (all upstream tiers
            # - reported_shares_outstanding, DEI dei:EntityCommonStockSharesOutstanding,
            # dual-class/FPI fallbacks, etc. - come up empty, ~line 2143). Reachable via the
            # main _compute_valuations() call site (line 1447), currently 0 live rows (data
            # happens to be clean right now) but a real unmapped string that would silently
            # fall to "Other" the moment it next fires. NOTE: its sibling "invalid_price"
            # (~line 2135, current_price <= 0) is deliberately NOT added here - that one is a
            # price_daily/prices-table gap, not a SEC/XBRL fact, so it correctly belongs in
            # "Other (errors / excluded)" below, same reasoning as stale_price_data there.
            "invalid_shares_outstanding",
            # entity_name_not_found/submissions_not_found_404/submissions_empty/
            # no_submissions: load_company_info_sec.py/load_earnings_calendar_sec.py/
            # load_current_reports_8k.py's own "SEC submissions.json has nothing for this
            # symbol/CIK" facts - same class as cik_not_found already above.
            "entity_name_not_found",
            "submissions_not_found_404",
            "submissions_empty",
            "no_submissions",
            # stockholders_equity_never_tagged_in_filings/total_liabilities_not_reported:
            # pb_ratio/debt_to_assets's own "never tagged this concept, full history" gates in
            # load_value_quality_growth_metrics.py - same class as stockholders_equity_not_
            # reported/total_debt_not_itemized already above.
            "stockholders_equity_never_tagged_in_filings",
            "total_liabilities_not_reported",
            # filings_key_missing/recent_filings_key_missing: load_earnings_calendar_sec.py's
            # sibling to submissions_not_found_404/submissions_empty above - SEC submissions
            # response came back but was missing the expected "filings" key structure.
            "filings_key_missing",
            "recent_filings_key_missing",
            # sec_form345_bulk_data_unavailable: load_insider_transaction_velocity.py's SEC
            # Form 3/4/5 bulk-data feed absence, same class as no_form345_filings_in_lookback_
            # window in "Ownership data unresolved" below but for the bulk-feed-itself-down
            # case rather than a per-symbol lookback gap.
            "sec_form345_bulk_data_unavailable",
            # ADDED 2026-09-02 (SEC/XBRL missing-data sweep): utils/external/sec_form345_
            # transaction_velocity_cached.py's CachedForm345Aggregator.get_velocity_metrics
            # writes this directly (bypassing load_insider_transaction_velocity.py's own
            # except-TimeoutError handler, which produces sec_form345_bulk_data_unavailable
            # above) when the caller's own wait_for_download blocks past timeout_seconds
            # (1080s) waiting on the shared background Form 3/4/5 bulk download - same "the
            # SEC bulk feed didn't come back in time" fact, just a different code path to the
            # same outcome. Still live-firing today (17 rows, most recent within the last
            # day), not stale debris - was falling through to "Other (errors / excluded)".
            "Form345_download_timeout",
            # filing_date_unavailable/segment_data_unavailable: load_sec_segment_info.py/
            # load_sec_segment_metrics.py's own "SEC segment XBRL data isn't there" facts,
            # same class as the other segment-data reasons already above. These two tables
            # are display-only/unscored (_UNSCORED_TABLES) but the coverage report still
            # categorizes their reasons, so they should read honestly too.
            "filing_date_unavailable",
            "segment_data_unavailable",
            # ADDED 2026-09-02 (same sweep): loaders/helpers/sec_base.py writes this when a
            # full unfiltered SEC refetch no longer reproduces a fiscal year the DB
            # currently marks available - that year's data is retracted/no longer backed by
            # any live SEC filing, the same "SEC data we have can't be trusted" class as
            # incomplete_sec_filing_* above. Was unmapped (73 live rows,
            # quarterly_income_statement.reason).
            "stale_fiscal_year_not_confirmed_by_full_sec_refetch",
            # ADDED 2026-08-20: earnings_calendar_sec's genuine "no SEC filings exist for
            # this symbol" case (the old false-positive version of this reason - foreign
            # private issuers filing 20-F/6-K instead of 10-K/10-Q - was already fixed
            # 2026-08-19 by widening _EARNINGS_BEARING_FORMS; what remains is real absence).
            "no_sec_filings_found",
            # ADDED 2026-08-29 (goal session: coverage-categorization sweep):
            # load_company_info_sec.py's shares_outstanding_unavailable_reason - the
            # symbol's CIK/annual-report lookup never turned up any SEC 10-K/10-K-equivalent
            # filing at all, so shares_outstanding was never extractable. Was unmapped
            # (150 live rows).
            "no_annual_report_filing",
            # ADDED 2026-08-29 (same sweep): load_company_info_sec.py's third
            # shares_outstanding_unavailable_reason bucket - a real annual filing exists but
            # shares_outstanding wasn't tagged in its XBRL AND the raw-filing-text fallback
            # extraction also came up empty. Was unmapped (48 live rows).
            "shares_outstanding_not_in_xbrl_or_filing_text",
            # ADDED 2026-08-22 (goal session: "Top Causes of Missing Data" Other-bucket
            # sweep): load_positioning_metrics.py's per-field marker for "no FINRA
            # short-interest row on file for this symbol at all" (as opposed to
            # short_interest_finra.reason's table-level "finra_data_unavailable"/
            # "finra_data_unavailable" fed row - same underlying fact, just written by a
            # different loader onto a different table/column). Was sitting in "Other
            # (errors / excluded)" even though it's the identical "the FINRA feed simply
            # doesn't cover this issue" absence as finra_data_unavailable two lines above,
            # not an error - 585 of 712 live "Other" rows (82%) were this single reason,
            # making the "how much is a genuine unexplained error" signal in that bucket
            # far noisier than the real number.
            "missing_finra_data",
            # ADDED 2026-08-20: utils/external/sec_xbrl_segments.py - the SEC companyfacts
            # API structurally never returns per-segment revenue at all (a permanent API
            # limitation, not a per-filer gap); kept here rather than "Legitimate / not
            # applicable" because it's the same "the SEC data isn't there" class as the
            # other segment-data reasons already in this bucket
            # (no_segment_revenue_in_xbrl_xml etc.), just a different root cause.
            "companyfacts_api_never_exposes_per_segment_revenue",
            # ADDED 2026-08-20 (goal session: unmapped-reason sweep, cross-checked every live
            # *_unavailable_reason value in the schema against this map): dividend_data's
            # equivalent of no_us_gaap_facts/no_xbrl_filings - the companyfacts response has no
            # "facts" key at all - was silently falling through to "Other (errors / excluded)"
            # for 11 live rows because nothing in this map matched it.
            "no_companyfacts",
            # ADDED 2026-08-20 (goal session: missing-data root-cause audit): utils/external/
            # sec_xbrl_segments.py's extraction returns this when every tagged segment's revenue
            # is negative (ASC 280 elimination/reconciling lines, excluded by design - see that
            # function's own comment) or the reportable total is exactly 0 - the segment XBRL
            # facts exist but aren't usable, same "SEC data we have can't be trusted" class as
            # the other segment-data reasons already here. Was unmapped and falling through to
            # "Other (errors / excluded)" (19 live rows, sec_segment_info.reason).
            "zero_total_segment_revenue",
            # ADDED 2026-08-21 (goal session: "is missing data really missing" audit):
            # load_company_profile.py's company_profile.reason - "no_sic_code_available"
            # means company_info_sec never resolved a SIC code for this symbol at all;
            # "sic_code_unmapped" (base of the dynamic "sic_code_unmapped:XXXX" reason,
            # matched via `base in keys` in _categorize_reason) means SEC assigned a real
            # SIC code but it has no SIC_TO_GICS mapping/division fallback yet - both are
            # "the SEC classification data isn't there/usable" facts, same class as the
            # other Missing SEC/XBRL reasons. Were unmapped and falling through to "Other
            # (errors / excluded)" (146 live rows combined).
            "no_sic_code_available",
            "sic_code_unmapped",
            # ADDED 2026-08-21 (same session): orphaned reason string with zero remaining
            # code references (grepped repo-wide) - written directly to the DB by a
            # one-off remediation script during the 2026-08-19 currency-conversion fixes
            # (see MEMORY.md's cny_currency_conversion / dividend_loader entries) that
            # NULLed out revenue/net_income poisoned by the pre-fix wrong-currency bug for
            # ~15-30 FPI symbols per statement table (TV, TKC, KSPI, IBN, KT, and other
            # ARS/TRY/KZT/INR/KRW filers), pending a real re-fetch to repopulate them.
            # Downstream value_metrics/quality_metrics already handle this safely (verified
            # live: no garbage ratios, correct NULL propagation with their own sensible
            # reasons), so this is inert bookkeeping debris, not an active bug - but it
            # represents a real "SEC data not currently available" fact and was falling
            # through to "Other (errors / excluded)" (61 live rows) for lack of a mapping.
            "currency_conversion_bug_remediation_20260819",
            # ADDED 2026-09-02 (goal session: "keep the missing-data number going down" SEC/
            # XBRL sweep, cross-checking today's own earlier fixes in this same session
            # against this map): load_value_quality_growth_metrics.py wired these four
            # "never tagged in any recent filing" gates (net_income_not_reported,
            # no_recent_total_assets_reported, eps_never_tagged_in_filings,
            # capex_never_tagged_in_recent_filings - see roe/roa/net_margin/sustainable_
            # growth_rate/asset_turnover/pe_ratio/peg_ratio/fcf_yield's own reason blocks)
            # earlier today to split a real "SEC never tagged this concept for this filer"
            # fact out of the generic missing_sec_data bucket, the same class as
            # total_debt_not_itemized/interest_expense_not_itemized/stockholders_equity_
            # not_reported already above - but none of the four were ever added here, so
            # all 286 live rows using them fell straight through to "Other (errors /
            # excluded)" instead, undoing the whole point of giving them an honest label.
            "net_income_not_reported",
            "no_recent_total_assets_reported",
            "eps_never_tagged_in_filings",
            "capex_never_tagged_in_recent_filings",
            # MOVED 2026-09-02 (SEC/XBRL missing-data sweep, live audit of the "Other" bucket):
            # "symbol_not_found" was sitting in "Other (errors / excluded)" as a bare set
            # literal with no explanation. Repo-wide grep of every write site (only two:
            # load_sec_segment_info.py's _handle_symbol_not_found and
            # load_current_reports_8k.py's CIK-lookup branch) shows both mean exactly
            # "self.sec_client.symbol_to_cik(symbol)"/"_get_cik(symbol)" found no SEC CIK for
            # this symbol - the identical fact "cik_not_found" already captures above, just a
            # different literal from two specific loaders. Not a processing error; a real SEC/
            # XBRL data gap. Was mislabeled as an unexplained "Other" error (53 live
            # sec_segment_info rows + 17 live current_reports_8k rows).
            "symbol_not_found",
        },
    ),
    (
        "Insufficient history",
        {
            "insufficient_history",
            "insufficient_quarterly_history",
            "insufficient_prior_year_data",
            "insufficient_quarterly_data",
            "insufficient_eps_data",
            "insufficient_eps_growth_datapoints",
            "insufficient_revenue_data",
            "insufficient_price_history",
            "insufficient_quarterly_eps_history",
            # ADDED 2026-08-20 (goal session: missing-data root-cause audit): loaders/
            # technical_indicators.py's compute_ad_rating() returns None (which
            # load_positioning_metrics.py then labels "ad_calculation_failed", despite the name
            # sounding like an error) only when len(close) < 20 or the recent window is all-NaN -
            # not a calculation bug, the same "not enough price history yet" fact as
            # "insufficient_price_history" right above (both come from
            # positioning_metrics.ad_rating_unavailable_reason). Was unmapped and falling through
            # to "Other (errors / excluded)" (11 live rows).
            "ad_calculation_failed",
            # ADDED 2026-08-21 (goal session: beta_unavailable_reason genericization fix,
            # loaders/load_risk_metrics_daily.py's _get_beta_from_db): the stock/benchmark
            # price series didn't have enough overlapping history yet to compute a
            # covariance-based beta - same "not enough history yet" class as
            # insufficient_price_history, just three different checkpoints along that
            # computation (SPY's own series, the aligned overlap, the resulting return
            # count) rather than one. See that function's docstring for the full set of
            # beta failure reasons - extreme_beta below is the one that ISN'T this class.
            "spy_price_data_insufficient",
            "insufficient_common_dates",
            "insufficient_returns",
            # ADDED 2026-09-03 (SEC/XBRL missing-data sweep, synchronous static sweep):
            # loaders/load_risk_metrics_daily.py's sibling beta-computation gate to the three
            # above - SPY's own aligned-window return variance came back exactly 0 (a
            # degenerate covariance denominator, distinct from extreme_beta below which fires
            # AFTER a beta value was successfully computed). Same "beta couldn't be computed
            # at all from this window" class as spy_price_data_insufficient/
            # insufficient_common_dates/insufficient_returns, not extreme_beta's "computed but
            # implausible" class. Was unmapped, falling through to "Other (errors / excluded)".
            "spy_variance_zero",
            # ADDED 2026-08-29 (goal session: coverage-categorization sweep, live audit of
            # the "Other (errors / excluded)" bucket via lambda/api/routes/scores.py's own
            # _get_scores_coverage output): load_value_quality_growth_metrics.py's
            # quality_score_unavailable_reason - available_quality_weight cleared 0 but
            # missed the min_quality_weight_pct completeness floor (thin-sample
            # extrapolation, not honest data) - same "not enough underlying data to trust a
            # computed value" class as the other reasons in this bucket, just phrased around
            # "completeness" instead of "history". Was unmapped (179 live rows).
            "insufficient_completeness",
            # ADDED 2026-09-02 (same sweep, static cross-check): earnings_growth_4q_avg/
            # eps_growth_stability/quarterly_growth_momentum's own "found fewer than 8
            # quarters of history with a same-quarter-prior-year match" case
            # (load_value_quality_growth_metrics.py) - same "not enough history yet" class as
            # insufficient_quarterly_history two lines above, just a more precise label for
            # the year-over-year-matching sub-case.
            "insufficient_year_over_year_quarterly_history",
        },
    ),
    (
        "No analyst coverage",
        {
            "no_analyst_coverage",
            "no_analyst_estimates",
            "analyst_estimates_not_in_sec_filings",
            # ADDED 2026-08-20: load_earnings_calendar.py's equivalent of "no coverage" -
            # same underlying fact (nobody publishes forward estimates/dates for this
            # symbol), just for the earnings-calendar table instead of analyst_* tables.
            "no_earnings_coverage",
            "no_next_earnings_available",
            # ADDED 2026-08-31 (goal session: reason-code accuracy sweep): distinct from
            # "no_analyst_estimates" - the symbol HAS real, current analyst coverage
            # (a real analyst_earnings_estimates row), just not this one specific derived
            # forward-growth/estimate-revision figure. See
            # ValueQualityGrowthMetricsLoader._get_analyst_forward_growth_estimates's own
            # docstring for the live evidence (AFRM/DB/VOD/NWG/WELL/L). Still fundamentally an
            # analyst-coverage gap, same bucket, more precise label.
            "analyst_coverage_incomplete_for_field",
        },
    ),
    ("Stale fiscal data", {"stale_fiscal_data"}),
    (
        "Ownership data unresolved",
        {
            "no_resolved_13f_holdings",
            # ADDED 2026-09-02 (same sweep, static grep of load_institutional_holdings_13f.py):
            # fetch_incremental()'s own "no row (or a row with institutional_ownership_pct
            # still NULL) found in institutional_holdings_13f for this symbol" fallback marker
            # (~line 316/360) - same "no 13F coverage" fact as no_resolved_13f_holdings above,
            # just written from the per-symbol incremental lookup path instead of the bulk
            # fetch_global() batch writer. Currently 0 live rows (fetch_global appears to be
            # the path that actually runs in production) but real, reachable code.
            "not_found_in_institutional_holdings_13f",
            "institutional_data_not_available",
            "shares_outstanding_unavailable",
            "shares_outstanding_unavailable_for_pct_calc",
            "no_form345_filings_in_lookback_window",
            "no_insider_transactions_in_lookback",
        },
    ),
    (
        "Implausible / rejected value",
        {
            "implausible_ratio",
            "shares_outstanding_invalid",
            # ADDED 2026-08-20: load_sec_valuations.py's market_cap sanity check (>10x vs
            # yfinance) rejects a mis-scaled shares_outstanding the same way
            # "shares_outstanding_invalid" does - this reason string existed in the loader
            # (and load_short_interest_finra.py excludes symbols carrying it, per its
            # 2026-08-20 fix) but was never wired in here, so every affected row fell
            # through to "Other (errors / excluded)" instead of this bucket.
            "shares_outstanding_scale_mismatch",
            # ADDED 2026-08-20 (goal session: unmapped-reason sweep): both confirmed via
            # loaders/load_value_quality_growth_metrics.py as genuine sanity-check rejections,
            # not errors - were silently falling through to "Other (errors / excluded)" for 15
            # live rows combined because nothing in this map matched them.
            # - implausible_dcf_result: the 2-stage FCFE DCF model produced a per-share value
            #   outside MAX_INTRINSIC_VALUE_PER_SHARE bounds (only reached when fcf_yield > 0 -
            #   the fcf_yield <= 0 case correctly returns negative_free_cash_flow instead, see
            #   intrinsic_value_reason_from_fcf_yield's own docstring/history).
            # - garbage_metric_value_implausible_growth_rate: an EPS/earnings growth rate whose
            #   magnitude exceeds MAX_PLAUSIBLE_GROWTH_PCT (2000%, tightened 2026-08-28 from the
            #   original MAX_TREND_PERCENTAGE_POINTS/100000% bound) - a near-zero denominator
            #   artifact, not a real growth rate, rejected the same way implausible_ratio is.
            #   RENAMED 2026-08-31 from "garbage_metric_value_abs_gt_100000" - that string had
            #   gone stale ever since the 2026-08-28 tightening (it still named the OLD 100000%
            #   bound while every site setting it had already switched to the 2000% one).
            "implausible_dcf_result",
            "garbage_metric_value_implausible_growth_rate",
            # ADDED 2026-09-02 (SEC/XBRL missing-data sweep): sibling of
            # garbage_metric_value_implausible_growth_rate above for non-growth-rate fields
            # (forward_eps_growth_current_fy and others, load_value_quality_growth_metrics.py)
            # - same implausible-value rejection, just missing from this set.
            "garbage_metric_value_implausible_ratio",
            # ADDED 2026-08-20 (goal session: missing-data root-cause audit): load_sec_valuations.py's
            # _sanity_check_pe_ratio (>10x vs yfinance) rejects a mis-scaled ttm_eps the same way
            # _sanity_check_market_cap rejects a mis-scaled shares_outstanding just above - same
            # per-filing XBRL scale-bug class, just a different concept. Was unmapped and falling
            # through to "Other (errors / excluded)" (35 live rows, sec_valuations.reason).
            "eps_scale_mismatch",
            # ADDED 2026-08-21 (goal session: beta_unavailable_reason genericization fix):
            # loaders/load_risk_metrics_daily.py's _get_beta_from_db rejects a computed
            # |beta| > 10 as a numerically degenerate regression result (near-zero SPY
            # variance denominator, not a real risk figure) - same class as implausible_ratio.
            "extreme_beta",
            # ADDED 2026-09-02 (same sweep, static cross-check): load_value_quality_growth_
            # metrics.py's forward_pe_reason - a real forward EPS estimate is on file, but the
            # resulting forward_pe fell below MIN_PLAUSIBLE_FORWARD_PE_RATIO (a near-zero-EPS
            # artifact, not a real valuation), rejected the same way implausible_ratio/
            # extreme_beta are rather than persisting a single extreme outlier value.
            "implausibly_low_forward_pe",
        },
    ),
    (
        "Other (errors / excluded)",
        {
            "fetch_error:ValueError",
            "fetch_error:RuntimeError",
            "data_unavailable_during_load",
            "unable to fetch after retries",
            "no_historical_data",
            "fed_rate_fetcher_not_implemented",
            "no_data_returned",
            "no_price_data_after_validation",
            "historical_date_enrichment_only_for_latest",
            "missing_price_data",
            "excluded_by_naming_pattern",
            "no_recent_price",
            # ADDED 2026-09-02 (SEC/XBRL missing-data sweep, live audit_unavailable_reasons.py
            # cross-check): loaders/load_risk_metrics_daily.py writes this literal (see the
            # STALE_PRICE FIX 2026-09-01 comment at its write site, ~line 411) onto
            # stability_metrics' beta/volatility/downside_volatility/max_drawdown_1y columns
            # when the symbol's price_daily feed has stopped updating (last close older than
            # STALE_PRICE_TRADING_DAYS_THRESHOLD) - deliberately not computing risk figures
            # from a frozen window. This isn't a SEC/XBRL gap (price_daily/yfinance is a
            # different data source entirely) and it isn't "missing" so much as "known-broken
            # for this symbol right now" - the same operational-error class as
            # no_recent_price/missing_price_data already in this bucket, just for a stopped
            # feed instead of an absent one. Was unmapped and falling through to the same
            # bucket anyway via the default, but silently (240 live rows, 30 symbols x 8
            # stability_metrics columns) - making it explicit here documents the fact instead
            # of leaving it looking like an unaccounted-for error.
            "stale_price_data",
            # ADDED 2026-09-02 (same sweep): load_sec_valuations.py's _compute_valuations()
            # current_price <= 0 gate (~line 2135) - sibling of no_recent_price/
            # missing_price_data already in this bucket. Deliberately NOT "Missing SEC/XBRL
            # data": current_price here is read from the prices table, a different data
            # source entirely, same reasoning as stale_price_data above. Currently 0 live
            # rows but reachable from the main _compute_valuations() call site.
            "invalid_price",
        },
    ),
    (
        "Legitimate / not applicable",
        {
            "non_dividend_paying_stock",
            "unprofitable_stock",
            # ADDED 2026-09-02 (SEC/XBRL missing-data sweep, load_value_quality_growth_
            # metrics.py commits 7cfb8e7ae/e29d475a1): same "the ratio is mathematically
            # undefined for real business reasons, not a data gap" class as
            # unprofitable_stock two lines above. negative_enterprise_value = a genuine
            # net-cash-rich filer (total_cash alone exceeds market_cap + total_debt), so
            # EV/EBITDA and EV/Revenue have no meaningful denominator relationship;
            # zero_revenue_reported_this_period = a real $0.00 anchor-year revenue (e.g. a
            # wind-down period), so EV/Revenue and P/S are undefined for that period
            # regardless of other years' history. Both would otherwise fall through to
            # "Other (errors / excluded)" via _categorize_reason's default, undoing the
            # point of giving them an honest label in the first place.
            "negative_enterprise_value",
            "zero_revenue_reported_this_period",
            # ADDED 2026-08-29 (goal session: signal_quality_scores bare_reason_tables
            # addition): the backfill marker [[signal_quality_scores_historical_reason_backfill_20260829]]
            # applied to 53,567 pre-2026-08-29 rows that predate this table's reason-tracking
            # entirely - a known historical gap already closed, not an ongoing/actionable one.
            "historical_row_predates_reason_tracking",
            # ADDED 2026-08-22 (goal session: "No analyst coverage" bucket audit):
            # load_value_quality_growth_metrics.py's forward-looking analogue of
            # unprofitable_stock two lines above - a real analyst forward-EPS estimate is on
            # file, it's just negative (the company is projected to lose money next year), so
            # forward_pe is undefined the same way trailing pe_ratio is for a current loss.
            # Was sharing "no_analyst_estimates" with genuine zero-coverage symbols - see that
            # loader's own comment on forward_pe_reason for the live-confirmed scope (848 of
            # 1,560 rows, including real large-caps like MRNA/RBLX/RIVN/RKLB/WBD/BNTX).
            "negative_forward_eps",
            "reit_special_entity",
            "negative_free_cash_flow",
            "negative_book_value",
            "negative_earnings_growth",
            "negative_invested_capital",
            "growth_undefined_sign_change",
            # ADDED 2026-08-29 (goal session: coverage-categorization sweep): _growth_reason()
            # in load_value_quality_growth_metrics.py's two siblings to
            # growth_undefined_sign_change directly above, from the exact same function - a
            # growth rate that's mathematically undefined (not merely unmeasured) because a
            # stock split/reverse-split changed the share count between the two comparison
            # points (growth_undefined_share_count_discontinuity, 2,044 live rows) or because
            # the prior-year base value was too close to zero for a percentage to be
            # meaningful (immaterial_prior_year_base, 1,275 live rows). Both were unmapped and
            # falling through to "Other (errors / excluded)" - together with the sign-change
            # case already here, these three cover every _growth_reason() branch.
            "growth_undefined_share_count_discontinuity",
            "immaterial_prior_year_base",
            # ADDED 2026-08-29 (same sweep): roce_pct's own negative-denominator undefined
            # case (load_value_quality_growth_metrics.py) - capital_employed <= 0, same
            # "the ratio is mathematically undefined for this company's balance sheet" class
            # as negative_invested_capital/negative_book_value directly above, just for ROCE
            # instead of ROIC/P-B. Was unmapped (183 live rows).
            "negative_capital_employed",
            # ADDED 2026-08-29 (same sweep): load_company_info_sec.py's shares_outstanding_
            # unavailable_reason for foreign private issuers - domestic shares_outstanding is
            # structurally inapplicable/excluded for FPIs by design, same permanent-exemption
            # class as foreign_private_issuer_shares_unavailable below (a different loader's
            # string for the same underlying FPI fact). Was unmapped (1,035 live rows - the
            # single largest unmapped reason found this sweep).
            "fpi_shares_excluded_domestic_only",
            # ADDED 2026-08-19 (goal session continuation): foreign private issuers are
            # exempt from mandatory 10-Q quarterly SEC reporting - a permanent regulatory
            # fact, not a data gap that more loader coverage could ever close. See
            # load_value_quality_growth_metrics.py's _compute_quarterly_metrics for the
            # live-confirmed CHKP/FVRR case this distinguishes from genuine
            # "insufficient_quarterly_history".
            "foreign_private_issuer_no_quarterly_filings",
            # ADDED 2026-08-19 (same session): foreign private issuers structurally never
            # file Form 8-K (they use 6-K instead) - same permanent-exemption distinction as
            # above, for current_reports_8k. See load_current_reports_8k.py.
            "foreign_private_issuer_no_8k_filings",
            # ADDED 2026-08-19 (same session, live-caught after backfilling): a PRE-EXISTING
            # reason string (load_insider_holdings_sec.py/load_insider_transaction_velocity.py,
            # predates this session) was never wired into this categorization at all - every
            # symbol using it fell through to "Other (errors / excluded)" instead of this
            # bucket. Live-confirmed: backfilling those two loaders' already-correct FPI
            # distinction relabeled 1,052 symbols to this reason, and "Other" visibly jumped
            # by exactly that amount on the live dashboard before this fix - the same
            # permanent-exemption fact as the two reasons above, just for Form 3/4/5 insider
            # filings (foreign private issuers are exempt from Section 16 reporting).
            "foreign_private_issuer_exempt",
            # ADDED 2026-08-20: same permanent-exemption class as the reasons above, for
            # short_interest_finra's short_pct computation - FPIs have no shares_outstanding
            # source that isn't in home-market (non-ADS) units, so short_pct is structurally
            # uncomputable, not a data gap. See load_short_interest_finra.py's max_fail_rate
            # comment (root-caused by load_sec_valuations.py's 2026-08-19 FPI unit-mismatch fix,
            # commit a123cdb46).
            "foreign_private_issuer_shares_unavailable",
            # ADDED 2026-08-19 (same session, industry-specific nuance pass): registered
            # investment companies (closed-end funds - the BlackRock BBN/BCAT/BGT/BIT/BKT-class
            # trusts and similar) file under SEC's "cef"/"ffd" XBRL taxonomies instead of
            # standard 10-K us-gaap/ifrs-full - live-confirmed those taxonomies contain zero
            # dividend/distribution concepts (N-2 prospectus fee-table data only), a permanent
            # structural absence, not a loader gap. See load_dividend_data.py's fetch_incremental.
            "registered_investment_company_no_xbrl",
            # ADDED 2026-08-21 (goal session: missing-data root-cause audit, "Other" bucket
            # sweep): load_current_reports_8k.py writes this when a symbol's SEC submissions
            # feed genuinely contains zero 8-Ks (8-Ks are event-driven - executive changes,
            # M&A, material agreements - not periodic, so most quiet filers legitimately have
            # none in any given window; see that loader's own comment on this exact reason for
            # why it's distinguished from the FPI-exemption case, foreign_private_issuer_no_8k_filings,
            # already above). Not an error or a gap more loader coverage could close - was the
            # single largest contributor to "Other (errors / excluded)" (1,092 of 2,017 live
            # rows, >50%), silently making the "which loaders need fixing" report itself look
            # far noisier than the real gap.
            "no_8k_filings_in_recent_submissions",
        },
    ),
]
_COVERAGE_CATEGORY_ORDER = [name for name, _ in _COVERAGE_CATEGORY_RULES]

# ADDED 2026-09-02 (goal session: "is this report classifying things right, especially
# valuation stuff"). This report's whole framing - the tab's own name, its tagline, the
# "Real Gap Instances" KPI - is "which SCORING factors are missing data". But a fair number
# of tracked *_unavailable_reason columns belong to fields loaders/load_stock_scores.py's
# live _score_value/_score_growth/_score_risk formulas do NOT read at all - they're kept
# computed/stored for the Deep Value page or historical/display purposes only (see each
# field's own "computed-but-unscored"/"REMOVED FROM SCORING" comment in that file). A
# 100%-missing ev_ebitda row was showing with the exact same visual weight as a
# 100%-missing pe_ratio row even though only pe_ratio can ever move stock_scores -
# live-confirmed via a fresh read of every current _score_* function body (not memory/
# docstrings, which the codebase's own fama_macbeth_composite_weights_stale_vs_live_pillar_
# formulas finding warns can drift from what's actually live). Deliberately keyed by
# (table, factor_name) rather than factor_name alone - a couple of these names could in
# principle collide with an unrelated, actually-scored field on a different table.
#
# Quality is NOT represented here: _score_quality reads only the single pre-computed
# quality_score field, but every quality_metrics per-field column (roe, roa,
# gross_profitability, ...) is a genuine upstream INPUT to that same quality_score,
# computed one stage earlier by load_value_quality_growth_metrics.py - a different pipeline
# stage, not a dead end - so none of those belong in this "has zero path to any score" set.
# Momentum has no entry either: none of its scored (momentum_3m, mom_12_1, rsi_14, macd,
# price_vs_sma_50/200) or unscored (momentum_6m) fields have their own tracked
# *_unavailable_reason column in this report at all (momentum_metrics only exposes a
# single bare `reason` column, and it isn't in `bare_reason_tables` below), so there's
# nothing to tag on that pillar.
#
# Positioning is handled as a whole TABLE, not a per-field set below (_UNSCORED_TABLES):
# _score_positioning was fully retired 2026-08-27 (Positioning pillar removed entirely -
# no method body remains in load_stock_scores.py, only a comment documenting the removal
# and the evidence trail) - every positioning_metrics/short_interest_finra field (A/D
# rating, institutional ownership, short interest and its % change) is display-only now
# (surfaced via the scores API's informational positioning_inputs field), not just a
# specific subset the way Value/Growth/Risk have a mix of scored and unscored fields.
#
# ADDED 2026-09-02 (goal session: SEC/XBRL missing-data sweep): sec_segment_info/
# sec_segment_metrics are ALSO a whole-table display-only case - grepped repo-wide across
# every scoring loader (load_value_quality_growth_metrics.py, load_enhanced_quality_
# growth_metrics.py, algo/scoring/, algo/orchestrator/phase7*) and found zero references;
# the only consumers are lambda/api/routes/market.py and financials.py (both informational
# display endpoints) plus this file's own coverage report. Segment revenue/count data has
# no path to any pillar score, same as Positioning - it just never got a whole-table entry
# here because the 317f7b60c/5c74a48e8 unscored-factor passes were scoped to fields that
# WERE recently scored and got retired, not tables that were never scored at all. These two
# tables alone account for 494 no_segment_dimension_contexts_in_xbrl_xml + 345
# no_segment_revenue_in_xbrl_xml (839 raw rows, scripts/audit_unavailable_reasons.py) that
# were inflating the "Missing SEC/XBRL data" headline for gaps that can never move a score.
_UNSCORED_TABLES: set[str] = {"positioning_metrics", "short_interest_finra", "sec_segment_info", "sec_segment_metrics"}

_UNSCORED_FACTORS: set[tuple[str, str]] = {
    # Value: _score_value's live formula is pe_ratio(27%) + pb_ratio(27%) + ps_ratio(27%)
    # + forward_pe(9%) + dividend_yield(10%) only - these six are computed/stored (Deep
    # Value page, PEG/margin-of-safety screens) but excluded from scoring entirely.
    ("value_metrics", "peg_ratio"),
    ("value_metrics", "ev_ebitda"),
    ("value_metrics", "ev_revenue"),
    ("value_metrics", "margin_of_safety"),
    ("value_metrics", "intrinsic_value"),
    ("value_metrics", "net_payout_yield"),
    ("value_metrics", "fcf_yield"),
    # market_cap: was the Size pillar's sole input, but _score_size/_score_positioning were
    # fully retired 2026-08-28/29 (no method body remains anywhere in load_stock_scores.py) -
    # market_cap itself stayed computed/stored (that file's own line ~3014 comment: "market_cap
    # is not scored anywhere"), just with nothing left to score it into.
    ("value_metrics", "market_cap"),
    # held_percent_institutions: zero references anywhere in load_stock_scores.py (verified via
    # repo-wide grep) - display-only (StockDetail.jsx / financials.py), never fed into any
    # pillar formula.
    ("value_metrics", "held_percent_institutions"),
    # Growth: _score_growth equal-weights the 12 GROWTH_SCORE_FIELDS; these 12 are computed
    # trend/YoY siblings explicitly removed from that field list (still shown on the scores
    # page as info rows per this repo's own "convert removed UI fields to info rows"
    # convention).
    ("growth_metrics", "book_value_growth"),
    ("growth_metrics", "net_income_growth_yoy"),
    ("growth_metrics", "operating_income_growth_yoy"),
    ("growth_metrics", "ocf_growth_yoy"),
    ("growth_metrics", "asset_growth_yoy"),
    ("growth_metrics", "fcf_growth_yoy"),
    ("growth_metrics", "eps_growth_stability"),
    ("growth_metrics", "eps_estimate_revision_90d_pct"),
    ("growth_metrics", "gross_margin_trend"),
    ("growth_metrics", "operating_margin_trend"),
    ("growth_metrics", "net_margin_trend"),
    ("growth_metrics", "roe_trend"),
    # earnings_beat_rate/earnings_surprise_avg: mislabeled proxies, confirmed dead code with
    # no scoring path/caller anywhere (memory: earnings_beat_rate/earnings_surprise_avg
    # mislabeled proxies finding). consecutive_positive_quarters: same - zero references in
    # load_stock_scores.py. All three were missed in this set's first pass (verified via
    # live API cross-check against GROWTH_SCORE_FIELDS, not assumed).
    ("growth_metrics", "earnings_beat_rate"),
    ("growth_metrics", "earnings_surprise_avg"),
    ("growth_metrics", "consecutive_positive_quarters"),
    # Risk: _score_risk uses volatility_60d/252d + beta + max_drawdown_1y + avg_dollar_volume_20d
    # only - the 30d volatility variant and all three downside-deviation variants are computed/
    # stored but never read by that function.
    ("stability_metrics", "volatility_30d"),
    ("stability_metrics", "downside_volatility_252d"),
    ("stability_metrics", "downside_volatility_60d"),
    ("stability_metrics", "downside_volatility_30d"),
}

_TABLE_GROUP = {
    "quality_metrics": "Quality",
    "growth_metrics": "Growth",
    "value_metrics": "Value",
    "positioning_metrics": "Positioning",
    "stability_metrics": "Risk",
    "stock_scores": "Scoring",
    "stock_symbols": "Universe",
    "dividend_data": "Dividend",
    "analyst_sentiment_analysis": "Analyst",
    "analyst_upgrade_downgrade": "Analyst",
    "current_reports_8k": "Filings",
    "earnings_metrics": "Earnings",
    "insider_transaction_velocity": "Insider",
    "price_weekly": "Price",
    "yfinance_snapshot": "Snapshot",
    "market_health_daily": "Market",
    "institutional_holdings_13f": "Institutional",
    "analyst_earnings_estimates": "Analyst",
    "sec_segment_info": "Segments",
    "sec_segment_metrics": "Segments",
    "short_interest_finra": "Positioning",
    "sec_valuations": "Value",
}


def _categorize_reason(reason: str) -> str:
    base = reason.split(":")[0].strip()
    if reason.startswith("missing_critical_fields"):
        return "Missing SEC/XBRL data"
    if reason.startswith("yfinance returned no data"):
        return "Other (errors / excluded)"
    # ADDED 2026-08-29 (goal session: coverage-categorization sweep): growth_metrics's
    # whole-row reason when all 7 growth periods failed (load_value_quality_growth_metrics.py,
    # f"Insufficient historical data: {...fields...} could not be computed") - a full
    # sentence, not a snake_case code, so `base` (split on the first ":") comes out as
    # "Insufficient historical data" and never matches any set literal below. Live-confirmed
    # this exact sentence (2,240 rows, always the same 7-field list since it only fires when
    # every period fails) was the single largest contributor to "Other (errors / excluded)" -
    # same "not enough history" fact as the insufficient_history/insufficient_* reasons in
    # "Insufficient history" below, just phrased as a sentence instead of a code.
    if reason.startswith("Insufficient historical data:"):
        return "Insufficient history"
    # ADDED 2026-09-02 (SEC/XBRL missing-data sweep): loaders/load_risk_metrics_daily.py
    # builds momentum_metrics.reason as a ";"-joined "momentum_{period}:insufficient_
    # price_history" list per missing period (e.g. "momentum_3m:insufficient_price_history;
    # momentum_6m:insufficient_price_history") - `base` (split on the first ":") comes out
    # as "momentum_3m", which never matches a set literal below. Same "not enough history"
    # fact as the other Insufficient history members, just phrased per-period.
    if "insufficient_price_history" in reason:
        return "Insufficient history"
    # ADDED 2026-08-20: loaders/helpers/sec_base.py builds this reason dynamically as
    # f"no_{period}_{statement_type}_data_in_sec_edgar_reit_or_special_entity" (6 period x
    # statement_type combinations) for REITs/SPAC-shells/other entities SEC EDGAR
    # structurally has no income-statement/balance-sheet/cash-flow data for - the same
    # permanent, non-fixable fact as the literal "reit_special_entity" reason already in
    # "Legitimate / not applicable" below, just per-statement-type instead of a single
    # flag. A set literal can't match every combination, hence the suffix check here.
    if reason.endswith("_data_in_sec_edgar_reit_or_special_entity"):
        return "Legitimate / not applicable"
    # ADDED 2026-08-29 (goal session: "full data" audit continuation, signal_quality_scores
    # bare_reason_tables addition above): loaders/signal_quality_scorer.py builds these two
    # reason strings dynamically with the symbol/date range embedded inline (f"... scoring
    # failed for {symbol} [{start} to {end}]: ..." / f"... No VCP patterns found for {symbol}
    # in date range {start} to {end}. ..."), so `base` is unique per symbol and never matches
    # a set literal. Both mean "the underlying event (a buy/sell breakout, a VCP
    # contraction pattern) genuinely hasn't occurred for this symbol in the lookback window
    # yet" - see [[buy_sell_daily_intermittent_71pct_shortfall_unresolved_20260821]] for the
    # live-confirmed evidence that buy_sell_daily is deliberately sparse/event-driven (most
    # of the universe legitimately has zero signals at any given time), not a loader bug -
    # same "not enough qualifying data yet" class as "Insufficient history"'s other members.
    if reason.startswith(("[SIGNAL_QUALITY]", "[VCP_NO_DATA]")):
        return "Insufficient history"
    # ADDED 2026-09-03 (SEC/XBRL missing-data sweep, synchronous static sweep): stock_scores'
    # own `reason` column - the FINAL composite-scoring stage, written by
    # load_stock_scores.py's `_build_score_row` when too few of the 5 pillars
    # (quality/growth/value/risk/momentum) were available to trust a composite score -
    # f"Completeness {pct:.2f}% < {threshold}% threshold (missing metrics: {...})". A full
    # sentence with a variable percentage, not a snake_case code, so `base` (split on the
    # first ":") comes out as "Completeness NN.NN% < NN.N% threshold (missing metrics" and
    # never matches a set literal below - same "sentence instead of a code" shape as
    # "Insufficient historical data:" above. Live-confirmed 227 rows, the largest unmapped
    # stock_scores reason. Same "not enough underlying data to trust a computed value" class
    # as insufficient_completeness (quality_score's own analogous gate, already in
    # "Insufficient history" below). Deliberately does NOT also catch the sibling
    # "Operation failed: {exception}" wrapper two lines below in the source (RuntimeError's
    # generic exception-message wrapper, `raise RuntimeError(f"Operation failed: {e}")`) -
    # that one can wrap an arbitrary exception, not always a data-completeness fact, so
    # bucketing it here would risk mislabeling a genuine bug as a data gap.
    if reason.startswith("Completeness "):
        return "Insufficient history"
    for cat, keys in _COVERAGE_CATEGORY_RULES:
        if base in keys or reason in keys:
            return cat
    return "Other (errors / excluded)"


def _coverage_order_col(cur: cursor, table: str, cols: set[str]) -> str:
    """Pick the best "latest row per symbol" ordering column available on a table.

    Same candidate order/fallback contract as scripts/audit_unavailable_reasons.py's
    select_order_col() - keep the two in sync if either changes.

    FIXED 2026-08-21 (goal session: "is missing data really missing, or are we doing it
    wrong again"): picking the first candidate that merely EXISTS on the table (old
    behavior) breaks on event-log tables where that column exists but is never populated -
    live-confirmed on earnings_calendar, which has a `fiscal_year` column (ranked above
    updated_at) that is NULL on all 450,856 rows. `DISTINCT ON (symbol) ORDER BY
    fiscal_year DESC` then has no real sort key at all (every row ties), so Postgres
    returns an arbitrary row per symbol instead of the actual latest one - live-reproduced
    on symbol A: a fresh, real row from today (updated_at 2026-08-21 06:10, eps_estimate
    populated) coexists with two stale, already-self-healed fetch_error rows from
    2026-08-12, and the old logic picked one of the stale errors, not today's real data.
    That's exactly the kind of "different freshness methodologies disagree" trap already
    documented for monitor_data_staleness.py vs Phase 1 - except here it wasn't even two
    real methodologies, just a candidate column nobody checked was populated. Now queries
    each present candidate's non-null count and picks the first that actually has data;
    tables where fiscal_year IS the real per-row key (annual/quarterly statements,
    sec_segment_info) are unaffected since it's populated on every row there.
    """
    candidates = [c for c in ("date", "fiscal_year", "updated_at", "created_at") if c in cols]
    if not candidates:
        return ""
    cur.execute(f"SELECT {', '.join(f'count({c})' for c in candidates)} FROM {table}")
    counts = cur.fetchone()
    for candidate, count in zip(candidates, counts, strict=True):
        if count:
            return candidate
    return candidates[0]


# Known *_data_source / *_source_tracking raw values -> human-readable labels (2026-08-21,
# goal: "show which source - SEC/yfinance/FRED/etc - each factor's data comes from"). These
# are the actual literal strings loaders write (see migrations 1022/1023/1135/1185/1202/1207
# and each loader's own `"data_source": "..."` assignment) - not guessed. Anything not in this
# map falls back to _prettify_source()'s generic token-capitalization instead of silently
# showing a raw snake_case value.
_SOURCE_LABELS: dict[str, str] = {
    "sec_audited": "SEC (audited financials)",
    "sec_audited_except_dual_class_shares_yfinance": "SEC (audited, dual-class shares via Yahoo Finance)",
    "sec_audited_except_forward_pe_yfinance": "SEC (audited, forward P/E via Yahoo Finance)",
    # ADDED 2026-08-29 (goal session: coverage-categorization sweep continuation): load_sec_
    # valuations.py's data_source for foreign private issuers, whose shares_outstanding comes
    # from a live yfinance fetch instead of SEC XBRL (SEC's own domestic-only shares tag isn't
    # usable for FPIs - see fpi_shares_excluded_domestic_only in
    # [[scores_coverage_other_bucket_96pct_fixed_20260829]]). Was falling through to the
    # generic snake_case-to-Title-Case fallback ("SEC Audited Except Fpi Shares Yahoo
    # Finance" - "Fpi" not expanded since "fpi" wasn't in _SOURCE_ACRONYMS either) instead of
    # a real label, unlike every sibling sec_audited_except_* entry above/below it (539 live
    # rows).
    "sec_audited_except_fpi_shares_yfinance": "SEC (audited, foreign-issuer shares via Yahoo Finance)",
    "sec_edgar_submissions": "SEC EDGAR submissions",
    "sec_edgar_filings": "SEC EDGAR filings",
    "sec_13f": "SEC Form 13F",
    "sec_form13f_bulk": "SEC Form 13F (bulk)",
    "sec_form4": "SEC Form 4/5",
    "sec_form345_bulk": "SEC Form 3/4/5 (bulk)",
    "yfinance_api": "Yahoo Finance",
    "yfinance_snapshot": "Yahoo Finance (snapshot, deprecated)",
    "yfinance_earnings_estimate": "Yahoo Finance (estimates)",
    "finra": "FINRA",
    "finra_query_api": "FINRA",
    "price_daily_aggregated": "Computed (price history)",
    "computed_from_price_daily": "Computed (price history)",
    "alpaca_api": "Alpaca",
    "mixed": "Mixed / legacy",
    "none": "Unavailable",
    "unavailable": "Unavailable",
    "not_recorded": "Not recorded",
}
_SOURCE_ACRONYMS = {
    "sec",
    "api",
    "xbrl",
    "fred",
    "cik",
    "13f",
    "10k",
    "20f",
    "finra",
    "cef",
    "reit",
    "spac",
    "gaap",
    "etf",
    "aaii",
    "naaim",
    "cusip",
    "ad",
    # ADDED 2026-08-29 (goal session: coverage-categorization sweep continuation): future-
    # proofs the generic fallback path for any not-yet-mapped raw source string containing
    # "fpi" (foreign private issuer) - see the sec_audited_except_fpi_shares_yfinance
    # _SOURCE_LABELS entry added the same session for the one already-known case.
    "fpi",
}


def _prettify_source(raw: str) -> str:
    """Turn a raw `data_source`/`source_tracking` value into a display label.

    Known values get an exact label from _SOURCE_LABELS (most of them, live-verified above).
    Anything else - a future loader's new source string this map hasn't been updated for -
    gets a generic snake_case-to-Title-Case pass instead of showing raw underscores, so a new
    source never renders as garbage, just as slightly-less-polished.
    """
    if raw in _SOURCE_LABELS:
        return _SOURCE_LABELS[raw]
    words = raw.replace("-", "_").split("_")
    out = []
    for w in words:
        lw = w.lower()
        if lw == "yfinance":
            out.append("Yahoo Finance")
        elif lw in _SOURCE_ACRONYMS:
            out.append(lw.upper())
        else:
            out.append(w.capitalize() if w else w)
    return " ".join(p for p in out if p)


def _fetch_table_source_breakdown(
    cur: cursor, table: str, cols: set[str], has_symbol: bool, order_col: str
) -> list[dict[str, Any]] | None:
    """Latest-row-per-symbol breakdown of a table's `data_source` column, or None if the
    table has no such column (or isn't per-symbol). See _get_scores_coverage's call site
    comment for why this is computed once per table rather than per factor.

    REWRITTEN 2026-09-01 (goal session: "this one timing out") - unlike the sparse
    *_unavailable_reason columns this loop otherwise deals with, `data_source` is dense
    (populated on essentially every row), so the "candidates" trick in the main query above
    doesn't apply here - genuinely needs each active symbol's actual latest-row source.
    The original `DISTINCT ON (symbol) ... ORDER BY symbol, order_col DESC` form forces
    Postgres to sort every one of the table's rows per symbol before picking the top one -
    live-confirmed this cost price_daily.data_source ~8s alone (26.2M rows across ~5,100
    active symbols), on top of the main query's own cost. A `LATERAL ... ORDER BY order_col
    DESC LIMIT 1` per active symbol instead lets Postgres walk the existing (symbol, date DESC)
    index straight to each symbol's one latest row without materializing or sorting the rest -
    live-verified byte-identical output, ~0.5s (16x faster) on price_daily, and
    indistinguishable on every smaller table tested.
    """
    if not (has_symbol and order_col and "data_source" in cols):
        return None
    try:
        cur.execute(
            f"""
            SELECT source_val, COUNT(*) FROM (
                SELECT pd.data_source AS source_val
                FROM stock_symbols _su
                CROSS JOIN LATERAL (
                    SELECT {table}.data_source
                    FROM {table}
                    WHERE {table}.symbol = _su.symbol
                    ORDER BY {table}.{order_col} DESC
                    LIMIT 1
                ) pd (data_source)
                WHERE _su.active = true
            ) latest
            GROUP BY source_val
            ORDER BY COUNT(*) DESC
            """
        )
        src_rows = cur.fetchall()
        src_total = sum(int(r[1]) for r in src_rows) or 1
        return [
            {
                "source": str(r[0]) if r[0] is not None else "not_recorded",
                "label": _prettify_source(str(r[0]) if r[0] is not None else "not_recorded"),
                "count": int(r[1]),
                "pct": round(100 * int(r[1]) / src_total, 1),
            }
            for r in src_rows
        ]
    except Exception as src_err:
        logger.warning(f"[SCORES_COVERAGE] Skipping data_source for {table}: {src_err}")
        return None


def _fetch_table_source_tracking(
    cur: cursor, table: str, cols: set[str], has_symbol: bool, order_col: str
) -> dict[str, list[dict[str, Any]]] | None:
    """Latest-row-per-symbol breakdown of a table's `source_tracking` JSONB column (per-field
    provenance, e.g. positioning_metrics' short_interest/institutional/insider), keyed by field
    name. None if the table has no such column.

    Same LATERAL-per-symbol rewrite as _fetch_table_source_breakdown above, for the same
    reason - see that function's docstring.
    """
    if not (has_symbol and order_col and "source_tracking" in cols):
        return None
    try:
        cur.execute(
            f"""
            SELECT kv.field_key, kv.source_val, COUNT(*) FROM (
                SELECT pd.source_tracking AS st
                FROM stock_symbols _su
                CROSS JOIN LATERAL (
                    SELECT {table}.source_tracking
                    FROM {table}
                    WHERE {table}.symbol = _su.symbol
                    ORDER BY {table}.{order_col} DESC
                    LIMIT 1
                ) pd (source_tracking)
                WHERE _su.active = true
            ) latest, LATERAL jsonb_each_text(COALESCE(latest.st, '{{}}'::jsonb)) AS kv(field_key, source_val)
            GROUP BY kv.field_key, kv.source_val
            ORDER BY kv.field_key, COUNT(*) DESC
            """
        )
        st_rows = cur.fetchall()
        field_totals: dict[str, int] = {}
        for field_key, _source_val, cnt in st_rows:
            field_totals[field_key] = field_totals.get(field_key, 0) + int(cnt)
        per_field: dict[str, list[dict[str, Any]]] = {}
        for field_key, source_val, cnt in st_rows:
            total = field_totals.get(field_key) or 1
            per_field.setdefault(field_key, []).append(
                {
                    "source": str(source_val),
                    "label": _prettify_source(str(source_val)),
                    "count": int(cnt),
                    "pct": round(100 * int(cnt) / total, 1),
                }
            )
        return per_field
    except Exception as st_err:
        logger.warning(f"[SCORES_COVERAGE] Skipping source_tracking for {table}: {st_err}")
        return None


# BUG FOUND 2026-08-24 (goal session data-source audit): a plain `field_key in factor_name`
# substring check missed positioning_metrics' top_10_institutions_pct - the source_tracking
# field key is "institutional" (from load_positioning_metrics.py's institutional_source), but
# the column is spelled "institutions" (no trailing "al"), so the two words never matched as
# substrings of each other. top_10_institutions_pct is always SEC Form 13F-sourced (same
# sec_inst_row as institutional_ownership_pct/institutional_holders_count, which DO match) but
# silently fell through to the table-wide data_source breakdown instead - which, for
# positioning_metrics, is dominated by FINRA (load_positioning_metrics.py's data_source column
# picks short_interest_source over institutional_source/insider_source whenever short-interest
# data exists, which is true for most symbols) - so this one factor's SEC-sourced data was
# misattributed to FINRA in the Data Sources dashboard. Aliases below cover known field_key /
# factor_name spelling mismatches; add to this list rather than the substring check itself if
# another one turns up.
_SOURCE_TRACKING_FACTOR_ALIASES: dict[str, tuple[str, ...]] = {
    "institutional": ("institutional", "institutions"),
}


def _resolve_factor_sources(
    table_source_cache: dict[str, list[dict[str, Any]] | None],
    table_source_tracking_cache: dict[str, dict[str, list[dict[str, Any]]] | None],
    table: str,
    factor_name: str,
) -> list[dict[str, Any]] | None:
    """Pick this factor's source breakdown: a source_tracking per-field split when the factor
    name matches one of its keys, else the table-wide data_source breakdown. See
    table_source_cache's definition at the _get_scores_coverage call site for why sources are
    computed per-table, not per-factor."""
    st_detail = table_source_tracking_cache.get(table)
    if st_detail:
        for field_key, breakdown in st_detail.items():
            aliases = _SOURCE_TRACKING_FACTOR_ALIASES.get(field_key, (field_key,))
            if any(alias in factor_name for alias in aliases):
                return breakdown
    return table_source_cache.get(table)


def _resolve_factor_value_col(
    cur: cursor, table: str, column: str, table_all_cols_cache: dict[str, set[str]]
) -> tuple[str, str | None]:
    """Derives the factor name from a `*_unavailable_reason` column and, if a same-named
    value column exists on `table`, returns it too - see _get_scores_coverage's own
    2026-09-01 call-site comment for why: some loaders deliberately keep a real value (e.g.
    dividend_yield=0.0 for a confirmed non-payer) alongside a non-NULL reason "for
    transparency", so the reason column alone isn't sufficient to infer "missing". Returns
    (factor_name, None) when no matching value column exists (the bare_reason_tables case,
    where "reason" describes the whole row rather than one specific field) - callers fall
    back to reason-only behavior in that case. `table_all_cols_cache` is populated lazily,
    once per table, and shared across every factor column on that table."""
    factor_name_candidate = re.sub(r"_?unavailable_reason$", "", column).rstrip("_")
    if not factor_name_candidate or factor_name_candidate in ("data", "reason"):
        return factor_name_candidate, None
    if table not in table_all_cols_cache:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s",
            (table,),
        )
        table_all_cols_cache[table] = {r[0] for r in cur.fetchall()}
    value_col = factor_name_candidate if factor_name_candidate in table_all_cols_cache[table] else None
    return factor_name_candidate, value_col


def _get_scores_coverage(cur: cursor, group_filter: str | None = None, meta_only: bool = False) -> Any:
    """Factor-level data coverage report: which *_unavailable_reason columns are
    missing data across the universe, how much, and why - aggregated by root cause.

    Powers the ServiceHealth "Scores Data Coverage" tab. Read-only, ~100+ small
    grouped-count queries (one per *_unavailable_reason column found in the schema) -
    not meant to be polled on a tight interval, hence no data_freshness auto-refresh
    wiring; the frontend refetches on manual click only.

    `group_filter` scopes the (expensive) per-table loop below to a single
    `_TABLE_GROUP` value, so one HTTP call covers a handful of tables instead of all
    ~20 - see the 2026-09-01 fix note at this function's call site for why. `meta_only`
    short-circuits before any per-table query runs at all, returning just the group
    list the frontend chunks its requests by.
    """
    try:
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE column_name LIKE %s
              AND table_schema = 'public'
            ORDER BY table_name, column_name
            """,
            ("%unavailable_reason%",),
        )
        reason_columns = [(r[0], r[1]) for r in cur.fetchall()]

        # FIXED 2026-08-19 (goal session continuation - "which factor inputs are missing the
        # most" audit): yfinance_snapshot.unavailable_reason was reporting 2,146 active-symbol
        # gaps (45.8% of the table, the #2 largest "Missing SEC/XBRL data" contributor after
        # dividend_data) as if it were an actionable loader gap. It isn't: yfinance_snapshot
        # has had NO active loader since Session 275 (see load_value_quality_growth_metrics.py's
        # and load_positioning_metrics.py's own "yfinance_snapshot is deprecated" comments -
        # every real consumer was migrated off it, nothing writes to it anymore, its rows are
        # frozen at whatever they were on 2026-07-16). No amount of "fixing loaders" can ever
        # change this number, so surfacing it here as a live gap actively misleads the exact
        # workflow ("find which factor inputs are missing the most, fix the loaders") this
        # report exists to support. Excludes any table with no entry in loader_registry.py's
        # LOADER_TABLES/PSEUDO_LOADER_TABLES (the canonical active-loader-output mapping) rather
        # than hardcoding "yfinance_snapshot" by name, so a future loader removal is excluded
        # automatically instead of silently reintroducing this same trap a second way.
        _tables_with_active_loader = {t for tables in LOADER_TABLES.values() for t in tables} | {
            t for tables in PSEUDO_LOADER_TABLES.values() for t in tables
        }
        reason_columns = [(t, c) for t, c in reason_columns if t in _tables_with_active_loader]

        # FIXED 2026-08-19 (goal: "no SEC data"/missing factor inputs audit, same-day
        # follow-up to the active-universe fix above): the "%unavailable_reason%" name
        # match above misses every table whose gap-reason column is just called "reason"
        # instead - live-confirmed this is a completely different, real blind spot, not
        # overlap: institutional_holdings_13f,
        # analyst_earnings_estimates, sec_segment_info/metrics, short_interest_finra, and
        # sec_valuations are all genuine per-symbol data SOURCES (not just downstream
        # computed factors) with a real, populated "reason" column - sec_segment_metrics
        # alone had 2,067 of 5,546 rows (37%) unavailable with real, specific reasons
        # (no_segment_dimension_contexts_in_xbrl_xml, no_segment_revenue_in_xbrl_xml, ...),
        # 100% invisible to this report the whole time. Scoped to this specific allowlist
        # (verified against the schema below, not a blanket "reason" scan) rather than
        # every bare "reason" column in the DB - most of those belong to internal
        # audit/log/algo-state tables (data_loader_status, circuit_breaker_log,
        # algo_orchestrator_state, ...) that aren't per-symbol factor data at all, and
        # quality_metrics/growth_metrics/value_metrics/positioning_metrics/
        # stability_metrics/institutional_holdings_13f-consumers already have their own
        # much more granular *_unavailable_reason columns covered above - their bare
        # "reason" is just a coarse whole-row fallback (live-confirmed quality_metrics:
        # only 151 rows, mostly a single generic "Insufficient SEC financial data"
        # message) that would only add noise, not information, if included too.
        # ADDED 2026-08-29 (goal session: "full data" audit continuation): signal_quality_scores
        # is exactly the same "genuine per-symbol data source with a real, populated bare
        # `reason` column" shape as the 6 tables above, but was missed when this allowlist was
        # built - live-confirmed 100% invisible to this report despite being the single
        # largest bare-reason population found this session (964,110 total reason rows,
        # ~899,000 active-universe). Two dynamic, per-symbol reason families
        # (`[SIGNAL_QUALITY] ... No buy/sell signals found` / `[VCP_NO_DATA] ... No VCP
        # patterns found`) embed the ticker/date range inline, so _categorize_reason's
        # `base = reason.split(":")[0]` never matches a set-literal key for either - see the
        # startswith checks added there for both patterns.
        bare_reason_tables = (
            "institutional_holdings_13f",
            "analyst_earnings_estimates",
            "sec_segment_info",
            "sec_segment_metrics",
            "short_interest_finra",
            "sec_valuations",
            "signal_quality_scores",
        )
        cur.execute(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE column_name = 'reason'
              AND table_schema = 'public'
              AND table_name = ANY(%s)
            ORDER BY table_name
            """,
            (list(bare_reason_tables),),
        )
        reason_columns.extend((r[0], r[1]) for r in cur.fetchall())

        if meta_only:
            groups = sorted({_TABLE_GROUP.get(t, t) for t, _ in reason_columns})
            return json_response(200, {"groups": groups, "factor_count": len(reason_columns)})

        if group_filter:
            reason_columns = [(t, c) for t, c in reason_columns if _TABLE_GROUP.get(t, t) == group_filter]

        denom_cache: dict[str, int | None] = {}
        table_cols_cache: dict[str, set[str]] = {}
        table_all_cols_cache: dict[str, set[str]] = {}
        # Per-table (not per-factor) source breakdown caches - `data_source`/`source_tracking`
        # are table-level columns shared by every *_unavailable_reason factor on that table, so
        # they're computed once per table and attached to each of that table's factor rows below,
        # not recomputed per factor.
        table_source_cache: dict[str, list[dict[str, Any]] | None] = {}
        table_source_tracking_cache: dict[str, dict[str, list[dict[str, Any]]] | None] = {}
        factors: list[dict[str, Any]] = []

        for table, column in reason_columns:
            if table not in table_cols_cache:
                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=%s
                      AND column_name IN ('symbol','date','fiscal_year','updated_at','created_at',
                                           'data_source','source_tracking')
                    """,
                    (table,),
                )
                table_cols_cache[table] = {r[0] for r in cur.fetchall()}
            cols = table_cols_cache[table]
            has_symbol = "symbol" in cols
            order_col = _coverage_order_col(cur, table, cols)

            # FIXED 2026-09-01 (goal: "are these gaps real" audit, live-caught via
            # value_metrics.dividend_yield): this report used to infer "missing" purely from
            # the *_unavailable_reason column being non-NULL, on the unstated assumption that
            # every loader nulls the reason out the moment it fills the real value. That's true
            # almost everywhere but not universal - load_value_quality_growth_metrics.py
            # deliberately sets dividend_yield=0.0 (a real, correct value) for confirmed
            # non-payers while KEEPING dividend_yield_unavailable_reason='non_dividend_paying_stock'
            # "for transparency" (see that file's 2026-08-05 fix comment) - live-confirmed 2,771
            # rows carry a real non-NULL value alongside a non-NULL reason, inflating
            # dividend_yield's reported gap from a real ~5.6% to a shown 59.6%. Resolving the
            # matching value column (same name as the factor, e.g. "dividend_yield" for
            # "dividend_yield_unavailable_reason") and requiring it be NULL too closes this for
            # every factor at once rather than special-casing dividend_yield - live-audited via a
            # full-schema scan and found only 3 other, negligible (1-8 row) instances of the same
            # pattern (company_info_sec.shares_outstanding, quality_metrics.
            # estimate_momentum_60d/90d), so this generalizes cleanly. Falls back to the old
            # reason-only behavior when no matching value column exists (the bare_reason_tables
            # case, where "reason" describes the whole row rather than one specific field).
            factor_name_candidate, value_col = _resolve_factor_value_col(cur, table, column, table_all_cols_cache)

            # FIXED 2026-08-19 (goal: "no SEC data"/missing factor inputs audit): every
            # query below used to scan {table} directly with no active-universe filter, so
            # a symbol delisted/failed-SPAC/dropped from stock_symbols.active but never
            # pruned from a metrics table (live-confirmed: 6-9% of rows in quality_metrics/
            # growth_metrics/value_metrics/positioning_metrics/stability_metrics/
            # dividend_data belong to symbols no longer active) counted as a live "gap in
            # the real, scored universe" here - inflating every factor's numerator AND
            # denominator, and inactive symbols are disproportionately gap-heavy (delisted
            # shells, failed SPACs), so this wasn't just proportional noise. The actual
            # user-facing /api/algo/scores query already joins stock_scores -> stock_symbols
            # (stock_scores itself is 99.7% clean of inactive symbols - the scoring loader
            # already scopes to the active universe), so this report was measuring a
            # DIFFERENT, larger, stale-inflated population than what real users ever see.
            # Joining to stock_symbols and filtering active=true here makes this report
            # match that same real, live-scored universe.
            active_join = (
                f" JOIN stock_symbols _su ON _su.symbol = {table}.symbol AND _su.active = true" if has_symbol else ""
            )

            if table not in denom_cache:
                if has_symbol:
                    try:
                        cur.execute(f"SELECT COUNT(DISTINCT {table}.symbol) FROM {table}{active_join}")
                        denom_cache[table] = cur.fetchone()[0]
                    except Exception:
                        denom_cache[table] = None
                else:
                    denom_cache[table] = None

            # Data source breakdown (goal 2026-08-21: "which sources - SEC/yfinance/etc - and
            # what % from each, per input"). Table-level, not column-level - computed once per
            # table (same latest-row-per-symbol population as denom_cache above) and attached to
            # every factor row from that table below. `source_tracking` (positioning_metrics only
            # today) gives a finer per-field breakdown when the factor name matches one of its
            # keys (short_interest/institutional/insider); everything else uses the table-wide
            # `data_source` column. Split into helpers above to keep this loop's own complexity
            # in check.
            if table not in table_source_cache:
                table_source_cache[table] = _fetch_table_source_breakdown(cur, table, cols, has_symbol, order_col)
                table_source_tracking_cache[table] = _fetch_table_source_tracking(
                    cur, table, cols, has_symbol, order_col
                )

            try:
                if has_symbol and order_col:
                    # {table}-qualify column/order_col (not just symbol) - active_join's _su
                    # alias is another copy of the SAME table for the stock_symbols.
                    # data_unavailable_reason case (self-join), and stock_symbols also has
                    # updated_at/created_at, either of which order_col can pick as the
                    # ordering column for OTHER tables too - both would otherwise be
                    # ambiguous between {table} and the joined _su copy.
                    #
                    # FIXED (goal session, "so many from yfinance still" data-accuracy audit):
                    # a plain `ORDER BY {order_col} DESC` picks the row with the highest
                    # fiscal_year/date even when THAT row is an unavailable placeholder (e.g.
                    # annual_income_statement writes a data_unavailable=TRUE marker row for the
                    # current, not-yet-filed fiscal year) while an older row for the same symbol
                    # has real, usable data - live-confirmed on annual_income_statement (3,076
                    # symbols) via stocks.py's identical bug in the deep-value screener CTEs,
                    # fixed alongside this. A symbol only counts as "missing" here if it has
                    # NEVER once had a row where this factor was available, regardless of
                    # fiscal_year/date - same "once real, always real" rule
                    # load_value_quality_growth_metrics.py's own "latest row" helpers already
                    # apply when computing ratios from these same tables.
                    #
                    # REWRITTEN 2026-09-01 (goal session: "this one timing out") - the original
                    # form of this query (`DISTINCT ON (symbol) ... ORDER BY symbol, (reason_val
                    # IS NULL) DESC, order_col DESC`) computed the exact same "once real, always
                    # real" result but by sorting EVERY row of the table per symbol, which is
                    # what a plain per-symbol DISTINCT ON always costs regardless of how rare the
                    # non-null reason values actually are - live-confirmed price_daily.
                    # data_unavailable_reason (26.2M rows, only 15 ever non-null) alone cost
                    # ~27s this way, the dominant cost in the whole report and enough on its own
                    # to exceed the frontend's 28s client timeout even after the per-group
                    # chunking added alongside this (ScoresDataCoverage.jsx's header comment).
                    # This form is mathematically the same computation, just reordered to do the
                    # cheap, selective part first: `candidates` finds the (usually tiny) set of
                    # symbols that have EVER had a non-null reason row - a single filtered scan,
                    # not a per-symbol sort - and `never_available` then keeps only the ones that
                    # NEVER had a null-reason row either, which is exactly "missing" under the
                    # same rule as before. Only that (typically tiny) survivor set ever reaches
                    # the DISTINCT ON, so its per-symbol sort is now bounded by how many symbols
                    # are actually missing, not by the table's total size - live-verified to
                    # return byte-identical results to the original query on every table tested
                    # (quality_metrics, growth_metrics, stability_metrics, value_metrics,
                    # price_weekly, price_daily), 12-25x faster on the two price_* tables and
                    # indistinguishable on the smaller ones.
                    # value_col cross-check (see this loop's own 2026-09-01 comment above): a
                    # symbol only belongs in `candidates`/`never_available` when the real value
                    # column is ALSO null, not just the reason column - otherwise a factor like
                    # dividend_yield (real 0.0 kept alongside its reason "for transparency")
                    # gets double-counted as missing on top of its genuinely-null rows.
                    value_is_null = f" AND {table}.{value_col} IS NULL" if value_col else ""
                    never_exists_clause = f"t2.{value_col} IS NOT NULL" if value_col else f"t2.{column} IS NULL"
                    query = f"""
                        WITH candidates AS (
                            SELECT DISTINCT {table}.symbol FROM {table}{active_join}
                            WHERE {table}.{column} IS NOT NULL{value_is_null}
                        ),
                        never_available AS (
                            SELECT c.symbol FROM candidates c
                            WHERE NOT EXISTS (
                                SELECT 1 FROM {table} t2 WHERE t2.symbol = c.symbol AND {never_exists_clause}
                            )
                        )
                        SELECT reason_val, COUNT(*) FROM (
                            SELECT DISTINCT ON ({table}.symbol) {table}.symbol, {table}.{column} AS reason_val
                            FROM {table}
                            JOIN never_available na ON na.symbol = {table}.symbol
                            ORDER BY {table}.symbol, {table}.{order_col} DESC
                        ) latest
                        WHERE reason_val IS NOT NULL
                        GROUP BY reason_val
                        ORDER BY COUNT(*) DESC
                    """
                else:
                    # Same active-universe scoping as the has_symbol branch above, for the
                    # rarer has_symbol-but-no-order_col case (a market-wide/no-symbol table
                    # skips the join entirely since active_join is "" when not has_symbol).
                    # Same value_col cross-check as the branch above.
                    value_is_null = f" AND {table}.{value_col} IS NULL" if value_col else ""
                    query = f"""
                        SELECT {table}.{column} AS reason_val, COUNT(*)
                        FROM {table}{active_join}
                        WHERE {table}.{column} IS NOT NULL{value_is_null}
                        GROUP BY {table}.{column}
                        ORDER BY COUNT(*) DESC
                    """
                cur.execute(query)
                rows = cur.fetchall()
            except Exception as col_err:
                logger.warning(f"[SCORES_COVERAGE] Skipping {table}.{column}: {col_err}")
                continue

            if not rows:
                continue

            total_missing = sum(int(r[1]) for r in rows)
            denom = denom_cache[table]
            pct_missing = round(100 * total_missing / denom, 1) if denom else None

            categories: dict[str, int] = {}
            reasons_out = []
            for reason_val, count in rows:
                cat = _categorize_reason(str(reason_val))
                categories[cat] = categories.get(cat, 0) + int(count)
                reasons_out.append({"reason": str(reason_val), "count": int(count), "category": cat})

            factor_name = factor_name_candidate
            # A bare "reason" column (the bare_reason_tables case above) doesn't match the
            # unavailable_reason suffix at all and would otherwise show the unhelpful
            # literal "reason" as the factor name - same fallback as the "data"/empty case.
            if not factor_name or factor_name in ("data", "reason"):
                factor_name = table

            factors.append(
                {
                    "table": table,
                    "group": _TABLE_GROUP.get(table, table),
                    "factor": factor_name,
                    "column": column,
                    "total_missing": total_missing,
                    "denom": denom,
                    "pct_missing": pct_missing,
                    "reasons": reasons_out,
                    "categories": categories,
                    "sources": _resolve_factor_sources(
                        table_source_cache, table_source_tracking_cache, table, factor_name
                    ),
                    # ADDED 2026-09-02: see _UNSCORED_FACTORS/_UNSCORED_TABLES's own comments
                    # above - a gap here can never move stock_scores, unlike every other
                    # factor on this page.
                    "scored": table not in _UNSCORED_TABLES and (table, factor_name) not in _UNSCORED_FACTORS,
                }
            )

        factors.sort(key=lambda f: -1 if f["pct_missing"] is None else -f["pct_missing"])

        category_totals = dict.fromkeys(_COVERAGE_CATEGORY_ORDER, 0)
        for f in factors:
            for c, v in f["categories"].items():
                category_totals[c] = category_totals.get(c, 0) + v

        # Table-wide source rollup for the summary KPI/chart - one table's data_source
        # breakdown counted once (not once per factor column on that table), same dedup
        # reasoning as table_source_cache being keyed by table above.
        #
        # FIXED 2026-08-23 (goal: data-source accuracy review): keyed by s["label"], not
        # s["source"]. Different tables write different literal data_source strings that
        # _prettify_source() maps to the SAME human label - e.g. "finra" (short_interest_finra)
        # and "finra_query_api" (positioning_metrics) both -> "FINRA". Keying by the raw string
        # left them as two separate same-labeled bars/legend entries in the summary chart
        # (e.g. "FINRA 5,192" and "FINRA 4,918" shown side by side) instead of one merged
        # ~10,110-count bar. Per-factor source breakdowns (_resolve_factor_sources) are
        # unaffected - only this table-wide rollup used the raw string as its dict key.
        source_totals: dict[str, int] = {}
        source_labels: dict[str, str] = {}
        _seen_source_tables: set[str] = set()
        for f in factors:
            t = f["table"]
            if t in _seen_source_tables:
                continue
            _seen_source_tables.add(t)
            # BUG FOUND 2026-08-24 (goal session data-source audit): a table with
            # source_tracking (positioning_metrics today) has MULTIPLE independently-sourced
            # fields (short_interest/institutional/insider) but only ONE flat table-wide
            # data_source column, which picks a single winning field per row (see
            # load_positioning_metrics.py: short_interest_source wins over
            # institutional/insider whenever short-interest data exists, true for ~95% of
            # symbols). Summing table_source_cache here counted every row as "FINRA" even
            # for symbols whose institutional_ownership_pct/insider_ownership_pct came from
            # SEC 13F/Form 4-5 - live-confirmed this collapsed ~4,100 real SEC-sourced rows
            # for each of those two fields into the FINRA bucket, undercounting SEC Form
            # 13F/Form 4-5 in this summary by >99% versus their true per-factor breakdown
            # (_resolve_factor_sources, unaffected by this bug). Sum each of the table's
            # source_tracking fields separately when present - each field is a real,
            # independent source population - falling back to the flat data_source rollup
            # only for tables with no source_tracking column at all.
            st_detail = table_source_tracking_cache.get(t)
            per_table_sources = (
                [s for field_breakdown in st_detail.values() for s in field_breakdown]
                if st_detail
                else (table_source_cache.get(t) or [])
            )
            for s in per_table_sources:
                label = s["label"]
                source_totals[label] = source_totals.get(label, 0) + s["count"]
                source_labels[label] = label
        source_order = sorted(source_totals, key=lambda s: -source_totals[s])

        # stock_symbols is the actual universe registry - prefer it over other tables'
        # denom counts, since a table like price_weekly can carry more distinct symbols
        # than the live universe (delisted/historical rows never pruned), which would
        # otherwise overstate "universe_estimate" via a naive max().
        universe_estimate = denom_cache.get("stock_symbols") or max((d for d in denom_cache.values() if d), default=0)

        result = {
            "summary": {
                "universe_estimate": universe_estimate,
                "factor_count": len(factors),
                "category_order": _COVERAGE_CATEGORY_ORDER,
                "category_totals": category_totals,
                "source_order": source_order,
                "source_totals": source_totals,
                "source_labels": source_labels,
            },
            "factors": factors,
        }
        return json_response(200, result)

    except Exception as e:
        code, error_type, message = handle_db_error(e, "get scores coverage")
        return error_response(code, error_type, message)
