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
                "Cannot default to implicit 0.75% — caller must explicitly specify intended position size."
            )

        if not entry_price or entry_price <= 0:
            return error_response(400, "invalid_entry_price", "Entry price must be provided and positive")

        shares = int(position_dollars / entry_price)
        actual_dollars = shares * entry_price
        if portfolio_value <= 0:
            return error_response(503, "service_unavailable", "Portfolio value invalid")
        pct_of_portfolio = (actual_dollars / portfolio_value * 100)

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
                    sector_val_raw = sr["sector_value"]
                    if sector_val_raw is None:
                        logger.warning(f"Sector {sr['sector']} has NULL position_value sum — skipping")
                        continue
                    try:
                        sector_val = float(sector_val_raw)
                        if sector_val < 0:
                            logger.warning(f"Sector {sr['sector']} has negative exposure ({sector_val}) — data corruption")
                            continue
                    except (ValueError, TypeError) as e:
                        return error_response(503, "data_format_error", f"Sector exposure not numeric: {e}")
                    sector_exposure[sr["sector"]] = sector_val
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Unexpected error: {e}") from e

        if portfolio_value <= 0:
            return error_response(400, "invalid_portfolio", f"Portfolio value invalid ({portfolio_value})")

        # CRITICAL: Sector exposure must be known or explicitly 'Unknown', never silent 0.0
        if sector is None:
            return error_response(400, "sector_unknown", f"Cannot size position for {symbol}: sector not found in company_profile")
        if sector not in sector_exposure:
            # 'Unknown' sector should exist from COALESCE in query, but validate it
            return error_response(503, "sector_exposure_incomplete", f"Sector exposure missing for '{sector}'. Database query incomplete.")

        current_sector_dollars = sector_exposure[sector]  # Explicit access, no fallback to 0.0
        projected_sector_dollars = current_sector_dollars + actual_dollars
        projected_sector_pct = projected_sector_dollars / portfolio_value * 100

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
                        (current_sector_dollars / portfolio_value * 100),
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
        if entry_price <= 0:
            return error_response(400, "invalid_entry_price", "Entry price must be positive")
        shares = int(position_dollars / entry_price)
        if portfolio_value <= 0:
            return error_response(503, "service_unavailable", "Portfolio value invalid")
        pct_of_portfolio = (shares * entry_price / portfolio_value * 100)
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
def _get_rejection_funnel(cur: cursor) -> Any:  # noqa: C901
    """Get signal rejection funnel with detailed breakdown by filter."""
    try:
        today = date.today()

        # Get all candidate counts in single query using score thresholds for funnel tiers
        cur.execute("""
                SELECT
                    COUNT(DISTINCT symbol) as total_signals,
                    COUNT(DISTINCT symbol) FILTER (WHERE score > 0) as t1_count,
                    COUNT(DISTINCT symbol) FILTER (WHERE score >= 40) as t2_count,
                    COUNT(DISTINCT symbol) FILTER (WHERE score >= 50) as t3_count,
                    COUNT(DISTINCT symbol) FILTER (WHERE score >= 55) as t4_count,
                    COUNT(DISTINCT symbol) FILTER (WHERE score >= 60) as t5_count,
                    ROUND(AVG(score)::numeric, 1) as avg_score,
                    MAX(date) as signal_date
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
        required_fields = ["total_signals", "t1_count", "t5_count"]
        missing = [f for f in required_fields if row_data.get(f) is None]
        if missing:
            error_msg = f"Signal data incomplete: missing {missing}"
            logger.error(error_msg)
            return error_response(503, "incomplete_data", error_msg)

        initial_count = int(row_data["total_signals"])
        t1_count = int(row_data["t1_count"])

        t2_val = row_data.get("t2_count")
        if t2_val is None:
            logger.error("Signal rejection funnel data missing t2_count — cannot generate funnel tiers")
            return error_response(503, "incomplete_data", "Signal tier counts missing: t2_count")
        t2_count = int(t2_val)

        t3_val = row_data.get("t3_count")
        if t3_val is None:
            logger.error("Signal rejection funnel data missing t3_count — cannot generate funnel tiers")
            return error_response(503, "incomplete_data", "Signal tier counts missing: t3_count")
        t3_count = int(t3_val)

        t4_val = row_data.get("t4_count")
        if t4_val is None:
            logger.error("Signal rejection funnel data missing t4_count — cannot generate funnel tiers")
            return error_response(503, "incomplete_data", "Signal tier counts missing: t4_count")
        t4_count = int(t4_val)

        t5_val = row_data.get("t5_count")
        if t5_val is None:
            logger.error("Signal rejection funnel data missing t5_count — cannot generate funnel tiers")
            return error_response(503, "incomplete_data", "Signal tier counts missing: t5_count")
        high_quality_count = int(t5_val)

        if initial_count <= 0 or high_quality_count <= 0:
            logger.error(f"Invalid tier counts: initial={initial_count}, t5={high_quality_count}")
            return error_response(503, "invalid_data", "Signal tiers have zero/negative counts")

        computed_avg_score = float(row_data["avg_score"]) if row_data.get("avg_score") is not None else None
        signal_date = row_data.get("signal_date")

        def _funnel_stage(stage: str, count: int, prior: int, reason: str | None) -> dict[str, Any]:
            if initial_count <= 0:
                raise ValueError("CRITICAL: Initial count is zero — cannot calculate funnel percentages")
            pct = round((count / initial_count * 100), 2)
            rejected = prior - count
            if prior <= 0:
                raise ValueError(f"CRITICAL: Prior count is zero/negative ({prior}) for stage {stage} — cannot calculate rejection %")
            rej_pct = round((rejected / prior * 100), 2)
            return {
                "stage": stage,
                "count": count,
                "pct": pct,
                "rejection_reason": reason,
                "rejection_count": rejected,
                "rejection_pct": rej_pct,
            }

        funnel = [
            {
                "stage": "All Evaluated",
                "count": initial_count,
                "pct": 100,
                "rejection_reason": None,
                "rejection_count": 0,
                "rejection_pct": 0,
            }
        ]
        if initial_count > 0:
            funnel.append(
                _funnel_stage("Scored (SQS > 0)", t1_count, initial_count, "Failed SQS calculation or data validation")
            )
        if t1_count > 0:
            funnel.append(_funnel_stage("Emerging (SQS ≥ 40)", t2_count, t1_count, "Insufficient momentum or trend"))
        if t2_count > 0:
            funnel.append(_funnel_stage("Developing (SQS ≥ 50)", t3_count, t2_count, "Below trend quality threshold"))
        if t3_count > 0:
            funnel.append(
                _funnel_stage("Quality (SQS ≥ 55)", t4_count, t3_count, "Near-threshold, below quality floor")
            )
        if t4_count > 0:
            funnel.append(
                _funnel_stage(
                    "High-Quality (SQS ≥ 60)", high_quality_count, t4_count, "Low signal quality score (SQS < 60)"
                )
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
                reason_text = str(row["rejection_reason"] or "")
                count = row["count"]
                if not reason_text or count is None:
                    continue
                rejected_list.append(
                    {
                        "evaluation_reason": reason_text,
                        "description": _get_rejection_reason_description(reason_text),
                        "n": count,
                    }
                )
        except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
            raise RuntimeError(f"Signal rejection data schema error: {e}") from e

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
            "t1": t1_count,
            "t2": t2_count,
            "t3": t3_count,
            "t4": t4_count,
            "t5": high_quality_count,
            "avg_score": computed_avg_score,
            "signal_date": signal_date.isoformat() if hasattr(signal_date, "isoformat") else signal_date,
        }
        is_valid, validation_error = ResponseValidator.validate_endpoint_response("sig_eval", result)
        if not is_valid:
            assert validation_error is not None
            logger.error(f"Endpoint response validation failed: {validation_error}")
            return error_response(500, "response_validation_error", validation_error)
        return json_response(200, result)
    except (psycopg2.OperationalError, psycopg2.DatabaseError) as e:
        logger.error(
            f"Failed to fetch rejection funnel: {type(e).__name__}: {e}\n  Operation: Query candidate_signals_reject table\n  Endpoint: GET /api/algo/rejection-funnel"
        )
        raise
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as e:
        raise RuntimeError(f"Signal rejection funnel schema error - required tables missing: {e}") from e


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
def _get_swing_scores(cur: cursor, limit: int = 100, min_score: float | None = None, symbol: str | None = None) -> Any:
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
def _get_swing_scores_history(cur: cursor, days: int = 30) -> Any:
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
