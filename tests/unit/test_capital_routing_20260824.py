"""Unit tests for algo/risk/capital_routing.py - the leftover-capital router added
2026-08-24 (user-directed /goal, following the exposure-score redesign) that decides what
to do with the (100 - exposure_pct)% of capital NOT going into stocks, among GLD/IEF/DBC/
cash. See that module's docstring for the full design rationale.

Covers: inverse-vol sizing math, trend-gating, MOVE veto (IEF-only), staleness guards,
and the data_unavailable degrade path when market_exposure_daily has no row yet.
"""

from datetime import date

import pytest

from algo.risk.capital_routing import CapitalRouting


class TestSizeLegs:
    """_size_legs: inverse-volatility weighting among qualifying legs only."""

    def _leg(self, trend_up, vol, unavailable=False):
        if unavailable:
            return {"data_unavailable": True}
        return {"data_unavailable": False, "trend_up": trend_up, "vol_20d": vol}

    def test_all_legs_trending_up_splits_by_inverse_vol(self):
        cr = CapitalRouting()
        leg_data = {
            "GLD": self._leg(True, 0.20),
            "IEF": self._leg(True, 0.05),
            "DBC": self._leg(True, 0.20),
        }
        weights = cr._size_legs(leg_data, move_veto=False)
        # IEF has the lowest vol (0.05) so should get the largest weight
        assert weights["IEF"] > weights["GLD"]
        assert weights["IEF"] > weights["DBC"]
        assert weights["GLD"] == pytest.approx(weights["DBC"])
        assert weights["CASH"] == 0.0
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_no_legs_trending_up_goes_all_cash(self):
        cr = CapitalRouting()
        leg_data = {
            "GLD": self._leg(False, 0.20),
            "IEF": self._leg(False, 0.05),
            "DBC": self._leg(False, 0.20),
        }
        weights = cr._size_legs(leg_data, move_veto=False)
        assert weights == {"GLD": 0.0, "IEF": 0.0, "DBC": 0.0, "CASH": 1.0}

    def test_down_trend_leg_excluded_even_with_lowest_vol(self):
        """IEF has the lowest vol but a down trend - must get zero weight regardless."""
        cr = CapitalRouting()
        leg_data = {
            "GLD": self._leg(True, 0.20),
            "IEF": self._leg(False, 0.01),  # lowest vol, but down trend
            "DBC": self._leg(True, 0.20),
        }
        weights = cr._size_legs(leg_data, move_veto=False)
        assert weights["IEF"] == 0.0
        assert weights["GLD"] == pytest.approx(0.5)
        assert weights["DBC"] == pytest.approx(0.5)

    def test_move_veto_zeroes_ief_only_not_gld_or_dbc(self):
        cr = CapitalRouting()
        leg_data = {
            "GLD": self._leg(True, 0.20),
            "IEF": self._leg(True, 0.05),  # trending up, would otherwise dominate
            "DBC": self._leg(True, 0.20),
        }
        weights = cr._size_legs(leg_data, move_veto=True)
        assert weights["IEF"] == 0.0
        assert weights["GLD"] > 0.0
        assert weights["DBC"] > 0.0
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_unavailable_leg_excluded(self):
        cr = CapitalRouting()
        leg_data = {
            "GLD": self._leg(True, 0.20),
            "IEF": self._leg(True, 0.05, unavailable=True),
            "DBC": self._leg(True, 0.20),
        }
        weights = cr._size_legs(leg_data, move_veto=False)
        assert weights["IEF"] == 0.0
        assert weights["GLD"] == pytest.approx(0.5)
        assert weights["DBC"] == pytest.approx(0.5)

    def test_zero_or_negative_vol_leg_excluded_not_div_by_zero(self):
        cr = CapitalRouting()
        leg_data = {
            "GLD": self._leg(True, 0.0),
            "IEF": self._leg(True, 0.05),
            "DBC": self._leg(True, -0.1),
        }
        weights = cr._size_legs(leg_data, move_veto=False)
        assert weights["GLD"] == 0.0
        assert weights["DBC"] == 0.0
        assert weights["IEF"] == pytest.approx(1.0)


