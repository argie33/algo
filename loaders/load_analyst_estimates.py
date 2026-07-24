"""Load analyst estimates (forward P/E, earnings estimates) from Polygon.io API."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "").strip()
POLYGON_BASE_URL = "https://api.polygon.io/v1"


def fetch_forward_pe_estimates(symbol: str) -> dict[str, Any]:
    """Fetch forward earnings estimates from Polygon.io.

    Returns dict with:
    - forward_pe: forward P/E ratio (current_price / estimated_forward_eps)
    - forward_eps: estimated earnings per share
    - forward_pe_unavailable_reason: reason if fetch failed
    """
    if not POLYGON_API_KEY:
        return {
            "forward_pe": None,
            "forward_eps": None,
            "forward_pe_unavailable_reason": "polygon_api_key_not_configured",
        }

    try:
        # Use Polygon reference API for ticker details (includes analyst estimates if available)
        url = f"{POLYGON_BASE_URL}/reference/tickers/{symbol}"
        response = requests.get(
            url,
            params={"apiKey": POLYGON_API_KEY},
            timeout=5,
        )

        if response.status_code == 401:
            logger.warning(f"[POLYGON] Invalid API key - check POLYGON_API_KEY environment variable")
            return {
                "forward_pe": None,
                "forward_eps": None,
                "forward_pe_unavailable_reason": "invalid_polygon_api_key",
            }

        if response.status_code == 404:
            logger.debug(f"[POLYGON] {symbol} not found in Polygon database")
            return {
                "forward_pe": None,
                "forward_eps": None,
                "forward_pe_unavailable_reason": "symbol_not_found",
            }

        if response.status_code != 200:
            logger.debug(f"[POLYGON] {symbol} API error: {response.status_code}")
            return {
                "forward_pe": None,
                "forward_eps": None,
                "forward_pe_unavailable_reason": "api_error",
            }

        data = response.json()
        if "results" not in data or not data["results"]:
            logger.debug(f"[POLYGON] {symbol} no estimate data available")
            return {
                "forward_pe": None,
                "forward_eps": None,
                "forward_pe_unavailable_reason": "no_estimate_data",
            }

        result = data["results"][0]

        # Try to get forward EPS from various possible fields
        # Polygon's schema varies, so check multiple locations
        forward_eps = None
        if "forward_eps" in result and result["forward_eps"] is not None:
            forward_eps = result["forward_eps"]
        elif "last_quote" in result and "forward_eps" in result["last_quote"]:
            forward_eps = result["last_quote"]["forward_eps"]

        if forward_eps is None or forward_eps <= 0:
            logger.debug(f"[POLYGON] {symbol} no forward EPS estimate")
            return {
                "forward_pe": None,
                "forward_eps": None,
                "forward_pe_unavailable_reason": "no_analyst_estimates",
            }

        # Forward P/E will be calculated in the metrics loader using current price
        # Return the forward_eps estimate here
        return {
            "forward_pe": None,  # Will be calculated as current_price / forward_eps
            "forward_eps": float(forward_eps),
            "forward_pe_unavailable_reason": None,
        }

    except requests.Timeout:
        logger.debug(f"[POLYGON] {symbol} API timeout")
        return {
            "forward_pe": None,
            "forward_eps": None,
            "forward_pe_unavailable_reason": "api_timeout",
        }
    except requests.RequestException as e:
        logger.debug(f"[POLYGON] {symbol} request error: {e}")
        return {
            "forward_pe": None,
            "forward_eps": None,
            "forward_pe_unavailable_reason": "network_error",
        }
    except (KeyError, TypeError, ValueError) as e:
        logger.debug(f"[POLYGON] {symbol} parse error: {e}")
        return {
            "forward_pe": None,
            "forward_eps": None,
            "forward_pe_unavailable_reason": "parse_error",
        }
