"""Route: algo"""

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
)

from shared_contracts.response_validator import ResponseValidator
from utils.validation import (
    format_decimal_string,
)

logger = logging.getLogger(__name__)


def _calculate_pre_trade_impact(cur: cursor, body: dict[str, Any]) -> dict[str, Any]:
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
        cur.execute("""
            SELECT total_portfolio_value, position_count FROM algo_portfolio_snapshots
            ORDER BY snapshot_date DESC LIMIT 1
        """)
        port_row = cur.fetchone()
        if port_row is None:
            return error_response(503, "service_unavailable", "Portfolio snapshot unavailable")
        portfolio_value = float(port_row["total_portfolio_value"])
        open_positions = int(port_row["position_count"])

        if not portfolio_value or portfolio_value <= 0:
            return error_response(503, "service_unavailable", "Portfolio value unavailable")

        # Determine position size
        entry_price = req.entry_price
        if req.position_dollars:
            position_dollars = req.position_dollars
        elif req.position_pct:
            position_dollars = portfolio_value * (req.position_pct / 100)
        else:
            position_dollars = portfolio_value * 0.0075  # default 0.75% risk unit

        shares = int(position_dollars / entry_price) if entry_price and entry_price > 0 else 0
        actual_dollars = shares * entry_price if entry_price else position_dollars
        pct_of_portfolio = (actual_dollars / portfolio_value * 100) if portfolio_value > 0 else 0

        # Symbol sector
        cur.execute(
            """
            SELECT sector FROM company_profile WHERE ticker = %s LIMIT 1
        """,
            (symbol,),
        )
        profile_row = cur.fetchone()
        sector = profile_row["sector"] if profile_row else None

        # Current sector exposure
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
                    sector_val = float(sr["sector_value"])
                    if sector_val is None:
                        return error_response(503, "data_unavailable", "Sector exposure data incomplete")
                    sector_exposure[sr["sector"]] = sector_val
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Unexpected error: {e}") from e

        current_sector_dollars = sector_exposure.get(sector, 0.0) if sector else 0.0
        projected_sector_dollars = current_sector_dollars + actual_dollars
        projected_sector_pct = (projected_sector_dollars / portfolio_value * 100) if portfolio_value > 0 else 0

        max_positions = 15
        if open_positions is None:
            return error_response(503, "data_unavailable", "Position count unavailable")
        available_slots = max(0, max_positions - open_positions)
        sector_warning = sector and projected_sector_pct > 30

        return json_response(
            200,
            {
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
                        ((current_sector_dollars / portfolio_value * 100) if portfolio_value > 0 else 0),
                        precision=2,
                    ),
                    "projected_pct": format_decimal_string(projected_sector_pct, precision=2),
                    "warning": sector_warning,
                    "warning_msg": (
                        f"Sector {sector} would reach {projected_sector_pct:.1f}% (limit 30%)"
                        if sector_warning
                        else None
                    ),
                },
            },
        )

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "calculate pre-trade impact")
        return error_response(code, error_type, message)


@db_route_handler("calculate trade preview")
def _calculate_trade_preview(cur: cursor, body: dict[str, Any]) -> dict[str, Any]:
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
        portfolio_value = float(portfolio_row["total_portfolio_value"]) if portfolio_row else None

        if not portfolio_value or portfolio_value <= 0:
            return error_response(
                503,
                "service_unavailable",
                "Portfolio value unavailable for position sizing",
            )

        risk_amount = None
        if stop_loss_price and entry_price > stop_loss_price:
            risk_amount = entry_price - stop_loss_price

        base_risk_pct = 0.0075
        position_dollars = portfolio_value * base_risk_pct
        shares = int(position_dollars / entry_price) if entry_price > 0 else 0
        pct_of_portfolio = (shares * entry_price / portfolio_value * 100) if portfolio_value > 0 else 0
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


