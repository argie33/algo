"""Regression test for lambda/api/routes/market.py::_handle_technicals's A/D line query.

_ad_line() (algo/market_exposure factor calculator, part of the 12-factor exposure
redesign) stores its 20-day net advance/decline change under the "ad_change_20d" key
of market_exposure_daily.factors->'ad_line'. But _handle_technicals's A/D line history
query (feeds the /api/market/technicals "mcclellan_oscillator" chart) still read the
old pre-redesign "value" key, which no longer exists in that JSON blob - so the WHERE
clause's `(factors->'ad_line'->>'value') IS NOT NULL` filtered out every single row and
the chart silently rendered with zero data points, indefinitely. Fixed 2026-08-21 by
reading "ad_change_20d" instead. This test locks in that the executed SQL references
the real key and that a row with only "ad_change_20d" populated (no "value" key) is
returned, not filtered out.

'lambda' is a Python keyword, so the module under test is loaded via importlib.

NOTE (2026-09-05): _handle_technicals moved from the flat lambda/api/routes/market.py into
lambda/api/routes/market/technicals.py (file-size-ratchet package split - see
lambda/api/routes/market/__init__.py for the full rationale). execute_with_timeout and
check_data_freshness are patched on that submodule (not the market package's __init__.py)
because patch.object() resolves attributes on the literal module object named, and
technicals.py has its own top-level import of both names from routes.utils.
"""

import importlib
from unittest.mock import MagicMock, patch

market_module = importlib.import_module("lambda.api.routes.market.technicals")


def test_ad_line_query_reads_ad_change_20d_not_stale_value_key():
    cur = MagicMock()
    # _handle_technicals's raw cur.fetchall() is only used for the A/D line query -
    # simulate a real row keyed by ad_change_20d (the current factor calculator output),
    # not "value" (the removed pre-redesign key).
    cur.fetchall.return_value = [{"date": "2026-08-20", "advance_decline_line": 42.5}]

    technicals_row = {
        "date": "2026-08-20",
        "advance_decline_ratio": 1.2,
        "new_highs_count": 10,
        "new_lows_count": 5,
        "up_volume_percent": 55.0,
        "breadth_momentum_10d": 1.0,
        "vix_level": 15.0,
        "put_call_ratio": 0.9,
        "market_trend": "up",
        "market_stage": "confirmed_uptrend",
    }
    breadth_row = {"advancing": 100, "declining": 50, "unchanged": 5, "total_stocks": 155}

    with (
        patch.object(market_module, "execute_with_timeout", side_effect=[[technicals_row], [breadth_row]]),
        patch.object(market_module, "check_data_freshness", return_value={"status": "fresh"}),
    ):
        response = market_module._handle_technicals(cur)

    executed_sql = [call.args[0] for call in cur.execute.call_args_list if "ad_line" in call.args[0]]
    assert executed_sql, "expected a query referencing factors->'ad_line'"
    ad_line_sql = executed_sql[0]
    assert "ad_change_20d" in ad_line_sql, "query must read the real 'ad_change_20d' key"
    assert "->>'value'" not in ad_line_sql, "query must not read the removed pre-redesign 'value' key"

    data = response["data"] if isinstance(response, dict) and "data" in response else response
    assert data["mcclellan_oscillator"] == [{"date": "2026-08-20", "advance_decline_line": 42.5}]
