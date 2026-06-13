"""API-based data layer for dashboard (Issue 3 FIX: Dual data architecture consolidation).

This module consolidates all dashboard data fetching through a single API layer
instead of dual DB/API sources. It eliminates field name mismatches and ensures
consistent data freshness.

ISSUE 1.1 FIX: Consistent API Response Handling
================================================
All API responses follow a standardized format from the backend via _wrap_response():
- Format: {statusCode: 200, data: {...payload...}, ...metadata}
- Error format: {statusCode: 4xx, errorType: "...", message: "...", _error: "..."}

FIX IMPLEMENTATION:
1. api_call() invokes _unwrap_api_response() to extract just the payload
2. _unwrap_api_response() returns response["data"] directly
3. All data fetchers work with unwrapped payloads (no more nested data fields)

Result: Consistent response handling — all methods access fields at the same nesting level.

Migration status:
- Positions, Trades, Performance, Signals: ✅ API-only + standardized
- Portfolio Status: ✅ API-only (via /api/algo/status)
- Health/Data Status: ✅ API-only (via /api/algo/data-status)
- Config: ✅ API-only (via /api/algo/config)
- Economic/Market data: Still DB-based (no dedicated API endpoints yet)
"""

import logging
import requests
import os
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

API_BASE_URL = os.environ.get("DASHBOARD_API_URL", "http://localhost:3001")
API_TIMEOUT = 10
API_MAX_RETRIES = 3


def api_call(endpoint: str, params: Optional[Dict] = None, method: str = "GET") -> Dict:
    """Call API endpoint with retry logic and standardized response unwrapping.

    Standardizes API responses into a consistent format regardless of the endpoint's
    internal response wrapper (statusCode, data, items, etc). This fixes Issue 1.1
    by ensuring all endpoints are parsed the same way.

    Args:
        endpoint: API endpoint path (e.g., "/api/algo/positions")
        params: Query parameters dict
        method: HTTP method (GET or POST)

    Returns:
        Unwrapped response dict containing actual data fields (no statusCode wrapper),
        or {"_error": message} on failure
    """
    url = f"{API_BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}

    for attempt in range(API_MAX_RETRIES):
        try:
            if method == "GET":
                resp = requests.get(url, params=params, headers=headers, timeout=API_TIMEOUT)
            else:
                resp = requests.post(url, json=params, headers=headers, timeout=API_TIMEOUT)

            if resp.status_code >= 400:
                logger.warning(f"API {endpoint}: {resp.status_code}")
                if attempt < API_MAX_RETRIES - 1:
                    continue
                return {"_error": f"API error {resp.status_code}"}

            data = resp.json()
            if isinstance(data, dict) and data.get("statusCode", 200) >= 400:
                logger.warning(f"API {endpoint}: error in response")
                if attempt < API_MAX_RETRIES - 1:
                    continue
                return {"_error": data.get("message", "Unknown error")}

            # Standardize response: unwrap statusCode wrapper and return clean payload
            # API responses always include statusCode, but consumers should work with
            # the actual data (items, data field, or direct fields like n, total, etc)
            return _unwrap_api_response(data)
        except requests.exceptions.Timeout:
            if attempt < API_MAX_RETRIES - 1:
                logger.warning(f"API {endpoint} timeout, retry...")
                continue
            return {"_error": "API timeout"}
        except Exception as e:
            if attempt < API_MAX_RETRIES - 1:
                logger.warning(f"API {endpoint} error: {e}, retry...")
                continue
            return {"_error": str(e)}

    return {"_error": "API max retries exceeded"}


def _unwrap_api_response(response: Dict) -> Dict:
    """Unwrap standardized API response wrapper.

    All API responses follow the format: {statusCode: 200, data: {...}, ...metadata}
    This function extracts and returns ONLY the payload, removing all metadata.

    Args:
        response: Full API response dict with format {statusCode: X, data: {...}, ...}

    Returns:
        Unwrapped payload (contents of the 'data' field) ready for use by callers
    """
    if not isinstance(response, dict):
        return response

    # Extract the data field (all endpoints wrap payloads in 'data' via _wrap_response in api_router)
    # This is the only field that contains actual application data; everything else is metadata
    if "data" in response:
        return response["data"]

    # Fallback for error responses that have no 'data' field
    # Remove only metadata markers (statusCode, headers) and return rest
    unwrapped = {k: v for k, v in response.items() if k not in ("statusCode", "headers")}
    return unwrapped if unwrapped else {}


