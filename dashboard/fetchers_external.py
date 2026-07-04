"""Fetcher functions for external and enrichment data sources."""

import logging
from typing import Any, cast

from utils.validation.framework import safe_float

from .api_data_layer import api_call
from .fetchers_common import format_fetcher_error, get_endpoint_path, record_data_quality_issue
from .utilities import CY, G, R, Y

logger = logging.getLogger(__name__)


def fetch_economic_pulse(c: None) -> dict[str, Any]:  # noqa: C901
    """Fetch economic macro indicators. Fail-fast: error only on failure.

    Fetches from /api/economic/yield-curve-full and /api/economic/indicators.
    Both endpoints must succeed; partial data is not accepted (can't distinguish
    None from "API error" vs "field missing in successful response").
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        # Fetch yield curve (treasury yields + credit spreads + breakevens)
        yc_data = api_call("/api/economic/yield-curve-full")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(yc_data)
        if is_error:
            record_data_quality_issue("eco", "api_call", "yield_curve_error", cast(str, error_msg))
            return FetcherValidator.build_error_response(cast(str, error_msg))

        # Fetch macro indicators (CPI, unemployment, fed funds, oil, DXY, etc.)
        ind_data = api_call("/api/economic/indicators")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(ind_data)
        if is_error:
            record_data_quality_issue("eco", "api_call", "indicators_error", cast(str, error_msg))
            return FetcherValidator.build_error_response(cast(str, error_msg))

        # Extract yield curve data
        d = yc_data
        curve = None
        spreads = None
        credit = None
        credit_latest = None
        if isinstance(d, dict):
            curve = d.get("currentCurve")
            spreads = d.get("spreads")
            credit = d.get("credit")
        if isinstance(credit, dict):
            credit_latest = credit.get("currentSpreads")

        # Critical yield curve data: strict mode (risk calculations depend on accuracy)
        if not isinstance(curve, dict):
            raise ValueError("Yield curve data missing from API response")
        t10 = safe_float(curve.get("10Y"), strict=True, field_name="curve.10Y")
        t2 = safe_float(curve.get("2Y"), strict=True, field_name="curve.2Y")
        t3m = safe_float(curve.get("3M"), strict=True, field_name="curve.3M")
        t6m = safe_float(curve.get("6M"), strict=True, field_name="curve.6M")

        # Critical spreads: strict mode (signal generation depends on accuracy)
        if not isinstance(spreads, dict):
            raise ValueError("Spreads data missing from API response")
        yc_10_2 = safe_float(spreads.get("T10Y2Y"), strict=True, field_name="spreads.T10Y2Y")
        yc_10_3m = safe_float(spreads.get("T10Y3M"), strict=True, field_name="spreads.T10Y3M")

        # Credit spreads: strict mode (portfolio risk depends on accuracy)
        if not isinstance(credit_latest, dict):
            raise ValueError("Credit spread data missing from API response")
        hy = safe_float(
            credit_latest.get("BAMLH0A0HYM2"),
            strict=True,
            field_name="credit.BAMLH0A0HYM2",
        )
        ig_val = credit_latest.get("BAMLH0A0IG")
        if ig_val is None:
            # CRITICAL: Investment Grade spread is a key factor in 10-point exposure calculation.
            # Do not silently fallback to alternative series IDs; fail-fast so data issue is caught.
            logger.error(
                "CRITICAL: Investment Grade spread (BAMLH0A0IG) missing from credit spreads API. "
                "This is a required input for market exposure scoring (4 of 10 factors depend on credit spreads). "
                "Check: Fred API data availability, load_market_exposure_daily logs."
            )
            raise ValueError(
                "Investment Grade credit spread (BAMLH0A0IG) missing from API — "
                "cannot compute market risk tier without this factor. Exposure calculation incomplete."
            )
        ig = safe_float(
            ig_val,
            strict=True,
            field_name="credit.BAMLH0A0IG",
        )

        # Extract indicators data
        d2 = ind_data
        indicators = None
        if isinstance(d2, dict):
            indicators = d2.get("indicators")
            if not isinstance(indicators, list):
                indicators = None
        by_series: dict[str, float] = {}
        if indicators:
            for i in indicators:
                if isinstance(i, dict) and i.get("series_id"):
                    raw_val = i.get("rawValue")
                    if raw_val is None:
                        raise ValueError(f"Missing rawValue for indicator {i.get('series_id')}")
                    try:
                        val = safe_float(
                            raw_val,
                            strict=True,
                            field_name=f"indicator.{i.get('series_id')}.rawValue",
                        )
                        if val is not None and isinstance(val, float):
                            series_id = i.get("series_id")
                            by_series[series_id] = val
                    except Exception as e:
                        raise ValueError(f"Invalid indicator value for {i.get('series_id')}: {e}") from e

        # Critical indicators: fail fast if missing
        # FEDFUNDS: Current policy rate—required for all economic models
        fed_funds = by_series.get("FEDFUNDS")
        if fed_funds is None:
            raise ValueError("Federal Funds Rate (FEDFUNDS) missing from indicators")

        # Optional indicators (None if not published, but logged for monitoring)
        # These are used in economic stress scoring but have published gaps.
        # Callers must handle None explicitly.
        cpi_yoy = by_series.get("CPIAUCSL")  # CPI inflation (optional, publish lag)
        if cpi_yoy is None:
            logger.debug("[FETCH] CPIAUCSL (CPI YoY) missing from indicators—using None for eco scoring")

        unrate = by_series.get("UNRATE")  # Unemployment rate (optional, publish lag)
        if unrate is None:
            logger.debug("[FETCH] UNRATE (unemployment) missing from indicators—using None for eco scoring")

        be10 = by_series.get("T10YIE")  # 10-year breakeven inflation (optional)
        if be10 is None:
            logger.debug("[FETCH] T10YIE (10Y breakeven) missing from indicators—using None for eco scoring")

        be5 = by_series.get("T5YIE")  # 5-year breakeven inflation (optional)
        if be5 is None:
            logger.debug("[FETCH] T5YIE (5Y breakeven) missing from indicators—using None for eco scoring")

        # CRITICAL: Use ONLY DXY_ICE (actual ICE Dollar Index)
        # DTWEXBGS is a trade-weighted proxy—NOT the same index, must not silently swap
        dxy = by_series.get("DXY_ICE")
        if dxy is None:
            logger.error("[DXY] DXY_ICE missing from economic indicators")

        oil = by_series.get("DCOILWTICO")  # Oil price (optional)
        if oil is None:
            logger.debug("[FETCH] DCOILWTICO (oil) missing from indicators—using None for eco scoring")
        anfci = by_series.get("ANFCI")
        # CRITICAL: Advanced National Financial Conditions Index (ANFCI) is required for accurate
        # exposure tier calculation. It measures credit, funding, and asset price conditions.
        # STLFSI4 (St. Louis Financial Stress Index) measures different dimensions and is NOT
        # a valid substitute—must not silently fallback (would cause incorrect position sizing).
        if anfci is None:
            raise ValueError(
                "Advanced National Financial Conditions Index (ANFCI) missing from indicators. "
                "This is required for market exposure tier calculation (affects position sizing). "
                "Check: Fred API data availability, load_market_exposure_daily logs."
            )
        nfci = anfci
        nfci_source = "ANFCI"

        umcsent = by_series.get("UMCSENT")  # Consumer sentiment (optional)
        if umcsent is None:
            logger.debug("[FETCH] UMCSENT (consumer sentiment) missing from indicators—using None for eco scoring")

        mortgage = by_series.get("MORTGAGE30US")  # 30-year mortgage rate (optional)
        if mortgage is None:
            logger.debug("[FETCH] MORTGAGE30US (mortgage rate) missing from indicators—using None for eco scoring")

        return {
            "t10": t10,
            "t2": t2,
            "t3m": t3m,
            "t6m": t6m,
            "yc_10_2": yc_10_2,
            "yc_10_3m": yc_10_3m,
            "hy": hy,
            "ig": ig,
            "oil": oil,
            "nfci": nfci,
            "nfci_source": nfci_source,
            "fed_funds": fed_funds,
            "cpi_yoy": cpi_yoy,
            "unrate": unrate,
            "be10": be10,
            "be5": be5,
            "dxy": dxy,
            "mortgage": mortgage,
            "umcsent": umcsent,
        }
    except Exception as e:
        from dashboard.fetcher_validator import FetcherValidator

        error_msg = format_fetcher_error("eco", e)
        logger.error(error_msg)
        record_data_quality_issue("eco", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_economic_calendar(c: None) -> dict[str, Any]:
    """Fetch economic calendar events. API returns {items: [{event_date,
    event_name, country, importance, category, ...}], total: N}."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("econ_cal"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("econ_cal", "api_call", "api_error", cast(str, error_msg))
            return FetcherValidator.build_error_response(cast(str, error_msg))

        raw = data
        items = None
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Economic calendar API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("econ_cal", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(raw, list):
            items = raw
        else:
            error_msg = f"Economic calendar API response: expected dict or list, got {type(raw).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("econ_cal", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        return {"items": items}
    except Exception as e:
        error_msg = format_fetcher_error("econ_cal", e)
        logger.error(error_msg)
        record_data_quality_issue("econ_cal", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_exec_history(c: None) -> dict[str, Any] | list[Any]:
    """Fetch recent execution history. Panel expects a flat list (not wrapped
    in a dict) so it can do valid_hist[:7] directly."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(
            get_endpoint_path("exec_hist"),
            params={"days": 7, "limit": 10},
        )

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("exec_hist", "api_call", "api_error", cast(str, error_msg))
            return FetcherValidator.build_error_response(cast(str, error_msg))

        raw = data
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Execution history API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("exec_hist", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
            return items
        if isinstance(raw, list):
            return raw
        error_msg = f"Execution history API response unexpected type: expected list or dict, got {type(raw).__name__}"
        logger.error(error_msg)
        record_data_quality_issue("exec_hist", "validation", "invalid_response_type")
        return FetcherValidator.build_error_response(error_msg)
    except Exception as e:
        error_msg = format_fetcher_error("exec_hist", e)
        logger.error(error_msg)
        record_data_quality_issue("exec_hist", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_sentiment(c: None) -> dict[str, Any]:
    """API-only sentiment data. Fail-fast: error only on failure."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("sentiment"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("sentiment", "api_call", "api_error", cast(str, error_msg))
            return FetcherValidator.build_error_response(cast(str, error_msg))

        d = data
        # Validate required fields
        required = ["fear_greed_index", "label"]
        valid, error_msg = FetcherValidator.require_fields(d, required, "fetch_sentiment")
        if not valid:
            logger.error(error_msg)
            record_data_quality_issue("sentiment", "validation", "missing_fields")
            return FetcherValidator.build_error_response(error_msg)

        fg_raw = d.get("fear_greed_index")
        if fg_raw is None:
            raise ValueError("fear_greed_index cannot be None after validation")
        if not isinstance(fg_raw, (int, float, str)):
            raise ValueError(f"fear_greed_index must be numeric, got {type(fg_raw)}")
        fg = float(fg_raw)
        label = d.get("label")
        c_fg = R if fg <= 25 else (Y if fg <= 45 else (G if fg >= 75 else CY))
        return {
            "fg": round(fg, 1),
            "label": label,
            "date": d.get("date"),
            "color": c_fg,
        }
    except Exception as e:
        error_msg = format_fetcher_error("sentiment", e)
        logger.error(error_msg)
        record_data_quality_issue("sentiment", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_industry_ranking(c: None) -> dict[str, Any]:
    """Fetch industry rankings. API returns {items: [{industry, sector,
    current_rank, overall_rank, rank_1w_ago, rank_4w_ago}], total: N}."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("irank"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("irank", "api_call", "api_error", cast(str, error_msg))
            return FetcherValidator.build_error_response(cast(str, error_msg))

        raw = data
        items = None
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Industry ranking API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("irank", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(raw, list):
            items = raw
        else:
            error_msg = f"Industry ranking API response: expected dict or list, got {type(raw).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("irank", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        if not items:
            error_msg = "No industry ranking data available"
            logger.error(error_msg)
            record_data_quality_issue("irank", "validation", "no_items")
            return FetcherValidator.build_error_response(error_msg)

        return {"items": items}
    except Exception as e:
        error_msg = format_fetcher_error("irank", e)
        logger.error(error_msg)
        record_data_quality_issue("irank", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_activity(c: None) -> dict[str, Any]:
    """Fetch activity from audit log API (fail-fast: error if unavailable)."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("activity"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("activity", "api_call", "api_error", cast(str, error_msg))
            return FetcherValidator.build_error_response(cast(str, error_msg))

        raw = data
        items = None
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Activity API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("activity", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(raw, list):
            items = raw
        else:
            error_msg = f"Activity API response: expected dict or list, got {type(raw).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("activity", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        # Extract run timestamp and ID with explicit validation
        run_at = None
        if items and len(items) > 0:
            run_at = items[0].get("action_date")
            if run_at is None:
                logger.warning("[FETCH] Activity items present but first item missing 'action_date' field")
        else:
            logger.warning("[FETCH] No activity items available - run_at will be None")

        # Extract run_id with explicit search and logging
        run_id = None
        for i in items:
            details = i.get("details")
            if details is not None and isinstance(details, dict):
                candidate_run_id = details.get("run_id")
                if candidate_run_id is not None:
                    run_id = candidate_run_id
                    break
        if run_id is None:
            logger.debug("[FETCH] No run_id found in activity details - run_id will be None")

        # Extract phase events
        phases = []
        for item in items:
            action_type = item.get("action_type")
            if action_type is not None and isinstance(action_type, str) and action_type.startswith("phase_"):
                phases.append(item)
            elif action_type is not None and not isinstance(action_type, str):
                logger.warning(f"[ACTIVITY] Item has non-string action_type: {type(action_type).__name__}")

        return {
            "run_id": run_id,
            "run_at": run_at,
            "phases": phases,
            "recent_actions": items[:20],
        }
    except Exception as e:
        error_msg = format_fetcher_error("activity", e)
        logger.error(error_msg)
        record_data_quality_issue("activity", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_audit_log(c: None) -> dict[str, Any] | list[Any]:
    """Fetch audit log entries. Panel expects a flat list (not wrapped in a
    dict) for direct iteration. API returns {items: [...], total, limit, offset}."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("audit"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("audit", "api_call", "api_error", cast(str, error_msg))
            return FetcherValidator.build_error_response(cast(str, error_msg))

        raw = data
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Audit log API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("audit", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
            return items
        if isinstance(raw, list):
            return raw
        error_msg = f"Audit log API response unexpected type: expected list or dict, got {type(raw).__name__}"
        logger.error(error_msg)
        record_data_quality_issue("audit", "validation", "invalid_response_type")
        return FetcherValidator.build_error_response(error_msg)
    except Exception as e:
        error_msg = format_fetcher_error("audit", e)
        logger.error(error_msg)
        record_data_quality_issue("audit", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_notifications(c: None) -> dict[str, Any]:
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("notifs"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("notifs", "api_call", "api_error", cast(str, error_msg))
            return FetcherValidator.build_error_response(cast(str, error_msg))

        raw = data
        items = None
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Notifications API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("notifs", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(raw, list):
            items = raw
        else:
            error_msg = f"Notifications API response: expected dict or list, got {type(raw).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("notifs", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        return {"items": items}
    except Exception as e:
        error_msg = format_fetcher_error("notifs", e)
        logger.error(error_msg)
        record_data_quality_issue("notifs", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
