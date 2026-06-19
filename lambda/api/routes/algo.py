"""Route: algo - Refactored dispatcher with modular handlers."""

import logging
import re

import psycopg2
import psycopg2.errors
from routes.utils import (
    json_response,
    raise_api_error,
    raise_db_error,
    safe_days,
    safe_limit,
    safe_offset,
)

from utils.rate_limiting import (
    ADMIN_RATE_LIMITS,
    PUBLIC_RATE_LIMITS,
    check_admin_rate_limit,
    check_public_rate_limit,
)
from utils.validation import safe_float_strict

from .algo_handlers.config import (
    _get_algo_config,
    _get_algo_config_key,
    _reset_algo_config_key,
    _update_algo_config_key,
)

# Import handler functions from modular packages
from .algo_handlers.dashboard import (
    _get_algo_positions,
    _get_algo_status,
    _get_algo_trades,
    _get_circuit_breakers,
    _get_dashboard_signals,
    _get_equity_curve,
)
from .algo_handlers.external import (
    _get_economic_calendar,
    _get_sentiment,
)
from .algo_handlers.market import (
    _get_data_quality,
    _get_data_status,
    _get_market,
    _get_market_factors,
    _get_market_sentiment,
    _get_markets,
    _get_trend_criteria,
)
from .algo_handlers.metrics import (
    _get_algo_metrics,
    _get_algo_performance,
    _get_algo_portfolio,
    _get_daily_return_histogram,
    _get_holding_period_distribution,
    _get_performance_analytics,
    _get_performance_metrics_endpoint,
    _get_portfolio_summary,
    _get_risk_metrics,
    _get_stage_distribution,
    _get_trade_distribution,
)
from .algo_handlers.monitoring import (
    _get_algo_audit_log,
    _get_last_run,
    _get_notifications,
    _get_patrol_log,
    _trigger_data_patrol,
)
from .algo_handlers.orchestration import (
    _get_orchestrator_execution_details,
    _get_orchestrator_execution_failed,
    _get_orchestrator_execution_patterns,
    _get_orchestrator_execution_recent,
    _get_orchestrator_execution_stats,
)
from .algo_handlers.sector import (
    _get_algo_evaluate,
    _get_sector_breadth,
    _get_sector_position_warnings,
    _get_sector_rotation,
    _get_sector_stage2,
)
from .algo_handlers.signals import (
    _calculate_pre_trade_impact,
    _calculate_trade_preview,
    _get_rejection_funnel,
    _get_swing_scores,
    _get_swing_scores_history,
)


logger = logging.getLogger(__name__)


def _check_admin_access(jwt_claims: dict) -> bool:
    """Check if user has admin access from verified JWT claims only."""
    if not jwt_claims:
        return False
    groups = jwt_claims.get("cognito:groups")
    if groups is None:
        groups = []
    return "admin" in groups


def handle(
    cur,
    path: str,
    method: str,
    params: dict,
    body: dict | None = None,
    jwt_claims: dict | None = None,
    idempotency_key: str | None = None,
) -> dict:
    """Handle /api/algo/* endpoints."""
    try:
        return _dispatch(cur, path, method, params, body, jwt_claims, idempotency_key)
    except Exception as e:
        # Re-raise APIException so api_router can format it properly
        try:
            from exceptions import APIException
            if isinstance(e, APIException):
                raise
        except ImportError:
            pass
        logger.error(f"[ALGO] unhandled {type(e).__name__}: {e}", exc_info=True)
        raise_db_error(e, "handle algo")


