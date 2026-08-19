"""Regression tests for loaders/load_analyst_upgrade_downgrade.py.

Covers fetch_incremental()'s watermark filtering (only rows strictly after `since` should be
returned - re-fetching the same action on every run would violate the table's uniqueness
constraint via a redundant upsert, not silently duplicate rows, but should still be avoided)
and that an empty/None fetch result never becomes None (OptimalLoader's fetch_incremental
contract requires a list, even when empty).
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from loaders.load_analyst_upgrade_downgrade import AnalystUpgradeDowngradeLoader
from utils.infrastructure.timezone import EASTERN_TZ


def _row(action_date: date, firm: str = "Some Firm") -> dict:
    return {
        "symbol": "AAPL",
        "action_date": action_date,
        "firm": firm,
        "old_rating": "Hold",
        "new_rating": "Buy",
        "action": "up",
    }


def _fake_db_context():
    """A DatabaseContext("write") stand-in that records executed queries, no real DB."""
    cur = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=cur)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, cur


class TestFetchIncremental:
    def test_no_coverage_returns_data_unavailable_marker(self):
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        with (
            patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=None),
            patch.object(loader, "_has_prior_real_coverage", return_value=False),
        ):
            result = loader.fetch_incremental("ZZZZ", since=None)
        assert len(result) == 1
        assert result[0]["symbol"] == "ZZZZ"
        assert result[0]["data_unavailable"] is True
        assert result[0]["data_unavailable_reason"] == "no_analyst_coverage"

    def test_no_coverage_marker_sets_every_primary_key_field(self):
        """FIX 2026-08-10: primary_key = ("symbol", "action_date", "firm") but the marker
        used to only set "symbol", omitting both other PK fields entirely.
        OptimalLoader._validate_row() requires every declared primary_key field present and
        non-None (same bug class as migration 1168's dividend_data fix) - live-reproduced:
        every no-coverage symbol crashed with "Row missing required primary key field
        'action_date'" the moment migration 1201 stopped a separate missing-governance-
        column bug from masking it first."""
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        with (
            patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=None),
            patch.object(loader, "_has_prior_real_coverage", return_value=False),
        ):
            result = loader.fetch_incremental("ZZZZ", since=None)
        for key in AnalystUpgradeDowngradeLoader.primary_key:
            assert key in result[0], f"marker missing primary_key field '{key}'"
            assert result[0][key] is not None, f"marker has None for primary_key field '{key}'"

    def test_empty_fetch_for_already_covered_symbol_skips_the_marker(self):
        """FIX 2026-08-18 (goal session, "which factor inputs are missing the most" audit):
        a symbol with real historical rows already on record (e.g. NVDA, 308 real rows) got
        an empty fetch_analyst_actions() result on some run days - almost certainly transient
        yfinance flakiness, not a genuine loss of coverage. Writing a fresh
        "no_analyst_coverage" marker (action_date=today) in that case permanently wins any
        "latest row per symbol" read since it postdates every real historical action_date,
        wrongly making a fully-covered symbol look data-unavailable. Must return [] instead -
        leaving the real historical rows as the visible truth - not manufacture a marker."""
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        with (
            patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=None),
            patch.object(loader, "_has_prior_real_coverage", return_value=True),
        ):
            result = loader.fetch_incremental("NVDA", since=date(2026, 8, 11))
        assert result == []

    def test_since_none_returns_all_rows(self):
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        rows = [_row(date(2026, 1, 1)), _row(date(2026, 6, 1))]
        ctx, _cur = _fake_db_context()
        with (
            patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=rows),
            patch("loaders.load_analyst_upgrade_downgrade.DatabaseContext", return_value=ctx),
        ):
            result = loader.fetch_incremental("AAPL", since=None)
        assert result == rows

    def test_since_filters_out_rows_strictly_before_watermark(self):
        # Watermark filter is inclusive (>=), not exclusive: a different firm can issue a
        # same-day action after the watermark was already advanced to that date by an earlier
        # run, and the idempotent ON CONFLICT upsert makes re-fetching the watermark date safe -
        # same pattern as load_current_reports_8k.py.
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        rows = [_row(date(2026, 1, 1)), _row(date(2026, 6, 1)), _row(date(2026, 6, 2))]
        ctx, _cur = _fake_db_context()
        with (
            patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=rows),
            patch("loaders.load_analyst_upgrade_downgrade.DatabaseContext", return_value=ctx),
        ):
            result = loader.fetch_incremental("AAPL", since=date(2026, 6, 1))
        assert result == [_row(date(2026, 6, 1)), _row(date(2026, 6, 2))]

    def test_real_fetch_retracts_stale_marker_rows(self):
        """FIX 2026-08-19 (follow-up to the 2026-08-18 empty-fetch fix above): the earlier
        fix stops WRITING new markers once a symbol has real coverage, but never retracted
        markers already written before it landed. Live-confirmed NVDA/MSFT/TSM/GOOGL - mega-
        caps with hundreds of real rows on record - still carried an unretracted marker dated
        more recently than any real action (a marker's action_date is always today() at
        write time), permanently shadowing genuine coverage in any "latest row per symbol"
        read. A successful real fetch is the strongest possible evidence any existing marker
        for that symbol was wrong - it must be deleted."""
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        rows = [_row(date(2026, 8, 11))]
        ctx, cur = _fake_db_context()
        with (
            patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=rows),
            patch("loaders.load_analyst_upgrade_downgrade.DatabaseContext", return_value=ctx) as db_ctx,
        ):
            result = loader.fetch_incremental("NVDA", since=None)

        assert result == rows
        db_ctx.assert_called_once_with("write")
        cur.execute.assert_called_once()
        query, params = cur.execute.call_args[0]
        assert "DELETE FROM analyst_upgrade_downgrade" in query
        assert "data_unavailable = true" in query
        assert params == ("NVDA",)

    def test_real_fetch_retraction_runs_even_when_since_filters_out_every_row(self):
        """A symbol with only old real history and nothing new since the last watermark must
        still get its stale marker retracted - the raw fetch already proved coverage is
        real, even though every row happens to be filtered out of this run's return value."""
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        rows = [_row(date(2026, 1, 1))]
        ctx, cur = _fake_db_context()
        with (
            patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=rows),
            patch("loaders.load_analyst_upgrade_downgrade.DatabaseContext", return_value=ctx),
        ):
            result = loader.fetch_incremental("NVDA", since=date(2026, 6, 1))

        assert result == []
        cur.execute.assert_called_once()

    def test_no_coverage_marker_path_does_not_touch_the_db(self):
        # The retraction DELETE must only run on the real-fetch path - the no-coverage
        # marker path (empty fetch, never covered) has nothing to retract.
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        with (
            patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=None),
            patch.object(loader, "_has_prior_real_coverage", return_value=False),
            patch("loaders.load_analyst_upgrade_downgrade.DatabaseContext") as db_ctx,
        ):
            loader.fetch_incremental("ZZZZ", since=None)
        db_ctx.assert_not_called()

    def test_table_and_key_config_matches_live_schema(self):
        assert AnalystUpgradeDowngradeLoader.table_name == "analyst_upgrade_downgrade"
        assert AnalystUpgradeDowngradeLoader.primary_key == ("symbol", "action_date", "firm")
