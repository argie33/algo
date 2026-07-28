"""Regression test for utils/external/yfinance_analyst_ratings.py's same-day dedup logic.

Found live 2026-07-27 while building load_analyst_upgrade_downgrade.py (restoring
analyst_upgrade_downgrade, which had no writer since Session 275): a single firm can
issue more than one action for the same symbol on the same calendar date (yfinance's
GradeDate carries a real timestamp, but analyst_upgrade_downgrade only stores a DATE).
Two rows that collapse onto the same (symbol, action_date, firm) key crash the whole
INSERT batch with psycopg2.errors.CardinalityViolation ("ON CONFLICT DO UPDATE command
cannot affect row a second time") - confirmed live against AAPL's real data before the
fix. fetch_analyst_actions() must dedupe to one row per (action_date, firm), keeping the
latest real timestamp.
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd

from utils.external.yfinance_analyst_ratings import fetch_analyst_actions


def _mock_ticker_with(df: pd.DataFrame) -> MagicMock:
    ticker = MagicMock()
    ticker.upgrades_downgrades = df
    return ticker


class TestSameDaySameFirmDedup:
    def test_two_actions_same_symbol_date_firm_collapse_to_one_row(self):
        index = pd.to_datetime(
            [
                datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc),
                datetime(2026, 7, 20, 15, 30, tzinfo=timezone.utc),  # later same-day update
            ]
        )
        df = pd.DataFrame(
            {
                "Firm": ["Morgan Stanley", "Morgan Stanley"],
                "FromGrade": ["Overweight", "Overweight"],
                "ToGrade": ["Overweight", "Overweight"],
                "Action": ["main", "main"],
            },
            index=index,
        )
        df.index.name = "GradeDate"

        with patch("yfinance.Ticker", return_value=_mock_ticker_with(df)):
            rows = fetch_analyst_actions("AAPL")

        assert rows is not None
        assert len(rows) == 1
        assert rows[0]["action_date"] == date(2026, 7, 20)
        assert rows[0]["firm"] == "Morgan Stanley"

    def test_keeps_the_later_timestamp_when_ratings_disagree(self):
        index = pd.to_datetime(
            [
                datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc),
                datetime(2026, 7, 20, 15, 30, tzinfo=timezone.utc),
            ]
        )
        df = pd.DataFrame(
            {
                "Firm": ["Morgan Stanley", "Morgan Stanley"],
                "FromGrade": ["Hold", "Overweight"],
                "ToGrade": ["Overweight", "Overweight"],
                "Action": ["up", "main"],
            },
            index=index,
        )
        df.index.name = "GradeDate"

        with patch("yfinance.Ticker", return_value=_mock_ticker_with(df)):
            rows = fetch_analyst_actions("AAPL")

        assert len(rows) == 1
        # The later (15:30) row wins, not the earlier "up" action
        assert rows[0]["action"] == "main"
        assert rows[0]["old_rating"] == "Overweight"

    def test_different_firms_same_date_both_kept(self):
        index = pd.to_datetime(
            [
                datetime(2026, 7, 20, 9, 0, tzinfo=timezone.utc),
                datetime(2026, 7, 20, 15, 30, tzinfo=timezone.utc),
            ]
        )
        df = pd.DataFrame(
            {
                "Firm": ["Morgan Stanley", "HSBC"],
                "FromGrade": ["Overweight", "Hold"],
                "ToGrade": ["Overweight", "Buy"],
                "Action": ["main", "up"],
            },
            index=index,
        )
        df.index.name = "GradeDate"

        with patch("yfinance.Ticker", return_value=_mock_ticker_with(df)):
            rows = fetch_analyst_actions("AAPL")

        assert len(rows) == 2
        firms = {r["firm"] for r in rows}
        assert firms == {"Morgan Stanley", "HSBC"}

    def test_no_coverage_returns_none(self):
        with patch("yfinance.Ticker", return_value=_mock_ticker_with(pd.DataFrame())):
            rows = fetch_analyst_actions("XYZQ")

        assert rows is None
