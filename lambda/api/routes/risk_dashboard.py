"""Route: risk_dashboard - Real-time risk metrics for decision-making.

Endpoints:
  /api/algo/risk-dashboard - All current risk metrics
  /api/algo/risk-dashboard/drawdown - Current drawdown %
  /api/algo/risk-dashboard/exposure-tier - Current tier and why
  /api/algo/risk-dashboard/position-sizing-audit - Why trades were sized as they were
  /api/algo/risk-dashboard/stop-loss-audit - Why stops were chosen
  /api/algo/risk-dashboard/exit-rules - Which exit rules fired most
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from auth_utils import check_admin_access
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    error_response,
    execute_with_timeout,
    handle_db_error,
    json_response,
    list_response,
    safe_limit,
)

logger = logging.getLogger(__name__)


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Route risk dashboard endpoints."""
    if not check_admin_access(jwt_claims):
        return error_response(403, "forbidden", "Admin access required")
    if path == "/api/algo/risk-dashboard":
        return _get_comprehensive_risk_dashboard(cur)
    elif path == "/api/algo/risk-dashboard/drawdown":
        return _get_drawdown_metrics(cur)
    elif path == "/api/algo/risk-dashboard/exposure-tier":
        return _get_exposure_tier_info(cur)
    elif path == "/api/algo/risk-dashboard/position-sizing-audit":
        # GOVERNANCE: Explicit parameter validation instead of silent defaults.
        days = params.get("days") if params and isinstance(params, dict) else None
        if days is None:
            logger.debug("days parameter missing, using default=30")
            days_int = 30
        elif isinstance(days, list) and len(days) > 0:
            days_int = safe_limit(days[0], max_val=365, default=30)
        else:
            logger.warning(f"Invalid days parameter: {days}, using default=30")
            days_int = 30
        return _get_position_sizing_audit(cur, days_int)
    elif path == "/api/algo/risk-dashboard/stop-loss-audit":
        # GOVERNANCE: Explicit parameter validation instead of silent defaults.
        days = params.get("days") if params and isinstance(params, dict) else None
        if days is None:
            logger.debug("days parameter missing, using default=30")
            days_int = 30
        elif isinstance(days, list) and len(days) > 0:
            days_int = safe_limit(days[0], max_val=365, default=30)
        else:
            logger.warning(f"Invalid days parameter: {days}, using default=30")
            days_int = 30
        return _get_stop_loss_audit(cur, days_int)
    elif path == "/api/algo/risk-dashboard/exit-rules":
        # GOVERNANCE: Explicit parameter validation instead of silent defaults.
        days = params.get("days") if params and isinstance(params, dict) else None
        if days is None:
            logger.debug("days parameter missing, using default=30")
            days_int = 30
        elif isinstance(days, list) and len(days) > 0:
            days_int = safe_limit(days[0], max_val=365, default=30)
        else:
            logger.warning(f"Invalid days parameter: {days}, using default=30")
            days_int = 30
        return _get_exit_rules_distribution(cur, days_int)
    else:
        return error_response(404, "not_found", f"No risk dashboard handler for {path}")