@db_route_handler("fetch rejection funnel")
def _get_rejection_funnel(cur: cursor) -> dict[str, Any]:
    """Get signal rejection funnel with detailed breakdown by filter."""
    try:
        today = date.today()

        # Get all candidate counts in single query
        cur.execute("""
                SELECT
                    COUNT(DISTINCT symbol) as total_signals,
                    COUNT(DISTINCT symbol) as scored,
                    COUNT(DISTINCT symbol) FILTER (WHERE score >= 60) as high_quality
                FROM swing_trader_scores
                WHERE date >= CURRENT_DATE - INTERVAL '14 days'
            """)
        row = cur.fetchone()
        if not row:
            error_msg = "No signal data available in swing_trader_scores (no records in last 14 days)"
            logger.error(error_msg)
            return error_response(503, "no_data", error_msg)

        row_data = safe_json_serialize(safe_dict_convert(row))
        # Fail-fast: required fields must be present
        required_fields = ["total_signals", "scored", "high_quality"]
        missing = [f for f in required_fields if row_data.get(f) is None]
        if missing:
            error_msg = f"Signal data incomplete: missing {missing}"
            logger.error(error_msg)
            return error_response(503, "incomplete_data", error_msg)

        initial_count = int(row_data["total_signals"])
        scored_count = int(row_data["scored"])
        high_quality_count = int(row_data["high_quality"])

        # Build funnel stages with rejection reasons
        funnel = [
            {
                "stage": "All Signals Generated",
                "count": initial_count,
                "pct": 100,
                "rejection_reason": None,
                "rejection_count": 0,
                "rejection_pct": 0,
            }
        ]

        if initial_count > 0:
            scored_rejection = initial_count - scored_count
            scored_pct = round((scored_count / initial_count * 100), 2) if initial_count else 0

            funnel.append(
                {
                    "stage": "Passed Quality Filters",
                    "count": scored_count,
                    "pct": scored_pct,
                    "rejection_reason": "Failed SQS calculation or data validation",
                    "rejection_count": scored_rejection,
                    "rejection_pct": (round((scored_rejection / initial_count * 100), 2) if initial_count else 0),
                }
            )

            if scored_count > 0:
                hq_rejection = scored_count - high_quality_count
                hq_pct = round((high_quality_count / scored_count * 100), 2) if scored_count else 0

                funnel.append(
                    {
                        "stage": "High-Quality Candidates (SQS ≥ 60)",
                        "count": high_quality_count,
                        "pct": hq_pct,
                        "rejection_reason": "Low signal quality score (SQS < 60)",
                        "rejection_count": hq_rejection,
                        "rejection_pct": (round((hq_rejection / scored_count * 100), 2) if scored_count else 0),
                    }
                )

        # Get detailed rejection reasons grouped by reason type (top reasons across all tiers)
        rejected_list = []
        try:
            cur.execute(
                """
                    SELECT rejection_reason, COUNT(*) as count
                    FROM filter_rejection_log
                    WHERE eval_date = %s AND rejection_reason IS NOT NULL AND rejection_reason != ''
                    GROUP BY rejection_reason
                    ORDER BY count DESC
                    LIMIT 10
                """,
                (today,),
            )

            for row in cur.fetchall():
                reason_text = row["rejection_reason"]
                count = row["count"]
                if reason_text is None or count is None:
                    continue
                rejected_list.append(
                    {
                        "evaluation_reason": reason_text,
                        "description": _get_rejection_reason_description(reason_text),
                        "n": count,
                    }
                )
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
            rejected_list = []

        result = {
            "funnel": funnel,
            "summary": {
                "total_initial": initial_count,
                "total_passed": high_quality_count,
                "total_rejected": initial_count - high_quality_count,
                "pass_rate_pct": (round((high_quality_count / initial_count * 100), 2) if initial_count else 0),
            },
            "rejected": rejected_list,
            "total": initial_count,
            "t1": initial_count - scored_count if initial_count > 0 else 0,
            "t5": high_quality_count,
            "avg_score": 0,
        }
        is_valid, error_msg = ResponseValidator.validate_endpoint_response("sig_eval", result)
        if not is_valid:
            logger.error(f"Endpoint response validation failed: {error_msg}")
            return error_response(500, "response_validation_error", error_msg or "Validation failed")
        return json_response(200, result)
    except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
        logger.error(
            f"Failed to fetch rejection funnel: {type(e).__name__}: {e}\n  Operation: Query candidate_signals_reject table\n  Endpoint: GET /api/algo/rejection-funnel"
        )
        raise
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        return json_response(
            200,
            {
                "funnel": [],
                "summary": {
                    "total_initial": 0,
                    "total_passed": 0,
                    "total_rejected": 0,
                    "pass_rate_pct": 0,
                },
                "rejected": [],
            },
        )


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
        "min_swing_grade": "B",
        "min_swing_score": 60.0,
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
        "min_swing_grade": "B",
        "min_swing_score": 65.0,
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
        "min_swing_grade": "A",
        "min_swing_score": 75.0,
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
        "min_swing_grade": "A+",
        "min_swing_score": 100.0,
    },
}


