"""Route: algo"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from models.requests import PreTradeImpactRequest, TradePreviewRequest
from psycopg2.extensions import cursor
from pydantic import ValidationError
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

from algo.infrastructure.config.sql_intervals import get_interval_sql
from algo.risk.exposure_policy import EXPOSURE_TIERS
from utils.validation import (
    format_decimal_string,
    safe_float,
)

logger = logging.getLogger(__name__)


def _validate_portfolio_snapshot(cur: cursor) -> tuple[dict[str, Any], Any] | Any:
    cur.execute("""
        SELECT total_portfolio_value, position_count FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
    """)
    port_row = cur.fetchone()
    if port_row is None:
        return None, error_response(503, "service_unavailable", "Portfolio snapshot unavailable")

    port_row = safe_dict_convert(port_row)
    # BUG FOUND 2026-08-10 (NaN-comparison-guard class): bare float() here bypassed this
    # same module's already-imported safe_float() (utils/validation/framework.py), which
    # explicitly rejects NaN/Infinity. `not portfolio_value or portfolio_value <= 0` never
    # catches NaN (always False in Python) - a NaN total_portfolio_value would have sailed
    # through and silently produced a NaN pct_of_portfolio in this endpoint's response.
    try:
        portfolio_value = safe_float(port_row["total_portfolio_value"], strict=True, field_name="total_portfolio_value")
    except Exception:
        return None, error_response(503, "service_unavailable", "Portfolio value unavailable")
    open_positions = int(port_row["position_count"])

    if not portfolio_value or portfolio_value <= 0:
        return None, error_response(503, "service_unavailable", "Portfolio value unavailable")

    return (port_row, portfolio_value, open_positions), None


def _get_symbol_sector(cur: cursor, symbol: str) -> str | Any:
    cur.execute(
        """
        SELECT sector FROM company_profile WHERE symbol = %s LIMIT 1
    """,
        (symbol,),
    )
    profile_row = cur.fetchone()
    sector = None
    if profile_row:
        profile_row = safe_dict_convert(profile_row)
        sector = profile_row.get("sector")

    if sector is None:
        return error_response(
            400, "sector_unknown", f"Cannot size position for {symbol}: sector not found in company_profile"
        )
    return sector


def _fetch_sector_exposure(cur: cursor) -> dict[str, Any] | Any:
    sector_exposure = {}
    try:
        # FAIL-FAST: Do not use COALESCE(sector, 'Unknown') - this masks missing enrichment data
        # Instead, fail explicitly when sector enrichment unavailable
        # Positions without sector enrichment indicate data quality issue in company_profile loader
        cur.execute("""
            SELECT cp.sector,
                   SUM(ap.position_value) AS sector_value,
                   COUNT(ap.symbol) as sector_position_count
            FROM algo_positions ap
            LEFT JOIN company_profile cp ON cp.symbol = ap.symbol
            WHERE ap.status = 'open'
            GROUP BY cp.sector
        """)
        for sr in cur.fetchall():
            # CRITICAL FAIL-FAST: Sector NULL means company_profile enrichment missing
            # Do not silently skip positions without sector data
            if sr["sector"] is None:
                # FIX: Direct access - query ALWAYS returns sector_position_count.
                # Using .get() with default 0 masks when key is missing (indicates query corruption).
                unmapped_count = sr["sector_position_count"]
                error_msg = (
                    f"CRITICAL: {unmapped_count} open positions missing sector enrichment in company_profile. "
                    f"Cannot compute sector exposure without complete enrichment. "
                    f"Sector exposure calculations would be invalid. "
                    f"Fix company_profile loader or skip signal generation until data complete."
                )
                logger.error(error_msg)
                return error_response(503, "sector_enrichment_incomplete", error_msg)

            sector_val_raw = sr["sector_value"]
            if sector_val_raw is None:
                error_msg = (
                    f"Sector {sr['sector']} has NULL position_value sum - "
                    "cannot proceed without complete sector exposure"
                )
                logger.error(error_msg)
                return error_response(503, "sector_exposure_incomplete", error_msg)
            # Validate type before conversion - non-numeric values cause silent failures downstream
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
                    error_msg = f"Sector {sr['sector']} has negative exposure ({sector_val}) - data corruption detected"
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
        # but at least one must be provided. Do NOT default to implicit 0.75% - caller must specify intent.
        entry_price = req.entry_price
        if not entry_price or entry_price <= 0:
            cur.execute(
                "SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1",
                (symbol,),
            )
            price_row = cur.fetchone()
            if price_row and price_row[0]:
                # BUG FOUND 2026-08-10 (NaN-comparison-guard class): bare float() here meant
                # a NaN price_daily.close would reach `int(position_dollars / entry_price)`
                # below unguarded (`entry_price <= 0` at line ~187 never catches NaN).
                # safe_float() rejects NaN/Infinity explicitly; caught by this function's
                # own outer `except (..., Exception)` and turned into a clean error response.
                entry_price = safe_float(price_row[0], strict=True, field_name="entry_price")

        if req.position_dollars:
            position_dollars = req.position_dollars
        elif req.position_pct:
            position_dollars = portfolio_value * (req.position_pct / 100)
        else:
            return error_response(
                400,
                "missing_position_size",
                "Pre-trade impact requires either position_dollars or position_pct. "
                "Cannot default to implicit 0.75% - caller must explicitly specify intended position size.",
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
        # A sector absent from sector_exposure means zero open positions currently hold
        # that sector (a normal GROUP BY result) - not a data quality issue. Only sectors
        # that *are* returned are validated above (non-null, numeric, non-negative).
        current_sector_dollars = sector_exposure.get(sector, 0.0)
        projected_sector_dollars = current_sector_dollars + actual_dollars
        projected_sector_pct = projected_sector_dollars / portfolio_value * 100

        # 'Unknown' bucket only appears when some open position lacks sector enrichment;
        # a fully-enriched portfolio legitimately has no 'Unknown' entry.
        unknown_sector_exposure = sector_exposure.get("Unknown", 0.0)
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
        if portfolio_row is None:
            return error_response(
                503,
                "service_unavailable",
                "Portfolio snapshot unavailable for position sizing",
            )

        portfolio_row = safe_dict_convert(portfolio_row)
        portfolio_value_raw = portfolio_row.get("total_portfolio_value")
        if portfolio_value_raw is None:
            return error_response(
                503,
                "service_unavailable",
                "Portfolio value field is NULL - snapshot data incomplete",
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
        shares = int(position_dollars / entry_price)
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


@db_route_handler("fetch rejection funnel")
@validate_api_response("sig_eval")
def _get_rejection_funnel(cur: cursor) -> Any:
    """Get signal evaluation funnel stats from stock_scores composite_score.

    SWING SCORE MIGRATION: Previously used swing_trader_scores table.
    Now calculates funnel stages from stock_scores composite_score tiers:
    - t1: all candidates evaluated (composite_score > 0)
    - t2: quality tier C+ (composite_score >= 55)
    - t3: quality tier B+ (composite_score >= 65)
    - t4: quality tier A+ (composite_score >= 75)
    - t5: top tier A++ (composite_score >= 85)
    """
    try:
        cur.execute("SET LOCAL statement_timeout = '10000ms'")

        # Get today's stock_scores evaluation stats by composite_score tier
        # CRITICAL: Filter to stocks only (exclude ETFs) per GOVERNANCE.md
        # Note: stock_scores has no 'etf' column, so use only etf_symbols table check
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                COUNT(CASE WHEN composite_score > 0 THEN 1 END) AS t1,
                COUNT(CASE WHEN composite_score >= 55 THEN 1 END) AS t2,
                COUNT(CASE WHEN composite_score >= 65 THEN 1 END) AS t3,
                COUNT(CASE WHEN composite_score >= 75 THEN 1 END) AS t4,
                COUNT(CASE WHEN composite_score >= 85 THEN 1 END) AS t5,
                ROUND(AVG(composite_score)::NUMERIC, 1) AS avg_score,
                MAX(created_at::date) AS signal_date
            FROM stock_scores
            WHERE created_at::date = CURRENT_DATE AND data_unavailable = FALSE
            AND symbol NOT IN (SELECT symbol FROM etf_symbols)
        """)
        result = cur.fetchone()
        if result is None:
            logger.info("No stock_scores found for today - returning zero funnel")
            return json_response(
                200,
                {
                    "total": 0,
                    "t1": 0,
                    "t2": 0,
                    "t3": 0,
                    "t4": 0,
                    "t5": 0,
                    "avg_score": None,
                    "signal_date": None,
                    "rejected": 0,
                },
            )

        result_dict = safe_dict_convert(result)

        # Validate all required count fields exist (SQL COUNT always returns non-None)
        required_fields = ["total", "t1", "t2", "t3", "t4", "t5"]
        for field in required_fields:
            if field not in result_dict:
                raise ValueError(
                    f"Signal funnel query missing required field '{field}' - possible database schema change"
                )

        # Direct access (already validated fields exist)
        total = int(result_dict["total"])
        t1 = int(result_dict["t1"])
        t2 = int(result_dict["t2"])
        t3 = int(result_dict["t3"])
        t4 = int(result_dict["t4"])
        t5 = int(result_dict["t5"])

        # Derived/optional fields may be None (avg_score and signal_date)
        avg_score = result_dict.get("avg_score")
        signal_date = result_dict.get("signal_date")

        # Rejected count = total - t1 (candidates with 0 or NULL composite_score)
        rejected = max(0, total - t1) if total > 0 else 0

        return json_response(
            200,
            {
                "total": total,
                "t1": t1,
                "t2": t2,
                "t3": t3,
                "t4": t4,
                "t5": t5,
                "avg_score": safe_float(avg_score, default=None, strict=True) if avg_score is not None else None,
                "signal_date": signal_date,
                "rejected": rejected,
            },
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch rejection funnel")
        return error_response(code, error_type, message)


# BUG FOUND 2026-08-24 (real-money-readiness goal, position-sizing re-verification pass):
# this used to be an independent, hand-maintained copy of algo/risk/exposure_policy.py's
# EXPOSURE_TIERS - drifted out of sync with the real values the trading system actually
# uses (confirmed_uptrend max_new 5 vs real 4; uptrend_under_pressure/caution/correction
# risk_mult 0.6/0.3/0.2 vs real 0.65/0.35/0.0; caution halt=True vs real
# halt_new_entries=False). Since this dict backs a live, user-facing endpoint
# (lambda/api/routes/algo_handlers/market.py's active_tier response, rendered directly by
# webapp/frontend/src/pages/MarketsHealth.jsx as risk_mult/max_new/a HALTED-ALLOWED badge),
# the drift meant the dashboard was showing an operator the WRONG risk posture - most
# seriously, claiming "caution" entries are HALTED when the live system is not halted in
# that tier at all (only "correction" halts). Rebuilt to derive from EXPOSURE_TIERS
# directly so this can't drift again - single source of truth, matching this codebase's own
# established fix for the equivalent position_sizer.py regime_mult double-counting bug
# (one signal, one place it's read from).
_TIER_CONFIG = {
    tier["name"]: {
        "description": tier["description"],
        "min_pct": tier["min_pct"],
        "max_pct": tier["max_pct"],
        "risk_mult": tier["risk_multiplier"],
        "risk_multiplier": tier["risk_multiplier"],
        "max_new": tier["max_new_positions_today"],
        "max_new_positions_today": tier["max_new_positions_today"],
        "halt": tier["halt_new_entries"],
        "halt_new_entries": tier["halt_new_entries"],
        "min_composite_score": tier["min_composite_score"],
        "max_concentration_pct": tier["max_concentration_pct"],
        # min_grade has no equivalent in EXPOSURE_TIERS (a display-only field with zero
        # confirmed consumers anywhere in webapp/frontend as of this fix) - kept as its own
        # static mapping rather than invented, since there's no canonical source for it.
        "min_grade": {
            "confirmed_uptrend": "B",
            "uptrend_under_pressure": "B",
            "caution": "A",
            "correction": "A+",
        }[tier["name"]],
    }
    for tier in EXPOSURE_TIERS
}


def _get_rejection_reason_description(reason: str) -> str:
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


@db_route_handler("fetch swing candidates")
@validate_api_response("scores")
def _get_swing_scores(
    cur: cursor,
    limit: int = 100,
    min_score: float | None = None,
    symbol: str | None = None,
    signal: str | None = None,
) -> Any:
    """Get the full-universe swing-candidate list: real stock_scores output joined to each
    symbol's latest real buy_sell_daily signal (see algo/signals/buy_signal_generator.py /
    lambda/api/routes/signals.py's /api/signals/stocks for the same source of truth).

    Deliberately ignores portfolio-level restrictions (sector/industry concentration caps,
    max-new-positions, halt state, etc.) - those live in algo/risk/exposure_policy.py and
    algo/orchestrator/phase8_guards.py and only apply once a candidate is actually being
    routed for execution. This endpoint is the pre-restriction reference list: every symbol
    with a real, currently-latest BUY or SELL signal, regardless of whether the live system
    would actually be allowed to act on it today.

    Previously (pre-2026-09-15) this endpoint faked a 7-component breakdown
    (setup/trend/momentum/volume/fundamentals/sector/multi_tf) that never existed in
    stock_scores - leftover from the deleted swing_trader_scores schema (migration 110) -
    and hardcoded pass_gates=TRUE/fail_reason=NULL for every row. Both removed; this now
    returns only real columns from stock_scores and buy_sell_daily.
    """
    try:
        # CRITICAL: Filter to stocks only (exclude ETFs) per GOVERNANCE.md
        # CRITICAL: Only return stocks with available metrics (data_unavailable = FALSE)
        interval_14d = get_interval_sql("14d")
        filters = [
            # stock_scores is one row per symbol (refreshed via UPDATE), so created_at is a
            # static one-time insert stamp, not a freshness signal - updated_at is.
            psycopg2.sql.SQL(f"s.updated_at::date >= CURRENT_DATE - {interval_14d}"),
            psycopg2.sql.SQL("s.symbol NOT IN (SELECT symbol FROM etf_symbols)"),
            psycopg2.sql.SQL("(s.data_unavailable = FALSE OR s.data_unavailable IS NULL)"),
            # "still relevant" = the symbol's most recent buy_sell_daily evaluation is an
            # active BUY or SELL (not HOLD/NULL) - buy_sell_daily is re-evaluated daily, so
            # the latest row already reflects whether price is still in the computed buy
            # zone / sell level as of the latest trading day.
            psycopg2.sql.SQL("b.signal IN ('BUY', 'SELL')"),
        ]
        query_params: list[Any] = []
        if min_score is not None:
            filters.append(psycopg2.sql.SQL("s.composite_score >= %s"))
            query_params.append(min_score)
        if symbol:
            filters.append(psycopg2.sql.SQL("s.symbol = %s"))
            query_params.append(symbol.upper())
        if signal:
            filters.append(psycopg2.sql.SQL("b.signal = %s"))
            query_params.append(signal.upper())
        where_clause = psycopg2.sql.SQL(" AND ").join(filters)
        query_params.append(limit)
        query = psycopg2.sql.SQL("""
                SELECT
                    s.symbol, s.updated_at::date AS date, s.composite_score,
                    s.quality_score, s.growth_score, s.value_score,
                    s.momentum_score, s.risk_score, s.rs_percentile,
                    CASE
                        WHEN s.composite_score >= 85 THEN 'A+'
                        WHEN s.composite_score >= 75 THEN 'A'
                        WHEN s.composite_score >= 65 THEN 'B'
                        WHEN s.composite_score >= 55 THEN 'C'
                        ELSE 'D'
                    END AS grade,
                    cp.sector, cp.industry,
                    t.weinstein_stage AS stage_number,
                    CASE t.weinstein_stage
                        WHEN 1 THEN 'Stage 1'
                        WHEN 2 THEN 'Stage 2 - Markup'
                        WHEN 3 THEN 'Stage 3 - Topping'
                        WHEN 4 THEN 'Stage 4'
                    END AS market_stage,
                    t.minervini_trend_score AS trend_template_score,
                    b.signal, b.date AS signal_date, b.signal_triggered_date,
                    b.signal_quality_score, b.entry_quality_score, b.strength, b.reason,
                    b.base_type, b.base_length_days,
                    b.buy_zone_start, b.buy_zone_end, b.pivot_price,
                    b.sell_level, b.initial_stop, b.trailing_stop,
                    b.entry_price, b.close, b.risk_reward_ratio,
                    b.profit_target_8pct, b.profit_target_20pct, b.profit_target_25pct
                FROM stock_scores s
                INNER JOIN LATERAL (
                    SELECT * FROM buy_sell_daily bsd
                    WHERE bsd.symbol = s.symbol
                    ORDER BY bsd.date DESC
                    LIMIT 1
                ) b ON TRUE
                LEFT JOIN company_profile cp ON s.symbol = cp.symbol
                LEFT JOIN trend_template_data t ON t.symbol = s.symbol
                    AND t.date = (SELECT MAX(tt.date) FROM trend_template_data tt WHERE tt.symbol = s.symbol)
                WHERE {where_clause}
                ORDER BY s.composite_score DESC
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
        code, error_type, message = handle_db_error(e, "fetch swing candidates")
        return error_response(code, error_type, message)


@db_route_handler("fetch stock scores history")
@validate_api_response("scores")
def _get_swing_scores_history(cur: cursor, days: int = 30) -> Any:
    try:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
        cur.execute(
            """
                SELECT created_at::date AS eval_date,
                    COUNT(CASE WHEN composite_score >= 85 THEN 1 END) AS grade_aplus,
                    COUNT(CASE WHEN composite_score >= 75 THEN 1 END) AS grade_a,
                    COUNT(CASE WHEN composite_score >= 50 THEN 1 END) AS pass_count,
                    COUNT(*) AS total_candidates,
                    ROUND(AVG(composite_score)::NUMERIC, 1) AS avg_score
                FROM stock_scores
                WHERE created_at::date >= %s AND data_unavailable = FALSE
                AND symbol NOT IN (SELECT symbol FROM etf_symbols)
                GROUP BY created_at::date
                ORDER BY created_at::date ASC
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
