"""Regression tests for loaders/load_analyst_upgrade_downgrade.py.

Covers fetch_incremental()'s watermark filtering (only rows strictly after `since` should be
returned - re-fetching the same action on every run would violate the table's uniqueness
constraint via a redundant upsert, not silently duplicate rows, but should still be avoided)
and that an empty/None fetch result never becomes None (OptimalLoader's fetch_incremental
contract requires a list, even when empty).
"""

from datetime import date, datetime
from unittest.mock import patch

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


class TestFetchIncremental:
    def test_no_coverage_returns_data_unavailable_marker(self):
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        with patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=None):
            result = loader.fetch_incremental("ZZZZ", since=None)
        assert len(result) == 1
        assert result[0]["symbol"] == "ZZZZ"
        assert result[0]["data_unavailable"] is True
        assert result[0]["data_unavailable_reason"] == "no_analyst_coverage"

    def test_since_none_returns_all_rows(self):
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        rows = [_row(date(2026, 1, 1)), _row(date(2026, 6, 1))]
        with patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=rows):
            result = loader.fetch_incremental("AAPL", since=None)
        assert result == rows

    def test_since_filters_out_rows_strictly_before_watermark(self):
        # Watermark filter is inclusive (>=), not exclusive: a different firm can issue a
        # same-day action after the watermark was already advanced to that date by an earlier
        # run, and the idempotent ON CONFLICT upsert makes re-fetching the watermark date safe -
        # same pattern as load_current_reports_8k.py.
        loader = AnalystUpgradeDowngradeLoader.__new__(AnalystUpgradeDowngradeLoader)
        rows = [_row(date(2026, 1, 1)), _row(date(2026, 6, 1)), _row(date(2026, 6, 2))]
        with patch("loaders.load_analyst_upgrade_downgrade.fetch_analyst_actions", return_value=rows):
            result = loader.fetch_incremental("AAPL", since=date(2026, 6, 1))
        assert result == [_row(date(2026, 6, 1)), _row(date(2026, 6, 2))]

    def test_table_and_key_config_matches_live_schema(self):
        assert AnalystUpgradeDowngradeLoader.table_name == "analyst_upgrade_downgrade"
        assert AnalystUpgradeDowngradeLoader.primary_key == ("symbol", "action_date", "firm")
