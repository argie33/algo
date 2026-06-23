"""Route: algo"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from psycopg2.extensions import cursor

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    ensure_valid_response,
    error_response,
    handle_db_error,
    json_response,
    list_response,
    safe_dict_convert,
    safe_json_serialize,
)

from utils.validation import (
    APIResponseValidator,
    format_decimal_string,
)

logger = logging.getLogger(__name__)


@db_route_handler("fetch algo positions")
def _get_algo_positions(cur: cursor, user_id: str | None = None) -> dict[str, Any]:
    """Get current open positions with computed fields.

    Provides comprehensive position data with:
    - Current price, unrealized P&L, risk metrics
    - Stop/target levels and distance percentages
    - Technical scores (Weinstein stage, Minervini trend)
    - Sector allocation for pie chart
    - Ladder percentage points for visualization
    """
    cur.execute("SET LOCAL statement_timeout = '30000ms'")

    cur.execute("""
            SELECT
            symbol,
            quantity,
            avg_entry_price,
            current_price,
            position_value,
            unrealized_pnl,
            unrealized_pnl_pct,
            status,
            days_since_entry,
            stop_loss_price,
            target_1_price,
            target_2_price,
            target_3_price,
            target_1_r_multiple,
            target_2_r_multiple,
            target_3_r_multiple,
            sector,
            industry,
            r_multiple,
            initial_risk_per_share,
            open_risk_dollars,
            distance_to_stop_pct,
            distance_to_t1_pct,
            distance_to_t2_pct,
            distance_to_t3_pct,
            minervini_trend_score,
            weinstein_stage,
            percent_from_52w_low,
            percent_from_52w_high,
            stage_in_exit_plan
            FROM algo_positions_with_risk
            ORDER BY position_value DESC
            LIMIT 1000
        """)
    positions = cur.fetchall()

    items = []
    sector_risk: dict[str, float] = {}  # For aggregating sector allocation
    invalid_positions: list[str] = []

    for p in positions:
        d = safe_json_serialize(safe_dict_convert(p))

        # Validate required data before adding to items (Issue #1 fix)
        pos_val_raw = d.get("position_value")
        if pos_val_raw is None:
            invalid_positions.append(d.get("symbol", "unknown"))
            continue
        try:
            pos_val = float(pos_val_raw)
        except (ValueError, TypeError) as e:
            invalid_positions.append(d.get("symbol", "unknown"))
            logger.warning(f"Position {d.get('symbol')} has invalid position_value: {pos_val_raw} ({e})")
            continue

        # Compute ladder_pct_* fields for visualization (Issue #2)
        # Validate all price fields before conversion
        entry_raw = d.get("avg_entry_price")
        cur_price_raw = d.get("current_price")
        stop_raw = d.get("stop_loss_price")
        t1_raw = d.get("target_1_price")
        t2_raw = d.get("target_2_price")
        t3_raw = d.get("target_3_price")

        if any(v is None for v in [entry_raw, cur_price_raw, stop_raw, t1_raw, t2_raw, t3_raw]):
            invalid_positions.append(d.get("symbol", "unknown"))
            logger.warning(f"Position {d.get('symbol')} missing required price fields")
            continue

        try:
            entry = float(entry_raw)
            cur_price = float(cur_price_raw)
            stop = float(stop_raw)
            t1 = float(t1_raw)
            t2 = float(t2_raw)
            t3 = float(t3_raw)
        except (ValueError, TypeError) as e:
            invalid_positions.append(d.get("symbol", "unknown"))
            logger.warning(f"Position {d.get('symbol')} has invalid price fields: {e}")
            continue

        if entry and cur_price and stop:
            lo = min(stop, entry, cur_price)
            hi = max(t3 or t2 or t1 or entry, cur_price)
            span = max(0.0001, hi - lo)

            def pos(price: float | None, _lo: float = lo, _span: float = span) -> float | None:
                return ((price - _lo) / _span) * 100 if price is not None else None

            d["ladder_pct_stop"] = pos(stop)
            d["ladder_pct_entry"] = pos(entry)
            d["ladder_pct_current"] = pos(cur_price)
            d["ladder_pct_t1"] = pos(t1)
            d["ladder_pct_t2"] = pos(t2)
            d["ladder_pct_t3"] = pos(t3)
        else:
            d["ladder_pct_stop"] = None
            d["ladder_pct_entry"] = None
            d["ladder_pct_current"] = None
            d["ladder_pct_t1"] = None
            d["ladder_pct_t2"] = None
            d["ladder_pct_t3"] = None

        # Compute stage_label for stage distribution (Issue #8)
        stage_raw = d.get("weinstein_stage")
        stage = None
        if stage_raw is None:
            logger.warning(f"Position {d.get('symbol')} missing weinstein_stage")
            d["stage_label"] = "Unknown"
        else:
            try:
                stage = int(stage_raw)
            except (ValueError, TypeError):
                logger.warning(f"Position {d.get('symbol')} has invalid weinstein_stage: {stage_raw}")
                d["stage_label"] = "Unknown"

        trend_score_raw = d.get("minervini_trend_score")
        trend_score = float(trend_score_raw) if trend_score_raw is not None else None
        if stage == 2:
            if trend_score and trend_score < 4:
                d["stage_label"] = "Early Stage-2"
            elif trend_score and trend_score >= 6:
                d["stage_label"] = "Late Stage-2"
            else:
                d["stage_label"] = "Mid Stage-2"
        elif stage == 1:
            d["stage_label"] = "Stage 1 (base)"
        elif stage == 3:
            d["stage_label"] = "Stage 3 (top)"
        elif stage == 4:
            d["stage_label"] = "Stage 4 (down)"
        else:
            d["stage_label"] = "Unknown"

        # Normalize field names for frontend compatibility
        if "percent_from_52w_low" in d:
            d["pct_from_52w_low"] = d.pop("percent_from_52w_low")
        if "percent_from_52w_high" in d:
            d["pct_from_52w_high"] = d.pop("percent_from_52w_high")

        items.append(d)

        # Accumulate sector allocation - all added items have valid position_value
        sector = d.get("sector", "Unknown")
        if sector not in sector_risk:
            sector_risk[sector] = 0
        sector_risk[sector] += pos_val

    if invalid_positions:
        logger.warning(
            f"Filtered out {len(invalid_positions)} positions with missing position_value: {', '.join(invalid_positions[:5])}"
        )

    # Compute sector_allocation array after processing all positions (E5 fix)
    # Use absolute values to handle portfolios with shorts: total = sum of |position values|
    # This prevents negative totals when shorts exceed longs, which would invert all percentages
    total_abs_value = sum(abs(v) for v in sector_risk.values()) or 1
    sector_allocation = [
        {
            "sector": sector,
            "allocation_pct": round((abs(value) / total_abs_value) * 100, 1),
            "is_overweight": (abs(value) / total_abs_value) * 100 > 30,
        }
        for sector, value in sorted(sector_risk.items(), key=lambda x: abs(x[1]), reverse=True)
    ]

    freshness = check_data_freshness(cur, "algo_positions", "updated_at", warning_days=1)
    stale_alerts = []
    if freshness.get("is_stale"):
        stale_alerts.append(f"Position data {freshness.get('data_age_days', '?')}d old")

    response_data = {
        "items": items,
        "sector_allocation": sector_allocation,
        "pagination": {"total": len(items), "limit": 10000, "offset": 0},
        "stale_alerts": stale_alerts,
        "data_freshness": freshness,
    }
    sanitized = APIResponseValidator.sanitize_response(response_data)

    # Validate positions response matches contract schema
    ensure_valid_response("pos", sanitized)

    return json_response(200, sanitized)


@db_route_handler("fetch algo status")
def _get_algo_status(cur: cursor) -> dict[str, Any]:
    """Get latest algo execution status plus latest portfolio snapshot."""
    cur.execute("""
            SELECT
                details->>'run_id' AS run_id,
                action_type,
                action_date,
                details->>'summary' AS message,
                status,
                created_at
            FROM algo_audit_log
            ORDER BY created_at DESC
            LIMIT 1
        """)
    row = cur.fetchone()
    if row is None:
        return error_response(503, "no_data", "No trading activity available yet")

    portfolio = {}
    try:
        cur.execute("""
                SELECT total_portfolio_value, total_cash, daily_return_pct,
                       unrealized_pnl_total, position_count
                FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1
            """)
        snap = cur.fetchone()
        if snap:
            pv = float(snap["total_portfolio_value"])
            unrealized_pnl = float(snap["unrealized_pnl_total"])
            unrealized_pnl_pct = None
            if pv and pv > 0 and unrealized_pnl is not None:
                unrealized_pnl_pct = unrealized_pnl / pv * 100
            portfolio = {
                "total_portfolio_value": format_decimal_string(pv, precision=2, allow_none=True),
                "total_cash": format_decimal_string(float(snap["total_cash"]) or 0, precision=2),
                "position_count": int(snap["position_count"]),
                "daily_return_pct": format_decimal_string(
                    float(snap["daily_return_pct"]), precision=2, allow_none=True
                ),
                "unrealized_pnl_pct": format_decimal_string(
                    unrealized_pnl_pct,
                    precision=2,
                    allow_none=True,
                ),
                "unrealized_pnl_dollars": format_decimal_string(unrealized_pnl, precision=2, allow_none=True),
            }
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch portfolio snapshot")
        return error_response(code, error_type, message)

    freshness = check_data_freshness(cur, "algo_audit_log", "created_at", warning_days=1)
    return json_response(
        200,
        {
            "run_id": row["run_id"],
            "last_run": row["action_date"].isoformat() if row["action_date"] else None,
            "current_phase": row["action_type"],
            "status": row["status"],
            "message": row["message"],
            "portfolio": portfolio,
            "data_freshness": freshness,
        },
    )


@db_route_handler("fetch algo trades")
def _get_algo_trades(
    cur: cursor, limit: int = 200, user_id: str | None = None, status: str | None = None
) -> dict[str, Any]:
    """Get recent trades with all fields for frontend (scoped to user if user_id provided, filtered by status if provided)."""
    where_parts: list[str] = []
    params: list[Any] = []

    if user_id:
        where_parts.append("cognito_sub = %s")
        params.append(user_id)

    if status:
        # Validate status parameter to prevent SQL injection
        valid_statuses = ["open", "closed", "halted", "cancelled"]
        if status not in valid_statuses:
            logger.warning(f"Invalid trade status requested: {status}, ignoring filter")
            status = None
        else:
            where_parts.append("status = %s")
            params.append(status)

    where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    params.append(limit)

    cur.execute(
        f"""
            SELECT trade_id, symbol, signal_date, trade_date, entry_price, entry_time,
                   entry_quantity, entry_reason, exit_price, exit_date, exit_time,
                   exit_reason, exit_r_multiple, profit_loss_dollars, profit_loss_pct,
                   status, swing_score, swing_grade, base_type, stage_phase,
                   trade_duration_days, mfe_pct, mae_pct, created_at
            FROM algo_trades
            {where_clause}
            ORDER BY trade_date DESC, trade_id DESC
            LIMIT %s
        """,
        params,
    )
    trades = cur.fetchall()
    items = [safe_json_serialize(safe_dict_convert(t)) for t in trades]
    freshness = check_data_freshness(cur, "algo_trades", "created_at", warning_days=1)
    response_data = {
        "items": items,
        "pagination": {"total": len(items), "limit": limit, "offset": 0},
        "data_freshness": freshness,
    }
    sanitized = APIResponseValidator.sanitize_response(response_data)

    # Validate trades response matches contract schema
    ensure_valid_response("trades", sanitized)

    return json_response(200, sanitized)


@db_route_handler("fetch circuit breakers")
def _get_circuit_breakers(cur: cursor) -> dict[str, Any]:
    """Get real-time circuit breaker state with current values vs thresholds."""
    try:
        today = date.today()
        breakers = []

        # CRITICAL: Validate required circuit breaker configuration tables exist
        required_tables = [
            "algo_portfolio_snapshots",
            "algo_trades",
            "market_health_daily",
            "algo_positions",
        ]
        missing_tables = []
        for table in required_tables:
            try:
                from utils.db.sql_safety import assert_safe_table

                table_safe = assert_safe_table(table)
                cur.execute(psycopg2.sql.SQL("SELECT 1 FROM {} LIMIT 1").format(psycopg2.sql.Identifier(table_safe)))
            except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedSchema):
                missing_tables.append(table)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                logger.error(f"Unexpected error checking table {table}: {type(e).__name__}: {e}")
                missing_tables.append(table)

        if missing_tables:
            logger.error(f"ALERT: Circuit breaker CRITICAL config tables missing: {missing_tables}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Data unavailable",
                    },
                    "errorType": "missing_critical_tables",
                    "message": f"Circuit breaker configuration incomplete: missing tables {missing_tables}. Trading is disabled until data is available.",
                    "_error": f"Circuit breaker configuration incomplete: missing tables {missing_tables}. Trading is disabled until data is available.",
                },
            )

        # Fetch pre-computed circuit breaker metrics from database
        # CRITICAL: Fail-fast if metrics are unavailable (don't default to 0 for trading safety)
        cbm_data = {}
        try:
            cur.execute(
                "SELECT portfolio_drawdown_pct, daily_loss_pct, weekly_loss_pct, open_risk_pct, consecutive_losses, vix_level, market_stage FROM circuit_breaker_status ORDER BY check_date DESC LIMIT 1"
            )
            cbm_row = cur.fetchone()
            if not cbm_row:
                logger.warning("Circuit breaker metrics unavailable (circuit_breaker_status table empty)")
                return json_response(
                    503,
                    {
                        "breakers": [],
                        "any_triggered": False,
                        "triggered_count": 0,
                        "data_freshness": {
                            "data_age_days": None,
                            "is_stale": True,
                            "warning": "Circuit breaker data unavailable",
                        },
                        "errorType": "missing_circuit_breaker_data",
                        "message": "Circuit breaker metrics unavailable. Trading disabled until data is available.",
                        "_error": "Circuit breaker metrics unavailable. Trading disabled until data is available.",
                    },
                )

            # Validate critical fields exist and are non-null (fail-closed)
            critical_fields = [
                "portfolio_drawdown_pct",
                "daily_loss_pct",
                "weekly_loss_pct",
                "open_risk_pct",
                "consecutive_losses",
                "market_stage",
            ]
            missing = [f for f in critical_fields if cbm_row[f] is None]
            if missing:
                logger.error(f"Circuit breaker critical fields missing: {missing}")
                return json_response(
                    503,
                    {
                        "breakers": [],
                        "any_triggered": False,
                        "triggered_count": 0,
                        "data_freshness": {
                            "data_age_days": None,
                            "is_stale": True,
                            "warning": "Circuit breaker data incomplete",
                        },
                        "errorType": "incomplete_circuit_breaker_data",
                        "message": f"Circuit breaker data incomplete (missing {', '.join(missing)}). Trading disabled.",
                        "_error": "Circuit breaker data incomplete. Trading disabled.",
                    },
                )

            cbm_data = {
                "drawdown": float(cbm_row["portfolio_drawdown_pct"]),
                "daily_loss": float(cbm_row["daily_loss_pct"]),
                "weekly_loss": float(cbm_row["weekly_loss_pct"]),
                "total_risk": float(cbm_row["open_risk_pct"]),
                "consecutive_losses": int(cbm_row["consecutive_losses"]),
                "vix_level": float(cbm_row["vix_level"]),  # VIX is optional
                "market_stage": int(cbm_row["market_stage"]),
            }
        except (
            psycopg2.errors.UndefinedTable,
            psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError,
            psycopg2.DatabaseError,
            Exception,
        ) as e:
            code, error_type, message = handle_db_error(e, "fetch circuit breaker metrics")
            return error_response(code, error_type, message)

        # CB1: Portfolio drawdown (from pre-computed metrics)
        try:
            dd = cbm_data["drawdown"]
            threshold_dd = 20.0
            breakers.append(
                {
                    "id": "drawdown",
                    "label": "Portfolio Drawdown",
                    "triggered": dd >= threshold_dd,
                    "current": dd,
                    "threshold": threshold_dd,
                    "unit": "%",
                    "description": f"Halt when drawdown from peak ≥ {threshold_dd:.0f}%",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB1 (drawdown) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (drawdown): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB2: Daily loss (from pre-computed metrics)
        try:
            daily_loss = cbm_data["daily_loss"]
            threshold_dl = 2.0
            breakers.append(
                {
                    "id": "daily_loss",
                    "label": "Daily Loss",
                    "triggered": daily_loss >= threshold_dl,
                    "current": daily_loss,
                    "threshold": threshold_dl,
                    "unit": "%",
                    "description": f"Halt when today's loss ≥ {threshold_dl:.0f}%",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB2 (daily_loss) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (daily_loss): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB3: Consecutive losses (from pre-computed metrics)
        try:
            streak = cbm_data["consecutive_losses"]
            threshold_cl = 3
            breakers.append(
                {
                    "id": "consecutive_losses",
                    "label": "Consecutive Losses",
                    "triggered": streak >= threshold_cl,
                    "current": streak,
                    "threshold": threshold_cl,
                    "unit": "",
                    "description": f"Halt after {threshold_cl} consecutive losing trades",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB3 (consecutive_losses) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (consecutive_losses): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB4: VIX spike (from pre-computed metrics)
        try:
            vix = cbm_data["vix_level"] if cbm_data else None
            threshold_vix = 35.0
            breakers.append(
                {
                    "id": "vix_spike",
                    "label": "VIX Spike",
                    "triggered": vix is not None and vix >= threshold_vix,
                    "current": vix,
                    "threshold": threshold_vix,
                    "unit": "",
                    "description": f"Halt when VIX ≥ {threshold_vix:.0f} (extreme fear)",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"CB4 (vix_spike) computation failed: {type(e).__name__}: {e}")
            breakers.append(
                {
                    "id": "vix_spike",
                    "label": "VIX Spike",
                    "triggered": False,
                    "current": 0,
                    "threshold": 35,
                    "unit": "",
                    "description": "No market data yet",
                }
            )

        # CB5: Weekly portfolio loss (from pre-computed metrics)
        try:
            weekly_loss = cbm_data["weekly_loss"]
            threshold_wl = 5.0
            breakers.append(
                {
                    "id": "weekly_loss",
                    "label": "Weekly Loss",
                    "triggered": weekly_loss >= threshold_wl,
                    "current": weekly_loss,
                    "threshold": threshold_wl,
                    "unit": "%",
                    "description": f"Halt when 7-day loss ≥ {threshold_wl:.0f}%",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB5 (weekly_loss) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (weekly_loss): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB6: Market stage break (Stage 4 = downtrend) (from pre-computed metrics)
        try:
            stage = cbm_data["market_stage"]
            breakers.append(
                {
                    "id": "market_stage",
                    "label": "Market Stage",
                    "triggered": stage == 4,
                    "current": stage,
                    "threshold": 4,
                    "unit": "",
                    "description": "Halt when market enters Stage 4 (confirmed downtrend)",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB6 (market_stage) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (market_stage): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB7: Total open risk (from pre-computed metrics)
        try:
            risk_pct = cbm_data["total_risk"]
            threshold_risk = 4.0
            breakers.append(
                {
                    "id": "total_risk",
                    "label": "Total Open Risk",
                    "triggered": risk_pct >= threshold_risk,
                    "current": risk_pct,
                    "threshold": threshold_risk,
                    "unit": "%",
                    "description": f"Halt when total open risk ≥ {threshold_risk:.0f}% of portfolio",
                }
            )
        except (ValueError, ZeroDivisionError, TypeError, KeyError) as e:
            logger.error(f"CB7 (total_risk) computation failed: {type(e).__name__}: {e}")
            return json_response(
                503,
                {
                    "breakers": [],
                    "any_triggered": False,
                    "triggered_count": 0,
                    "data_freshness": {
                        "data_age_days": None,
                        "is_stale": True,
                        "warning": "Circuit breaker data error",
                    },
                    "errorType": "circuit_breaker_computation_error",
                    "message": f"Circuit breaker computation error (total_risk): {e!s}",
                    "_error": "Circuit breaker computation failed. Trading disabled.",
                },
            )

        # CB8: Intraday market health (SPY down >2% yesterday)
        try:
            cur.execute(
                """
                    SELECT close FROM price_daily
                    WHERE symbol = 'SPY' AND date <= %s
                    ORDER BY date DESC LIMIT 2
                """,
                (today,),
            )
            prices = cur.fetchall()
            if len(prices) >= 2:
                latest = float(prices[0][0])
                prior = float(prices[1][0])
                if latest > 0 and prior > 0:
                    market_change = (latest - prior) / prior * 100
                    threshold_mc = -2.0
                    breakers.append(
                        {
                            "id": "intraday_health",
                            "label": "Prior-Day Market Health",
                            "triggered": market_change <= threshold_mc,
                            "current": round(market_change, 2),
                            "threshold": threshold_mc,
                            "unit": "%",
                            "description": f"Halt if SPY dropped >{abs(threshold_mc):.0f}% yesterday (await stability)",
                        }
                    )
                else:
                    raise ValueError("Invalid price data")
            else:
                raise ValueError("Insufficient price history")
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"CB8 (intraday_health) computation failed: {type(e).__name__}: {e}")
            breakers.append(
                {
                    "id": "intraday_health",
                    "label": "Prior-Day Market Health",
                    "triggered": False,
                    "current": 0,
                    "threshold": -2.0,
                    "unit": "%",
                    "description": "No price history yet",
                }
            )

        # CB9: Win rate floor
        try:
            cur.execute("""
                    SELECT COUNT(*) FILTER (WHERE profit_loss_pct > 0) as wins,
                           COUNT(*) FILTER (WHERE profit_loss_pct < 0) as losses,
                           COUNT(*) as total
                    FROM (
                        SELECT profit_loss_pct
                        FROM algo_trades
                        WHERE status = 'closed' AND exit_date IS NOT NULL
                        ORDER BY exit_date DESC LIMIT 30
                    ) recent_trades
                """)
            wr_result = cur.fetchone()
            if wr_result:
                wins = int(wr_result["wins"])
                losses = int(wr_result["losses"])
                decisive = wins + losses
                win_rate = (wins / decisive * 100) if decisive > 0 else 0
                threshold_wr = 40.0
                breakers.append(
                    {
                        "id": "win_rate",
                        "label": "Win Rate Floor",
                        "triggered": win_rate < threshold_wr and decisive >= 10,
                        "current": round(win_rate, 1),
                        "threshold": threshold_wr,
                        "unit": "%",
                        "description": f"Halt if win rate drops below {threshold_wr:.0f}% (last 30 closed)",
                    }
                )
            else:
                raise ValueError("No trade data")
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"CB9 (win_rate) computation failed: {type(e).__name__}: {e}")
            breakers.append(
                {
                    "id": "win_rate",
                    "label": "Win Rate Floor",
                    "triggered": False,
                    "current": 0,
                    "threshold": 40,
                    "unit": "%",
                    "description": "Insufficient closed trades (need 10+)",
                }
            )

        any_halted = any(b["triggered"] for b in breakers)
        triggered_count = sum(1 for b in breakers if b["triggered"])
        freshness = check_data_freshness(cur, "algo_portfolio_snapshots", "snapshot_date", warning_days=1)

        for breaker in breakers:
            if breaker["unit"] == "%":
                breaker["current"] = format_decimal_string(breaker["current"], precision=2, allow_none=True)
                breaker["threshold"] = format_decimal_string(breaker["threshold"], precision=2, allow_none=False)
            elif breaker["unit"] == "" and breaker["id"] == "vix_spike":
                breaker["current"] = format_decimal_string(breaker["current"], precision=2, allow_none=True)
                breaker["threshold"] = format_decimal_string(breaker["threshold"], precision=2, allow_none=False)

        cb_response = {
            "breakers": breakers,
            "any_triggered": any_halted,
            "triggered_count": triggered_count,
            "data_freshness": freshness,
        }

        # Validate circuit breaker response matches contract schema
        ensure_valid_response("cb", cb_response)

        return json_response(200, cb_response)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch circuit breakers")
        return error_response(code, error_type, message)


@db_route_handler("fetch dashboard signals")
def _get_dashboard_signals(cur: cursor) -> dict[str, Any]:
    """Get dashboard-specific signal data with aggregations for the Ops Terminal.

    Returns: BUY signals with quality scores, grade distribution (A-D by score),
    near-miss signals, top A-grade stocks, and signal trend.
    """
    try:
        # buy_sell_daily was removed from the pipeline; use swing_trader_scores instead.
        cur.execute("""
                SELECT COUNT(*) AS n, MAX(date) AS d FROM swing_trader_scores
                WHERE date=(SELECT MAX(date) FROM swing_trader_scores)""")
        sig = cur.fetchone()
        if sig is None or sig.get("n") is None:
            return error_response(503, "no_data", "No swing trader signals available")
        total_n = int(sig["n"])

        # Top swing candidates with swing score and sector
        cur.execute("""
                SELECT s.symbol, t.weinstein_stage AS stage_number, s.score AS signal_quality_score,
                       s.score AS entry_quality_score, p.close,
                       s.components->>'fail_reason' AS reason,
                       cp.sector,
                       s.score AS swing_score
                FROM swing_trader_scores s
                LEFT JOIN company_profile cp ON cp.ticker = s.symbol
                LEFT JOIN trend_template_data t ON t.symbol = s.symbol AND t.date = s.date
                LEFT JOIN LATERAL (
                    SELECT close FROM price_daily WHERE symbol = s.symbol ORDER BY date DESC LIMIT 1
                ) p ON true
                WHERE s.date=(SELECT MAX(date) FROM swing_trader_scores)
                ORDER BY s.score DESC
                LIMIT 30""")
        buy_sigs = [safe_json_serialize(safe_dict_convert(row)) for row in cur.fetchall()]

        # Grade distribution (A/B/C/D by swing score)
        cur.execute("""
                SELECT COUNT(*) FILTER (WHERE score >= 80) AS a,
                       COUNT(*) FILTER (WHERE score >= 60 AND score < 80) AS b,
                       COUNT(*) FILTER (WHERE score >= 40 AND score < 60) AS c,
                       COUNT(*) FILTER (WHERE score < 40) AS d,
                       COUNT(*) AS total
                FROM swing_trader_scores
                WHERE date=(SELECT MAX(date) FROM swing_trader_scores)""")
        grades_r = cur.fetchone()
        grades = safe_dict_convert(grades_r) if grades_r else {}

        # Near-misses: scored stocks close to BUY threshold
        cur.execute("""
                SELECT s.symbol, s.score, cp.sector
                FROM swing_trader_scores s
                LEFT JOIN company_profile cp ON cp.ticker = s.symbol
                WHERE s.date=(SELECT MAX(date) FROM swing_trader_scores)
                  AND s.score BETWEEN 55 AND 69
                ORDER BY s.score DESC LIMIT 15""")
        near = [safe_json_serialize(safe_dict_convert(row)) for row in cur.fetchall()]

        # Top A-grade stocks by name (radar display â€" score ≥ 80)
        cur.execute("""
                SELECT s.symbol, s.score
                FROM swing_trader_scores s
                WHERE s.date=(SELECT MAX(date) FROM swing_trader_scores)
                  AND s.score >= 80
                ORDER BY s.score DESC LIMIT 20""")
        top_a = [safe_json_serialize(safe_dict_convert(row)) for row in cur.fetchall()]

        # Signal count trend: last 7 trading days from swing_trader_scores
        cur.execute("""
                SELECT date,
                       COUNT(*) FILTER (WHERE score >= 60) AS buy_n,
                       COUNT(*) AS total_n
                FROM swing_trader_scores
                WHERE date >= CURRENT_DATE - 14
                GROUP BY date ORDER BY date DESC LIMIT 7""")
        trend = [safe_json_serialize(safe_dict_convert(row)) for row in cur.fetchall()]

        freshness = check_data_freshness(cur, "swing_trader_scores", "date", warning_days=1)

        # Count qualifying buy signals (score >= 70) for the "n BUY" display
        qualifying_buy_count = sum(
            1 for s in buy_sigs if s.get("signal_quality_score") is not None and s.get("signal_quality_score") >= 70
        )
        sig_response = {
            "n": qualifying_buy_count,
            "total": total_n,
            "date": sig["d"] if sig else None,
            "buy_sigs": buy_sigs[:15] if buy_sigs else [],
            "near": near[:8] if near else [],
            "top_a": top_a[:20] if top_a else [],
            "grades": grades,
            "trend": trend,
            "data_freshness": freshness,
        }

        # Validate signals response matches contract schema
        ensure_valid_response("sig", sig_response)

        return json_response(200, sig_response)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch dashboard signals")
        return error_response(code, error_type, message)


@db_route_handler("fetch equity curve")
def _get_equity_curve(cur: cursor, days: int = 180) -> dict[str, Any]:
    """Get equity curve for last N days."""
    try:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()
        cur.execute(
            """
                WITH snapshots AS (
                    SELECT snapshot_date, total_portfolio_value, total_cash,
                           unrealized_pnl_total, position_count, daily_return_pct,
                           MAX(total_portfolio_value) OVER (
                               ORDER BY snapshot_date ASC
                               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                           ) AS running_peak
                    FROM algo_portfolio_snapshots
                    WHERE snapshot_date >= %s AND total_portfolio_value > 0
                )
                SELECT snapshot_date, total_portfolio_value, total_cash,
                       unrealized_pnl_total, position_count, daily_return_pct,
                       ROUND(
                           (total_portfolio_value - running_peak) / NULLIF(running_peak, 0) * 100,
                           4
                       ) AS drawdown_pct
                FROM snapshots
                ORDER BY snapshot_date DESC
                LIMIT 1000
            """,
            (cutoff_date,),
        )
        curve = cur.fetchall()
        freshness = check_data_freshness(cur, "algo_portfolio_snapshots", "snapshot_date", warning_days=1)
        return list_response(
            [safe_json_serialize(safe_dict_convert(c)) for c in reversed(curve) if c],
            data_freshness=freshness,
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch equity curve")
        return error_response(code, error_type, message)
