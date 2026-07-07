"""Fetcher functions for signal data and evaluation metrics."""

import logging
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from utils.validation.framework import safe_float, safe_int

from .api_data_layer import api_call
from .fetchers_common import format_fetcher_error, get_endpoint_path, record_data_quality_issue

ET = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)


def fetch_signals(c: None) -> dict[str, Any]:
    """Fetch dashboard signals from API. Gracefully degrade on transient 503 errors.

    Dashboard optimization: Signals API can be slow (10+ seconds). Use 5-second timeout
    so dashboard doesn't hang on loading screen. Signals are non-critical enrichment.
    """
    from dashboard.fetcher_validator import FetcherValidator
    import threading

    try:
        # Fetch signals with 5-second timeout using thread (cross-platform compatible)
        data_container: list[Any] = [None]
        error_container: list[Exception | None] = [None]

        def fetch_with_timeout() -> None:
            try:
                data_container[0] = api_call(get_endpoint_path("sig"))
            except Exception as e:
                error_container[0] = e

        thread = threading.Thread(target=fetch_with_timeout, daemon=True)
        thread.start()
        thread.join(timeout=5)

        if thread.is_alive():
            # Timeout - return empty signals
            logger.warning("Signals API timeout (5s limit) - returning empty signals")
            record_data_quality_issue("sig", "timeout", "dashboard_timeout")
            return {
                "n": 0,
                "total": 0,
                "buy_sigs": [],
                "near": [],
                "top_a": [],
                "trend": [],
                "grades": {},
                "data_unavailable": True,
                "reason": "Signals service slow - dashboard will render without signals",
                "unavailability_type": "dashboard_timeout",
            }

        thread_error = error_container[0]
        if thread_error is not None:
            raise thread_error

        data = data_container[0]

        # Check for API error (fail-fast pattern: check error first)
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            # IMPORTANT: Distinguish between temporary service issues and real errors
            # Signals are critical but should degrade gracefully on transient 503/504
            # This allows dashboard to render without signals during brief API issues
            is_transient_503 = data.get("_is_transient_503") is True
            is_transient_504 = data.get("_is_transient_504") is True
            is_transient = is_transient_503 or is_transient_504
            if is_transient:
                logger.warning(
                    f"Signals API temporarily unavailable: {error_msg} - "
                    f"Dashboard will render without signals. Service will recover."
                )
                record_data_quality_issue("sig", "api_call", "api_unavailable_transient")
                return {
                    "n": 0,
                    "total": 0,
                    "buy_sigs": [],
                    "near": [],
                    "top_a": [],
                    "trend": [],
                    "grades": {},
                    "data_unavailable": True,
                    "reason": "Signals service temporarily unavailable - dashboard will render without signals",
                    "unavailability_type": "transient_service_error",
                }

            # Other errors (database, validation, auth, etc): fail-fast
            record_data_quality_issue("sig", "api_call", "api_error", cast(str, error_msg))
            return FetcherValidator.build_error_response(cast(str, error_msg))

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

        # CRITICAL: Track which data source was used for n and total (transparency for data quality)
        n = result.get("n")
        n_source = "api" if n is not None else None
        if n is None:
            if buy_sigs:
                n = len(buy_sigs)
                n_source = "buy_sigs_derived"
                logger.info(f"Signal count 'n' derived from buy_sigs array length ({n}). API 'n' field was missing.")
            else:
                raise ValueError(
                    "CRITICAL: Signal response missing 'n' field and cannot derive from buy_sigs (empty or missing). "
                    "Signal count is required for panel display. Check API response schema and buy_sigs array."
                )

        total = result.get("total")
        total_source = "api" if total is not None else None
        if total is None:
            if n is not None:
                total = n
                total_source = "n_derived"
                logger.info(f"Total signal count 'total' derived from n ({total}). API 'total' field was missing.")
            elif buy_sigs:
                total = len(buy_sigs)
                total_source = "buy_sigs_derived"
                logger.info(
                    f"Total signal count 'total' derived from buy_sigs array ({total}). "
                    f"API 'total' and 'n' fields were missing."
                )
            else:
                raise ValueError(
                    "CRITICAL: Signal response missing 'total' field and cannot derive from n or buy_sigs. "
                    "Total signal count is required for panel display. Check API response schema."
                )

        return {
            "n": n,
            "n_source": n_source,
            "total": total,
            "total_source": total_source,
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
    """Fetch signal evaluation stats from API.

    CRITICAL: Use strict mode for all numeric conversions. Parse errors must raise,
    never silently default to None which could hide data corruption.
    """
    from dashboard.data_validation import StrictValidationError
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("sig_eval"))

        # Check for API error (fail-fast pattern: check error first)
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("sig_eval", "api_call", "api_error", cast(str, error_msg))
            return FetcherValidator.build_error_response(cast(str, error_msg))

        result = data

        # CRITICAL: Use strict=True for all finance data conversions.
        # Parse errors must raise exceptions, never silently default to None.
        try:
            total_val = result.get("total")
            t1_val = result.get("t1")
            t2_val = result.get("t2")
            t3_val = result.get("t3")
            t4_val = result.get("t4")
            t5_val = result.get("t5")
            avg_score_val = result.get("avg_score")

            def _safe_int(v: Any) -> int | None:
                return safe_int(v, default=None, strict=True) if v is not None else None

            def _safe_float(v: Any) -> float | None:
                return safe_float(v, default=None, strict=True) if v is not None else None

            return {
                "total": _safe_int(total_val),
                "t1": _safe_int(t1_val),
                "t2": _safe_int(t2_val),
                "t3": _safe_int(t3_val),
                "t4": _safe_int(t4_val),
                "t5": _safe_int(t5_val),
                "avg_score": _safe_float(avg_score_val),
                "date": result.get("signal_date"),
                "rejected": result.get("rejected"),
            }
        except (StrictValidationError, ValueError, TypeError) as e:
            error_msg = f"Signal evaluation data contains invalid numeric values: {e}"
            logger.error(error_msg)
            record_data_quality_issue("sig_eval", "validation", "numeric_parse_error", str(e))
            return FetcherValidator.build_error_response(error_msg)
    except Exception as e:
        error_msg = format_fetcher_error("sig_eval", e)
        logger.error(error_msg)
        record_data_quality_issue("sig_eval", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_scores(c: None) -> dict[str, Any]:
    """Fetch top stock scores from /api/algo/scores. Used by signals panel for composite score display.

    HANDLES 503 GRACEFULLY: Scores enhance signal quality ranking but are not critical for trading.
    On 503 errors (service unavailable), return empty scores list with explicit marker instead of
    failing the entire dashboard. This allows trading to continue with signals, just without score rankings.

    DASHBOARD OPTIMIZATION: Scores API can be slow (7+ seconds). Return empty with marker after 3s
    so dashboard doesn't hang on loading screen. Scores are non-critical enrichment.
    """
    from dashboard.fetcher_validator import FetcherValidator
    import threading

    try:
        # Fetch scores with 3-second timeout (non-critical for dashboard responsiveness)
        # Uses thread-based timeout for cross-platform compatibility
        top_data_container: list[dict[str, Any] | None] = [None]  # Mutable container to store result from thread
        error: list[Exception | None] = [None]

        def fetch_with_timeout() -> None:
            try:
                top_data_container[0] = api_call(
                    "/api/algo/scores", params={"limit": 50, "sortOrder": "desc", "offset": 0}
                )
            except Exception as e:
                error[0] = e

        thread = threading.Thread(target=fetch_with_timeout, daemon=True)
        thread.start()
        thread.join(timeout=3)  # Wait max 3 seconds

        if thread.is_alive():
            # Timeout occurred - scores took too long
            logger.warning("Scores API timeout (3s dashboard limit) - displaying without scores")
            record_data_quality_issue("scores", "timeout", "dashboard_timeout")
            return {
                "top": [],
                "data_unavailable": True,
                "reason": "Scores service slow - dashboard will display without score rankings",
                "unavailability_type": "dashboard_timeout_for_responsiveness",
            }

        thread_error = error[0]
        if thread_error is not None:
            raise thread_error

        top_data = top_data_container[0]
        if top_data is None:
            # No data returned from API (shouldn't happen after thread completed successfully)
            return {
                "top": [],
                "data_unavailable": True,
                "reason": "Scores API returned no data",
                "unavailability_type": "no_data_response",
            }

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(top_data)
        if is_error:
            # IMPORTANT: Distinguish between temporary service issues and real errors
            # Scores are non-critical enrichment — 503 (unavailable) and 504 (query timeout)
            # are both transient; allow signals to display without score rankings
            # CRITICAL FIX: Check each flag explicitly (not with OR) to distinguish error types
            is_transient_503 = top_data.get("_is_transient_503") is True
            is_transient_504 = top_data.get("_is_transient_504") is True
            is_transient = is_transient_503 or is_transient_504
            if is_transient:
                logger.warning(
                    f"Scores API temporarily unavailable: {error_msg} - "
                    f"Signals will display without composite score rankings. Service will recover."
                )
                record_data_quality_issue("scores", "api_call", "api_unavailable_transient")
                return {
                    "top": [],
                    "data_unavailable": True,
                    "reason": "Scores service temporarily unavailable - signals display without score rankings",
                    "unavailability_type": "transient_service_error",
                }

            # Other errors (database, validation, auth, etc): fail-fast
            # These indicate infrastructure problems that must be surfaced
            logger.error(
                f"Scores API error (fail-fast): {error_msg} - "
                f"Signal quality ranking unavailable. Check API and database."
            )
            record_data_quality_issue("scores", "api_call", "api_error", cast(str, error_msg))
            return FetcherValidator.build_error_response(cast(str, error_msg))

        # Validate response structure - fail-fast if missing top field
        if not isinstance(top_data, dict):
            error_msg = f"Scores API response: expected dict, got {type(top_data).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        if "top" not in top_data:
            error_msg = "Scores API response: missing required 'top' field"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "missing_top_field")
            return FetcherValidator.build_error_response(error_msg)

        top = top_data["top"]
        if not isinstance(top, list):
            error_msg = "Scores API response: 'top' field is not a list"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "top_not_list")
            return FetcherValidator.build_error_response(error_msg)

        return {"top": top}
    except Exception as e:
        error_msg = format_fetcher_error("scores", e)
        logger.error(error_msg)
        record_data_quality_issue("scores", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
