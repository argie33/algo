"""Regression test: /api/market/trends must exist and map trend_direction correctly.

BUG FOUND 2026-08-10 (frontend/dashboard audit pass): MarketsHealth.jsx's TrendHealthCard
has polled `/api/market/trends` every 5 minutes since it was written, but no handler for
this path existed in lambda/api/routes/market.py - every load showed "Trend data
unavailable". Separately, trend_template_data.trend_direction stores "up"/"down"/"sideways",
not the "uptrend"/"downtrend"/"consolidation" strings the frontend filters on - a bare
passthrough would still have shown 0% for every category even with a handler present.
"""

import importlib

market = importlib.import_module("lambda.api.routes.market")


def test_trends_registered_in_handler_registry():
    registry = market._MarketHandlerRegistry()
    handler = registry.get_handler("/api/market/trends")
    assert handler is market._get_trend_health


def test_trend_direction_mapping_matches_frontend_expected_values():
    # MarketsHealth.jsx's TrendHealthCard filters on exactly these 3 strings.
    assert market._TREND_DIRECTION_TO_TYPE == {
        "up": "uptrend",
        "down": "downtrend",
        "sideways": "consolidation",
    }
