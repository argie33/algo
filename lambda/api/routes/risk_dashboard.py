"""Route: risk_dashboard - Real-time risk metrics for decision-making.

Endpoints:
  /api/algo/risk-dashboard - All current risk metrics
  /api/algo/risk-dashboard/drawdown - Current drawdown %
  /api/algo/risk-dashboard/exposure-tier - Current tier and why
  /api/algo/risk-dashboard/position-sizing-audit - Why trades were sized as they were
  /api/algo/risk-dashboard/stop-loss-audit - Why stops were chosen
  /api/algo/risk-dashboard/exit-rules - Which exit rules fired most
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, cast

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

from utils.validation import CognitoValidator

logger = logging.getLogger(__name__)


def _check_admin_access(jwt_claims: dict | None) -> bool:
    """Check if user has admin access from verified JWT claims only."""
    return bool(CognitoValidator.validate_admin_access(jwt_claims))


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Route risk dashboard endpoints."""
    if os.environ.get("DEV_BYPASS_AUTH") != "true" and not _check_admin_access(jwt_claims):
        return cast(dict[str, Any], error_response(403, "forbidden", "Admin access required"))
    if path == "/api/algo/risk-dashboard":
        return _get_comprehensive_risk_dashboard(cur)
    elif path == "/api/algo/risk-dashboard/drawdown":
        return _get_drawdown_metrics(cur)
    elif path == "/api/algo/risk-dashboard/exposure-tier":
        return _get_exposure_tier_info(cur)
    elif path == "/api/algo/risk-dashboard/position-sizing-audit":
        days = params.get("days", ["30"])
        days_int = safe_limit(days[0], max_val=365)
        return _get_position_sizing_audit(cur, days_int)
    elif path == "/api/algo/risk-dashboard/stop-loss-audit":
        days = params.get("days", ["30"])
        days_int = safe_limit(days[0], max_val=365)
        return _get_stop_loss_audit(cur, days_int)
    elif path == "/api/algo/risk-dashboard/exit-rules":
        days = params.get("days", ["30"])
        days_int = safe_limit(days[0], max_val=365)
        return _get_exit_rules_distribution(cur, days_int)
    else:
        return cast(dict[str, Any], error_response(404, "not_found", f"No risk dashboard handler for {path}"))