def _get_comprehensive_risk_dashboard(cur: cursor) -> Any:
    """Get all current risk metrics in one view."""
    try:
        result: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "drawdown": None,
            "exposure_tier": None,
            "vix_metrics": None,
            "position_sizing_stats": None,
            "exit_rules_distribution": None,
        }

        # Drawdown
        try:
            drawdown_info = _fetch_drawdown_info(cur)
            result["drawdown"] = drawdown_info
        except Exception as e:
            raise RuntimeError(f"Critical risk metric unavailable: drawdown fetch failed: {e}") from e

        # Exposure tier
        try:
            tier_info = _fetch_exposure_tier_info(cur)
            result["exposure_tier"] = tier_info
        except Exception as e:
            raise RuntimeError(f"Critical risk metric unavailable: exposure tier fetch failed: {e}") from e

        # VIX metrics
        try:
            rows = execute_with_timeout(
                cur,
                """
                SELECT vix_level FROM market_health_daily
                WHERE vix_level IS NOT NULL
                ORDER BY date DESC LIMIT 1
            """,
                timeout_sec=5,
            )
            row = rows[0] if rows else None
            if row:
                vix = float(row["vix_level"]) if row["vix_level"] is not None else None
                if vix is None or vix <= 0:
                    raise RuntimeError(
                        f"Market health data invalid: VIX level missing or invalid ({vix}). "
                        "Cannot compute risk-adjusted drawdown multiplier. "
                        "Check market_health_daily table and load_market_health_daily logs."
                    )
                if vix <= 25:
                    risk_reduction = 1.0
                elif vix < 35:
                    risk_reduction = 0.75
                else:
                    risk_reduction = 0.0
                result["vix_metrics"] = {
                    "vix_level": vix,
                    "caution_threshold": 25.0,
                    "halt_threshold": 35.0,
                    "risk_reduction_multiplier": risk_reduction,
                }
            else:
                raise RuntimeError("VIX data unavailable: no recent market_health_daily records")
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Critical risk metric unavailable: VIX calculation failed: {e}") from e

        # Position sizing statistics
        try:
            rows = execute_with_timeout(
                cur,
                """
                SELECT
                    COUNT(*) as total_trades,
                    AVG(cascade_multiplier) as avg_cascade,
                    MIN(cascade_multiplier) as min_cascade,
                    MAX(cascade_multiplier) as max_cascade,
                    AVG(position_size_pct) as avg_position_size_pct
                FROM algo_position_sizing_audit
                WHERE created_at >= NOW() - INTERVAL '30 days'
            """,
                timeout_sec=8,
            )
            row = rows[0] if rows else None
            if row:
                result["position_sizing_stats"] = {
                    "trades_30d": row["total_trades"],
                    "avg_cascade_multiplier": (float(row["avg_cascade"]) if row["avg_cascade"] is not None else None),
                    "min_cascade_multiplier": (float(row["min_cascade"]) if row["min_cascade"] is not None else None),
                    "max_cascade_multiplier": (float(row["max_cascade"]) if row["max_cascade"] is not None else None),
                    "avg_position_size_pct": (
                        float(row["avg_position_size_pct"]) if row["avg_position_size_pct"] is not None else None
                    ),
                }
            else:
                raise RuntimeError("Position sizing audit data unavailable: no records in algo_position_sizing_audit")
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Critical risk metric unavailable: position sizing calculation failed: {e}") from e

        # Exit rules distribution (top 5)
        try:
            exit_rows = execute_with_timeout(
                cur,
                """
                SELECT exit_rule, COUNT(*) as count
                FROM algo_exit_rules_distribution
                WHERE created_at >= NOW() - INTERVAL '30 days'
                GROUP BY exit_rule
                ORDER BY count DESC
                LIMIT 5
            """,
                timeout_sec=8,
            )
            if not exit_rows:
                raise RuntimeError("Exit rules data unavailable: no records in algo_exit_rules_distribution")
            rules = {}
            for row in exit_rows:
                rules[row["exit_rule"]] = row["count"]
            result["exit_rules_distribution"] = rules
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Critical risk metric unavailable: exit rules calculation failed: {e}") from e

        freshness = check_data_freshness(cur, "algo_portfolio_snapshots", "snapshot_date", warning_days=1)
        response = json_response(200, result)
        if freshness:
            response["data_freshness"] = freshness
        return response
    except (ValueError, ZeroDivisionError, TypeError) as e:
        code, error_type, message = handle_db_error(e, "fetch comprehensive risk dashboard")
        return error_response(code, error_type, message)


