"""Regression test for a silent-fabrication bug in
ValueAtRisk.generate_daily_risk_report() (algo/risk/var.py):

beta_exposure() and concentration_report() each already return an explicit
{"...": 0.0, "data_unavailable": False} dict for the genuine "no open positions"
case. Any exception either raises for instead (stale/missing portfolio snapshot,
corrupted position data, insufficient SPY/stock history) is a real failure - not
"zero exposure". generate_daily_risk_report() previously caught *any* exception
from these two calls and silently substituted portfolio_beta=0.0 /
top_5_concentration_pct=0.0, which made the `beta > 2.0` / `concentration > 30%`
alert checks unable to ever fire on a broken calculation, and persisted the
fabricated zero to algo_risk_daily indistinguishable from a genuinely flat
portfolio. This locks in the fix: a real failure must now raise, not fabricate.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from algo.risk.var import ValueAtRisk


@pytest.fixture
def var_calculator():
    # max_simulated_var_pct/max_top5_concentration_pct/max_portfolio_beta added 2026-09-06:
    # generate_daily_risk_report()'s alert thresholds now read these config-driven values
    # (fixed cross-layer drift vs. pretrade_checks.py/unified_risk_monitor.py, which already
    # enforced them) instead of hardcoded literals - required whenever the corresponding
    # metric dict is non-empty.
    return ValueAtRisk(
        {
            "var_percentile": 5,
            "cvar_percentile": 5,
            "stressed_var_percentile": 10,
            "max_simulated_var_pct": 2.0,
            "max_top5_concentration_pct": 30.0,
            "max_portfolio_beta": 2.0,
        }
    )


def _stub_out_everything_except(var_calculator, **overrides):
    """Point every generate_daily_risk_report() dependency at a benign stub,
    then override the ones under test."""
    defaults = {
        "historical_var": lambda: None,
        "cvar": lambda: None,
        "stressed_var": lambda: None,
        "beta_exposure": lambda report_date=None: {"portfolio_beta": 0.5, "data_unavailable": False},
        "concentration_report": lambda report_date=None: {"top_5_concentration_pct": 10.0, "data_unavailable": False},
    }
    defaults.update(overrides)
    for name, fn in defaults.items():
        setattr(var_calculator, name, fn)


class TestBetaExposureFailFast:
    def test_beta_exposure_exception_raises_not_fabricates_zero(self, var_calculator):
        def _raise(report_date=None):
            raise RuntimeError("[VAR CRITICAL] Portfolio snapshot is stale")

        _stub_out_everything_except(var_calculator, beta_exposure=_raise)

        with pytest.raises(RuntimeError, match="beta exposure is REQUIRED"):
            var_calculator.generate_daily_risk_report(date(2026, 8, 4))

    def test_beta_exposure_missing_key_raises(self, var_calculator):
        _stub_out_everything_except(var_calculator, beta_exposure=lambda report_date=None: {"data_unavailable": False})

        with pytest.raises(RuntimeError, match="portfolio_beta"):
            var_calculator.generate_daily_risk_report(date(2026, 8, 4))

    def test_beta_exposure_no_positions_is_legitimate_zero(self, var_calculator):
        """The explicit no-open-positions zero dict must still flow through untouched."""
        mock_cur = MagicMock()
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur

        _stub_out_everything_except(var_calculator)

        with patch("algo.risk.var.DatabaseContext", return_value=mock_ctx):
            result = var_calculator.generate_daily_risk_report(date(2026, 8, 4))

        assert result["beta_exposure"]["portfolio_beta"] == 0.5
        assert result["status"] == "ok"


class TestConcentrationReportFailFast:
    def test_concentration_report_exception_raises_not_fabricates_zero(self, var_calculator):
        def _raise(report_date=None):
            raise RuntimeError("[CONCENTRATION CRITICAL] Portfolio snapshot has NULL date")

        _stub_out_everything_except(var_calculator, concentration_report=_raise)

        with pytest.raises(RuntimeError, match="concentration is REQUIRED"):
            var_calculator.generate_daily_risk_report(date(2026, 8, 4))

    def test_concentration_report_missing_key_raises(self, var_calculator):
        _stub_out_everything_except(
            var_calculator, concentration_report=lambda report_date=None: {"data_unavailable": False}
        )

        with pytest.raises(RuntimeError, match="top_5_concentration_pct"):
            var_calculator.generate_daily_risk_report(date(2026, 8, 4))
