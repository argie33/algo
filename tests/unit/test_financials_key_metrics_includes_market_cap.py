"""Regression test: /api/financials/{symbol}/key-metrics must select vm.market_cap.

Live user report (2026-08-09): the Stock Detail page's hero "Market Cap" stat showed
"No data" even though value_metrics.market_cap is populated for 89.3% of the universe
(computed by load_value_quality_growth_metrics.py). Root cause: the frontend
(webapp/frontend/src/pages/StockDetail.jsx) reads km.market_cap from this endpoint's
response, but the endpoint's SELECT list never included vm.market_cap - a one-line
omission, not a data-loading gap. (Separately, /api/scores/stockscores already selected
vm.market_cap correctly, which is why the scores grid displayed it fine while the
individual stock detail page didn't.)
"""

import importlib
import inspect

financials = importlib.import_module("lambda.api.routes.financials")


def _key_metrics_sql_block() -> str:
    source = inspect.getsource(financials.handle)
    start = source.index('if endpoint == "key-metrics"')
    end = source.index('if endpoint ==', start + 1) if 'if endpoint ==' in source[start + 1 :] else len(source)
    return source[start:end]


def test_key_metrics_select_includes_market_cap():
    block = _key_metrics_sql_block()
    assert "vm.market_cap" in block, (
        "key-metrics SELECT must include vm.market_cap - the frontend reads km.market_cap "
        "from this endpoint's response and has no other source for it"
    )