def _fetch_drawdown_info(cur: cursor) -> Any:
    """Get current portfolio drawdown and thresholds.

    CAVEAT: Intraday drawdowns are invisible. Only EOD snapshots are tracked, so if the algo
    experiences a -15% intraday crash that recovers by close, max_drawdown_pct will show the
    recovery only. This is a known limitation of the current architecture.
    """
    rows = execute_with_timeout(
        cur,
        """
        SELECT MAX(total_portfolio_value) AS peak,
               (SELECT total_portfolio_value FROM algo_portfolio_snapshots
                ORDER BY snapshot_date DESC LIMIT 1) AS current
        FROM algo_portfolio_snapshots
    """,
        timeout_sec=8,
    )
    row = rows[0] if rows else None
    if row is None:
        raise ValueError(
            "Portfolio drawdown data unavailable: algo_portfolio_snapshots table empty or query failed. "
            "No portfolio history yet or snapshot loader not running. Check data loader status."
        )
    if row["peak"] is None or row["current"] is None:
        raise ValueError(
            f"Portfolio snapshot incomplete: peak={row['peak']}, current={row['current']}. "
            "Cannot compute drawdown without both values. Check snapshot calculation."
        )

    peak = float(row["peak"])
    current = float(row["current"])
    if peak <= 0:
        raise ValueError(
            f"Portfolio snapshot data invalid: peak value must be > 0, got {peak}. "
            "This indicates corrupted data or abnormal portfolio state. Check algo_portfolio_snapshots."
        )
    drawdown_pct = (peak - current) / peak * 100

    return {
        "current_drawdown_pct": max(0, drawdown_pct),
        "peak_portfolio_value": peak,
        "current_portfolio_value": current,
        "thresholds": {
            "caution_5pct": -5.0,
            "caution_10pct": -10.0,
            "caution_15pct": -15.0,
            "halt_20pct": -20.0,
        },
        "risk_multipliers": {
            "at_minus_5": 0.75,
            "at_minus_10": 0.5,
            "at_minus_15": 0.25,
            "at_minus_20": 0.0,
        },
        "status": _get_drawdown_status(drawdown_pct),
        "caveat": "Intraday gaps invisible - only EOD snapshots tracked",
    }


def _fetch_exposure_tier_info(cur: cursor) -> Any:
    """Get current market exposure tier (NORMAL/CAUTION/PRESSURE).

    FAIL-FAST: Raises if market exposure data is unavailable or invalid.
    Market tier is critical for position sizing — missing/invalid data must halt trading.
    No defaults allowed for exposure_pct or tier fields.
    """
    rows = execute_with_timeout(
        cur,
        """
        SELECT exposure_pct, regime, halt_reasons
        FROM market_exposure_daily
        ORDER BY date DESC LIMIT 1
    """,
        timeout_sec=5,
    )
    if not rows:
        raise ValueError("No market exposure data available (exposure_daily table empty)")

    row = rows[0]
    if not row:
        raise ValueError("Market exposure data invalid (null row)")

    try:
        exposure_pct_raw = row["exposure_pct"]
        if exposure_pct_raw is None or (isinstance(exposure_pct_raw, float) and exposure_pct_raw < 0):
            raise ValueError(
                "CRITICAL: exposure_pct missing or invalid from market_exposure_daily. "
                "Phase 4 (market exposure calculation) must complete successfully. "
                "Cannot compute position sizing without valid exposure_pct."
            )
        exposure_pct = float(exposure_pct_raw)

        tier_raw = row["regime"]
        if tier_raw is None or str(tier_raw).strip() == "":
            raise ValueError(
                "CRITICAL: regime missing from market_exposure_daily. "
                "Phase 4 (market exposure calculation) must compute valid regime. "
                "Cannot determine position size multiplier without valid regime."
            )
        tier = str(tier_raw).strip().lower()

        # Validate tier is one of the known regimes
        tier_multipliers = {
            "confirmed_uptrend": 1.0,
            "uptrend_under_pressure": 0.75,
            "caution": 0.50,
            "correction": 0.0,
        }
        if tier not in tier_multipliers:
            raise ValueError(
                f"CRITICAL: Invalid regime '{tier}' from market_exposure_daily. "
                f"Expected one of: {', '.join(tier_multipliers.keys())}. "
                f"Check market exposure computation — regime field corrupt."
            )

        rationale = row["halt_reasons"]
        if rationale is None:
            rationale = "No halt reasons recorded"
        else:
            rationale = str(rationale).strip()

        return {
            "current_tier": tier,
            "exposure_pct": exposure_pct,
            "rationale": rationale,
            "position_size_multiplier": tier_multipliers[tier],
        }
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.critical(f"Exposure tier computation failed: {e}")
        raise ValueError(f"Failed to compute market exposure tier: {e}") from e


def _get_drawdown_metrics(cur: cursor) -> Any:
    """GET /api/algo/risk-dashboard/drawdown"""
    try:
        info = _fetch_drawdown_info(cur)
        return json_response(200, info)
    except (ValueError, ZeroDivisionError, TypeError) as e:
        code, error_type, message = handle_db_error(e, "fetch drawdown metrics")
        return error_response(code, error_type, message)


