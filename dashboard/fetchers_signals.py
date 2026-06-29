"""Fetcher functions for signal data and evaluation metrics."""

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from utils.safe_data_conversion import safe_float, safe_int

from .api_data_layer import api_call
from .fetchers_common import format_fetcher_error, get_endpoint_path, record_data_quality_issue

ET = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)






def fetch_signals(c: None) -> dict[str, Any]:
    """Fetch dashboard signals from API. Fail-fast: error only on failure."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("sig"))

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
        if n is None:
            if buy_sigs:
                n = len(buy_sigs)
                logger.info(f"Signal count derived from buy_sigs array length ({n}). API 'n' field was missing.")
            else:
                raise ValueError(
                    "CRITICAL: Signal response missing 'n' field and cannot derive from buy_sigs (empty or missing). "
                    "Signal count is required for panel display. Check API response schema and buy_sigs array."
                )

        total = result.get("total")
        if total is None:
            if n is not None:
                total = n
                logger.info(f"Total signal count derived from n ({total}). API 'total' field was missing.")
            elif buy_sigs:
                total = len(buy_sigs)
                logger.info(f"Total signal count derived from buy_sigs array ({total}). API 'total' and 'n' fields were missing.")
            else:
                raise ValueError(
                    "CRITICAL: Signal response missing 'total' field and cannot derive from n or buy_sigs. "
                    "Total signal count is required for panel display. Check API response schema."
                )

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
        error_msg = format_fetcher_error("sig", e)
        logger.error(error_msg)
        record_data_quality_issue("sig", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_signal_eval(c: None) -> dict[str, Any]:
    """Fetch signal evaluation stats from API."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("sig_eval"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("sig_eval", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        result = data
        return {
            "total": safe_int(result.get("total"), default=None),
            "t1": safe_int(result.get("t1"), default=None),
            "t2": safe_int(result.get("t2"), default=None),
            "t3": safe_int(result.get("t3"), default=None),
            "t4": safe_int(result.get("t4"), default=None),
            "t5": safe_int(result.get("t5"), default=None),
            "avg_score": safe_float(result.get("avg_score"), default=None),
            "date": result.get("signal_date"),
            "rejected": result.get("rejected"),
        }
    except Exception as e:
        error_msg = format_fetcher_error("sig_eval", e)
        logger.error(error_msg)
        record_data_quality_issue("sig_eval", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_scores(c: None) -> dict[str, Any]:
    """Fetch top stock scores from /api/scores. Used by signals panel for composite score display.

    On 503 transient errors, falls back to cached scores if available (optional data).
    """
    from dashboard.api_data_layer import get_cached_response
    from dashboard.fetcher_validator import FetcherValidator

    try:
        top_data = api_call("/api/scores", params={"limit": 50, "sortOrder": "desc", "offset": 0})

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(top_data)
        if is_error:
            # On 503 transient error, try cached scores (optional data can use stale cache)
            if top_data.get("_is_transient_503"):
                logger.warning("Scores API returned 503, attempting cache fallback")
                try:
                    cached = get_cached_response("/api/scores")
                    if cached and isinstance(cached, dict) and "items" in cached:
                        items = cached["items"]
                        if items:
                            logger.info("Scores: Using cached data due to API 503 (stale cache acceptable for optional data)")
                            return {"top": items, "_stale_cache": True}
                except RuntimeError as cache_err:
                    logger.warning(f"Scores cache fallback failed (stale cache): {cache_err}")
                    # Cache is too old or corrupted, continue to error response below

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

        return {"top": items}
    except Exception as e:
        error_msg = format_fetcher_error("scores", e)
        logger.error(error_msg)
        record_data_quality_issue("scores", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
