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


def _fake_db_context(delete_rowcount: int = 0):
    """A DatabaseContext("write") stand-in that records executed queries, no real DB."""
    cur = MagicMock()
    cur.rowcount = delete_rowcount
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
        ctx, cur = _fake_db_context(delete_rowcount=0)
        with (
            patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=None),
            patch.object(loader, "_has_prior_real_coverage", return_value=True),
            patch("loaders.load_analyst_upgrade_downgrade.DatabaseContext", return_value=ctx),
        ):
            result = loader.fetch_incremental("NVDA", since=date(2026, 8, 11))
        assert result == []
        cur.execute.assert_called_once()

    def test_empty_fetch_for_already_covered_symbol_retracts_pre_existing_marker(self):
        """BUG FOUND 2026-08-21 (follow-up to the 2026-08-18 fix above): "skip the marker
        write" is not enough on its own - it never retracts a marker already written BEFORE
        that fix landed (2026-08-10 through 2026-08-17, when markers were written
        unconditionally). Live-confirmed 15 symbols (AMAL among them: one real 2024-07-29
        action, then 6 straight days of markers before the fix stopped touching it) stuck
        showing that pre-fix marker as their permanent "latest row" forever, since this
        early-return path never retracted it and the yfinance window for these symbols may
        legitimately stay empty indefinitely. Any marker coexisting with confirmed real
        coverage is always wrong - retract it here too, not just on the "rows non-empty"
        path below."""
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        ctx, cur = _fake_db_context(delete_rowcount=1)
        with (
            patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=None),
            patch.object(loader, "_has_prior_real_coverage", return_value=True),
            patch("loaders.load_analyst_upgrade_downgrade.DatabaseContext", return_value=ctx),
        ):
            result = loader.fetch_incremental("AMAL", since=date(2026, 8, 17))
        assert result == []
        query, params = cur.execute.call_args[0]
        assert "DELETE FROM analyst_upgrade_downgrade" in query
        assert "data_unavailable = true" in query
        assert params == ("AMAL",)

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

    def test_since_filters_survive_when_no_marker_was_retracted(self):
        """A symbol with real, continuous coverage (no stale marker on record - the DELETE
        matches zero rows) and only old history / nothing new since the last watermark
        should still get [] - the watermark is trustworthy here, unlike the poisoned-
        watermark case below."""
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        rows = [_row(date(2026, 1, 1))]
        ctx, cur = _fake_db_context(delete_rowcount=0)
        with (
            patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=rows),
            patch("loaders.load_analyst_upgrade_downgrade.DatabaseContext", return_value=ctx),
        ):
            result = loader.fetch_incremental("NVDA", since=date(2026, 6, 1))

        assert result == []
        cur.execute.assert_called_once()

    def test_retracted_marker_poisoned_watermark_is_bypassed_and_reset(self):
        """FIX 2026-08-21 (goal session - BRK.B/dot-suffix ticker audit): live-confirmed
        BRK.A/BRK.B/BF.B/MOG.A all stuck at zero rows despite a real, current yfinance
        fetch succeeding, because a "no_analyst_coverage" marker written on 2026-08-19
        (action_date=today()-at-write-time, back when these dot-suffix symbols still hit
        the pre-fix yfinance dash-conversion bug) became this symbol's watermark. Every
        real historical action is necessarily older than that fabricated date, so the old
        behavior (previous test, now renamed/scoped to the non-poisoned case) silently
        discarded 100% of the real rows forever. When the marker DELETE actually matches a
        row (proof the watermark was never real progress), `since` must be ignored for
        this call AND the persisted watermark row deleted so future runs don't inherit the
        same poison."""
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        rows = [_row(date(2026, 1, 1)), _row(date(2026, 6, 1))]
        ctx, cur = _fake_db_context(delete_rowcount=1)
        with (
            patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=rows),
            patch("loaders.load_analyst_upgrade_downgrade.DatabaseContext", return_value=ctx),
        ):
            result = loader.fetch_incremental("BRK.B", since=date(2026, 8, 19))

        assert result == rows
        queries = [c.args[0] for c in cur.execute.call_args_list]
        assert any("DELETE FROM analyst_upgrade_downgrade" in q for q in queries)
        assert any("DELETE FROM loader_watermarks" in q for q in queries)
        watermark_delete = next(c for c in cur.execute.call_args_list if "loader_watermarks" in c.args[0])
        assert watermark_delete.args[1] == ("load_analyst_upgrade_downgrade", "BRK.B")

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
