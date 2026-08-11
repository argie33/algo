"""Regression test for the 2026-08-11 fix: lambda/api/routes/market.py's
_get_cap_distribution() joined against `key_metrics` for market_cap - but key_metrics has had
no active writer since 2026-05-21 (not in loaders/loader_registry.py, not scheduled anywhere).
The endpoint never errored (the frozen table still had rows), so it silently served ~3-month-
stale market cap categorization the whole time. sec_valuations (written daily by the actively-
scheduled load_sec_valuations.py) has the same symbol/market_cap shape and is the real,
current source - migrated the query to it.
"""

import importlib
import inspect

market = importlib.import_module("lambda.api.routes.market")


def _cap_distribution_source() -> str:
    """Return the function body only, skipping the leading explanatory comment block
    that (correctly) mentions key_metrics by name when describing the bug that was fixed."""
    source = inspect.getsource(market._get_cap_distribution)
    body_start = source.index("cur.execute(")
    return source[body_start:]


def test_cap_distribution_does_not_query_stale_key_metrics_table():
    source = _cap_distribution_source()
    assert "key_metrics" not in source, (
        "key_metrics has had no active writer since 2026-05-21 - querying it silently serves "
        "stale market cap data with no error"
    )


def test_cap_distribution_uses_actively_written_sec_valuations():
    source = _cap_distribution_source()
    assert "sec_valuations" in source, (
        "must join against sec_valuations (written daily by the scheduled "
        "load_sec_valuations.py loader), the real live source for market_cap"
    )