def _get_exposure_tier_info(cur: cursor) -> Any:
    """GET /api/algo/risk-dashboard/exposure-tier"""
    try:
        info = _fetch_exposure_tier_info(cur)
        return json_response(200, info)
    except (ValueError, ZeroDivisionError, TypeError) as e:
        code, error_type, message = handle_db_error(e, "fetch exposure tier info")
        return error_response(code, error_type, message)


def _get_position_sizing_audit(cur: cursor, days: int) -> Any:
    """GET /api/algo/risk-dashboard/position-sizing-audit?days=30"""
    try:
        audit_rows = execute_with_timeout(
            cur,
            """
            SELECT symbol, signal_date, entry_price, stop_loss_price,
                   base_shares, final_shares, position_size_pct,
                   cascade_multiplier, reasons_json, created_at
            FROM algo_position_sizing_audit
            WHERE created_at >= NOW() - INTERVAL '1 day' * %s
            ORDER BY created_at DESC
            LIMIT 100
        """,
            (days,),
            timeout_sec=10,
        )

        items = []
        for row in audit_rows:
            if row["position_size_pct"] is None:
                error_msg = (
                    f"Position sizing audit incomplete for {row['symbol']}: position_size_pct missing. "
                    "Cannot provide forensics without calculated position size. Check position sizing calculation."
                )
                logger.error(error_msg)
                return error_response(503, "incomplete_audit_data", error_msg)
            if row["cascade_multiplier"] is None:
                error_msg = (
                    f"Position sizing audit incomplete for {row['symbol']}: cascade_multiplier missing. "
                    "Cannot determine position scaling without multiplier. Check cascade calculation."
                )
                logger.error(error_msg)
                return error_response(503, "incomplete_audit_data", error_msg)

            try:
                reasons = json.loads(row["reasons_json"]) if row["reasons_json"] else {}
            except (json.JSONDecodeError, TypeError):
                reasons = {}

            # FAIL-FAST: Extract required position sizing fields upfront with validation
            from utils.validation import DatabaseResultValidator

            symbol = DatabaseResultValidator.safe_get_str(row, "symbol", strict=True)
            base_shares = DatabaseResultValidator.safe_get_int(row, "base_shares", strict=True)
            final_shares = DatabaseResultValidator.safe_get_int(row, "final_shares", strict=True)
            entry_price = DatabaseResultValidator.safe_get_float(row, "entry_price", default=None)
            stop_loss_price = DatabaseResultValidator.safe_get_float(row, "stop_loss_price", default=None)
            signal_date = row.get("signal_date")
            created_at = row.get("created_at")

            items.append(
                {
                    "symbol": symbol,
                    "signal_date": (signal_date.isoformat() if signal_date is not None else None),
                    "entry_price": entry_price,
                    "stop_loss_price": stop_loss_price,
                    "base_shares": base_shares,
                    "final_shares": final_shares,
                    "position_size_pct": float(row["position_size_pct"]),
                    "cascade_multiplier": float(row["cascade_multiplier"]),
                    "reasons": reasons,
                    "created_at": (created_at.isoformat() if created_at is not None else None),
                }
            )

        return list_response(items)
    except (ValueError, ZeroDivisionError, TypeError) as e:
        code, error_type, message = handle_db_error(e, "fetch position sizing audit")
        return error_response(code, error_type, message)


