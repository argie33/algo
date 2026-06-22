"""Fetcher functions for signal data and evaluation metrics."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .api_data_layer import api_call

ET = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)


def record_data_quality_issue(*args, **kwargs):
    """Placeholder for data quality issue recording."""


def _format_fetcher_error(fetcher_name: str, error: Exception) -> str:
    """Format fetcher error with endpoint context for better troubleshooting.

    Returns error string like: "Fetcher run (/api/algo/last-run: Last algo run status) timed out"
    """
    from .fetchers import FETCHER_METADATA

    meta = FETCHER_METADATA.get(fetcher_name)
    endpoint = meta.get("endpoint", "unknown endpoint") if meta else "unknown endpoint"
    desc = meta.get("desc", "") if meta else ""

    error_type = type(error).__name__
    error_msg = str(error)

    context = f"{endpoint}"
    if desc:
        context += f": {desc}"

    if error_msg:
        return f"Fetcher {fetcher_name} ({context}) - {error_type}: {error_msg}"
    else:
        return f"Fetcher {fetcher_name} ({context}) - {error_type}"


def _get_endpoint_path(fetcher_key: str, params: dict | None = None) -> str:
    """Map fetcher key to full endpoint path with optional query parameters.

    Examples:
      _get_endpoint_path('pos') → '/api/algo/positions'
      _get_endpoint_path('trades', params={'limit': 10}) → '/api/algo/trades' (params passed to api_call)
    """
    from .fetchers import FETCHER_METADATA

    meta = FETCHER_METADATA.get(fetcher_key)
    if not meta:
        # For endpoints with direct paths (like '/api/algo/last-run')
        return fetcher_key
    endpoint = meta.get("endpoint", "")
    if not endpoint:
        return fetcher_key
    return endpoint


def fetch_signals(c):
    """Fetch dashboard signals from API. Fail-fast: error only on failure."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("sig"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("sig", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        if not data:
            error_msg = "No data returned from /api/algo/dashboard-signals"
            logger.error(error_msg)
            record_data_quality_issue("sig", "validation", "no_data")
            return FetcherValidator.build_error_response(error_msg)

        result = data
        buy_sigs = result.get("buy_sigs")
        if buy_sigs is not None and not isinstance(buy_sigs, list):
            error_msg = f"Signals response 'buy_sigs' must be list, got {type(buy_sigs).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sig", "validation", "buy_sigs_invalid_type")
            return FetcherValidator.build_error_response(error_msg)

        near = result.get("near")
        if near is not None and not isinstance(near, list):
            error_msg = f"Signals response 'near' must be list, got {type(near).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sig", "validation", "near_invalid_type")
            return FetcherValidator.build_error_response(error_msg)

        top_a = result.get("top_a")
        if top_a is not None and not isinstance(top_a, list):
            error_msg = f"Signals response 'top_a' must be list, got {type(top_a).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sig", "validation", "top_a_invalid_type")
            return FetcherValidator.build_error_response(error_msg)

        trend = result.get("trend")
        if trend is not None and not isinstance(trend, list):
            error_msg = f"Signals response 'trend' must be list, got {type(trend).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sig", "validation", "trend_invalid_type")
            return FetcherValidator.build_error_response(error_msg)

        grades = result.get("grades")
        if grades is not None and not isinstance(grades, dict):
            error_msg = f"Signals response 'grades' must be dict, got {type(grades).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sig", "validation", "grades_invalid_type")
            return FetcherValidator.build_error_response(error_msg)

        n = result.get("n")
        if n is None and buy_sigs:
            n = len(buy_sigs)
        total = result.get("total")
        if total is None and n is not None:
            total = n
        elif total is None and buy_sigs:
            total = len(buy_sigs)

        return {
            "n": n,
            "total": total,
            "buy_sigs": buy_sigs,
            "grades": grades,
            "near": near,
            "top_a": top_a,
            "trend": trend,
            "date": result.get("date"),
            "timestamp": datetime.now(ET),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("sig", e)
        logger.error(error_msg)
        record_data_quality_issue("sig", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_signal_eval(c):
    """Fetch signal evaluation stats from API."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("sig_eval"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("sig_eval", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        result = data
        return {
            "total": int(result.get("total")),
            "t1": int(result.get("t1")),
            "t2": int(result.get("t2")),
            "t3": int(result.get("t3")),
            "t4": int(result.get("t4")),
            "t5": int(result.get("t5")),
            "avg_score": float(result.get("avg_score")),
            "date": result.get("signal_date"),
            "rejected": result.get("rejected"),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("sig_eval", e)
        logger.error(error_msg)
        record_data_quality_issue("sig_eval", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_scores(c):
    """Fetch top stock scores from /api/scores. Used by signals panel for composite score display."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        top_data = api_call("/api/scores", params={"limit": 50, "sortOrder": "desc"})

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(top_data)
        if is_error:
            record_data_quality_issue("scores", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        # Validate response structure - fail-fast if missing items field
        if not isinstance(top_data, dict):
            error_msg = f"Scores API response: expected dict, got {type(top_data).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        if "items" not in top_data:
            error_msg = "Scores API response: missing required 'items' field"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "missing_items_field")
            return FetcherValidator.build_error_response(error_msg)

        items = top_data["items"]
        if not isinstance(items, list):
            error_msg = "Scores API response: 'items' field is not a list"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "items_not_list")
            return FetcherValidator.build_error_response(error_msg)

        if not items:
            error_msg = "No score data available"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "no_items")
            return FetcherValidator.build_error_response(error_msg)

        return {"top": items}
    except Exception as e:
        error_msg = _format_fetcher_error("scores", e)
        logger.error(error_msg)
        record_data_quality_issue("scores", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
