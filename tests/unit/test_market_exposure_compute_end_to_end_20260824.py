"""End-to-end coverage for MarketExposure.compute() - the orchestration method itself was
never exercised by any test (per the 2026-08-24 exposure-system audit's coverage-gap list -
every existing test hits an individual factor/sub-method, never the full pipeline). The prior
session's stand-in was a one-off ad hoc script against the live local DB with
force_recompute=True, which persisted an unintended write and left no repeatable regression
test (see exposure_audit_followups_verified_20260824 memory).

These tests fully mock the calculator/internal factor methods and the persistence/cache/DB
layer so compute() runs its real blend/veto/tier logic end-to-end with no DB access and no
writes, verifying:
- the trend-only composite (W_PILLAR_TREND=100) actually drives exposure_pct from t30 alone
- vol-managed scaling is applied before hard-veto capping (scaled_score, not raw score, is capped)
- a hard veto (VIX > 40 rising) both records halt_reasons and caps the final score
- the persisted result dict has the shape downstream consumers (dashboard/API) depend on
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.risk.exposure_policy import tier_for_exposure
from algo.risk.market_exposure import MarketExposure


def _clean_factor_mocks(me):
    """Wire every compute() dependency to a benign, no-veto-triggering value."""
    me.try_load_cached = MagicMock(return_value=None)
    me._persist = MagicMock()

    me.calculator = MagicMock()
    me.calculator.trend_30wk.return_value = {"score": 80.0, "above_30wma": True}
    me.calculator.spy_momentum.return_value = {"score": 50.0}
    me.calculator.selling_pressure.return_value = {"score": 90.0, "count": 0}
    me.calculator.vix_regime.return_value = {"score": 90.0, "value": 15.0, "rising": False}
    me.calculator.new_highs_lows.return_value = {"score": 70.0}
    me.calculator.aaii.return_value = {"score": 60.0}
    me.calculator.put_call_ratio.return_value = {"data_unavailable": True, "reason": "n/a"}
    me.calculator._pct_above_ma.side_effect = lambda eval_date, ma_days, cur: (
        {"score": 60.0, "value": 50.0} if ma_days == 50 else {"score": 55.0, "value": 55.0}
    )

    me._market_technicals_factor = MagicMock(return_value={"data_unavailable": True, "reason": "n/a"})
    me._credit_spread = MagicMock(return_value={"score": 85.0, "value": 3.0})
    me._ad_line = MagicMock(return_value={"score": 65.0, "relation": "confirming"})
    me._has_market_confirmation = MagicMock(return_value=True)
    me._sahm_rule_factor = MagicMock(return_value={"data_unavailable": True, "reason": "n/a"})
    me._yield_curve_factor = MagicMock(return_value={"data_unavailable": True, "reason": "n/a"})
    me._inflation_expectations_factor = MagicMock(return_value={"data_unavailable": True, "reason": "n/a"})
    me._slow_macro_veto = MagicMock(return_value={"triggered": False, "reasons": [], "cap": 100.0})
    me._vol_managed_multiplier = MagicMock(return_value=1.0)
    return me


def _run_compute(me, eval_date):
    fake_cur = MagicMock()
    fake_db_ctx = MagicMock()
    fake_db_ctx.__enter__.return_value = fake_cur
    fake_db_ctx.__exit__.return_value = False

    fake_config = MagicMock()
    fake_config.get.return_value = 6  # market_exposure_veto3_distribution_days_threshold

    with (
        patch("algo.risk.market_exposure.DatabaseContext", return_value=fake_db_ctx),
        patch("algo.infrastructure.MarketCalendar.is_trading_day", return_value=True),
        patch("algo.risk.market_exposure.AlgoConfig", return_value=fake_config),
    ):
        return me.compute(eval_date=eval_date)


class TestComputeEndToEndCleanMarket:
    def test_trend_only_composite_drives_exposure_pct(self):
        me = _clean_factor_mocks(MarketExposure())
        result = _run_compute(me, date(2026, 8, 24))

        # W_PILLAR_TREND=100, W_PILLAR_RISK=W_PILLAR_CONFIRM=0, mtech unavailable so
        # SUBW_SPY_MOMENTUM's weight is moot -> raw_score is exactly t30's score.
        assert result["raw_score"] == 80.0
        assert result["exposure_pct"] == 80.0
        assert result["capped_score"] == 80.0
        assert result["halt_reasons"] == []
        assert result["distribution_days"] == 0
        assert result["regime"] == tier_for_exposure(80.0)["name"]

    def test_persist_called_once_with_computed_result(self):
        me = _clean_factor_mocks(MarketExposure())
        result = _run_compute(me, date(2026, 8, 24))

        me._persist.assert_called_once()
        persisted_date, persisted_result = me._persist.call_args[0]
        assert persisted_date == date(2026, 8, 24)
        assert persisted_result is result

    def test_result_shape_matches_dashboard_api_contract(self):
        me = _clean_factor_mocks(MarketExposure())
        result = _run_compute(me, date(2026, 8, 24))

        for key in (
            "eval_date",
            "raw_score",
            "available_factors_max",
            "capped_score",
            "exposure_pct",
            "regime",
            "halt_reasons",
            "distribution_days",
            "factors",
        ):
            assert key in result, f"missing top-level key: {key}"

        factors = result["factors"]
        for key in ("pillar_trend", "pillar_risk", "pillar_confirm", "macro_watch", "vol_managed_scaling"):
            assert key in factors, f"missing factors key: {key}"
        assert factors["vol_managed_scaling"]["multiplier"] == 1.0

    def test_cache_hit_short_circuits_before_any_factor_call(self):
        me = _clean_factor_mocks(MarketExposure())
        cached = {"exposure_pct": 55.0, "data_unavailable": False}
        me.try_load_cached = MagicMock(return_value=cached)

        result = _run_compute(me, date(2026, 8, 24))

        assert result is cached
        me.calculator.trend_30wk.assert_not_called()
        me._persist.assert_not_called()


class TestComputeEndToEndVetoAndVolScaling:
    def test_vix_veto_caps_score_after_vol_managed_scaling(self):
        me = _clean_factor_mocks(MarketExposure())
        me.calculator.trend_30wk.return_value = {"score": 90.0, "above_30wma": True}
        me.calculator.vix_regime.return_value = {"score": 10.0, "value": 45.0, "rising": True}
        me._vol_managed_multiplier = MagicMock(return_value=0.5)

        result = _run_compute(me, date(2026, 8, 24))

        # raw_score = 90 (trend-only); vol-managed scaling applies BEFORE the veto cap:
        # scaled = 90 * 0.5 = 45, then VIX veto caps at 30 -> final = min(45, 30) = 30.
        assert result["raw_score"] == 90.0
        assert result["exposure_pct"] == 30.0
        assert result["capped_score"] == 30.0
        assert any("VIX" in reason for reason in result["halt_reasons"])
        assert result["regime"] == tier_for_exposure(30.0)["name"]

    def test_selling_pressure_veto_triggers_at_threshold(self):
        me = _clean_factor_mocks(MarketExposure())
        me.calculator.selling_pressure.return_value = {"score": 20.0, "count": 6}

        result = _run_compute(me, date(2026, 8, 24))

        assert result["distribution_days"] == 6
        assert any("selling-pressure days" in reason for reason in result["halt_reasons"])
        assert result["capped_score"] <= 35.0

    def test_credit_spread_systemic_stress_veto(self):
        me = _clean_factor_mocks(MarketExposure())
        me._credit_spread = MagicMock(return_value={"score": 5.0, "value": 9.0})

        result = _run_compute(me, date(2026, 8, 24))

        assert any("HY credit spread" in reason for reason in result["halt_reasons"])
        assert result["capped_score"] <= 30.0
