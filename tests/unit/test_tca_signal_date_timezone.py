#!/usr/bin/env python3
"""Regression test for the 2026-07-21 TCA signal_date timezone fix.

record_fill() wrote signal_date using date.today() (system-local calendar date), while
this same file's daily_report() already used datetime.now(EASTERN_TZ).date() for the
identical purpose, with a comment explaining the exact date.today()-near-midnight bug this
avoids. signal_date is used for exact date-boundary filtering (WHERE signal_date = %s) in
daily_report()/monthly_summary(), so a fill recorded near midnight would be written under
the wrong trading day and silently missing from that day's TCA report. Fixed to match the
already-established pattern in the same file.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from algo.trading.tca import TCAEngine
from utils.infrastructure.timezone import EASTERN_TZ


class TestRecordFillUsesEasternDate:
    def test_record_fill_writes_eastern_time_date_not_system_local(self):
        engine = TCAEngine(config={})

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        expected_eastern_date = datetime.now(EASTERN_TZ).date()

        with patch("algo.trading.tca.DatabaseContext", return_value=mock_db_context):
            engine.record_fill(
                trade_id=1,
                symbol="AAPL",
                signal_price=100.0,
                fill_price=100.05,
                shares_requested=10,
                shares_filled=10,
                side="BUY",
            )

        insert_call_args = mock_cur.execute.call_args_list[0]
        insert_params = insert_call_args[0][1]
        # Params tuple order: (trade_id, symbol, signal_date, signal_price, fill_price, ...)
        written_signal_date = insert_params[2]

        assert written_signal_date == expected_eastern_date
        assert isinstance(written_signal_date, date)

    def test_record_fill_does_not_use_bare_date_today(self):
        """Guard against regressing back to date.today() - patch it to a value that would
        only appear in the write if the fix regresses (system-local date could legitimately
        equal Eastern date most of the day, so this asserts the *call site*, not just the
        value, by checking date.today is never invoked during record_fill)."""
        engine = TCAEngine(config={})

        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)
        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        with patch("algo.trading.tca.DatabaseContext", return_value=mock_db_context), patch(
            "algo.trading.tca.date"
        ) as mock_date_module:
            mock_date_module.today.side_effect = AssertionError(
                "record_fill() must not call date.today() - use datetime.now(EASTERN_TZ).date()"
            )
            engine.record_fill(
                trade_id=1,
                symbol="AAPL",
                signal_price=100.0,
                fill_price=100.05,
                shares_requested=10,
                shares_filled=10,
                side="BUY",
            )
        # No AssertionError raised means date.today() was never called.
