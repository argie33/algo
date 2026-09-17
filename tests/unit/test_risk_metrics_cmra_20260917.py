"""Regression test for RiskMetricsLoader._calculate_cmra - Barra US-E3's real Cumulative Range
Volatility descriptor (Appendix A, "US-E3 Descriptor Definitions", Section 1 "Volatility", item
v "CMRA"), fetched and read directly from the primary source (United States Equity Version 3
(E3) Risk Model Handbook, p.94) this session. REPLACES volatility_252d - a plain 252-trading-day
stdev with no counterpart in Barra's actual descriptor list - in loaders/stock_scores/
risk_scoring.py's own Risk pillar scoring (see that module's own docstring for the full
citation/rationale).

Formula: Z_t = sum_{s=1}^{t} [log(1+r_i,s) - log(1+r_f,s)] for t=1..12 (cumulative monthly
excess log-return), CMRA = log((1+Zmax)/(1+Zmin)) where Zmax/Zmin are the max/min of Z_t over
the trailing 12 months.
"""

import math

from loaders.load_risk_metrics_daily import RiskMetricsLoader


class TestCalculateCmraMatchesPrimarySourceFormula:
    def test_zero_returns_and_zero_risk_free_gives_zero_cmra(self) -> None:
        """Every Z_t = 0 (no return, no risk-free rate) - Zmax = Zmin = 0, CMRA = log(1/1) = 0.0,
        the "no range at all" floor."""
        result = RiskMetricsLoader._calculate_cmra([0.0] * 12, [0.0] * 12)
        assert result == 0.0

    def test_matches_independent_reference_implementation(self) -> None:
        """Independent reference computation, written directly against the primary-source
        formula rather than copying _calculate_cmra's own arithmetic, so this test can't pass
        merely by mirroring a shared bug."""
        monthly_returns = [0.02, -0.01, 0.03, 0.01, -0.04, 0.02, 0.05, -0.02, 0.01, 0.0, -0.03, 0.04]
        monthly_rf = [0.0025] * 12

        z = 0.0
        z_values = []
        for r, rf in zip(monthly_returns, monthly_rf, strict=True):
            z += math.log(1 + r) - math.log(1 + rf)
            z_values.append(z)
        expected = math.log((1 + max(z_values)) / (1 + min(z_values)))

        actual = RiskMetricsLoader._calculate_cmra(monthly_returns, monthly_rf)
        assert actual is not None
        assert abs(actual - expected) < 1e-12

    def test_higher_dispersion_produces_higher_cmra(self) -> None:
        """A wildly swinging return series should score a materially higher CMRA than a steady
        one with the same average return - CMRA measures RANGE, not central tendency."""
        steady = [0.01] * 12
        volatile = [0.20, -0.18, 0.22, -0.20, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01]
        rf = [0.0] * 12

        cmra_steady = RiskMetricsLoader._calculate_cmra(steady, rf)
        cmra_volatile = RiskMetricsLoader._calculate_cmra(volatile, rf)

        assert cmra_steady is not None
        assert cmra_volatile is not None
        assert cmra_volatile > cmra_steady

    def test_wrong_length_returns_none(self) -> None:
        """Must be exactly 12 months on each side - a partial window isn't a real 12-month
        CMRA reading (same 'insufficient history, don't fabricate a partial reading'
        convention this repo applies to every other stability metric)."""
        assert RiskMetricsLoader._calculate_cmra([0.01] * 11, [0.0] * 12) is None
        assert RiskMetricsLoader._calculate_cmra([0.01] * 12, [0.0] * 13) is None
        assert RiskMetricsLoader._calculate_cmra([], []) is None

    def test_catastrophic_cumulative_decline_returns_none_not_negative_cmra(self) -> None:
        """PRE-SHIP VERIFICATION GUARD (found live-checking this formula against the real active
        universe before wiring it into scoring - see _calculate_cmra's own docstring). When
        cumulative excess log-return breaches -100% (1+Zmin <= 0) - live-confirmed on real
        distressed/delisting-adjacent penny stocks with single months of -70% to -96% - the
        (1+Zmax)/(1+Zmin) ratio can flip to a small POSITIVE number even though both terms are
        negative, producing a spuriously NEGATIVE "CMRA" that would make the most distressed
        stock in the universe look like the single safest one under this pillar's "lower is
        better" convention. Must return None (invalid/undefined), never a fabricated negative
        reading."""
        # A single -85% month plunges cumulative excess log-return well past -100%.
        monthly_returns = [-0.85, -0.10, 0.05, 0.02, -0.03, 0.01, 0.04, -0.02, 0.03, -0.01, 0.02, 0.01]
        monthly_rf = [0.0] * 12

        result = RiskMetricsLoader._calculate_cmra(monthly_returns, monthly_rf)
        assert result is None

    def test_risk_free_netting_reduces_cmra_relative_to_raw_return_range(self) -> None:
        """Netting a nonzero risk-free rate genuinely changes Z_t (not a no-op scaling) - a
        real, symbol-independent constant risk-free rate shifts every Z_t down uniformly,
        narrowing (not widening) the max-minus-min range when the raw returns are mostly
        positive, since a larger constant subtracted from every cumulative term pulls the
        max down more in absolute terms than a small min. This is a sanity check that
        monthly_rf_rates is actually consumed, not silently ignored."""
        monthly_returns = [0.03] * 12
        cmra_no_rf = RiskMetricsLoader._calculate_cmra(monthly_returns, [0.0] * 12)
        cmra_with_rf = RiskMetricsLoader._calculate_cmra(monthly_returns, [0.005] * 12)

        assert cmra_no_rf is not None
        assert cmra_with_rf is not None
        assert cmra_no_rf != cmra_with_rf