class DashboardDataAPI:
    """Consolidated API data layer for all dashboard fetchers."""

    @staticmethod
    def get_portfolio() -> Dict[str, Any]:
        """Get portfolio snapshot via /api/algo/status."""
        resp = api_call("/api/algo/status")
        if "_error" in resp:
            return {"_error": resp["_error"]}

        # Response is already unwrapped (data field extracted), use directly
        portfolio = resp.get("portfolio", {})
        return {
            "total_portfolio_value": portfolio.get("total_value"),
            "total_cash": portfolio.get("total_cash"),
            "open_positions": portfolio.get("open_positions"),
            "daily_return_pct": portfolio.get("daily_return_pct"),
            "unrealized_pnl_pct": portfolio.get("unrealized_pnl_pct"),
            "last_run": resp.get("last_run"),
        }

    @staticmethod
    def get_positions() -> List[Dict]:
        """Get open positions via /api/algo/positions."""
        resp = api_call("/api/algo/positions")
        if "_error" in resp:
            logger.error(f"get_positions failed: {resp['_error']}")
            return []
        items = resp.get("items", [])
        if not isinstance(items, list):
            logger.error(f"get_positions: expected list, got {type(items).__name__}")
            return []
        valid_items = [item for item in items if isinstance(item, dict)]
        if len(valid_items) < len(items):
            logger.warning(f"get_positions: filtered {len(items) - len(valid_items)} non-dict items")
        return valid_items

    @staticmethod
    def get_performance() -> Dict[str, Any]:
        """Get performance metrics via /api/algo/performance."""
        resp = api_call("/api/algo/performance")
        if "_error" in resp:
            logger.error(f"get_performance failed: {resp['_error']}")
            return {}
        return resp

    @staticmethod
    def get_trades(limit: int = 100) -> List[Dict]:
        """Get recent trades via /api/algo/trades."""
        resp = api_call("/api/algo/trades", params={"limit": limit})
        if "_error" in resp:
            logger.error(f"get_trades failed: {resp['_error']}")
            return []
        return resp.get("items", [])

    @staticmethod
    def get_signals() -> Dict[str, Any]:
        """Get dashboard signals via /api/algo/dashboard-signals."""
        resp = api_call("/api/algo/dashboard-signals")
        if "_error" in resp:
            logger.error(f"get_signals failed: {resp['_error']}")
            return {"n": 0, "total": 0, "buy_sigs": [], "grades": {}, "near": [], "top_a": [], "trend": []}
        return resp

    @staticmethod
    def get_health() -> Dict[str, Any]:
        """Get data health status via /api/algo/data-status."""
        resp = api_call("/api/algo/data-status")
        if "_error" in resp:
            logger.error(f"get_health failed: {resp['_error']}")
            return {"ready_to_trade": False, "summary": {}, "sources": []}
        return resp

    @staticmethod
    def get_config() -> Dict[str, Any]:
        """Get algo configuration via /api/algo/config."""
        resp = api_call("/api/algo/config")
        if "_error" in resp:
            logger.error(f"get_config failed: {resp['_error']}")
            return {}
        return resp

    @staticmethod
    def get_notifications(limit: int = 10) -> List[Dict]:
        """Get recent notifications via /api/algo/notifications."""
        resp = api_call("/api/algo/notifications", params={"limit": limit})
        if "_error" in resp:
            logger.error(f"get_notifications failed: {resp['_error']}")
            return []
        return resp.get("items", []) if isinstance(resp, dict) else []

    @staticmethod
    def get_last_run() -> Dict[str, Any]:
        """Get last orchestrator run info via /api/algo/last-run."""
        resp = api_call("/api/algo/last-run")
        if "_error" in resp:
            logger.error(f"get_last_run failed: {resp['_error']}")
            return {}
        return resp

    @staticmethod
    def get_audit_log(limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """Get audit log via /api/algo/audit-log."""
        resp = api_call("/api/algo/audit-log", params={"limit": limit, "offset": offset})
        if "_error" in resp:
            logger.error(f"get_audit_log failed: {resp['_error']}")
            return {"items": [], "pagination": {}}
        return resp

    @staticmethod
    def get_circuit_breakers() -> Dict[str, Any]:
        """Get circuit breaker status via /api/algo/circuit-breakers."""
        resp = api_call("/api/algo/circuit-breakers")
        if "_error" in resp:
            logger.error(f"get_circuit_breakers failed: {resp['_error']}")
            return {"breakers": [], "any_triggered": False}
        return resp

    @staticmethod
    def get_sector_breadth() -> Dict[str, Any]:
        """Get sector breadth via /api/algo/sector-breadth."""
        resp = api_call("/api/algo/sector-breadth")
        if "_error" in resp:
            logger.error(f"get_sector_breadth failed: {resp['_error']}")
            return {}
        return resp
