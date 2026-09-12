"""Fetcher for the options CSP/covered-call candidate screener (goal session 2026-09-12 POC).

New module rather than adding to fetchers_config.py (already 1000+ lines) - same modular
split fetchers.py's own docstring describes (fetchers_market.py, fetchers_signals.py, etc.).
"""

import logging
import os
from typing import Any

from .api_data_layer import api_call
from .fetchers_common import format_fetcher_error, record_data_quality_issue

logger = logging.getLogger(__name__)

_DISABLED_MESSAGE = "Options screener disabled (set OPTIONS_SLEEVE_ENABLED=true to enable)"

_REQUIRED_ITEM_FIELDS = (
    "symbol",
    "option_type",
    "strike_price",
    "delta",
    "bid",
    "ask",
    "expiration_date",
    "quote_date",
)


def fetch_options(c: None) -> dict[str, Any]:
    """Fetch options CSP/covered-call candidates from the API.

    Splits results by option_type into csp_candidates (puts) and covered_call_candidates
    (calls) - both already restricted server-side to the 0.15-0.30 |delta| screening zone
    (see lambda/api/routes/options.py). Same strict-validation posture as fetch_circuit:
    missing/malformed fields fail loudly rather than silently defaulting, consistent with
    this dashboard's no-silent-fallback convention for finance data.
    """
    from dashboard.fetcher_validator import FetcherValidator

    if os.environ.get("OPTIONS_SLEEVE_ENABLED", "false").lower() != "true":
        # Deliberately off (default) - not a data-quality issue, so no
        # record_data_quality_issue call here, unlike a real fetch failure below.
        return FetcherValidator.build_error_response(_DISABLED_MESSAGE)

    try:
        data = api_call("/api/options/candidates")

        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("options", "api_call", "api_error", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        items = data.get("items")
        if items is None:
            error_msg = "Options API response missing required 'items' field"
            logger.error(error_msg)
            record_data_quality_issue("options", "validation", "missing_items_field")
            return FetcherValidator.build_error_response(error_msg)

        if not isinstance(items, list):
            error_msg = f"Options 'items' field must be list, got {type(items).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("options", "validation", "items_not_list")
            return FetcherValidator.build_error_response(error_msg)

        csp_candidates: list[dict[str, Any]] = []
        cc_candidates: list[dict[str, Any]] = []
        for item in items:
            missing = [f for f in _REQUIRED_ITEM_FIELDS if f not in item]
            if missing:
                error_msg = f"Options candidate missing required field(s) {missing}. Available: {list(item.keys())}"
                logger.error(error_msg)
                record_data_quality_issue("options", "validation", "missing_field", str(missing))
                return FetcherValidator.build_error_response(error_msg)

            option_type = item["option_type"]
            if option_type == "put":
                csp_candidates.append(item)
            elif option_type == "call":
                cc_candidates.append(item)
            else:
                error_msg = f"Options candidate has unexpected option_type: {option_type!r}"
                logger.error(error_msg)
                record_data_quality_issue("options", "validation", "unexpected_option_type", str(option_type))
                return FetcherValidator.build_error_response(error_msg)

        return {
            "csp_candidates": csp_candidates,
            "covered_call_candidates": cc_candidates,
            "data_freshness": data.get("data_freshness"),
        }
    except Exception as e:
        error_msg = format_fetcher_error("options", e)
        logger.error(error_msg)
        record_data_quality_issue("options", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
