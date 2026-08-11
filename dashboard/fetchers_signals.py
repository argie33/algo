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
    """Fetch dashboard signals from API. Fail-fast on any unavailability.

    CRITICAL: Signals are required for trading decisions. On ANY error (timeout, 503, 504, etc.),
    raise exception immediately instead of degrading. This ensures operators are alerted
    to data quality issues rather than silently proceeding with empty signals.

    Dashboard timeout: 5-second limit prevents hanging on slow API. If exceeded, fail-fast.
    """
    import threading

    from dashboard.fetcher_validator import FetcherValidator

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
            # Timeout - fail fast with explicit error
            logger.critical(
                "[SIGNALS_FETCHER] CRITICAL: API timeout (5s limit). "
                "Signals data required for trading decisions. Raising error instead of silently degrading."
            )
            record_data_quality_issue("sig", "timeout", "dashboard_timeout")
            raise RuntimeError(
                "[SIGNALS] API timeout after 5 seconds. Signals are critical for trading. "
                "If dashboard displays without signals, this is a data integrity issue that must be fixed. "
                "Check: (1) /api/algo/dashboard-signals endpoint health, (2) database performance, (3) network latency. "
                "Never silently degrade on missing critical trading data."
            )

        thread_error = error_container[0]
        if thread_error is not None:
            raise thread_error

        data = data_container[0]

        # Check for API error (fail-fast pattern: check error first)
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            # CRITICAL FIX: Signals are REQUIRED for trading decisions.
            # Even transient 503/504 errors must fail-fast, not degrade gracefully.
            # Silently returning empty signals with data_unavailable=True allows:
            # - Dashboard operators to miss data quality issues
            # - Trading system to proceed without critical signal data
            # - Silent data integrity violations
            #
            # TRADING RULE: If signals unavailable, halt - never continue with empty signals.
            is_transient_503 = data.get("_is_transient_503")
            is_transient_504 = data.get("_is_transient_504")
            is_transient = is_transient_503 or is_transient_504

            if is_transient:
                logger.critical(
                    f"[SIGNALS] CRITICAL FAILURE (transient): {error_msg}. "
                    f"Signals are required for trading. Failing fast instead of silently degrading. "
                    f"This prevents hidden data integrity issues where empty signals go unnoticed."
                )
                record_data_quality_issue("sig", "api_call", "api_unavailable_transient")
                raise RuntimeError(
                    f"[SIGNALS] API returned {503 if is_transient_503 else 504}: {error_msg}. "
                    f"Signals are critical for trading decisions. Cannot proceed with degraded mode. "
                    f"This error must be resolved before trading resumes. Check API health and database performance."
                )

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

    FAIL-FAST ON ANY UNAVAILABILITY: Scores are required for signal ranking and quality filtering.
    On any error (including transient 503/504), raise exception immediately instead of degrading.
    This ensures operators are alerted to data quality issues rather than silently proceeding.

    DASHBOARD TIMEOUT: Raise error after 8s to prevent hanging. The /api/algo/scores query
    (filter+limit before per-symbol LATERAL lookups) should return in <1s steady-state.
    8s timeout is for cold Lambda/RDS-Proxy connections. If exceeded, fail-fast.
    """
    import threading

    from dashboard.fetcher_validator import FetcherValidator

    try:
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
        thread.join(timeout=8)  # Wait max 8 seconds

        if thread.is_alive():
            # Timeout - fail fast. Never silently degrade even for "enrichment" data in finance apps.
            logger.critical(
                "[SCORES_FETCHER] CRITICAL: API timeout (8s limit). "
                "Scores are used for signal ranking and quality filtering. Failing fast instead of silently degrading."
            )
            record_data_quality_issue("scores", "timeout", "dashboard_timeout")
            raise RuntimeError(
                "[SCORES] API timeout after 8 seconds. Scores are required for signal ranking. "
                "Silently displaying without scores masks data quality issues. "
                "Check: (1) /api/algo/scores endpoint health, (2) RDS performance, (3) LATERAL join performance. "
                "Never degrade on missing data in finance apps."
            )

        thread_error = error[0]
        if thread_error is not None:
            raise thread_error

        top_data = top_data_container[0]
        if top_data is None:
            # No data returned from API - fail fast, this is a data integrity issue
            logger.critical(
                "[SCORES_FETCHER] CRITICAL: API returned no data. "
                "This indicates an infrastructure issue that must be investigated."
            )
            record_data_quality_issue("scores", "no_data", "no_response")
            raise RuntimeError(
                "[SCORES] API returned no data. Cannot proceed without response validation. "
                "This indicates a critical infrastructure or network issue. Check API logs and database connectivity."
            )

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(top_data)
        if is_error:
            # CRITICAL FIX: Even transient 503/504 errors must fail-fast, not degrade gracefully.
            # In finance apps, "temporarily unavailable" still means DATA IS MISSING.
            # Silently returning empty scores with data_unavailable=True allows:
            # - Dashboard operators to miss infrastructure issues
            # - Trading signals to be displayed without quality rankings
            # - Silent degradation that compounds data quality problems
            #
            # TRADING RULE: If data unavailable (even transiently), alert and halt - never continue degraded.
            is_transient_503 = top_data.get("_is_transient_503")
            is_transient_504 = top_data.get("_is_transient_504")
            is_transient = is_transient_503 or is_transient_504
            if is_transient:
                logger.critical(
                    f"[SCORES] CRITICAL FAILURE (transient): {error_msg}. "
                    f"Scores are required for signal ranking. Failing fast instead of silently degrading. "
                    f"This prevents hidden data integrity issues where missing scores go unnoticed."
                )
                record_data_quality_issue("scores", "api_call", "api_unavailable_transient")
                raise RuntimeError(
                    f"[SCORES] API returned {503 if is_transient_503 else 504}: {error_msg}. "
                    f"Scores are required for signal quality ranking. Cannot proceed without them. "
                    f"This error indicates a temporary infrastructure issue. Once resolved, restart the system."
                )

            # Other errors (database, validation, auth, etc): fail-fast
            logger.error(f"[SCORES] API error: {error_msg}. Check API and database connectivity.")
            record_data_quality_issue("scores", "api_call", "api_error", cast(str, error_msg))
            return FetcherValidator.build_error_response(cast(str, error_msg))

        # Validate response structure - fail-fast if missing top/items field
        if not isinstance(top_data, dict):
            error_msg = f"Scores API response: expected dict, got {type(top_data).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        # Handle multiple response formats: items (new), top (legacy), or wrapped data.top
        # The /api/scores endpoint returns {statusCode, items, pagination, data_freshness}
        # Adapt to dashboard's internal "top" format for consistency with other fetchers
        if "items" in top_data:
            # Current format: {statusCode, items, pagination, data_freshness}
            top = top_data["items"]
        elif "data" in top_data and isinstance(top_data["data"], dict):
            # Wrapped response format: {statusCode, data: {top, universe_total, ...}}
            response_data = top_data["data"]
            if "top" not in response_data:
                error_msg = "Scores API response: wrapped format missing required 'top' field in data wrapper"
                logger.error(error_msg)
                record_data_quality_issue("scores", "validation", "missing_top_field_wrapped")
                return FetcherValidator.build_error_response(error_msg)
            top = response_data["top"]
        elif "top" in top_data:
            # Legacy direct format (for backward compatibility with mocked responses)
            top = top_data["top"]
        else:
            error_msg = "Scores API response: missing required 'items' or 'top' field"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "missing_items_or_top_field")
            return FetcherValidator.build_error_response(error_msg)
        if not isinstance(top, list):
            error_msg = "Scores API response: 'top' field is not a list"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "top_not_list")
            return FetcherValidator.build_error_response(error_msg)

        # Summary metrics over the full filtered universe (not just this page) - optional,
        # since older API versions/mocks won't have them; the panel falls back to len(top).
        # Extract from the current response format ({statusCode, items, pagination, ...})
        # or from wrapped response_data if it's a legacy/wrapped format
        if "pagination" in top_data and isinstance(top_data["pagination"], dict):
            # Current format has pagination.total for the full universe count
            response_data_dict = top_data
            universe_total = top_data["pagination"].get("total") if "total" in top_data["pagination"] else None
        elif "data" in top_data and isinstance(top_data["data"], dict):
            response_data_dict = top_data["data"]
            universe_total = (
                response_data_dict.get("universe_total") if "universe_total" in response_data_dict else None
            )
        else:
            response_data_dict = top_data
            universe_total = (
                response_data_dict.get("universe_total") if "universe_total" in response_data_dict else None
            )
        if universe_total is not None and not isinstance(universe_total, int):
            error_msg = f"Scores response 'universe_total' must be int, got {type(universe_total).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "universe_total_invalid_type")
            return FetcherValidator.build_error_response(error_msg)

        avg_composite = response_data_dict.get("avg_composite")
        if avg_composite is not None and not isinstance(avg_composite, (int, float)):
            error_msg = f"Scores response 'avg_composite' must be numeric, got {type(avg_composite).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "avg_composite_invalid_type")
            return FetcherValidator.build_error_response(error_msg)

        grades = response_data_dict.get("grades")
        if grades is not None and not isinstance(grades, dict):
            error_msg = f"Scores response 'grades' must be dict, got {type(grades).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("scores", "validation", "grades_invalid_type")
            return FetcherValidator.build_error_response(error_msg)

        # BUG FOUND 2026-08-10: this "timestamp" was always datetime.now(ET) (client fetch
        # time), which can never detect genuinely stale underlying score data - the same class
        # already fixed for positions/portfolio (see dashboard/panels/positions.py's comment).
        # The API's real server-computed data_freshness (from stock_scores.updated_at, see
        # _get_dashboard_scores in lambda/api/routes/algo_handlers/dashboard.py) was available
        # in the response the whole time but never read here.
        return {
            "top": top,
            "universe_total": universe_total,
            "avg_composite": avg_composite,
            "grades": grades,
            "timestamp": datetime.now(ET),
            "data_freshness": top_data.get("data_freshness"),
        }
    except Exception as e:
        error_msg = format_fetcher_error("scores", e)
        logger.error(error_msg)
        record_data_quality_issue("scores", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
