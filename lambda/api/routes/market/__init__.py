"""Route: market

Split 2026-09-05 (file-size-ratchet compliance split of the original 1768-line flat
lambda/api/routes/market.py - see loaders/stock_scores/, lambda/api/routes/scores_handlers/
and lambda/api/routes/algo_handlers/dashboard/ for the established precedent this follows).
Each of the module's handler functions now lives in its own sibling module (market_status.py,
breadth.py, technicals.py, top_movers.py, distribution_days.py, seasonality.py, sentiment.py,
naaim.py, fear_greed.py, market_latest.py, correlation.py, cap_distribution.py, markets.py,
sector_overview.py, trend_health.py); helpers shared across more than one handler
(_rollback_savepoint, _parse_range_param) live in _shared.py. This file re-exports every name
so existing callers - notably `routes/__init__.py`'s `from . import market as market` and
api_router.py's `__import__("routes.market", ...)`, both of which only ever call
`module.handle(...)` - and the handful of tests that reach into `routes.market.<name>`
directly (test_market_cap_distribution_uses_live_source.py,
test_market_trends_endpoint_exists.py) require zero changes. The `_MarketHandlerRegistry`
class and `handle()` dispatcher stay here since this is the package's public entry point.

Pure move, no logic changed anywhere; each function's body is byte-for-byte identical to the
pre-split version (only the import header at the top of each new module differs, trimmed to
that function's actual dependencies).
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import raise_api_error, raise_db_error

from ._shared import _parse_range_param
from .breadth import _handle_breadth
from .cap_distribution import _get_cap_distribution
from .correlation import _get_correlation_matrix
from .distribution_days import _handle_distribution_days
from .fear_greed import _get_fear_greed_history
from .market_latest import _get_market_latest
from .market_status import _handle_market_status
from .markets import _get_index_names, _get_index_symbols, _get_markets
from .naaim import _handle_naaim
from .seasonality import _handle_seasonality
from .sector_overview import _get_sector_overview
from .sentiment import _handle_sentiment
from .technicals import _handle_technicals
from .top_movers import _handle_top_movers
from .trend_health import _TREND_DIRECTION_TO_TYPE, _get_trend_health

__all__ = [
    "_TREND_DIRECTION_TO_TYPE",
    "_get_cap_distribution",
    "_get_correlation_matrix",
    "_get_fear_greed_history",
    "_get_index_names",
    "_get_index_symbols",
    "_get_market_latest",
    "_get_markets",
    "_get_sector_overview",
    "_get_trend_health",
    "_handle_breadth",
    "_handle_distribution_days",
    "_handle_market_status",
    "_handle_naaim",
    "_handle_seasonality",
    "_handle_sentiment",
    "_handle_technicals",
    "_handle_top_movers",
    "_parse_range_param",
    "handle",
]

logger = logging.getLogger(__name__)


class _MarketHandlerRegistry:
    """Registry mapping market endpoint paths to handler functions."""

    def __init__(self) -> None:
        self._handlers = {
            "/api/market/status": _handle_market_status,
            "/api/market/indices": _get_markets,
            "/api/market/breadth": _handle_breadth,
            "/api/market/technicals": _handle_technicals,
            "/api/market/top-movers": _handle_top_movers,
            "/api/market/distribution-days": _handle_distribution_days,
            "/api/market/seasonality": _handle_seasonality,
            "/api/market/sentiment": self._wrap_sentiment,
            "/api/market/fear-greed": self._wrap_fear_greed,
            "/api/market/naaim": _handle_naaim,
            "/api/market/latest": _get_market_latest,
            "/api/market/cap-distribution": _get_cap_distribution,
            "/api/market/correlation": _get_correlation_matrix,
            "/api/market/sectors": _get_sector_overview,
            "/api/market/trends": _get_trend_health,
        }

    def _wrap_sentiment(self, cur: cursor, params: dict[str, Any] | None = None) -> Any:
        return _handle_sentiment(cur, params)

    def _wrap_fear_greed(self, cur: cursor, params: dict[str, Any] | None = None) -> Any:
        range_days = _parse_range_param(params) if params else 30
        return _get_fear_greed_history(cur, range_days)

    def get_handler(self, path: str) -> Any:
        if path in ["/api/market", "/api/market/status"] or path.startswith("/api/market?"):
            return self._handlers["/api/market/status"]
        return self._handlers.get(path)


_MARKET_REGISTRY = _MarketHandlerRegistry()


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/market/* endpoints."""
    try:
        handler = _MARKET_REGISTRY.get_handler(path)
        if handler is None:
            raise_api_error(404, "not_found", f"No market handler for {path}")

        if path == "/api/market/sentiment":
            return handler(cur, params)
        elif path == "/api/market/fear-greed":
            return handler(cur, params)
        else:
            return handler(cur)
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"[MARKET] Unhandled error: {type(e).__name__}: {e}")
        raise_db_error(e, "handle market")
