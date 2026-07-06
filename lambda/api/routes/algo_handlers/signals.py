"""Route: algo"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from models.requests import PreTradeImpactRequest, TradePreviewRequest
from psycopg2.extensions import cursor
from pydantic import ValidationError

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    list_response,
    safe_dict_convert,
    safe_json_serialize,
    validate_api_response,
)

from shared_contracts.response_validator import ResponseValidator
from utils.validation import (
    format_decimal_string,
)

logger = logging.getLogger(__name__)


def _validate_portfolio_snapshot(cur: cursor) -> tuple[dict[str, Any], Any] | Any:
    """Fetch and validate portfolio snapshot. Returns (portfolio_dict, error_response) or (portfolio_dict, None)."""
    cur.execute("""
        SELECT total_portfolio_value, position_count FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
    """)
    port_row = cur.fetchone()
    if port_row is None:
        return None, error_response(503, "service_unavailable", "Portfolio snapshot unavailable")

    portfolio_value = float(port_row["total_portfolio_value"])
    open_positions = int(port_row["position_count"])

    if not portfolio_value or portfolio_value <= 0:
        return None, error_response(503, "service_unavailable", "Portfolio value unavailable")

    return (port_row, portfolio_value, open_positions), None


def _get_symbol_sector(cur: cursor, symbol: str) -> str | Any:
    """Get sector for symbol or return error_response."""
    cur.execute(
        """
        SELECT sector FROM company_profile WHERE ticker = %s LIMIT 1
    """,
        (symbol,),
    )
    profile_row = cur.fetchone()
    sector = profile_row["sector"] if profile_row else None

    if sector is None:
        return error_response(
            400, "sector_unknown", f"Cannot size position for {symbol}: sector not found in company_profile"
        )
    return sector


def _fetch_sector_exposure(cur: cursor) -> dict[str, Any] | Any:
    """Fetch sector exposure data. Returns dict or error_response."""
    sector_exposure = {}
    try:
        cur.execute("""
            SELECT COALESCE(cp.sector, 'Unknown') AS sector,
                   SUM(ap.position_value) AS sector_value
            FROM algo_positions ap
            LEFT JOIN company_profile cp ON cp.ticker = ap.symbol
            WHERE ap.status = 'open'
            GROUP BY cp.sector
        """)
        for sr in cur.fetchall():
            if sr["sector"]:
                sector_val_raw = sr["sector_value"]
                if sector_val_raw is None:
                    error_msg = (
                        f"Sector {sr['sector']} has NULL position_value sum — "
                        "cannot proceed without complete sector exposure"
                    )
                    logger.error(error_msg)
                    return error_response(503, "sector_exposure_incomplete", error_msg)
                # Validate type before conversion — non-numeric values cause silent failures downstream
                if not isinstance(sector_val_raw, (int, float)):
                    error_msg = (
                        f"Sector {sr['sector']} has non-numeric position_value: {type(sector_val_raw).__name__} "
                        f"(value={sector_val_raw}). Cannot compute signal without valid numeric exposure."
                    )
                    logger.error(error_msg)
                    return error_response(503, "invalid_sector_value_type", error_msg)
                try:
                    sector_val = float(sector_val_raw)
                    if sector_val < 0:
                        error_msg = (
                            f"Sector {sr['sector']} has negative exposure ({sector_val}) — data corruption detected"
                        )
                        logger.error(error_msg)
                        return error_response(503, "data_corruption", error_msg)
                except (ValueError, TypeError) as e:
                    return error_response(503, "data_format_error", f"Sector exposure not numeric: {e}")
                sector_exposure[sr["sector"]] = sector_val
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        raise RuntimeError(f"Unexpected error: {e}") from e

    return sector_exposure


def _calculate_pre_trade_impact(cur: cursor, body: dict[str, Any]) -> Any:
    """Estimate portfolio impact before entering a trade.

    Input: { symbol, entry_price?, position_dollars?, position_pct? }
    Output: sector concentration, available slots, projected position size.
    """
    try:
        try:
            req = PreTradeImpactRequest(**body)
        except ValidationError as e:
            error_details = e.errors()[0] if e.errors() else {"msg": "Validation error"}
            return error_response(
                400,
                "bad_request",
                f"Invalid request: {error_details.get('msg', 'Validation failed')}",
            )

        symbol = req.symbol

        # Portfolio snapshot
        port_data, port_error = _validate_portfolio_snapshot(cur)
        if port_error:
            return port_error
        _, portfolio_value, open_positions = port_data
        assert isinstance(portfolio_value, (int, float)) and isinstance(open_positions, int)

        # Determine position size - CRITICAL: both position_dollars and position_pct are optional,
        # but at least one must be provided. Do NOT default to implicit 0.75% — caller must specify intent.
        entry_price = req.entry_price
        if req.position_dollars:
            position_dollars = req.position_dollars
        elif req.position_pct:
            position_dollars = portfolio_value * (req.position_pct / 100)
        else:
            return error_response(
                400,
                "missing_position_size",
                "Pre-trade impact requires either position_dollars or position_pct. "
                "Cannot default to implicit 0.75% — caller must explicitly specify intended position size.",
            )

        if not entry_price or entry_price <= 0:
            return error_response(400, "invalid_entry_price", "Entry price must be provided and positive")

        shares = int(position_dollars / entry_price)
        actual_dollars = shares * entry_price
        if portfolio_value <= 0:
            return error_response(503, "service_unavailable", "Portfolio value invalid")
        pct_of_portfolio = actual_dollars / portfolio_value * 100

        # Symbol sector
        sector = _get_symbol_sector(cur, symbol)
        if isinstance(sector, dict) and "error" in str(sector):  # Check if it's an error response
            return sector

        # Current sector exposure
        sector_exposure = _fetch_sector_exposure(cur)
        if isinstance(sector_exposure, dict) and "_error" in sector_exposure:
            return sector_exposure

        if portfolio_value <= 0:
            return error_response(400, "invalid_portfolio", f"Portfolio value invalid ({portfolio_value})")

        # CRITICAL: Sector exposure must be known or explicitly 'Unknown', never silent 0.0
        if sector is None:
            return error_response(
                400, "sector_unknown", f"Cannot size position for {symbol}: sector not found in company_profile"
            )
        if sector not in sector_exposure:
            # 'Unknown' sector should exist from COALESCE in query, but validate it
            return error_response(
                503, "sector_exposure_incomplete", f"Sector exposure missing for '{sector}'. Database query incomplete."
            )

        current_sector_dollars = sector_exposure[sector]  # Explicit access, no fallback to 0.0
        projected_sector_dollars = current_sector_dollars + actual_dollars
        projected_sector_pct = projected_sector_dollars / portfolio_value * 100

        # CRITICAL: Unknown sector exposure MUST be present (query should COALESCE it).
        # Fail fast if missing to prevent silent data quality issues.
        if "Unknown" not in sector_exposure:
            logger.error("[SECTOR_RISK] Unknown sector exposure missing from query result")
            return error_response(
                503,
                "sector_exposure_incomplete",
                "Unknown sector exposure missing. Database query incomplete (check COALESCE in SQL).",
            )

        unknown_sector_exposure = sector_exposure["Unknown"]  # Explicit access, no fallback
        if not isinstance(unknown_sector_exposure, (int, float)) or unknown_sector_exposure < 0:
            return error_response(
                503,
                "data_corruption",
                f"Invalid Unknown sector exposure value: {unknown_sector_exposure}",
            )

        unknown_sector_pct = (unknown_sector_exposure / portfolio_value * 100) if portfolio_value > 0 else 0
        if unknown_sector_pct > 10:
            logger.warning(
                f"[SECTOR RISK] Unknown sector exposure is {unknown_sector_pct:.1f}% - "
                f"catch-all bucket absorbing {unknown_sector_pct:.1f}% of portfolio. "
                f"Check company_profile data completeness for undefined sectors."
            )

        max_positions = 15
        if open_positions is None:
            return error_response(503, "data_unavailable", "Position count unavailable")
        available_slots = max(0, max_positions - open_positions)
        sector_warning = sector and projected_sector_pct > 30

        response_data = {
            "symbol": symbol,
            "sector": sector,
            "entry_price": format_decimal_string(entry_price, precision=2, allow_none=True),
            "shares": shares,
            "position_dollars": format_decimal_string(actual_dollars, precision=2),
            "pct_of_portfolio": format_decimal_string(pct_of_portfolio, precision=2),
            "portfolio_value": format_decimal_string(portfolio_value, precision=2),
            "open_positions": open_positions,
            "available_slots": available_slots,
            "sector_exposure": {
                "current_pct": format_decimal_string(
                    (current_sector_dollars / portfolio_value * 100),
                    precision=2,
                ),
                "projected_pct": format_decimal_string(projected_sector_pct, precision=2),
                "warning": sector_warning,
                "warning_msg": (
                    f"Sector {sector} would reach {projected_sector_pct:.1f}% (limit 30%)" if sector_warning else None
                ),
            },
        }

        # Include unknown sector exposure warning if significant
        if unknown_sector_pct > 0:
            response_data["unknown_sector_exposure_pct"] = round(unknown_sector_pct, 2)
            if unknown_sector_pct > 10:
                response_data["unknown_sector_warning"] = (
                    f"Unknown sector has {unknown_sector_pct:.1f}% of portfolio - "
                    f"may mask concentration risk if real sectors are undefined"
                )

        return json_response(200, response_data)

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "calculate pre-trade impact")
        return error_response(code, error_type, message)


@db_route_handler("calculate trade preview")  # type: ignore[untyped-decorator]
def _calculate_trade_preview(cur: cursor, body: dict[str, Any]) -> Any:
    """Calculate position preview before trade entry.

    Input: { symbol, entry_price, stop_loss_price }
    Output: { shares, pct_of_portfolio, risk_amount, targets {...} }
    """
    try:
        try:
            req = TradePreviewRequest(**body)
        except ValidationError as e:
            error_details = e.errors()[0] if e.errors() else {"msg": "Validation error"}
            return error_response(
                400,
                "bad_request",
                f"Invalid request: {error_details.get('msg', 'Validation failed')}",
            )

        symbol = req.symbol
        entry_price = req.entry_price
        stop_loss_price = req.stop_loss_price

        cur.execute("""
            SELECT total_portfolio_value FROM algo_portfolio_snapshots
            ORDER BY snapshot_date DESC LIMIT 1
        """)
        portfolio_row = cur.fetchone()
        if portfolio_row is None:
            return error_response(
                503,
                "service_unavailable",
                "Portfolio snapshot unavailable for position sizing",
            )

        portfolio_value_raw = portfolio_row.get("total_portfolio_value")
        if portfolio_value_raw is None:
            return error_response(
                503,
                "service_unavailable",
                "Portfolio value field is NULL — snapshot data incomplete",
            )

        try:
            portfolio_value = float(portfolio_value_raw)
        except (TypeError, ValueError):
            return error_response(
                503,
                "data_type_error",
                f"Portfolio value is not numeric: {portfolio_value_raw} ({type(portfolio_value_raw).__name__})",
            )

        if portfolio_value <= 0:
            return error_response(
                503,
                "service_unavailable",
                f"Portfolio value invalid ({portfolio_value}). Must be positive for position sizing.",
            )

        risk_amount = None
        if stop_loss_price and entry_price > stop_loss_price:
            risk_amount = entry_price - stop_loss_price

        base_risk_pct = 0.0075
        position_dollars = portfolio_value * base_risk_pct
        if entry_price <= 0:
            return error_response(400, "invalid_entry_price", "Entry price must be positive")
        shares = int(position_dollars / entry_price)
        if portfolio_value <= 0:
            return error_response(503, "service_unavailable", "Portfolio value invalid")
        pct_of_portfolio = shares * entry_price / portfolio_value * 100
        total_risk_amount = (risk_amount * shares) if risk_amount else None

        targets = {}
        if risk_amount and risk_amount > 0:
            for r_multiple in [1, 2, 3]:
                target_price = entry_price + (risk_amount * r_multiple)
                profit_per_share = target_price - entry_price
                profit_total = profit_per_share * shares
                alloc_pct = [0.50, 0.30, 0.20][r_multiple - 1]
                shares_to_sell = int(shares * alloc_pct)
                targets[f"target_{r_multiple}"] = {
                    "r_multiple": f"{r_multiple}R",
                    "price": format_decimal_string(target_price, precision=2),
                    "shares_to_sell": shares_to_sell,
                    "profit_at_target": format_decimal_string(profit_total, precision=2),
                }

        return json_response(
            200,
            {
                "symbol": symbol,
                "entry_price": format_decimal_string(entry_price, precision=2),
                "stop_loss_price": (
                    format_decimal_string(stop_loss_price, precision=2, allow_none=False) if stop_loss_price else None
                ),
                "shares": shares,
                "pct_of_portfolio": format_decimal_string(pct_of_portfolio, precision=2),
                "risk_amount": (format_decimal_string(total_risk_amount, precision=2) if total_risk_amount else None),
                "position_value": format_decimal_string(shares * entry_price, precision=2),
                "targets": targets,
                "portfolio_value": format_decimal_string(portfolio_value, precision=2),
            },
        )

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "calculate trade preview")
        return error_response(code, error_type, message)


@db_route_handler("fetch rejection funnel")  # type: ignore[untyped-decorator]
@validate_api_response("sig_eval")  # type: ignore[untyped-decorator]
def _get_rejection_funnel(cur: cursor) -> Any:
    """Get signal rejection funnel with detailed breakdown by filter.

    SWING SCORE REMOVAL: This endpoint is deprecated. The swing_trader_scores table
    no longer exists and has been retired in favor of composite_score from stock_scores.
    Returns 503 to indicate endpoint is no longer available.
    """
    error_msg = (
        "Signal rejection funnel endpoint has been retired. "
        "The swing_trader_scores table is no longer maintained. "
        "Swing score analysis has been replaced with composite_score from stock_scores table."
    )
    logger.warning(f"Deprecated endpoint called: /api/algo/rejection-funnel")
    return error_response(503, "deprecated_endpoint", error_msg)


_TIER_CONFIG = {
    "confirmed_uptrend": {
        "description": "Confirmed uptrend - full deployment",
        "min_pct": 70,
        "max_pct": 100,
        "risk_mult": 1.0,
        "risk_multiplier": 1.0,
        "max_new": 5,
        "max_new_positions_today": 5,
        "halt": False,
        "halt_new_entries": False,
        "min_grade": "B",
    },
    "uptrend_under_pressure": {
        "description": "Uptrend under pressure - reduced exposure",
        "min_pct": 45,
        "max_pct": 70,
        "risk_mult": 0.6,
        "risk_multiplier": 0.6,
        "max_new": 3,
        "max_new_positions_today": 3,
        "halt": False,
        "halt_new_entries": False,
        "min_grade": "B",
    },
    "caution": {
        "description": "Caution - entries halted unless exceptional",
        "min_pct": 25,
        "max_pct": 45,
        "risk_mult": 0.3,
        "risk_multiplier": 0.3,
        "max_new": 1,
        "max_new_positions_today": 1,
        "halt": True,
        "halt_new_entries": True,
        "min_grade": "A",
    },
    "correction": {
        "description": "Market correction - preserve capital",
        "min_pct": 0,
        "max_pct": 25,
        "risk_mult": 0.2,
        "risk_multiplier": 0.2,
        "max_new": 0,
        "max_new_positions_today": 0,
        "halt": True,
        "halt_new_entries": True,
        "min_grade": "A+",
    },
}


def _get_rejection_reason_description(reason: str) -> str:
    """Generate human-readable description for rejection reason."""
    # MEDIUM-FIX: Explicit None handling instead of OR fallback
    reason_lower = reason.lower() if reason is not None else ""
    descriptions = {
        "52w low": "Price within 5% of 52-week low (weak signal near lows)",
        "52-week low proximity": "Price within 5% of 52-week low (weak signal near lows)",
        "sector cap": "Already maximum sector exposure (sector limit reached)",
        "sector concentration": "Already maximum sector exposure (sector limit reached)",
        "industry cap": "Already maximum industry exposure (industry limit reached)",
        "industry concentration": "Already maximum industry exposure (industry limit reached)",
        "stage filter": "Does not meet technical stage requirements",
        "volume": "Insufficient volume (liquidity concern)",
        "relative strength": "Weak relative strength compared to peers",
        "rs": "Weak relative strength compared to peers",
        "market regime": "Market conditions unfavorable (not in confirmed uptrend)",
        "halt": "Position in halted/restricted status",
        "sqs": "Signal quality score below threshold (SQS < 60)",
        "signal quality": "Signal quality score below threshold",
    }

    for key, desc in descriptions.items():
        if key in reason_lower:
            return desc

    return reason or "Unknown rejection reason"


@db_route_handler("fetch stock scores")  # type: ignore[untyped-decorator]
@validate_api_response("scores")  # type: ignore[untyped-decorator]
def _get_swing_scores(cur: cursor, limit: int = 100, min_score: float | None = None, symbol: str | None = None) -> Any:
    """Get top stock candidates by composite score (SWING SCORE MIGRATION: now uses stock_scores).

    DEPRECATED: API renamed from swing_scores to stock_scores but endpoint kept for backward compat.
    Now queries stock_scores table using composite_score (primary ranking metric).
    """
    try:
        # Use psycopg2.sql for safe SQL composition
        filters = [psycopg2.sql.SQL("s.date >= CURRENT_DATE - INTERVAL '14 days'")]
        query_params: list[Any] = []
        if min_score is not None:
            filters.append(psycopg2.sql.SQL("s.composite_score >= %s"))
            query_params.append(min_score)
        if symbol:
            filters.append(psycopg2.sql.SQL("s.symbol = %s"))
            query_params.append(symbol.upper())
        where_clause = psycopg2.sql.SQL(" AND ").join(filters)
        query_params.append(limit)
        query = psycopg2.sql.SQL("""
                SELECT
                    s.symbol, s.date, s.composite_score AS swing_score,
                    CASE
                        WHEN s.composite_score >= 85 THEN 'A+'
                        WHEN s.composite_score >= 75 THEN 'A'
                        WHEN s.composite_score >= 65 THEN 'B'
                        WHEN s.composite_score >= 55 THEN 'C'
                        ELSE 'D'
                    END AS grade,
                    TRUE AS pass_gates,
                    NULL AS fail_reason,
                    jsonb_build_object(
                        'quality_score', s.quality_score,
                        'growth_score', s.growth_score,
                        'momentum_score', s.momentum_score,
                        'rs_percentile', s.rs_percentile
                    ) AS components,
                    cp.sector, cp.industry,
                    t.weinstein_stage AS stage, t.minervini_trend_score AS trend_template_score,
                    jsonb_build_object('weinstein_stage', t.weinstein_stage, 'trend_template_score', t.minervini_trend_score, 'stage_substage', 'Stage ' || COALESCE(t.weinstein_stage::text, '')) AS details
                FROM stock_scores s
                LEFT JOIN company_profile cp ON s.symbol = cp.ticker
                LEFT JOIN trend_template_data t ON s.symbol = t.symbol AND s.date = t.date
                WHERE {where_clause}
                ORDER BY s.date DESC, s.composite_score DESC
                LIMIT %s
            """).format(where_clause=where_clause)
        cur.execute(query, query_params)
        scores = cur.fetchall()
        return list_response([safe_json_serialize(safe_dict_convert(s)) for s in scores])
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch stock scores")
        return error_response(code, error_type, message)


@db_route_handler("fetch stock scores history")  # type: ignore[untyped-decorator]
@validate_api_response("scores")  # type: ignore[untyped-decorator]
def _get_swing_scores_history(cur: cursor, days: int = 30) -> Any:
    """Get stock scores historical data (SWING SCORE MIGRATION: now uses stock_scores.composite_score)."""
    try:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
        cur.execute(
            """
                SELECT date AS eval_date,
                    COUNT(CASE WHEN composite_score >= 85 THEN 1 END) AS grade_aplus,
                    COUNT(CASE WHEN composite_score >= 75 THEN 1 END) AS grade_a,
                    COUNT(CASE WHEN composite_score >= 50 THEN 1 END) AS pass_count,
                    COUNT(*) AS total_candidates,
                    ROUND(AVG(composite_score)::NUMERIC, 1) AS avg_score
                FROM stock_scores
                WHERE date >= %s AND data_unavailable = FALSE
                GROUP BY date
                ORDER BY date ASC
            """,
            (cutoff_date,),
        )
        history = cur.fetchall()
        return list_response([safe_json_serialize(safe_dict_convert(h)) for h in history])
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Failed to fetch stock scores history: {type(e).__name__}: {e!s}\n  Operation: Query stock_scores with days parameter\n  Endpoint: GET /api/algo/swing-scores-history",
            exc_info=True,
        )
        return error_response(500, "internal_error", "Failed to fetch stock scores history")