def _dispatch(
    cur,
    path: str,
    method: str,
    params: dict,
    body: dict | None = None,
    jwt_claims: dict | None = None,
    idempotency_key: str | None = None,
) -> dict:
    user_id = (jwt_claims or {}).get("sub", "")

    # SECURITY: Rate limit public endpoints to prevent DoS attacks
    if path in PUBLIC_RATE_LIMITS:
        limits = PUBLIC_RATE_LIMITS[path]
        is_allowed, error_msg = check_public_rate_limit(
            path, max_requests=limits["max_requests"], window_seconds=limits["window"]
        )
        if not is_allowed:
            logger.warning(f"Public endpoint rate limit exceeded for {path}")
            raise_api_error(429, "too_many_requests", error_msg)

    # Notification mark-as-read
    if method == "PATCH" and path.endswith("/read") and "/notifications/" in path:
        notif_id = path.split("/notifications/")[-1].replace("/read", "")
        if not _check_admin_access(
            jwt_claims
        ):
            logger.warning(
                f"Unauthorized notification mark-read attempt by {(jwt_claims or {}).get('sub')}"
            )
            raise_api_error(403, "forbidden", "Admin access required")
        try:
            try:
                notif_id_int = int(notif_id)
            except ValueError:
                raise_api_error(400, "bad_request", "ID must be numeric")

            cur.execute(
                "SELECT id FROM algo_notifications WHERE id=%s LIMIT 1", (notif_id_int,)
            )
            if not cur.fetchone():
                raise_api_error(404, "not_found", "Notification not found")

            cur.execute(
                "UPDATE algo_notifications SET seen=TRUE, seen_at=NOW() WHERE id=%s",
                (notif_id_int,),
            )
            return json_response(200, {"status": "updated"})
        except (
            psycopg2.errors.UndefinedTable,
            psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError,
            psycopg2.DatabaseError,
            Exception,
        ) as e:
            logger.error(f"Failed to mark notification as read: {type(e).__name__}")
            raise_db_error(e, "mark notification as read")

    # Notification delete
    if method == "DELETE" and "/notifications/" in path:
        notif_id = path.split("/notifications/")[-1]
        if not _check_admin_access(
            jwt_claims
        ):
            logger.warning(
                f"Unauthorized notification delete attempt by {(jwt_claims or {}).get('sub')}"
            )
            raise_api_error(403, "forbidden", "Admin access required")
        try:
            try:
                notif_id_int = int(notif_id)
            except ValueError:
                raise_api_error(400, "bad_request", "ID must be numeric")

            cur.execute(
                "SELECT id FROM algo_notifications WHERE id=%s LIMIT 1", (notif_id_int,)
            )
            if not cur.fetchone():
                raise_api_error(404, "not_found", "Notification not found")

            cur.execute("DELETE FROM algo_notifications WHERE id=%s", (notif_id_int,))
            return json_response(200, {"status": "deleted"})
        except (
            psycopg2.errors.UndefinedTable,
            psycopg2.errors.UndefinedColumn,
            psycopg2.OperationalError,
            psycopg2.DatabaseError,
            Exception,
        ) as e:
            logger.error(f"Failed to delete notification: {type(e).__name__}")
            raise_db_error(e, "delete notification")

    # Data patrol trigger
    if method == "POST" and path == "/api/algo/patrol":
        if not _check_admin_access(
            jwt_claims
        ):
            logger.warning(
                f"Unauthorized algo patrol access attempt by {(jwt_claims or {}).get('sub')}"
            )
            raise_api_error(403, "forbidden", "Admin access required")

        if path in ADMIN_RATE_LIMITS:
            limits = ADMIN_RATE_LIMITS[path]
            is_allowed, error_msg = check_admin_rate_limit(
                user_id,
                path,
                max_requests=limits["max_requests"],
                window_seconds=limits["window"],
            )
            if not is_allowed:
                raise_api_error(429, "too_many_requests", error_msg)

        response = _trigger_data_patrol()
        return response

    # Trade preview calculation
    if method == "POST" and path == "/api/algo/preview":
        if not body:
            raise_api_error(400, "bad_request", "Request body required")
        if not isinstance(body, dict):
            raise_api_error(400, "bad_request", "Request body must be a JSON object")
        return _calculate_trade_preview(cur, body)

    # Pre-trade impact calculation
    if method == "POST" and path == "/api/algo/pre-trade-impact":
        if not body:
            raise_api_error(400, "bad_request", "Request body required")
        if not isinstance(body, dict):
            raise_api_error(400, "bad_request", "Request body must be a JSON object")
        return _calculate_pre_trade_impact(cur, body)

    # Dispatch to handler functions by path
    if path == "/api/algo/status":
        return _get_algo_status(cur)
    elif path == "/api/algo/trades":
        limit_str = params.get("limit", [None])[0] if params else None
        limit = safe_limit(limit_str, max_val=10000, default=100)
        status_filter = params.get("status", [None])[0] if params else None
        if status_filter and status_filter not in ("open", "closed", "halted", "cancelled"):
            raise_api_error(400, "bad_request", f"Invalid status '{status_filter}'. Must be one of: open, closed, halted, cancelled")
        is_admin = _check_admin_access(jwt_claims)
        effective_user_id = None if is_admin else user_id
        return _get_algo_trades(cur, limit, user_id=effective_user_id, status=status_filter)
    elif path == "/api/algo/positions":
        return _get_algo_positions(cur, user_id=user_id)
    elif path == "/api/algo/dashboard-signals":
        return _get_dashboard_signals(cur)
    elif path == "/api/algo/performance":
        return _get_algo_performance(cur)
    elif path == "/api/algo/circuit-breakers":
        return _get_circuit_breakers(cur)
    elif path == "/api/algo/equity-curve":
        days_str = params.get("limit", [None])[0] if params else None
        days = safe_days(days_str, max_val=365, default=180)
        return _get_equity_curve(cur, days)
    elif path == "/api/algo/data-status":
        return _get_data_status(cur)
    elif path == "/api/algo/notifications":
        if not _check_admin_access(
            jwt_claims
        ):
            logger.warning(
                f"Unauthorized notifications access attempt by {(jwt_claims or {}).get('sub')}"
            )
            raise_api_error(403, "forbidden", "Admin access required")
        return _get_notifications(cur, params, jwt_claims)
    elif path == "/api/algo/patrol-log":
        if not _check_admin_access(
            jwt_claims
        ):
            logger.warning(
                f"Unauthorized algo patrol-log access attempt by {(jwt_claims or {}).get('sub')}"
            )
            raise_api_error(403, "forbidden", "Admin access required")
        limit_str = params.get("limit", [None])[0] if params else None
        limit = safe_limit(limit_str, max_val=10000, default=100)
        offset_str = params.get("offset", [None])[0] if params else None
        offset = safe_offset(offset_str)
        return _get_patrol_log(cur, limit, offset)
    elif path == "/api/algo/sector-rotation":
        days_str = params.get("limit", [None])[0] if params else None
        days = safe_days(days_str, max_val=365, default=180)
        return _get_sector_rotation(cur, days)
    elif path == "/api/algo/sector-breadth":
        return _get_sector_breadth(cur)
    elif path == "/api/algo/sector-position-warnings":
        return _get_sector_position_warnings(cur)
    elif path == "/api/algo/swing-scores":
        limit_str = params.get("limit", [None])[0] if params else None
        limit = safe_limit(limit_str, max_val=10000, default=100)
        min_score_str = params.get("min_score", [None])[0] if params else None
        min_score = (
            safe_float_strict(min_score_str, context="query param min_score")
            if min_score_str
            else None
        )
        if min_score_str and min_score is None:
            raise_api_error(400, "bad_request", "min_score must be numeric")
        symbol_filter = params.get("symbol", [None])[0] if params else None
        if symbol_filter:
            if not re.match(r"^[A-Z0-9\-\^]{1,10}$", symbol_filter.upper()):
                raise_api_error(400, "bad_request", "Invalid symbol format")
        return _get_swing_scores(cur, limit, min_score, symbol_filter)
    elif path == "/api/algo/swing-scores-history":
        days_str = params.get("days", [None])[0] if params else None
        days = safe_days(days_str, max_val=365, default=30)
        return _get_swing_scores_history(cur, days)
    elif path == "/api/algo/rejection-funnel":
        return _get_rejection_funnel(cur)
    elif path == "/api/algo/markets":
        return _get_markets(cur)
    elif path == "/api/algo/market":
        return _get_market(cur)
    elif path == "/api/algo/market-factors":
        return _get_market_factors(cur)
    elif path == "/api/algo/portfolio":
        return _get_algo_portfolio(cur)
    elif path == "/api/algo/metrics":
        return _get_algo_metrics(cur)
    elif path == "/api/algo/risk-metrics":
        return _get_risk_metrics(cur)
    elif path == "/api/algo/performance-analytics":
        return _get_performance_analytics(cur)
    elif path == "/api/algo/sentiment":
        return _get_sentiment(cur)
    elif path == "/api/algo/economic-calendar":
        return _get_economic_calendar(cur)
    elif path == "/api/algo/evaluate":
        return _get_algo_evaluate(cur)
    elif path == "/api/algo/data-quality":
        return _get_data_quality(cur)
    elif path == "/api/algo/sector-stage2":
        return _get_sector_stage2(cur)
    elif path == "/api/algo/config":
        return _get_algo_config(cur)
    elif path.startswith("/api/algo/config/"):
        if not _check_admin_access(
            jwt_claims
        ):
            logger.warning(
                f"Unauthorized algo config access attempt by {(jwt_claims or {}).get('sub')}"
            )
            raise_api_error(403, "forbidden", "Admin access required")
        key = path[len("/api/algo/config/") :]
        if method == "GET":
            return _get_algo_config_key(cur, key)
        elif method == "PUT":
            if not body or not isinstance(body, dict):
                raise_api_error(400, "bad_request", "Request body must be a JSON object")
            actor = (jwt_claims or {}).get("sub", "unknown")
            return _update_algo_config_key(cur, key, body, actor)
        elif method == "DELETE":
            actor = (jwt_claims or {}).get("sub", "unknown")
            return _reset_algo_config_key(cur, key, actor)
    elif path == "/api/algo/last-run":
        return _get_last_run(cur)
    elif path == "/api/algo/audit-log":
        if not _check_admin_access(
            jwt_claims
        ):
            logger.warning(
                f"Unauthorized algo audit-log access attempt by {(jwt_claims or {}).get('sub')}"
            )
            raise_api_error(403, "forbidden", "Admin access required")
        limit_str = params.get("limit", [None])[0] if params else None
        limit = safe_limit(limit_str, max_val=10000, default=100)
        offset_str = params.get("offset", [None])[0] if params else None
        offset = safe_offset(offset_str)
        action_type = params.get("action_type", [None])[0] if params else None
        if action_type:
            action_type = action_type.lower()
            valid_action_types = {
                "entry", "exit", "alert", "halt", "reconciliation", "error", "stop", "skip", "pass",
                "phase_0_halt_flag_detected", "phase_0_oom_prevention", "phase_0_table_validation",
                "phase_1_data_freshness", "phase_1_data_patrol", "phase_1_pipeline_health",
                "phase_1_signal_quality_scores", "phase_2_circuit_breakers", "phase_2_market_circuit_breaker",
                "phase_3_position_monitor", "phase_3_single_stock_halts", "phase_3_halt_check_error",
                "phase_3a_reconciliation", "phase_3b_exposure_policy", "phase_4_exit_execution",
                "phase_5_signal_generation", "phase_6_entry_execution", "phase_7_reconciliation",
                "phase_7_daily_report", "phase_7_ic_computation", "phase_7_performance",
                "phase_7_risk_metrics", "phase_7_signal_attribution", "phase_7_weight_optimization",
                "halt_flag_detected", "position_review", "position_monitor", "pipeline_health",
                "single_stock_halts", "halt_check_error",
            }
            if action_type not in valid_action_types:
                raise_api_error(
                    400, "bad_request", f"Invalid action_type: {action_type}"
                )
        return _get_algo_audit_log(cur, limit, offset, action_type)
    elif path == "/api/algo/execution/recent":
        if not _check_admin_access(
            jwt_claims
        ):
            logger.warning(
                f"Unauthorized execution history access attempt by {(jwt_claims or {}).get('sub')}"
            )
            raise_api_error(403, "forbidden", "Admin access required")
        days_str = params.get("days", [None])[0] if params else None
        days = safe_days(days_str, default=7, max_val=90)
        limit_str = params.get("limit", [None])[0] if params else None
        limit = safe_limit(limit_str, max_val=1000, default=50)
        return _get_orchestrator_execution_recent(cur, days, limit)
    elif path == "/api/algo/execution/failed":
        if not _check_admin_access(
            jwt_claims
        ):
            logger.warning(
                f"Unauthorized execution history access attempt by {(jwt_claims or {}).get('sub')}"
            )
            raise_api_error(403, "forbidden", "Admin access required")
        days_str = params.get("days", [None])[0] if params else None
        days = safe_days(days_str, default=30, max_val=90)
        return _get_orchestrator_execution_failed(cur, days)
    elif path.startswith("/api/algo/execution/details/"):
        if not _check_admin_access(
            jwt_claims
        ):
            logger.warning(
                f"Unauthorized execution history access attempt by {(jwt_claims or {}).get('sub')}"
            )
            raise_api_error(403, "forbidden", "Admin access required")
        run_id = path.split("/api/algo/execution/details/")[-1]
        return _get_orchestrator_execution_details(cur, run_id)
    elif path == "/api/algo/execution/patterns":
        if not _check_admin_access(
            jwt_claims
        ):
            logger.warning(
                f"Unauthorized execution history access attempt by {(jwt_claims or {}).get('sub')}"
            )
            raise_api_error(403, "forbidden", "Admin access required")
        days_str = params.get("days", [None])[0] if params else None
        days = safe_days(days_str, default=30, max_val=90)
        return _get_orchestrator_execution_patterns(cur, days)
    elif path == "/api/algo/execution/stats":
        if not _check_admin_access(
            jwt_claims
        ):
            logger.warning(
                f"Unauthorized execution history access attempt by {(jwt_claims or {}).get('sub')}"
            )
            raise_api_error(403, "forbidden", "Admin access required")
        days_str = params.get("days", [None])[0] if params else None
        days = safe_days(days_str, default=7, max_val=90)
        return _get_orchestrator_execution_stats(cur, days)
    elif path == "/api/algo/daily-return-histogram":
        if path in ADMIN_RATE_LIMITS:
            limits = ADMIN_RATE_LIMITS[path]
            is_allowed, error_msg = check_admin_rate_limit(
                user_id, path,
                max_requests=limits["max_requests"],
                window_seconds=limits["window"],
            )
            if not is_allowed:
                raise_api_error(429, "too_many_requests", error_msg)
        return _get_daily_return_histogram(cur)
    elif path == "/api/algo/trade-distribution":
        if path in ADMIN_RATE_LIMITS:
            limits = ADMIN_RATE_LIMITS[path]
            is_allowed, error_msg = check_admin_rate_limit(
                user_id, path,
                max_requests=limits["max_requests"],
                window_seconds=limits["window"],
            )
            if not is_allowed:
                raise_api_error(429, "too_many_requests", error_msg)
        return _get_trade_distribution(cur)
    elif path == "/api/algo/holding-period-distribution":
        if path in ADMIN_RATE_LIMITS:
            limits = ADMIN_RATE_LIMITS[path]
            is_allowed, error_msg = check_admin_rate_limit(
                user_id, path,
                max_requests=limits["max_requests"],
                window_seconds=limits["window"],
            )
            if not is_allowed:
                raise_api_error(429, "too_many_requests", error_msg)
        return _get_holding_period_distribution(cur)
    elif path == "/api/algo/stage-distribution":
        if path in ADMIN_RATE_LIMITS:
            limits = ADMIN_RATE_LIMITS[path]
            is_allowed, error_msg = check_admin_rate_limit(
                user_id, path,
                max_requests=limits["max_requests"],
                window_seconds=limits["window"],
            )
            if not is_allowed:
                raise_api_error(429, "too_many_requests", error_msg)
        return _get_stage_distribution(cur)
    elif path == "/api/algo/market-sentiment":
        if path in ADMIN_RATE_LIMITS:
            limits = ADMIN_RATE_LIMITS[path]
            is_allowed, error_msg = check_admin_rate_limit(
                user_id, path,
                max_requests=limits["max_requests"],
                window_seconds=limits["window"],
            )
            if not is_allowed:
                raise_api_error(429, "too_many_requests", error_msg)
        return _get_market_sentiment(cur)
    elif path == "/api/algo/trend-criteria":
        if path in ADMIN_RATE_LIMITS:
            limits = ADMIN_RATE_LIMITS[path]
            is_allowed, error_msg = check_admin_rate_limit(
                user_id, path,
                max_requests=limits["max_requests"],
                window_seconds=limits["window"],
            )
            if not is_allowed:
                raise_api_error(429, "too_many_requests", error_msg)
        return _get_trend_criteria(cur)
    elif path == "/api/algo/performance-metrics":
        if path in ADMIN_RATE_LIMITS:
            limits = ADMIN_RATE_LIMITS[path]
            is_allowed, error_msg = check_admin_rate_limit(
                user_id, path,
                max_requests=limits["max_requests"],
                window_seconds=limits["window"],
            )
            if not is_allowed:
                raise_api_error(429, "too_many_requests", error_msg)
        return _get_performance_metrics_endpoint(cur)
    elif path == "/api/algo/portfolio-summary":
        if path in ADMIN_RATE_LIMITS:
            limits = ADMIN_RATE_LIMITS[path]
            is_allowed, error_msg = check_admin_rate_limit(
                user_id, path,
                max_requests=limits["max_requests"],
                window_seconds=limits["window"],
            )
            if not is_allowed:
                raise_api_error(429, "too_many_requests", error_msg)
        return _get_portfolio_summary(cur)
    else:
        raise_api_error(404, "not_found", f"No algo handler for {path}")
