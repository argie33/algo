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
    list_response,
    safe_limit,
    safe_offset,
)

from shared_contracts.response_validator import ResponseValidator

logger = logging.getLogger(__name__)


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, str] | None,
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/scores/* endpoints."""
    try:
        if path in ["/api/scores", "/api/scores/stockscores"] or path.startswith(
            ("/api/scores?", "/api/scores/stockscores?")
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


def _get_stock_scores(
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
            "composite_score": "sc.composite_score",
            "momentum_score": "sc.momentum_score",
            "quality_score": "sc.quality_score",
            "value_score": "sc.value_score",
            "growth_score": "sc.growth_score",
            "positioning_score": "sc.positioning_score",
            "stability_score": "sc.stability_score",
            "symbol": "sc.symbol",
        }
        sort_col = allowed_sorts.get(sort_by, "sc.composite_score")
        sort_direction = "DESC" if sort_order == "desc" else "ASC"

        where_clause = """
            WHERE sc.composite_score > 0
            AND (ss.symbol NOT IN (SELECT symbol FROM etf_symbols) AND (ss.etf IS NULL OR ss.etf = 'N'))
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
            where_clause += " AND sc.data_completeness >= 70"

        # Use LATERAL joins instead of CTEs: CTEs scan all symbols before filtering
        # (full table scans on price_daily/technical_data_daily = timeout for bulk queries).
        # LATERAL evaluates per-row after WHERE, using (symbol, date) indexes efficiently.
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
                    sc.value_score, sc.growth_score, sc.positioning_score, sc.stability_score,
                    sc.rs_percentile, sc.data_completeness,
                    sc.updated_at AS last_updated,
                    pl.close AS current_price,
                    pl.close AS price,
                    (pl.close IS NULL) AS _is_fallback,
                    (qm.symbol IS NULL OR qm.data_unavailable = TRUE OR (qm.roe IS NULL AND qm.operating_margin IS NULL AND qm.net_margin IS NULL)) AS _financial_data_unavailable,
                    (gm.symbol IS NULL OR gm.data_unavailable = TRUE) AS _growth_data_unavailable,
                    (pm.symbol IS NULL OR pm.data_unavailable = TRUE) AS _positioning_data_unavailable,
                    (sm.symbol IS NULL OR sm.data_unavailable = TRUE) AS _stability_data_unavailable,
                    ROUND(CASE
                        WHEN pp.close IS NOT NULL THEN ((pl.close - pp.close) / NULLIF(pp.close, 0)) * 100
                        ELSE NULL
                    END, 2) AS change_percent,
                    vm.market_cap,
                    vm.pe_ratio AS trailing_pe,
                    vm.pb_ratio AS price_to_book,
                    vm.ps_ratio AS ps_ratio_val,
                    vm.peg_ratio AS peg_ratio_val,
                    vm.dividend_yield,
                    vm.fcf_yield AS fcf_yield_val,
                    vm.held_percent_insiders AS vm_held_insiders,
                    vm.held_percent_institutions AS vm_held_institutions,
                    qm.roe AS roe_pct,
                    qm.roa AS roa_val,
                    qm.debt_to_equity,
                    qm.current_ratio AS current_ratio_val,
                    qm.quick_ratio AS quick_ratio_val,
                    qm.operating_margin AS operating_margin_val,
                    qm.net_margin AS net_margin_val,
                    qm.interest_coverage AS interest_coverage_val,
                    gm.revenue_growth_1y AS rev_growth_1y_val,
                    gm.eps_growth_1y AS eps_growth_1y_val,
                    gm.revenue_growth_3y AS rev_growth_3y_val,
                    gm.eps_growth_3y AS eps_growth_3y_val,
                    gm.revenue_growth_5y AS rev_growth_5y_val,
                    gm.eps_growth_5y AS eps_growth_5y_val,
                    sm.beta AS beta_val,
                    sm.volatility_252d AS volatility_12m_val,
                    sm.volatility_30d AS volatility_30d_val,
                    sm.volatility_60d AS volatility_60d_val,
                    sm.debt_to_assets AS debt_to_assets_val,
                    pm.institutional_ownership AS inst_own_val,
                    pm.insider_ownership AS insider_own_val,
                    pm.short_interest_percent AS short_pct_val,
                    pm.shares_short_prior_month AS shares_short_prior_month_val,
                    pm.short_interest_trend AS short_interest_trend_val,
                    tl.rsi_14 AS tdd_rsi,
                    tl.macd AS tdd_macd,
                    tl.roc_20d AS tdd_roc_20d,
                    tl.roc_60d AS tdd_roc_60d,
                    tl.roc_120d AS tdd_roc_120d,
                    tl.roc_252d AS tdd_roc_252d,
                    ROUND(CASE WHEN tl.sma_50 > 0 THEN ((pl.close - tl.sma_50) / tl.sma_50 * 100) END, 2) AS price_vs_sma_50,
                    ROUND(CASE WHEN tl.sma_200 > 0 THEN ((pl.close - tl.sma_200) / tl.sma_200 * 100) END, 2) AS price_vs_sma_200,
                    p52.high_52w AS high_52w_val,
                    ROUND(CASE WHEN p52.high_52w > 0 THEN ((pl.close - p52.high_52w) / p52.high_52w * 100) END, 2) AS price_vs_52w_high_val
                FROM stock_scores sc
                JOIN stock_symbols ss ON ss.symbol = sc.symbol
                LEFT JOIN company_profile cp ON cp.ticker = sc.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
                LEFT JOIN stability_metrics sm ON sm.symbol = sc.symbol
                LEFT JOIN positioning_metrics pm ON pm.symbol = sc.symbol
                LEFT JOIN LATERAL (
                    SELECT close, date
                    FROM price_daily
                    WHERE symbol = sc.symbol
                    ORDER BY date DESC
                    LIMIT 1
                ) pl ON true
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
                    SELECT MAX(high) AS high_52w
                    FROM price_daily
                    WHERE symbol = sc.symbol
                      AND date >= CURRENT_DATE - INTERVAL '52 weeks'
                ) p52 ON true
                {where_clause}
                ORDER BY {sort_col} {sort_direction}
                LIMIT %s OFFSET %s
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

        items = []
        prices_missing_count = 0
        for row in scores:
            d = dict(row)

            # Note: We include scores even if current prices are missing
            # Scores are computed from other factors; current price is optional for display
            items.append(d)

        # Check data freshness
        freshness = check_data_freshness(cur, "stock_scores", "updated_at", warning_days=7)

        # Log warning if many scores have missing prices (data quality issue)
        prices_missing_count = sum(1 for item in items if item.get("current_price") is None)
        if prices_missing_count > 0 and items:
            filter_rate = prices_missing_count / len(items) if len(items) > 0 else 0
            if filter_rate > 0.5:
                logger.warning(
                    f"Scores endpoint: {prices_missing_count}/{len(items)} scores ({filter_rate * 100:.1f}%) "
                    f"have missing price data. Data quality is degraded."
                )
            else:
                logger.debug(
                    f"Scores endpoint: {prices_missing_count} scores have missing price data (out of {len(items)})"
                )

        result = list_response(items, data_freshness=freshness)
        is_valid, error_msg = ResponseValidator.validate_endpoint_response("scores", result)
        if not is_valid:
            logger.error(f"Endpoint response validation failed: {error_msg}")
            return error_response(500, "response_validation_error", error_msg or "Scores validation failed")
        return result
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "handle scores")
        return error_response(code, error_type, message)
