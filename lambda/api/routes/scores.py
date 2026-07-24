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
            where_clause += " AND sc.data_completeness >= 70 AND (sc.data_unavailable = false OR sc.data_unavailable IS NULL)"

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
                    qm.debt_to_assets AS debt_to_assets_val,
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
                    pm.institutional_ownership_pct AS inst_own_val,
                    pm.insider_ownership_pct AS insider_own_val,
                    pm.short_interest_pct AS short_pct_val,
                    pm.shares_short_prior_month AS shares_short_prior_month_val,
                    pm.short_interest_trend AS short_interest_trend_val,
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
                    (mm.symbol IS NULL OR mm.data_unavailable = TRUE) AS _momentum_data_unavailable
                FROM filtered_scores fs
                LEFT JOIN company_profile cp ON cp.ticker = fs.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = fs.symbol
                LEFT JOIN quality_metrics qm ON qm.symbol = fs.symbol
                LEFT JOIN growth_metrics gm ON gm.symbol = fs.symbol
                LEFT JOIN stability_metrics sm ON sm.symbol = fs.symbol
                LEFT JOIN positioning_metrics pm ON pm.symbol = fs.symbol
                LEFT JOIN momentum_metrics mm ON mm.symbol = fs.symbol
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
                "return_on_assets_pct": d.get("roa_val"),
                "return_on_invested_capital_pct": d.get("roic"),  # May be None if not in response
                "gross_margin_pct": d.get("gross_margin"),  # May be None if not in response
                "operating_margin_pct": d.get("operating_margin_val"),
                "profit_margin_pct": d.get("net_margin_val"),
                "ebitda_margin_pct": d.get("ebitda_margin"),  # May be None
                "fcf_to_net_income": d.get("fcf_to_ni"),  # May be None
                "operating_cf_to_net_income": d.get("ocf_to_ni"),  # May be None
                "debt_to_equity": d.get("debt_to_equity"),
                "current_ratio": d.get("current_ratio_val"),
                "quick_ratio": d.get("quick_ratio_val"),
                "earnings_surprise_avg": d.get("earnings_surprise"),  # May be None
                "eps_growth_stability": d.get("eps_growth_stability"),  # May be None
                "earnings_beat_rate": d.get("earnings_beat_rate"),  # May be None
                "consecutive_positive_quarters": d.get("consecutive_pos_q"),  # May be None
                "estimate_revision_direction": d.get("revision_direction"),  # May be None
                "revision_activity_30d": d.get("revision_activity_30d"),  # May be None
                "estimate_momentum_60d": d.get("estimate_momentum_60d"),  # May be None
                "estimate_momentum_90d": d.get("estimate_momentum_90d"),  # May be None
                "revision_trend_score": d.get("revision_trend_score"),  # May be None
                "payout_ratio": d.get("payout_ratio"),  # May be None
                "free_cashflow": d.get("free_cashflow"),  # May be None
                "operating_cashflow": d.get("operating_cashflow"),  # May be None
                "total_debt": d.get("total_debt"),  # May be None
                "total_cash": d.get("total_cash"),  # May be None
                "cash_per_share": d.get("cash_per_share"),  # May be None
                "earnings_growth_pct": d.get("earnings_growth"),  # May be None
                "revenue_growth_pct": d.get("revenue_growth"),  # May be None
                "earnings_growth_4q_avg": d.get("earnings_growth_4q_avg"),  # May be None
                "interest_coverage": d.get("interest_coverage_val"),
                "debt_to_assets": d.get("debt_to_assets_val"),
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
                "stock_forward_pe": d.get("forward_pe"),  # May be None
                "stock_pb": d.get("price_to_book"),
                "stock_ps": d.get("ps_ratio_val"),
                "peg_ratio": d.get("peg_ratio_val"),
                "stock_ev_ebitda": d.get("ev_ebitda"),  # May be None
                "stock_ev_revenue": d.get("ev_revenue"),  # May be None
                "fcf_yield": d.get("fcf_yield_val"),
                "stock_dividend_yield": d.get("dividend_yield"),
            }

            # Growth Inputs: Revenue and EPS growth
            d["growth_inputs"] = {
                "revenue_growth_1y_pct": d.get("rev_growth_1y_val"),
                "eps_growth_1y_pct": d.get("eps_growth_1y_val"),
                "revenue_growth_3y_cagr": d.get("rev_growth_3y_val"),
                "eps_growth_3y_cagr": d.get("eps_growth_3y_val"),
                "revenue_growth_5y_cagr": d.get("rev_growth_5y_val"),
                "eps_growth_5y_cagr": d.get("eps_growth_5y_val"),
                "net_income_growth_yoy": d.get("net_income_growth_yoy"),  # May be None
                "operating_income_growth_yoy": d.get("op_income_growth_yoy"),  # May be None
                "gross_margin_trend": d.get("gross_margin_trend"),  # May be None
                "operating_margin_trend": d.get("op_margin_trend"),  # May be None
                "net_margin_trend": d.get("net_margin_trend"),  # May be None
                "roe_trend": d.get("roe_trend"),  # May be None
                "sustainable_growth_rate": d.get("sustainable_growth_rate"),  # May be None
                "quarterly_growth_momentum": d.get("quarterly_growth_momentum"),  # May be None
                "fcf_growth_yoy": d.get("fcf_growth_yoy"),  # May be None
                "ocf_growth_yoy": d.get("ocf_growth_yoy"),  # May be None
                "asset_growth_yoy": d.get("asset_growth_yoy"),  # May be None
            }

            # Positioning Inputs: Ownership and short interest
            d["positioning_inputs"] = {
                "institutional_ownership_pct": d.get("inst_own_val"),
                "top_10_institutions_pct": d.get("top_10_inst_pct"),  # May be None
                "institutional_holders_count": d.get("inst_holders_count"),  # May be None
                "insider_ownership_pct": d.get("insider_own_val"),
                "short_interest_pct": d.get("short_pct_val"),
                "short_percent_of_float": d.get("short_pct_float"),  # May be None
                "short_interest_trend": d.get("short_interest_trend_val"),
                "shares_short_prior_month": d.get("shares_short_prior_month_val"),
                "short_ratio": d.get("days_to_cover"),  # May be None
                "ad_rating": d.get("ad_rating"),  # May be None
            }

            # Stability Inputs: Volatility, beta, financial stability
            # NOTE: Only fields computed by load_risk_metrics_daily.py are included
            # (downside_volatility, max_drawdown_52w, volume_consistency, etc. are not computed by any loader)
            d["stability_inputs"] = {
                "volatility_12m": d.get("volatility_12m_val"),
                "volatility_60d": d.get("volatility_60d_val"),
                "volatility_30d": d.get("volatility_30d_val"),
                "beta": d.get("beta_val"),
                "debt_to_assets": d.get("debt_to_assets_val"),
            }

        items = []
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

            # Debug: Log if factor inputs were added
            if "quality_inputs" in d:
                logger.debug(f"Factor inputs added for {d.get('symbol')}")
            else:
                logger.warning(f"Factor inputs NOT added for {d.get('symbol')} - quality_inputs missing after _build_factor_inputs call")

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

        # CRITICAL FIX: Return scores in standard paginated format
        # Dashboard/responseNormalizer expects {statusCode: 200, items: [...], pagination: {...}} format
        # This matches other paginated endpoints and works with frontend schema validation
        items_count = len(items) if items else 0
        # If we got fewer items than requested, we've hit the end of results
        # Otherwise, we estimate there might be more results
        is_last_page = items_count < limit
        estimated_total = offset + items_count if is_last_page else offset + limit + 1

        result = {
            "statusCode": 200,
            "items": items,
            "pagination": {
                "total": estimated_total,
                "limit": limit,
                "offset": offset,
                "page": (offset // limit) + 1 if limit > 0 else 1,
                "totalPages": ((estimated_total - 1) // limit) + 1 if limit > 0 else 1,
            }
        }
        if freshness:
            result["data_freshness"] = freshness
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
