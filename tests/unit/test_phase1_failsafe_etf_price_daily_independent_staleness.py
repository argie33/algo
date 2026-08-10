"""Regression test for the 2026-08-10 fix: _check_and_refresh_local()'s
`loaders_to_refresh` dict (algo/orchestrator/phase1_failsafe_retry.py) was entirely
missing `etf_price_daily`, despite it being PHASE_1_CRITICAL in
utils/loader_priority.py ("Must complete before Phase 1").

Live-confirmed: `etf_price_daily` sat 5 calendar days stale (MAX(date)=2026-08-05 vs
today=2026-08-10) while `price_daily` - the only table actually checked for this
"prices" loader_key - stayed fresh the whole time, because both tables are separate
output tables of the same load_prices.py run (one PriceLoader instance per asset_class
x interval combo), and a "prices" refresh here was only ever triggered by price_daily's
OWN staleness. etf_price_daily going stale independently (its own sub-run hanging/
crashing while price_daily's sub-run already succeeded) had no detection path at all -
nothing would ever notice or attempt to recover it.

Fixed by adding "etf_price_daily": "prices" to loaders_to_refresh (reusing the existing
"prices" loader_key, which already refreshes all of load_prices.py's output tables) and
a completeness-check branch reusing price_daily's `close`-column check (same schema).
"""

import datetime

from algo.orchestrator.phase1_failsafe_retry import _check_and_refresh_local


class _PerTableCursor:
    """MAX(date) returns `fresh` for price_daily, `stale` for etf_price_daily - the exact
    scenario found live: one output table of load_prices.py fresh, the sibling stale,
    with no shared trigger connecting the two."""

    def __init__(self, fresh: datetime.date, stale: datetime.date):
        self._fresh = fresh
        self._stale = stale
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query
        self._last_params = params or ()

    def fetchone(self):
        # Completeness-check COUNT(*) queries only run for tables the MAX(date) check
        # already decided are fresh (not stale) - technical_data_daily's own query shape
        # needs 5 columns (total + 4 indicator counts), every other table needs 2
        # (total, non_null).
        if "COUNT(*)" in self._last_query:
            if "FROM technical_data_daily" in self._last_query:
                return (100, 100, 100, 100, 100)
            return (100, 100)  # fully populated - every non-stale table passes cleanly
        if "FROM etf_price_daily" in self._last_query:
            return (self._stale,)
        # Every other configured table (including price_daily) - report fresh so only
        # etf_price_daily's independent staleness is exercised.
        return (self._fresh,)


class _PerTableDatabaseContext:
    def __init__(self, cursor):
        self._cur = cursor

    def __enter__(self):
        return self._cur

    def __exit__(self, *exc):
        return False


class TestEtfPriceDailyIndependentStaleness:
    def test_etf_price_daily_flagged_stale_independent_of_price_daily(self, monkeypatch):
        from algo.orchestrator import phase1_failsafe_retry as mod

        fresh = datetime.date(2026, 8, 10)
        stale = datetime.date(2026, 8, 5)
        cursor = _PerTableCursor(fresh, stale)
        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _PerTableDatabaseContext(cursor))
        monkeypatch.setattr(
            mod, "_get_expected_data_date", lambda **kwargs: (fresh, "EOD - test")
        )

        result = _check_and_refresh_local(run_date=fresh, pipeline_context="EOD", dry_run=True)

        assert "etf_price_daily" in result["incomplete_loaders"], (
            "etf_price_daily (5 days stale) must be independently detected as incomplete "
            "even though price_daily - the only table this used to check - is fresh"
        )
        assert "price_daily" not in result["incomplete_loaders"]

    def test_etf_price_daily_is_the_only_incomplete_loader_when_only_it_is_stale(self, monkeypatch):
        """Every other configured table reports fresh - etf_price_daily must be the sole
        entry, not swept in alongside unrelated tables or silently dropped."""
        from algo.orchestrator import phase1_failsafe_retry as mod

        fresh = datetime.date(2026, 8, 10)
        stale = datetime.date(2026, 8, 5)
        cursor = _PerTableCursor(fresh, stale)
        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _PerTableDatabaseContext(cursor))
        monkeypatch.setattr(mod, "_get_expected_data_date", lambda **kwargs: (fresh, "EOD - test"))

        result = _check_and_refresh_local(run_date=fresh, pipeline_context="EOD", dry_run=True)

        assert result["incomplete_loaders"] == ["etf_price_daily"]
