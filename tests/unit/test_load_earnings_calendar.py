"""Regression tests for loaders/load_earnings_calendar.py.

Covers fetch_incremental()'s deliberate `since`-ignoring behavior (unlike most event-log
loaders, earnings_calendar must always re-send its whole yfinance window so estimate-only
rows get their actual_eps/surprise_pct filled in once the earnings date passes - a
since-based skip would freeze those rows at their pre-earnings estimate forever) and that
a no-coverage/fetch-error result never becomes None (OptimalLoader's fetch_incremental
contract requires a list, even when empty).
"""

from datetime import date
from unittest.mock import patch

from loaders.load_earnings_calendar import EarningsCalendarLoader


def _row(earnings_date: date, actual_eps: float | None = None) -> dict:
    return {
        "symbol": "AAPL",
        "earnings_date": earnings_date,
        "eps_estimate": 1.5,
        "actual_eps": actual_eps,
        "surprise_pct": None,
    }


class TestFetchIncremental:
    def test_no_coverage_returns_data_unavailable_marker(self):
        loader = EarningsCalendarLoader.__new__(EarningsCalendarLoader)
        with patch("loaders.load_earnings_calendar.fetch_earnings_calendar", return_value=None):
            result = loader.fetch_incremental("ZZZZ", since=None)
        assert len(result) == 1
        assert result[0]["symbol"] == "ZZZZ"
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "no_earnings_coverage"

    def test_fetch_error_returns_data_unavailable_marker_not_raise(self):
        loader = EarningsCalendarLoader.__new__(EarningsCalendarLoader)
        with patch(
            "loaders.load_earnings_calendar.fetch_earnings_calendar",
            side_effect=RuntimeError("yfinance rate limited"),
        ):
            result = loader.fetch_incremental("AAPL", since=None)
        assert len(result) == 1
        assert result[0]["data_unavailable"] is True
        assert result[0]["reason"] == "fetch_error:RuntimeError"

    def test_since_is_ignored_full_window_always_returned(self):
        # Deliberately not filtered by `since` - see module docstring. A row that was
        # estimate-only before earnings needs to be re-sent after the date passes so its
        # real actual_eps/surprise_pct can be picked up via the ON CONFLICT upsert.
        loader = EarningsCalendarLoader.__new__(EarningsCalendarLoader)
        rows = [_row(date(2026, 1, 1), actual_eps=1.6), _row(date(2026, 10, 29))]
        with patch("loaders.load_earnings_calendar.fetch_earnings_calendar", return_value=rows):
            result = loader.fetch_incremental("AAPL", since=date(2026, 6, 1))
        assert len(result) == 2
        assert result[0]["earnings_date"] == date(2026, 1, 1)
        assert result[0]["actual_eps"] == 1.6
        assert result[1]["earnings_date"] == date(2026, 10, 29)
        assert all(r["data_unavailable"] is False for r in result)

    def test_table_and_key_config_matches_live_schema(self):
        assert EarningsCalendarLoader.table_name == "earnings_calendar"
        assert EarningsCalendarLoader.primary_key == ("symbol", "earnings_date")
        assert EarningsCalendarLoader.watermark_field == "earnings_date"
