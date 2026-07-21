#!/usr/bin/env python3
"""Regression test for the 2026-07-21 pretrade_checks.py eval_date timezone fix.

run_all() defaulted eval_date via date.today() (system-local calendar date) when the
caller didn't pass one explicitly, then fed it straight into EarningsBlackout.run() - a
documented hard gate that does exact trading-day arithmetic against the earnings date. A
server not running in America/New_York (e.g. UTC in AWS) could evaluate the blackout
window against the wrong calendar day near midnight. Fixed to match the same pattern
already established elsewhere in this codebase (algo/trading/tca.py's record_fill()).
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from algo.trading.pretrade_checks import PreTradeChecks
from utils.infrastructure.timezone import EASTERN_TZ


def _config():
    return {
        "max_position_size_pct": 10,
        "min_order_size_dollars": 100,
        "max_positions_per_sector": 5,
        "max_positions_per_industry": 3,
    }


class TestRunAllUsesEasternDateByDefault:
    def test_eval_date_defaults_to_eastern_time_not_system_local(self):
        checks = PreTradeChecks(config=_config())
        expected_eastern_date = datetime.now(EASTERN_TZ).date()

        mock_earnings = MagicMock()
        mock_earnings.run.return_value = {"pass": True, "reason": None}

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None  # no duplicate position, symbol found path varies per call
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        with patch("algo.trading.pretrade_checks.EarningsBlackout", return_value=mock_earnings), patch(
            "algo.trading.pretrade_checks.DatabaseContext", return_value=mock_db_context
        ):
            checks.run_all(
                symbol="AAPL",
                position_value=1000.0,
                portfolio_value=100000.0,
                side="BUY",
                eval_date=None,
            )

        mock_earnings.run.assert_called_once()
        called_symbol, called_eval_date = mock_earnings.run.call_args[0]
        assert called_symbol == "AAPL"
        assert called_eval_date == expected_eastern_date

    def test_explicit_eval_date_is_respected_not_overridden(self):
        """An explicitly-passed eval_date (e.g. from a backtest or specific-date check)
        must not be silently replaced by "now"."""
        checks = PreTradeChecks(config=_config())

        from datetime import date

        explicit_date = date(2026, 3, 15)

        mock_earnings = MagicMock()
        mock_earnings.run.return_value = {"pass": True, "reason": None}

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = None
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        with patch("algo.trading.pretrade_checks.EarningsBlackout", return_value=mock_earnings), patch(
            "algo.trading.pretrade_checks.DatabaseContext", return_value=mock_db_context
        ):
            checks.run_all(
                symbol="AAPL",
                position_value=1000.0,
                portfolio_value=100000.0,
                side="BUY",
                eval_date=explicit_date,
            )

        called_eval_date = mock_earnings.run.call_args[0][1]
        assert called_eval_date == explicit_date