def _get_comprehensive_risk_dashboard(cur: cursor) -> dict[str, Any]:
    """Get all current risk metrics in one view."""
    try:
        result = {
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
            result["drawdown"] = drawdown_info  # type: ignore[assignment]
        except Exception as e:
            logger.warning(f"Drawdown fetch failed: {e}")
            result["drawdown"] = None

        # Exposure tier
        try:
            tier_info = _fetch_exposure_tier_info(cur)
            result["exposure_tier"] = tier_info  # type: ignore[assignment]
        except Exception as e:
            logger.warning(f"Exposure tier fetch failed: {e}")
            result["exposure_tier"] = None

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
                vix = float(row["vix_level"]) if row["vix_level"] else None
                if vix is None or vix <= 25:
                    risk_reduction = 1.0
                elif vix < 35:
                    risk_reduction = 0.75
                else:
                    risk_reduction = 0.0
                result["vix_metrics"] = {  # type: ignore[assignment]
                    "vix_level": vix,
                    "caution_threshold": 25.0,
                    "halt_threshold": 35.0,
                    "risk_reduction_multiplier": risk_reduction,
                }
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.warning(f"VIX fetch failed: {e}")

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
                result["position_sizing_stats"] = {  # type: ignore[assignment]
                    "trades_30d": row["total_trades"],
                    "avg_cascade_multiplier": (float(row["avg_cascade"]) if row["avg_cascade"] else None),
                    "min_cascade_multiplier": (float(row["min_cascade"]) if row["min_cascade"] else None),
                    "max_cascade_multiplier": (float(row["max_cascade"]) if row["max_cascade"] else None),
                    "avg_position_size_pct": (
                        float(row["avg_position_size_pct"]) if row["avg_position_size_pct"] else None
                    ),
                }
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.warning(f"Position sizing stats fetch failed: {e}")

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
            rules = {}
            for row in exit_rows:
                rules[row["exit_rule"]] = row["count"]
            result["exit_rules_distribution"] = rules  # type: ignore[assignment]
        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.warning(f"Exit rules fetch failed: {e}")

        freshness = check_data_freshness(cur, "algo_portfolio_snapshots", "snapshot_date", warning_days=1)
        response = json_response(200, result)
        if freshness:
            response["data_freshness"] = freshness
        return response
    except (ValueError, ZeroDivisionError, TypeError) as e:
        code, error_type, message = handle_db_error(e, "fetch comprehensive risk dashboard")
        return cast(dict[str, Any], error_response(code, error_type, message))


def _fetch_drawdown_info(cur: cursor) -> dict[str, Any]:
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
    if not row or not row["peak"] or not row["current"]:
        return {"current_drawdown_pct": 0, "status": "no_history"}

    peak = float(row["peak"])
    current = float(row["current"])
    drawdown_pct = ((peak - current) / peak) * 100 if peak > 0 else 0

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


def _fetch_exposure_tier_info(cur: cursor) -> dict[str, Any]:
    """Get current market exposure tier (NORMAL/CAUTION/PRESSURE)."""
    try:
        rows = execute_with_timeout(
            cur,
            """
            SELECT exposure_pct, regime, halt_reasons
            FROM market_exposure_daily
            ORDER BY date DESC LIMIT 1
        """,
            timeout_sec=5,
        )
        row = rows[0] if rows else None
        if row:
            exposure_pct = float(row["exposure_pct"]) if row["exposure_pct"] else 100
            tier = row["regime"] or "NORMAL"
            rationale = row["halt_reasons"] or "No data"
            return {
                "current_tier": tier,
                "exposure_pct": exposure_pct,
                "rationale": rationale,
                "position_size_multiplier": {
                    "confirmed_uptrend": 1.0,
                    "uptrend_under_pressure": 0.75,
                    "caution": 0.50,
                    "correction": 0.0,
                }.get(tier.lower() if tier else "", 1.0),
            }
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.warning(f"Exposure tier computation failed, using defaults: {e}")

    return {
        "current_tier": "NORMAL",
        "exposure_pct": 100,
        "rationale": "Default (no data)",
        "position_size_multiplier": 1.0,
    }


def _get_drawdown_metrics(cur: cursor) -> dict[str, Any]:
    """GET /api/algo/risk-dashboard/drawdown"""
    try:
        info = _fetch_drawdown_info(cur)
        return cast(dict[str, Any], json_response(200, info))
    except (ValueError, ZeroDivisionError, TypeError) as e:
        code, error_type, message = handle_db_error(e, "fetch drawdown metrics")
        return cast(dict[str, Any], error_response(code, error_type, message))


def _get_exposure_tier_info(cur: cursor) -> dict[str, Any]:
    """GET /api/algo/risk-dashboard/exposure-tier"""
    try:
        info = _fetch_exposure_tier_info(cur)
        return cast(dict[str, Any], json_response(200, info))
    except (ValueError, ZeroDivisionError, TypeError) as e:
        code, error_type, message = handle_db_error(e, "fetch exposure tier info")
        return cast(dict[str, Any], error_response(code, error_type, message))


def _get_position_sizing_audit(cur: cursor, days: int) -> dict[str, Any]:
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
            try:
                reasons = json.loads(row["reasons_json"]) if row["reasons_json"] else {}
            except (json.JSONDecodeError, TypeError):
                reasons = {}

            items.append(
                {
                    "symbol": row["symbol"],
                    "signal_date": (row["signal_date"].isoformat() if row["signal_date"] else None),
                    "entry_price": (float(row["entry_price"]) if row["entry_price"] else None),
                    "stop_loss_price": (float(row["stop_loss_price"]) if row["stop_loss_price"] else None),
                    "base_shares": row["base_shares"],
                    "final_shares": row["final_shares"],
                    "position_size_pct": (float(row["position_size_pct"]) if row["position_size_pct"] else 0),
                    "cascade_multiplier": (float(row["cascade_multiplier"]) if row["cascade_multiplier"] else 1.0),
                    "reasons": reasons,
                    "created_at": (row["created_at"].isoformat() if row["created_at"] else None),
                }
            )

        return list_response(items)
    except (ValueError, ZeroDivisionError, TypeError) as e:
        code, error_type, message = handle_db_error(e, "fetch position sizing audit")
        return cast(dict[str, Any], error_response(code, error_type, message))


def _get_stop_loss_audit(cur: cursor, days: int) -> dict[str, Any]:
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
            try:
                candidates = json.loads(row["candidates_json"]) if row["candidates_json"] else {}
            except (json.JSONDecodeError, TypeError):
                candidates = {}

            items.append(
                {
                    "symbol": row["symbol"],
                    "signal_date": (row["signal_date"].isoformat() if row["signal_date"] else None),
                    "entry_price": (float(row["entry_price"]) if row["entry_price"] else None),
                    "stop_loss_price": (float(row["stop_loss_price"]) if row["stop_loss_price"] else None),
                    "distance_pct": (float(row["distance_pct"]) if row["distance_pct"] else 0),
                    "stop_method": row["stop_method"],
                    "stop_reasoning": row["stop_reasoning"],
                    "candidates": candidates,
                    "created_at": (row["created_at"].isoformat() if row["created_at"] else None),
                }
            )

        return list_response(items)
    except (ValueError, ZeroDivisionError, TypeError) as e:
        code, error_type, message = handle_db_error(e, "fetch stop loss audit")
        return cast(dict[str, Any], error_response(code, error_type, message))


def _get_exit_rules_distribution(cur: cursor, days: int) -> dict[str, Any]:
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
            count = row["count"]
            winning = row["winning_count"]
            losing = row["losing_count"]
            win_rate = (winning / count * 100) if (count is not None and winning is not None and count > 0) else None
            items.append(
                {
                    "exit_rule": row["exit_rule"],
                    "count": count,
                    "avg_pnl_pct": (float(row["avg_pnl_pct"]) if row["avg_pnl_pct"] else None),
                    "avg_r_multiple": (float(row["avg_r_multiple"]) if row["avg_r_multiple"] else None),
                    "winning_count": winning,
                    "losing_count": losing,
                    "win_rate_pct": win_rate,
                }
            )

        return list_response(items)
    except (ValueError, ZeroDivisionError, TypeError) as e:
        code, error_type, message = handle_db_error(e, "fetch exit rules distribution")
        return cast(dict[str, Any], error_response(code, error_type, message))


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