def _get_rejection_reason_description(reason: str) -> str:
    """Generate human-readable description for rejection reason."""
    reason_lower = (reason or "").lower()
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


@db_route_handler("fetch swing scores")
def _get_swing_scores(
    cur: cursor, limit: int = 100, min_score: float | None = None, symbol: str | None = None
) -> dict[str, Any]:
    """Get swing trade candidates with scoring."""
    try:
        # Use psycopg2.sql for safe SQL composition
        filters = [psycopg2.sql.SQL("s.date >= CURRENT_DATE - INTERVAL '14 days'")]
        query_params: list[Any] = []
        if min_score is not None:
            filters.append(psycopg2.sql.SQL("s.score >= %s"))
            query_params.append(min_score)
        if symbol:
            filters.append(psycopg2.sql.SQL("s.symbol = %s"))
            query_params.append(symbol.upper())
        where_clause = psycopg2.sql.SQL(" AND ").join(filters)
        query_params.append(limit)
        query = psycopg2.sql.SQL("""
                SELECT
                    s.symbol, s.date, s.score AS swing_score,
                    s.components->>'grade' AS grade,
                    COALESCE((s.components->>'pass_gates')::boolean, false) AS pass_gates,
                    s.components->>'fail_reason' AS fail_reason,
                    s.components AS components,
                    cp.sector, cp.industry,
                    t.weinstein_stage AS stage, t.minervini_trend_score AS trend_template_score,
                    jsonb_build_object('weinstein_stage', t.weinstein_stage, 'trend_template_score', t.minervini_trend_score, 'stage_substage', 'Stage ' || COALESCE(t.weinstein_stage::text, '')) AS details
                FROM swing_trader_scores s
                LEFT JOIN company_profile cp ON s.symbol = cp.ticker
                LEFT JOIN trend_template_data t ON s.symbol = t.symbol AND s.date = t.date
                WHERE {where_clause}
                ORDER BY s.date DESC, s.score DESC
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
        code, error_type, message = handle_db_error(e, "fetch swing scores")
        return error_response(code, error_type, message)


@db_route_handler("fetch swing scores history")
def _get_swing_scores_history(cur: cursor, days: int = 30) -> dict[str, Any]:
    """Get swing scores historical data."""
    try:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
        cur.execute(
            """
                SELECT date AS eval_date,
                    COUNT(CASE WHEN (components->>'grade') = 'A+' THEN 1 END) AS grade_aplus,
                    COUNT(CASE WHEN (components->>'grade') = 'A'  THEN 1 END) AS grade_a,
                    COUNT(CASE WHEN (components->>'pass_gates')::boolean IS TRUE THEN 1 END) AS pass_count,
                    COUNT(*) AS total_candidates,
                    ROUND(AVG(score)::NUMERIC, 1) AS avg_score
                FROM swing_trader_scores
                WHERE date >= %s
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
            f"Failed to fetch swing scores history: {type(e).__name__}: {e!s}\n  Operation: Query algo_swing_score_history with days parameter\n  Endpoint: GET /api/algo/swing-scores-history",
            exc_info=True,
        )
        return error_response(500, "internal_error", "Failed to fetch swing scores history")