def _get_stop_loss_audit(cur: cursor, days: int) -> Any:
    """GET /api/algo/risk-dashboard/stop-loss-audit?days=30"""
    try:
        cur.execute(
            """
            SELECT symbol, signal_date, entry_price, stop_loss_price,
                   distance_pct, stop_method, stop_reasoning, candidates_json, created_at
            FROM algo_stop_loss_audit
            WHERE created_at >= NOW() - INTERVAL '1 day' * %s
            ORDER BY created_at DESC
            LIMIT 100
        """,
            (days,),
        )

        items = []
        for row in cur.fetchall():
            if row["distance_pct"] is None:
                error_msg = (
                    f"Stop loss audit incomplete for {row['symbol']}: distance_pct missing. "
                    "Cannot compute R-multiple without stop loss distance. Check stop loss calculation."
                )
                logger.error(error_msg)
                return error_response(
                    503,
                    "incomplete_stop_loss_data",
                    error_msg,
                )

            try:
                candidates = json.loads(row["candidates_json"]) if row["candidates_json"] else {}
            except (json.JSONDecodeError, TypeError):
                candidates = {}

            # FAIL-FAST: Extract required stop loss audit fields upfront with validation
            from utils.validation import DatabaseResultValidator

            symbol = DatabaseResultValidator.safe_get_str(row, "symbol", strict=True)
            stop_method = DatabaseResultValidator.safe_get_str(row, "stop_method", strict=True)
            stop_reasoning = DatabaseResultValidator.safe_get_str(row, "stop_reasoning", strict=True)
            entry_price = DatabaseResultValidator.safe_get_float(row, "entry_price", default=None)
            stop_loss_price = DatabaseResultValidator.safe_get_float(row, "stop_loss_price", default=None)
            signal_date = row.get("signal_date")
            created_at = row.get("created_at")

            items.append(
                {
                    "symbol": symbol,
                    "signal_date": (signal_date.isoformat() if signal_date is not None else None),
                    "entry_price": entry_price,
                    "stop_loss_price": stop_loss_price,
                    "distance_pct": float(row["distance_pct"]),
                    "stop_method": stop_method,
                    "stop_reasoning": stop_reasoning,
                    "candidates": candidates,
                    "created_at": (created_at.isoformat() if created_at is not None else None),
                }
            )

        return list_response(items)
    except (ValueError, ZeroDivisionError, TypeError) as e:
        code, error_type, message = handle_db_error(e, "fetch stop loss audit")
        return error_response(code, error_type, message)


def _get_exit_rules_distribution(cur: cursor, days: int) -> Any:
    """GET /api/algo/risk-dashboard/exit-rules?days=30"""
    try:
        cur.execute(
            """
            SELECT exit_rule, COUNT(*) as count,
                   AVG(pnl_pct) as avg_pnl_pct,
                   AVG(r_multiple) as avg_r_multiple,
                   COUNT(CASE WHEN pnl_dollars > 0 THEN 1 END) as winning_count,
                   COUNT(CASE WHEN pnl_dollars < 0 THEN 1 END) as losing_count
            FROM algo_exit_rules_distribution
            WHERE created_at >= NOW() - INTERVAL '1 day' * %s
            GROUP BY exit_rule
            ORDER BY count DESC
        """,
            (days,),
        )

        items = []
        for row in cur.fetchall():
            # FAIL-FAST: Extract required exit rules fields upfront with validation
            from utils.validation import DatabaseResultValidator

            exit_rule = DatabaseResultValidator.safe_get_str(row, "exit_rule", strict=True)
            count = DatabaseResultValidator.safe_get_int(row, "count", strict=True)
            winning = DatabaseResultValidator.safe_get_int(row, "winning_count", default=0)
            losing = DatabaseResultValidator.safe_get_int(row, "losing_count", default=0)
            avg_pnl = DatabaseResultValidator.safe_get_float(row, "avg_pnl_pct", default=None)
            avg_r = DatabaseResultValidator.safe_get_float(row, "avg_r_multiple", default=None)

            win_rate = (winning / count * 100) if (count is not None and winning is not None and count > 0) else None
            items.append(
                {
                    "exit_rule": exit_rule,
                    "count": count,
                    "avg_pnl_pct": avg_pnl,
                    "avg_r_multiple": avg_r,
                    "winning_count": winning,
                    "losing_count": losing,
                    "win_rate_pct": win_rate,
                }
            )

        return list_response(items)
    except (ValueError, ZeroDivisionError, TypeError) as e:
        code, error_type, message = handle_db_error(e, "fetch exit rules distribution")
        return error_response(code, error_type, message)


def _get_drawdown_status(drawdown_pct: float) -> str:
    """Determine drawdown status."""
    if drawdown_pct >= 20:
        return "HALT"
    elif drawdown_pct >= 15:
        return "SEVERE"
    elif drawdown_pct >= 10:
        return "CAUTION"
    elif drawdown_pct >= 5:
        return "CAUTION"
    else:
        return "NORMAL"
