#!/usr/bin/env python3
"""Tests for algo/risk/capital_routing.py - the satellite GLD/IEF/DBC/cash router that
landed 2026-08-24 with zero test coverage of its own, found during a pre-live-money
review of the whole system's logic.

Primary focus: the staleness guards added to `_leg_signal`/`_move_veto` in that same
review. Live-found real bug the guards fix: IEF/DBC had gone 26 trading days stale in
price_daily/price_weekly (a prior essential-symbols trim had silently stopped fetching
them) on the same day this module first computed a real capital_routing_daily row against
that data - with no staleness check at all, the module confidently sized a GLD/DBC
allocation off a month-old DBC price. `^MOVE`'s "Alpaca-sourced" docstring claim was also
found to be wrong (it's yfinance-sourced, like `^VIX` - see the corrected module
docstring) - not a functional bug since the yfinance fallback does work today, but a
reason the MOVE veto's staleness guard matters independently: yfinance is a weaker link
elsewhere in this codebase than Alpaca (see MEMORY.md Loader Brittleness).

Also covers `_annualized_vol` and `_size_legs`, which had no coverage either.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

from algo.risk.capital_routing import (
    _MAX_STALE_TRADING_DAYS_DAILY,
    _MAX_STALE_TRADING_DAYS_MOVE,
    _MAX_STALE_TRADING_DAYS_WEEKLY,
    CapitalRouting,
)

EVAL_DATE = date(2026, 8, 24)  # a Monday


def _fresh_daily_rows(n=21, close=100.0):
    """n rows of (date, close), most-recent-first, ending at EVAL_DATE."""
    return [(EVAL_DATE - timedelta(days=i), close + i * 0.01) for i in range(n)]


class TestLegSignalStalenessGuard:
    def test_stale_weekly_data_marks_leg_unavailable(self):
        """price_weekly's latest row is far older than _MAX_STALE_TRADING_DAYS_WEEKLY
        trading days behind eval_date - must reject rather than compute a trend off it."""
        cur = MagicMock()
        stale_week = EVAL_DATE - timedelta(days=60)  # well past any weekly threshold
        cur.fetchone.return_value = (stale_week, 100.0, 95.0)
        cr = CapitalRouting()
        result = cr._leg_signal("DBC", EVAL_DATE, cur)
        assert result["data_unavailable"] is True
        assert "stale" in result["reason"].lower()

    def test_stale_daily_data_marks_leg_unavailable(self):
        """Weekly trend read is fresh, but the daily closes used for vol are stale -
        this is the exact shape of the live IEF/DBC bug (weekly SMA can still resolve
        from old data while the daily feed has stopped)."""
        cur = MagicMock()
        fresh_week = EVAL_DATE - timedelta(days=2)
        stale_daily_rows = [(EVAL_DATE - timedelta(days=40 + i), 100.0) for i in range(21)]
        cur.fetchone.return_value = (fresh_week, 100.0, 95.0)
        cur.fetchall.return_value = stale_daily_rows
        cr = CapitalRouting()
        result = cr._leg_signal("IEF", EVAL_DATE, cur)
        assert result["data_unavailable"] is True
        assert "stale" in result["reason"].lower()

    def test_fresh_data_computes_normally(self):
        cur = MagicMock()
        fresh_week = EVAL_DATE - timedelta(days=1)
        cur.fetchone.return_value = (fresh_week, 100.0, 95.0)
        cur.fetchall.return_value = _fresh_daily_rows()
        cr = CapitalRouting()
        result = cr._leg_signal("GLD", EVAL_DATE, cur)
        assert result["data_unavailable"] is False
        assert result["trend_up"] is True
        assert result["vol_20d"] is not None

    def test_exactly_at_threshold_still_accepted(self):
        """Boundary check: exactly _MAX_STALE_TRADING_DAYS_WEEKLY trading days old is
        still within tolerance (only strictly greater-than rejects)."""
        cur = MagicMock()
        week_date = EVAL_DATE - timedelta(days=_MAX_STALE_TRADING_DAYS_WEEKLY)
        cur.fetchone.return_value = (week_date, 100.0, 95.0)
        cur.fetchall.return_value = _fresh_daily_rows()
        cr = CapitalRouting()
        result = cr._leg_signal("GLD", EVAL_DATE, cur)
        assert result["data_unavailable"] is False

    def test_no_weekly_data_marks_unavailable(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        cr = CapitalRouting()
        result = cr._leg_signal("GLD", EVAL_DATE, cur)
        assert result["data_unavailable"] is True

    def test_nonfinite_trend_data_marks_unavailable(self):
        cur = MagicMock()
        fresh_week = EVAL_DATE - timedelta(days=1)
        cur.fetchone.return_value = (fresh_week, float("nan"), 95.0)
        cr = CapitalRouting()
        result = cr._leg_signal("GLD", EVAL_DATE, cur)
        assert result["data_unavailable"] is True


class TestMoveVetoStalenessGuard:
    def test_stale_move_data_treated_as_no_veto(self):
        cur = MagicMock()
        stale_date = EVAL_DATE - timedelta(days=30)
        cur.fetchone.return_value = (stale_date, 200.0)  # would veto if trusted
        cr = CapitalRouting()
        move_level, veto = cr._move_veto(EVAL_DATE, cur)
        assert move_level is None
        assert veto is False

    def test_fresh_high_move_vetoes(self):
        cur = MagicMock()
        fresh_date = EVAL_DATE - timedelta(days=1)
        cur.fetchone.return_value = (fresh_date, 200.0)
        cr = CapitalRouting()
        move_level, veto = cr._move_veto(EVAL_DATE, cur)
        assert move_level == 200.0
        assert veto is True

    def test_fresh_normal_move_no_veto(self):
        cur = MagicMock()
        fresh_date = EVAL_DATE - timedelta(days=1)
        cur.fetchone.return_value = (fresh_date, 90.0)
        cr = CapitalRouting()
        move_level, veto = cr._move_veto(EVAL_DATE, cur)
        assert move_level == 90.0
        assert veto is False

    def test_boundary_threshold_vetoes(self):
        cur = MagicMock()
        fresh_date = EVAL_DATE - timedelta(days=1)
        cur.fetchone.return_value = (fresh_date, CapitalRouting.MOVE_VETO_THRESHOLD)
        cr = CapitalRouting()
        _, veto = cr._move_veto(EVAL_DATE, cur)
        assert veto is True

    def test_no_move_data_no_veto(self):
        cur = MagicMock()
        cur.fetchone.return_value = None
        cr = CapitalRouting()
        move_level, veto = cr._move_veto(EVAL_DATE, cur)
        assert move_level is None
        assert veto is False

    def test_exactly_at_staleness_threshold_still_trusted(self):
        cur = MagicMock()
        boundary_date = EVAL_DATE - timedelta(days=_MAX_STALE_TRADING_DAYS_MOVE)
        cur.fetchone.return_value = (boundary_date, 200.0)
        cr = CapitalRouting()
        move_level, veto = cr._move_veto(EVAL_DATE, cur)
        assert move_level == 200.0
        assert veto is True


class TestAnnualizedVol:
    def test_flat_prices_zero_vol(self):
        closes_desc = [100.0] * 21
        vol = CapitalRouting._annualized_vol(closes_desc)
        assert vol == 0.0

    def test_insufficient_data_returns_none(self):
        assert CapitalRouting._annualized_vol([100.0]) is None
        assert CapitalRouting._annualized_vol([]) is None

    def test_nonpositive_prices_skipped_not_crashed(self):
        # oldest-first after reversal: 99, 0, -5, 101, 100, 103, 98 - the 0/-5 pair and
        # its neighbors get skipped (any leg touching a non-positive price), leaving
        # enough valid consecutive pairs (101->100, 100->103, 103->98) to compute vol
        # without raising or looping forever.
        closes_desc = [98.0, 103.0, 100.0, 101.0, -5.0, 0.0, 99.0]
        vol = CapitalRouting._annualized_vol(closes_desc)
        assert vol is not None
        assert vol >= 0.0

    def test_varying_prices_positive_vol(self):
        closes_desc = [105.0, 95.0, 110.0, 90.0, 100.0]
        vol = CapitalRouting._annualized_vol(closes_desc)
        assert vol is not None
        assert vol > 0.0


class TestSizeLegs:
    def _leg(self, trend_up, vol, data_unavailable=False):
        return {"data_unavailable": data_unavailable, "trend_up": trend_up, "vol_20d": vol}

    def test_all_legs_down_or_unavailable_goes_full_cash(self):
        leg_data = {
            "GLD": self._leg(False, 0.2),
            "IEF": self._leg(False, 0.05),
            "DBC": self._leg(True, None, data_unavailable=True),
        }
        cr = CapitalRouting()
        weights = cr._size_legs(leg_data, move_veto=False)
        assert weights["CASH"] == 1.0
        assert weights["GLD"] == 0.0 and weights["IEF"] == 0.0 and weights["DBC"] == 0.0

    def test_inverse_vol_weighting_favors_lower_vol_leg(self):
        leg_data = {
            "GLD": self._leg(True, 0.20),
            "IEF": self._leg(True, 0.05),
            "DBC": self._leg(False, 0.30),  # trend down - excluded
        }
        cr = CapitalRouting()
        weights = cr._size_legs(leg_data, move_veto=False)
        assert weights["DBC"] == 0.0
        assert weights["CASH"] == 0.0
        assert weights["IEF"] > weights["GLD"]  # lower vol -> bigger weight
        total = weights["GLD"] + weights["IEF"] + weights["DBC"] + weights["CASH"]
        assert abs(total - 1.0) < 1e-9

    def test_move_veto_excludes_only_ief(self):
        leg_data = {
            "GLD": self._leg(True, 0.20),
            "IEF": self._leg(True, 0.05),
            "DBC": self._leg(True, 0.25),
        }
        cr = CapitalRouting()
        weights = cr._size_legs(leg_data, move_veto=True)
        assert weights["IEF"] == 0.0
        assert weights["GLD"] > 0.0
        assert weights["DBC"] > 0.0
        assert weights["CASH"] == 0.0

    def test_zero_or_missing_vol_excludes_leg(self):
        leg_data = {
            "GLD": self._leg(True, 0.0),
            "IEF": self._leg(True, None),
            "DBC": self._leg(True, 0.25),
        }
        cr = CapitalRouting()
        weights = cr._size_legs(leg_data, move_veto=False)
        assert weights["GLD"] == 0.0
        assert weights["IEF"] == 0.0
        assert weights["DBC"] == 1.0
