"""Fetcher functions for external and enrichment data sources."""

import logging

from utils.safe_data_conversion import safe_float

from .api_data_layer import api_call
from .utilities import CY, G, R, Y

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


def fetch_economic_pulse(c):
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
            record_data_quality_issue("eco", "api_call", "yield_curve_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        # Fetch macro indicators (CPI, unemployment, fed funds, oil, DXY, etc.)
        ind_data = api_call("/api/economic/indicators")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(ind_data)
        if is_error:
            record_data_quality_issue("eco", "api_call", "indicators_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

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

        t10 = safe_float(curve.get("10Y"), default=None, field_name="curve.10Y") if isinstance(curve, dict) else None
        t2 = safe_float(curve.get("2Y"), default=None, field_name="curve.2Y") if isinstance(curve, dict) else None
        t3m = safe_float(curve.get("3M"), default=None, field_name="curve.3M") if isinstance(curve, dict) else None
        t6m = safe_float(curve.get("6M"), default=None, field_name="curve.6M") if isinstance(curve, dict) else None
        yc_10_2 = (
            safe_float(spreads.get("T10Y2Y"), default=None, field_name="spreads.T10Y2Y")
            if isinstance(spreads, dict)
            else None
        )
        yc_10_3m = (
            safe_float(spreads.get("T10Y3M"), default=None, field_name="spreads.T10Y3M")
            if isinstance(spreads, dict)
            else None
        )
        hy = (
            safe_float(
                credit_latest.get("BAMLH0A0HYM2"),
                default=None,
                field_name="credit.BAMLH0A0HYM2",
            )
            if isinstance(credit_latest, dict)
            else None
        )
        ig = None
        if isinstance(credit_latest, dict):
            ig = safe_float(
                credit_latest.get("BAMLH0A0IG") or credit_latest.get("BAMLC0A0CM"),
                default=None,
                field_name="credit.BAMLH0A0IG",
            )

        # Extract indicators data
        d2 = ind_data
        indicators = None
        if isinstance(d2, dict):
            indicators = d2.get("indicators")
            if not isinstance(indicators, list):
                indicators = None
        by_series = {}
        if indicators:
            by_series = {
                i["series_id"]: safe_float(
                    i.get("rawValue"),
                    default=None,
                    field_name=f"indicator.{i.get('series_id')}.rawValue",
                )
                for i in indicators
                if isinstance(i, dict) and i.get("series_id")
            }
        fed_funds = by_series.get("FEDFUNDS")
        cpi_yoy = by_series.get("CPIAUCSL")
        unrate = by_series.get("UNRATE")
        be10 = by_series.get("T10YIE")
        be5 = by_series.get("T5YIE")
        dxy = by_series.get("DTWEXBGS")
        oil = by_series.get("DCOILWTICO")
        nfci = by_series.get("ANFCI") if by_series.get("ANFCI") is not None else by_series.get("STLFSI4")
        umcsent = by_series.get("UMCSENT")
        mortgage = by_series.get("MORTGAGE30US")

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

        error_msg = _format_fetcher_error("eco", e)
        logger.error(error_msg)
        record_data_quality_issue("eco", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_economic_calendar(c):
    """Fetch economic calendar events. API returns {items: [{event_date,
    event_name, country, importance, category, ...}], total: N}."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("econ_cal"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("econ_cal", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

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
        error_msg = _format_fetcher_error("econ_cal", e)
        logger.error(error_msg)
        record_data_quality_issue("econ_cal", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_exec_history(c):
    """Fetch recent execution history. Panel expects a flat list (not wrapped
    in a dict) so it can do valid_hist[:7] directly."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(
            _get_endpoint_path("exec_hist"),
            params={"days": 7, "limit": 10},
        )

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("exec_hist", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

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
        error_msg = _format_fetcher_error("exec_hist", e)
        logger.error(error_msg)
        record_data_quality_issue("exec_hist", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_sentiment(c):
    """API-only sentiment data. Fail-fast: error only on failure."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("sentiment"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("sentiment", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        d = data
        # Validate required fields
        required = ["fear_greed_index", "label"]
        valid, error_msg = FetcherValidator.require_fields(d, required, "fetch_sentiment")
        if not valid:
            logger.error(error_msg)
            record_data_quality_issue("sentiment", "validation", "missing_fields")
            return FetcherValidator.build_error_response(error_msg)

        fg = float(d.get("fear_greed_index"))  # type: ignore[arg-type]
        label = d.get("label")
        c_fg = R if fg <= 25 else (Y if fg <= 45 else (G if fg >= 75 else CY))
        return {
            "fg": round(fg, 1),
            "label": label,
            "date": d.get("date"),
            "color": c_fg,
        }
    except Exception as e:
        error_msg = _format_fetcher_error("sentiment", e)
        logger.error(error_msg)
        record_data_quality_issue("sentiment", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_industry_ranking(c):
    """Fetch industry rankings. API returns {items: [{industry, sector,
    current_rank, overall_rank, rank_1w_ago, rank_4w_ago}], total: N}."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("irank"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("irank", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

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
        error_msg = _format_fetcher_error("irank", e)
        logger.error(error_msg)
        record_data_quality_issue("irank", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_activity(c):
    """Fetch activity from audit log API (fail-fast: error if unavailable)."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("activity"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("activity", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

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

        run_at = items[0].get("action_date") if items else None
        phases = [i for i in items if (i.get("action_type") or "").startswith("phase_")]
        return {
            "run_id": None,
            "run_at": run_at,
            "phases": phases,
            "recent_actions": items[:20],
        }
    except Exception as e:
        error_msg = _format_fetcher_error("activity", e)
        logger.error(error_msg)
        record_data_quality_issue("activity", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_audit_log(c):
    """Fetch audit log entries. Panel expects a flat list (not wrapped in a
    dict) for direct iteration. API returns {items: [...], total, limit, offset}."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("audit"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("audit", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

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
        error_msg = _format_fetcher_error("audit", e)
        logger.error(error_msg)
        record_data_quality_issue("audit", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_notifications(c):
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("notifs"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("notifs", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

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
        error_msg = _format_fetcher_error("notifs", e)
        logger.error(error_msg)
        record_data_quality_issue("notifs", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
