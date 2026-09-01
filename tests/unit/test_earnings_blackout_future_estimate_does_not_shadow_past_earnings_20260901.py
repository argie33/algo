"""Regression test: EarningsBlackout's post-earnings (days_after) window must not be
defeated by a symbol's own far-future forward earnings estimate already being on file.

algo/risk/earnings_blackout.py's earnings_date lookup previously ranked ALL real,
FUTURE earnings_date rows (rank 0) unconditionally above ALL real, PAST earnings_date
rows (rank 1), before ever considering distance to eval_date. That's correct for
placeholder-vs-real ranking (data_unavailable=TRUE placeholders must never outrank a
real date, see test_earnings_blackout_placeholder_deprioritized.py) but wrong for
real-vs-real ranking: almost every actively-covered symbol has BOTH its most recent
reported earnings (past) and its next forward estimate (future, often ~90 days out)
loaded simultaneously (yfinance's earnings_dates returns recent history plus forward
estimates together). The old query always picked the far-future estimate over the
true, days-old past earnings date - silently defeating the days_after blackout window
for exactly the whipsaw scenario this file's own history cites real losses for
("-19%, -9%, -8% losses on 2026-08-08").

Fixed 2026-09-01: real dates (future or past) now rank together (tier 0), ordered
purely by distance to eval_date - the nearest real earnings date always wins,
regardless of direction. Unavailable placeholders remain strictly tier 1.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from algo.risk.earnings_blackout import EarningsBlackout


def _config(days_after=1):
    cfg = {"earnings_blackout_days_before": 7, "earnings_blackout_days_after": days_after}
    m = MagicMock()
    m.get.side_effect = lambda k: cfg.get(k)
    return m


def _mock_db_returning(earnings_lookup_row):
    mock_cur = MagicMock()
    fresh_load = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=10)
    mock_cur.fetchone.side_effect = [(fresh_load,), earnings_lookup_row]
    mock_db_context = MagicMock()
    mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
    mock_db_context.__exit__ = MagicMock(return_value=False)
    return mock_db_context, mock_cur


class TestEarningsBlackoutQueryOrdersRealDatesByDistanceNotDirection:
    def test_sql_no_longer_unconditionally_prioritizes_future_over_past(self):
        """The rank-0 CASE branch must not special-case earnings_date >= eval_date -
        both future and past real dates must share tier 0, distance-ordered."""
        blackout = EarningsBlackout(config=_config())
        mock_db_context, mock_cur = _mock_db_returning(None)

        with patch("algo.risk.earnings_blackout.DatabaseContext", return_value=mock_db_context):
            blackout.run("XYZ", date(2026, 8, 31))

        earnings_query_sql = mock_cur.execute.call_args_list[1][0][0]
        # The old buggy query had "data_unavailable IS NOT TRUE AND earnings_date >= %s THEN 0"
        # as a distinct rank-0 branch from a plain "data_unavailable IS NOT TRUE THEN 1" -
        # i.e. two separate CASE branches for real data. The fix collapses these to one.
        assert earnings_query_sql.count("data_unavailable IS NOT TRUE") == 1, (
            "real (future or past) earnings dates must share a single tier, not be split "
            "into a future-favored rank ahead of a past rank"
        )

    def test_close_past_earnings_blocks_even_when_query_returns_it_over_a_far_future_estimate(self):
        """Simulates the corrected query: given a real past earnings date 1 trading day
        ago (inside a days_after=2 window) and given the query now correctly returns
        that nearest row (not a ~90-day-out future estimate), the blackout must fire."""
        blackout = EarningsBlackout(config=_config(days_after=2))
        # Real earnings 2026-08-28 (Friday), eval_date 2026-08-31 (Monday) = 1 trading
        # day post-earnings (< days_after=2).
        mock_db_context, _ = _mock_db_returning((date(2026, 8, 28), False))

        with patch("algo.risk.earnings_blackout.DatabaseContext", return_value=mock_db_context):
            result = blackout.run("XYZ", date(2026, 8, 31))

        assert result["pass"] is False, (
            f"a real earnings date 1 trading day in the past, inside the days_after window, "
            f"must block entry regardless of any far-future estimate also on file - got {result}"
        )
        assert "2026-08-28" in result["reason"]

    def test_far_future_estimate_still_passes_when_it_is_genuinely_the_nearest_real_date(self):
        """Sanity check the fix doesn't break the ordinary case: no recent past earnings
        on file, only a genuinely-far-future estimate - must still pass."""
        blackout = EarningsBlackout(config=_config())
        mock_db_context, _ = _mock_db_returning((date(2026, 11, 27), False))

        with patch("algo.risk.earnings_blackout.DatabaseContext", return_value=mock_db_context):
            result = blackout.run("XYZ", date(2026, 8, 31))

        assert result["pass"] is True
