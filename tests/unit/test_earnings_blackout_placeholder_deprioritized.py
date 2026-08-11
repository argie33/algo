"""Regression test: EarningsBlackout must rank a real earnings_date above a
data_unavailable placeholder row, not treat them as equally authoritative.

load_earnings_calendar.py's _unavailable_record() stamps earnings_date=today (the
fetch-attempt date, not a real earnings date) whenever a symbol's yfinance fetch fails
outright. The pre-fix query ordered "any future date beats any past date" regardless of
data_unavailable status, so a same-day fetch failure - which always sorts as "1 day in
the future" relative to eval_date - outranked a symbol's own real, already-past earnings
date whenever the real next cycle (~90 days out) hadn't been fetched yet. Live-reproduced
2026-08-09: WPM/BDX/DAC/GAIN/ERO each have a real earnings_date row days before the eval
date (correctly outside the blackout window) plus an unrelated data_unavailable=True
placeholder dated one day after eval_date (from a mass yfinance fetch-failure event that
wrote 4918 such rows in one run) - all 5 were blocked on "earnings tomorrow" sourced
entirely from the phantom row.

The fix must still fail closed when a symbol has NO real earnings_date on file at all -
that's the original documented incident this file's design defends against (see
earnings_blackout_data_unavailable_critical_bug memory).
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from algo.risk.earnings_blackout import EarningsBlackout


def _config():
    cfg = {"earnings_blackout_days_before": 7, "earnings_blackout_days_after": 1}
    m = MagicMock()
    m.get.side_effect = lambda k: cfg.get(k)
    return m


def _mock_db_returning(earnings_lookup_row):
    mock_cur = MagicMock()
    fresh_load = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=10)
    # First execute(): MAX(created_at) staleness check (fresh). Second: earnings_date lookup.
    mock_cur.fetchone.side_effect = [(fresh_load,), earnings_lookup_row]
    mock_db_context = MagicMock()
    mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
    mock_db_context.__exit__ = MagicMock(return_value=False)
    return mock_db_context, mock_cur


class TestEarningsBlackoutPrioritizesRealDataOverPlaceholder:
    def test_sql_ranks_real_dates_above_unavailable_placeholders(self):
        """The SQL itself must tier by data_unavailable status, not just future-vs-past."""
        blackout = EarningsBlackout(config=_config())
        mock_db_context, mock_cur = _mock_db_returning(None)

        with patch("algo.risk.earnings_blackout.DatabaseContext", return_value=mock_db_context):
            blackout.run("WPM", date(2026, 8, 7))

        earnings_query_sql = mock_cur.execute.call_args_list[1][0][0]
        assert "data_unavailable" in earnings_query_sql, (
            "earnings lookup must deprioritize data_unavailable rows below real ones"
        )

    def test_real_past_earnings_date_passes_even_when_query_would_also_find_a_placeholder(self):
        """Simulates the tiered query correctly returning the real (past, out-of-window)
        row instead of the closer-but-phantom future placeholder - the caller must not
        block the trade in that case."""
        blackout = EarningsBlackout(config=_config())
        # Real earnings 2026-08-06, 1 trading day before eval_date 2026-08-07: outside a
        # days_after=1 window (trading_days_away >= 1 required to block). The tiered SQL
        # would return this real row over the 2026-08-08 placeholder because it ranks
        # data_unavailable=FALSE above data_unavailable=TRUE.
        mock_db_context, _ = _mock_db_returning((date(2026, 8, 6),))

        with patch("algo.risk.earnings_blackout.DatabaseContext", return_value=mock_db_context):
            result = blackout.run("WPM", date(2026, 8, 7))

        assert result["pass"] is True, (
            f"a real earnings date safely outside the blackout window must not be shadowed "
            f"by a same-day fetch-failure placeholder - got {result}"
        )

    def test_placeholder_still_blocks_when_it_is_the_only_data_on_file(self):
        """A symbol with genuinely no real earnings_date anywhere (never confirmed) must
        still fail closed on the placeholder - preserves the original incident's fix."""
        blackout = EarningsBlackout(config=_config())
        mock_db_context, _ = _mock_db_returning((date(2026, 8, 8),))

        with patch("algo.risk.earnings_blackout.DatabaseContext", return_value=mock_db_context):
            result = blackout.run("NEWIPO", date(2026, 8, 7))

        assert result["pass"] is False, "with no real earnings data at all, the placeholder date must still fail closed"