class TestAnnualizedVol:
    def test_too_few_closes_returns_none(self):
        assert CapitalRouting._annualized_vol([100.0]) is None
        assert CapitalRouting._annualized_vol([]) is None

    def test_normal_series_returns_positive_finite_vol(self):
        # DESC order (most recent first), as returned by the real query
        closes = [103.0, 102.0, 104.0, 101.0, 100.0, 102.0, 99.0, 101.0, 100.0, 98.0]
        vol = CapitalRouting._annualized_vol(closes)
        assert vol is not None
        assert vol > 0
        assert vol < 10.0  # sane upper bound - not some blown-up NaN/Inf artifact

    def test_nan_and_infinite_prices_skipped_not_propagated(self):
        closes = [100.0, float("nan"), 101.0, float("inf"), 99.0, 100.0, 98.0, 101.0]
        vol = CapitalRouting._annualized_vol(closes)
        assert vol is not None
        import math

        assert not math.isnan(vol)
        assert not math.isinf(vol)

    def test_non_positive_prices_skipped(self):
        closes = [100.0, 0.0, -5.0, 101.0, 99.0, 100.0, 98.0]
        vol = CapitalRouting._annualized_vol(closes)
        # Should still compute from the remaining valid pairs, not crash
        assert vol is None or vol >= 0

    def test_constant_prices_zero_vol_not_none(self):
        closes = [100.0] * 10
        vol = CapitalRouting._annualized_vol(closes)
        assert vol == 0.0


class TestComputeDataUnavailable:
    def test_raises_on_non_trading_day(self, monkeypatch):
        cr = CapitalRouting()

        class _FakeCalendar:
            @staticmethod
            def is_trading_day(d):
                return False

        monkeypatch.setattr("algo.infrastructure.MarketCalendar", _FakeCalendar)
        with pytest.raises(ValueError, match="not a trading day"):
            cr.compute(date(2026, 8, 22))  # a Saturday

    def test_missing_market_exposure_row_returns_data_unavailable(self, monkeypatch):
        cr = CapitalRouting()

        class _FakeCalendar:
            @staticmethod
            def is_trading_day(d):
                return True

        monkeypatch.setattr("algo.infrastructure.MarketCalendar", _FakeCalendar)
        monkeypatch.setattr(cr, "try_load_cached", lambda eval_date: None)

        class _FakeCursor:
            def execute(self, *a, **kw):
                pass

            def fetchone(self):
                return None

        class _FakeDbContext:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return _FakeCursor()

            def __exit__(self, *a):
                return False

        monkeypatch.setattr("algo.risk.capital_routing.DatabaseContext", _FakeDbContext)
        result = cr.compute(date(2026, 8, 24), force_recompute=True)
        assert result["data_unavailable"] is True
        assert "market_exposure_daily" in result["reason"]

    def test_persist_never_sends_null_for_not_null_weight_columns(self, monkeypatch):
        """BUG FOUND 2026-08-27 (pre-live-money audit, live-reproduced against the real local
        DB): the data_unavailable branch's result dict has no gld_weight/ief_weight/
        dbc_weight/cash_weight/move_veto keys at all, and _persist() used to pass
        result.get(...) straight into the INSERT - a real None, not a missing param. Those 4
        weight columns are NOT NULL in the schema (migration 1227, DEFAULT 0/0/0/1) - but an
        explicit NULL in an INSERT always overrides a column DEFAULT, so this crashed with
        psycopg2.errors.NotNullViolation on every real call to this "graceful degradation"
        path instead of persisting the data_unavailable row it was trying to write. The
        old test above used a fully no-op fake cursor.execute() that silently accepted
        anything, including params real Postgres would reject - this test instead captures
        the actual params tuple and checks it the way a NOT NULL constraint would.
        """
        cr = CapitalRouting()

        class _FakeCalendar:
            @staticmethod
            def is_trading_day(d):
                return True

        monkeypatch.setattr("algo.infrastructure.MarketCalendar", _FakeCalendar)
        monkeypatch.setattr(cr, "try_load_cached", lambda eval_date: None)

        captured_params = []

        class _FakeCursor:
            def execute(self, query, params=None):
                if params is not None and "INSERT INTO capital_routing_daily" in query:
                    captured_params.append(params)

            def fetchone(self):
                return None

        class _FakeDbContext:
            def __init__(self, *a, **kw):
                pass

            def __enter__(self):
                return _FakeCursor()

            def __exit__(self, *a):
                return False

        monkeypatch.setattr("algo.risk.capital_routing.DatabaseContext", _FakeDbContext)
        result = cr.compute(date(2026, 8, 24), force_recompute=True)
        assert result["data_unavailable"] is True
        assert len(captured_params) == 1
        # Column order per _persist()'s INSERT: date, exposure_pct, uninvested_capital_pct,
        # gld_trend_up, ief_trend_up, dbc_trend_up, gld_vol_20d, ief_vol_20d, dbc_vol_20d,
        # gld_weight, ief_weight, dbc_weight, cash_weight, move_index, move_veto, factors,
        # data_unavailable, reason
        params = captured_params[0]
        not_null_weight_indices = {9: "gld_weight", 10: "ief_weight", 11: "dbc_weight", 12: "cash_weight"}
        for idx, name in not_null_weight_indices.items():
            assert params[idx] is not None, f"{name} (index {idx}) is None - would violate NOT NULL constraint"
        assert params[14] is not None, "move_veto (index 14) is None - would violate NOT NULL constraint"
        assert params[9:13] == (0.0, 0.0, 0.0, 1.0)
        assert params[14] is False
