"""Regression test for the 2026-08-21 fix (goal session - "make sure everything is
perfectly accurate from a finance point of view"): EarningsBlackout.run() must fail
closed when the earnings_date lookup query finds NO row at all within its lookback/
lookahead window - not silently pass=True.

Live-confirmed on two currently-active, currently-tradeable symbols:
- AZUL: real SEC earnings dates on file through 2025-05-14, but nothing newer loaded
  15+ months later - the loader hasn't found/predicted its next earnings date.
- CNET: a reused ticker. stock_symbols' real underlying company today is "ZW Data
  Action Technologies", but every earnings_calendar row on file for this symbol
  predates 2012 - leftover from the ticker's prior occupant.

Both would have silently returned pass=True (no blackout enforced) despite
GOVERNANCE.md's explicit "Earnings blackout fails closed (no confirmed_date -> BLOCK
all)" rule. The bug: the function's final fallback (`return {"pass": True, ...}`) was
shared by two different cases - "a real earnings_date was found but sits safely outside
the window" (correctly pass=True) and "no row was found at all" (should fail closed,
was incorrectly also pass=True). Fixed by returning pass=True only when a real row was
found and confirmed outside the window, and failing closed in a separate branch when no
row exists at all.
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
    mock_cur.fetchone.side_effect = [(fresh_load,), earnings_lookup_row]
    mock_db_context = MagicMock()
    mock_db_context.__enter__ = MagicMock(return_value=mock_cur)
    mock_db_context.__exit__ = MagicMock(return_value=False)
    return mock_db_context


class TestEarningsBlackoutNoRowInWindowFailsClosed:
    def test_no_row_found_at_all_fails_closed(self):
        """AZUL/CNET-shaped case: earnings_calendar has been refreshed recently (passes
        the freshness gate) but the date-range query finds nothing - must block, not pass."""
        blackout = EarningsBlackout(config=_config())
        mock_db_context = _mock_db_returning(None)

        with patch("algo.risk.earnings_blackout.DatabaseContext", return_value=mock_db_context):
            result = blackout.run("AZUL", date(2026, 8, 21))

        assert result["pass"] is False, (
            f"no earnings_calendar row in the lookback/lookahead window must fail closed - got {result}"
        )
        assert "no earnings date on file" in result["reason"].lower()

    def test_real_row_found_but_outside_window_still_passes(self):
        """Distinguishes the fixed bug from the legitimate case: a real earnings_date IS
        on file, just safely outside the blackout window - must still pass."""
        blackout = EarningsBlackout(config=_config())
        far_future = date(2026, 8, 21) + timedelta(days=100)
        mock_db_context = _mock_db_returning((far_future,))

        with patch("algo.risk.earnings_blackout.DatabaseContext", return_value=mock_db_context):
            result = blackout.run("WPM", date(2026, 8, 21))

        assert result["pass"] is True, f"a real earnings date safely outside the window must pass - got {result}"
