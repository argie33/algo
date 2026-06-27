"""Route: scores"""

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
    method,
    params,
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
            AND NOT EXISTS (SELECT 1 FROM etf_symbols WHERE symbol = sc.symbol)
            AND ss.etf = 'N'
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

        query = f"""
                WITH latest_d AS (
                    SELECT date AS cur_date FROM price_daily ORDER BY date DESC LIMIT 1
                ),
                latest_prices AS (
                    SELECT pd.symbol, pd.close AS current_close
                    FROM price_daily pd, latest_d
                    WHERE pd.date = latest_d.cur_date
                ),
                prev_prices AS (
                    SELECT pd.symbol, pd.close AS prev_close
                    FROM price_daily pd, latest_d
                    WHERE pd.date = (
                        SELECT date FROM price_daily WHERE date < latest_d.cur_date
                        ORDER BY date DESC LIMIT 1
                    )
                )
                SELECT
                    sc.symbol,
                    COALESCE(ss.security_name, sc.symbol) AS company_name,
                    -- CRITICAL FIX: Return NULL for missing sector (don't hide with 'Unknown')
                    cp.sector,
                    cp.industry,
                    sc.composite_score, sc.momentum_score, sc.quality_score,
                    sc.value_score, sc.growth_score, sc.positioning_score, sc.stability_score,
                    sc.rs_percentile, sc.data_completeness,
                    sc.updated_at AS last_updated,
                    lp.current_close AS current_price,
                    lp.current_close AS price,
                    (lp.current_close IS NULL) AS _is_fallback,
                    (qm.symbol IS NULL OR (qm.roe IS NULL AND qm.operating_margin IS NULL AND qm.net_margin IS NULL)) AS _financial_data_unavailable,
                    ROUND(CASE
                        WHEN pp.prev_close IS NOT NULL THEN ((lp.current_close - pp.prev_close) / NULLIF(pp.prev_close, 0)) * 100
                        ELSE NULL
                    END, 2) AS change_percent,
                    -- Value metrics
                    vm.market_cap,
                    vm.pe_ratio AS trailing_pe,
                    vm.pb_ratio AS price_to_book,
                    vm.ps_ratio AS ps_ratio_val,
                    vm.peg_ratio AS peg_ratio_val,
                    vm.dividend_yield,
                    vm.fcf_yield AS fcf_yield_val,
                    vm.held_percent_insiders AS vm_held_insiders,
                    vm.held_percent_institutions AS vm_held_institutions,
                    -- Quality metrics
                    qm.roe AS roe_pct,
                    qm.roa AS roa_val,
                    qm.debt_to_equity,
                    qm.current_ratio AS current_ratio_val,
                    qm.quick_ratio AS quick_ratio_val,
                    qm.operating_margin AS operating_margin_val,
                    qm.net_margin AS net_margin_val,
                    qm.interest_coverage AS interest_coverage_val,
                    -- Growth metrics
                    gm.revenue_growth_1y AS rev_growth_1y_val,
                    gm.eps_growth_1y AS eps_growth_1y_val,
                    gm.revenue_growth_3y AS rev_growth_3y_val,
                    gm.eps_growth_3y AS eps_growth_3y_val,
                    gm.revenue_growth_5y AS rev_growth_5y_val,
                    gm.eps_growth_5y AS eps_growth_5y_val,
                    -- Stability metrics
                    sm.beta AS beta_val,
                    sm.volatility_252d AS volatility_12m_val,
                    sm.volatility_30d AS volatility_30d_val,
                    sm.volatility_60d AS volatility_60d_val,
                    sm.debt_to_assets AS debt_to_assets_val,
                    -- Positioning metrics
                    pm.institutional_ownership AS inst_own_val,
                    pm.insider_ownership AS insider_own_val,
                    pm.short_interest_percent AS short_pct_val,
                    pm.shares_short_prior_month AS shares_short_prior_month_val,
                    pm.short_interest_trend AS short_interest_trend_val,
                    -- Technical indicators
                    tdd.rsi_14 AS tdd_rsi,
                    tdd.macd AS tdd_macd,
                    tdd.roc_20d AS tdd_roc_20d,
                    tdd.roc_60d AS tdd_roc_60d,
                    tdd.roc_120d AS tdd_roc_120d,
                    tdd.roc_252d AS tdd_roc_252d,
                    ROUND(CASE WHEN tdd.sma_50 > 0 THEN ((lp.current_close - tdd.sma_50) / tdd.sma_50 * 100) END, 2) AS price_vs_sma_50,
                    ROUND(CASE WHEN tdd.sma_200 > 0 THEN ((lp.current_close - tdd.sma_200) / tdd.sma_200 * 100) END, 2) AS price_vs_sma_200,
                    -- 52-week high from price history
                    pw52.high_52w AS high_52w_val,
                    ROUND(CASE WHEN pw52.high_52w > 0 THEN ((lp.current_close - pw52.high_52w) / pw52.high_52w * 100) END, 2) AS price_vs_52w_high_val
                FROM stock_scores sc
                JOIN stock_symbols ss ON ss.symbol = sc.symbol
                LEFT JOIN company_profile cp ON cp.ticker = sc.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
                LEFT JOIN stability_metrics sm ON sm.symbol = sc.symbol
                LEFT JOIN positioning_metrics pm ON pm.symbol = sc.symbol
                LEFT JOIN latest_prices lp ON lp.symbol = sc.symbol
                LEFT JOIN prev_prices pp ON pp.symbol = sc.symbol
                LEFT JOIN LATERAL (
                    SELECT td.rsi_14, td.macd,
                           td.sma_50, td.sma_200,
                           td.roc_20d, td.roc_60d,
                           td.roc_120d, td.roc_252d
                    FROM technical_data_daily td
                    WHERE td.symbol = sc.symbol
                    ORDER BY td.date DESC LIMIT 1
                ) tdd ON true
                LEFT JOIN LATERAL (
                    SELECT MAX(ph.high) AS high_52w
                    FROM price_daily ph
                    WHERE ph.symbol = sc.symbol
                      AND ph.date >= CURRENT_DATE - INTERVAL '52 weeks'
                ) pw52 ON true
                {where_clause}
                ORDER BY {sort_col} {sort_direction}
                LIMIT %s OFFSET %s
            """
        params_list.extend([limit, offset])
        scores = execute_with_timeout(cur, query, params_list, timeout_sec=30)

        def _f(v):
            return float(v) if v is not None else None

        items = []
        prices_missing_count = 0
        for row in scores:
            d = dict(row)

            # FAIL-FAST: Skip scores with missing price data (no fallback to 0)
            if d.get("current_price") is None or d.get("price") is None:
                prices_missing_count += 1
                continue

            # Compute 12-3 momentum: 12-month return minus 3-month (skip short-term reversal)
            roc252 = _f(d.get("tdd_roc_252d"))
            roc60 = _f(d.get("tdd_roc_60d"))
            momentum_12_3 = round(roc252 - roc60, 4) if (roc252 is not None and roc60 is not None) else roc252

            d["quality_inputs"] = {
                "return_on_equity_pct": _f(d.get("roe_pct")),
                "return_on_assets_pct": _f(d.get("roa_val")),
                "operating_margin_pct": _f(d.get("operating_margin_val")),
                "profit_margin_pct": _f(d.get("net_margin_val")),
                "debt_to_equity": _f(d.get("debt_to_equity")),
                "current_ratio": _f(d.get("current_ratio_val")),
                "quick_ratio": _f(d.get("quick_ratio_val")),
                "interest_coverage": _f(d.get("interest_coverage_val")),
            }
            d["value_inputs"] = {
                "stock_pe": _f(d.get("trailing_pe")),
                "stock_pb": _f(d.get("price_to_book")),
                "stock_ps": _f(d.get("ps_ratio_val")),
                "peg_ratio": _f(d.get("peg_ratio_val")),
                "stock_dividend_yield": _f(d.get("dividend_yield")),
                "fcf_yield": _f(d.get("fcf_yield_val")),
            }
            d["growth_inputs"] = {
                "revenue_growth_1y_pct": _f(d.get("rev_growth_1y_val")),
                "eps_growth_1y_pct": _f(d.get("eps_growth_1y_val")),
                "revenue_growth_3y_cagr": _f(d.get("rev_growth_3y_val")),
                "eps_growth_3y_cagr": _f(d.get("eps_growth_3y_val")),
                "revenue_growth_5y_cagr": _f(d.get("rev_growth_5y_val")),
                "eps_growth_5y_cagr": _f(d.get("eps_growth_5y_val")),
            }
            d["stability_inputs"] = {
                "volatility_12m": _f(d.get("volatility_12m_val")),
                "volatility_60d": _f(d.get("volatility_60d_val")),
                "volatility_30d": _f(d.get("volatility_30d_val")),
                "beta": _f(d.get("beta_val")),
                "debt_to_assets": _f(d.get("debt_to_assets_val")),
            }
            d["positioning_inputs"] = {
                "institutional_ownership_pct": _f(d.get("inst_own_val")),
                "top_10_institutions_pct": _f(d.get("vm_held_institutions")),
                "insider_ownership_pct": _f(d.get("insider_own_val")),
                "short_percent_of_float": _f(d.get("short_pct_val")),
                "short_interest_pct": _f(d.get("short_pct_val")),
                "shares_short_prior_month": d.get("shares_short_prior_month_val"),
                "short_interest_trend": d.get("short_interest_trend_val"),
            }
            d["momentum_inputs"] = {
                "current_price": _f(d.get("current_price")),
                "price_vs_sma_50": _f(d.get("price_vs_sma_50")),
                "price_vs_sma_200": _f(d.get("price_vs_sma_200")),
                "price_vs_52w_high": _f(d.get("price_vs_52w_high_val")),
                "momentum_3m": _f(d.get("tdd_roc_60d")),
                "momentum_6m": _f(d.get("tdd_roc_120d")),
                "momentum_12_3": momentum_12_3,
                "rsi": _f(d.get("tdd_rsi")),
                "macd": _f(d.get("tdd_macd")),
            }
            items.append(d)

        # FAIL-FAST: If no valid scores are available (all had missing prices), return error
        if not items and prices_missing_count > 0:
            logger.error(
                f"Scores endpoint: filtered out {prices_missing_count} scores due to missing price data. "
                f"yfinance data loading issue - cannot provide score data without prices."
            )
            return error_response(
                503,
                "data_unavailable",
                f"Price data unavailable for {prices_missing_count} symbols. yfinance data loader needs attention.",
            )

        # Check data freshness
        freshness = check_data_freshness(cur, "stock_scores", "updated_at", warning_days=7)

        # FAIL-FAST: If >50% of scores filtered due to missing prices, fail instead of returning partial results
        total_scores = prices_missing_count + len(items)
        if prices_missing_count > 0 and items:
            filter_rate = prices_missing_count / total_scores if total_scores > 0 else 0
            if filter_rate > 0.5:
                logger.error(
                    f"Scores endpoint: {prices_missing_count}/{total_scores} scores ({filter_rate*100:.1f}%) "
                    f"filtered due to missing price data. Data quality threshold exceeded."
                )
                return error_response(
                    503,
                    "data_unavailable",
                    f"Price data unavailable for {prices_missing_count}/{total_scores} symbols ({filter_rate*100:.1f}%). "
                    "Cannot provide reliable stock scores with >50% data loss.",
                )
            else:
                logger.warning(
                    f"Scores endpoint: {prices_missing_count} scores filtered (out of {total_scores})"
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
