"""Regression tests for two related Quality-pillar fixes (2026-08-28, goal session "figure out
the industry-best right formula" - see algo/research/quality_industry_leader_formula_comparison_
20260828.py for the full Fama-MacBeth evidence trail and MEMORY.md for the write-up):

1. SECTOR-CONDITIONAL FORMULA (superseded 2026-09-07): Financial Services/Real Estate symbols
   used to get a 7-input, two-cluster (profitability + safety) quality_score construction
   instead of the universal flat 8-input weighted average, dropping asset_turnover_score for
   those two sectors. The "best and brightest" scoring-methodology rewrite collapsed this back
   to one flat formula for every sector (see TestUniformFormulaAcrossSectors below) - published
   multi-factor methodology has no per-sector aggregation shape, and the isolated-testing
   finding behind the original split was diagnosed against the old absolute-curve
   architecture, which no longer applies once quality_score is finalized by
   update_quality_sector_neutral_scores()'s sector-neutral z-scoring.

2. MARGIN VOLATILITY DEAD-CODE BUG: found by accident while building test #1's fixture -
   `margin_volatility_score` read `metrics.get("margin_volatility")` before that key was ever
   written into `metrics` (the write happens much later in the function), so it silently scored
   None for every single symbol despite being documented as a real, scored, 7%-weighted input.
   Fixed to read the `margin_volatility` parameter directly (the value the caller actually
   passed in). This affects ALL symbols, not just Financial Services/Real Estate.

Expected values below are independently derived using
`ValueQualityGrowthMetricsLoader._margin_curve` (the same standalone curve-score
helper `test_quality_roe_roce_percentile_ranking_20260828.py` already uses for this exact
purpose) applied to the SAME breakpoints live in `_compute_quality_metrics`, not copied from a
particular run's output - if either the curve breakpoints or the composite weights drift, this
test should fail, not silently keep matching.
"""

from unittest.mock import MagicMock, patch

import pytest

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader as L


def _row(
    stockholders_equity=10_000_000.0,
    total_liabilities=5_000_000.0,
    total_assets=15_000_000.0,
    net_income=1_500_000.0,
    revenue=20_000_000.0,
    operating_income=1_800_000.0,
    cost_of_revenue=12_000_000.0,
    long_term_debt=2_000_000.0,
):
    # Same 34-column shape as test_quality_metrics_completeness_floor_20260826.py's fixture.
    return (
        stockholders_equity,  # 0
        total_liabilities,  # 1
        total_assets,  # 2
        net_income,  # 3
        revenue,  # 4
        operating_income,  # 5
        6_000_000.0,  # 6 current_assets
        3_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        200_000.0,  # 10 interest_expense
        1_000_000.0,  # 11 shares_outstanding
        cost_of_revenue,  # 12
        2_000_000.0,  # 13 operating_cash_flow
        1_600_000.0,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        8_000_000.0,  # 19 gross_profit
        long_term_debt,  # 20
        500_000.0,  # 21 cash_and_equivalents
        None,  # 22 income_tax_expense
        None,  # 23 pretax_income
        None,  # 24 prior_year_net_income
        None,  # 25 prior_year_operating_income
        None,  # 26 prior_year_operating_cash_flow
        None,  # 27 prior_year_free_cash_flow
        None,  # 28 prior_year_cost_of_revenue
        None,  # 29 prior_year_total_assets
        None,  # 30 prior_year_stockholders_equity
        None,  # 31 prior_year_pretax_income
        None,  # 32 prior_year_interest_expense
        None,  # 33 prior_year_gross_profit
    )


_EV_METRICS = (2_000_000.0, 500_000.0, 3_000_000.0)  # (total_debt, total_cash, ebitda)


def _make_loader():
    loader = L.__new__(L)
    return loader


class _FakeCursor:
    def execute(self, query, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __enter__(self):
        return _FakeCursor()

    def __exit__(self, *exc):
        return False


@pytest.fixture(autouse=True)
def _mock_db(monkeypatch):
    # _compute_quality_metrics has a same-fiscal-year fallback query path (income tax/pretax
    # income lookup) that fires under some input combinations - under pytest's DB_NAME=
    # algo_trading test DB this returns real-but-different-shaped rows than the local dev DB,
    # producing a confusing KeyError far from any of these tests' actual point. Mock DatabaseContext
    # globally (same pattern as test_quality_metrics_completeness_floor_20260826.py) so every
    # test in this file is a pure unit test of _compute_quality_metrics's own logic, not
    # incidentally dependent on which DB happens to be configured.
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())


class TestMarginVolatilityScoreActuallyWired:
    """The dead-code bug (#2 above): margin_volatility_score must reflect the real
    margin_volatility parameter, not silently be None."""

    def test_margin_volatility_changes_quality_score(self):
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Technology"
        row = _row()

        low_vol = loader._compute_quality_metrics("STABLE", row, ev_metrics=_EV_METRICS, margin_volatility=2.0)
        high_vol = loader._compute_quality_metrics("VOLATILE", row, ev_metrics=_EV_METRICS, margin_volatility=25.0)

        assert low_vol["quality_score"] is not None
        assert high_vol["quality_score"] is not None
        # Lower margin volatility (more stable) must score >= higher volatility - if this ever
        # reads a not-yet-populated dict key again, both would come back identical (None
        # contribution renormalized away in both cases) instead of differing.
        assert low_vol["quality_score"] > high_vol["quality_score"]

    def test_universal_formula_matches_independently_derived_expected_value(self):
        # Full hand-computable case, all 8 inputs available, Technology sector (universal
        # 8-input branch). Expected value derived from the same curve breakpoints live in
        # _compute_quality_metrics, applied via _margin_curve - see module
        # docstring for why this isn't just copying one run's observed output.
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Technology"

        roe_curve = L._margin_curve(15.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)])
        roa_curve = L._margin_curve(10.0, [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
        roce_curve = L._margin_curve(15.0, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)])
        fcf_curve = L._margin_curve(8.0, [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)])
        gp_curve = L._margin_curve(53.333333333333336, [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)])
        d2e_score = max(0.0, min(100.0, 100.0 - (0.2 / 2.0) * 100.0))
        mv_score = 100.0 - L._margin_curve(10.0, [(5.0, 20.0), (15.0, 60.0), (30.0, 100.0)])
        at_curve = L._margin_curve(133.33333333333331, [(30.0, 40.0), (80.0, 75.0), (150.0, 100.0)])

        weighted_sum = (
            roe_curve * 11
            + roa_curve * 18
            + roce_curve * 18
            + fcf_curve * 15
            + d2e_score * 18
            + mv_score * 7
            + at_curve * 7
            + gp_curve * 7
        )
        expected = weighted_sum / 101.0

        metrics = loader._compute_quality_metrics("TECHCO", _row(), ev_metrics=_EV_METRICS, margin_volatility=10.0)

        assert metrics["quality_score"] == expected


class TestUniformFormulaAcrossSectors:
    """REWRITE 2026-09-07 ("best and brightest" scoring-methodology directive): the Financial
    Services/Real Estate two-cluster construction this class used to test was collapsed to the
    same flat 8-input weighted average every sector uses (see vqg_quality.py's REWRITE comment
    where that branch used to be) - published multi-factor methodology (Barra/AQR/Fama-French)
    has no per-sector aggregation shape, only per-sector metric substitution/z-score peer
    grouping (handled in update_quality_sector_neutral_scores(), not here). This Pass-1
    curve-based composite is now PROVISIONAL for every sector alike; these tests confirm every
    sector reaches the identical universal formula, not a different one.
    """

    def _expected_universal_score(self):
        roe_curve = L._margin_curve(15.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)])
        roa_curve = L._margin_curve(10.0, [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
        roce_curve = L._margin_curve(15.0, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)])
        fcf_curve = L._margin_curve(8.0, [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)])
        gp_curve = L._margin_curve(53.333333333333336, [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)])
        d2e_score = max(0.0, min(100.0, 100.0 - (0.2 / 2.0) * 100.0))
        mv_score = 100.0 - L._margin_curve(10.0, [(5.0, 20.0), (15.0, 60.0), (30.0, 100.0)])
        at_curve = L._margin_curve(133.33333333333331, [(30.0, 40.0), (80.0, 75.0), (150.0, 100.0)])

        weighted_sum = (
            roe_curve * 11
            + roa_curve * 18
            + roce_curve * 18
            + fcf_curve * 15
            + d2e_score * 18
            + mv_score * 7
            + at_curve * 7
            + gp_curve * 7
        )
        return weighted_sum / 101.0

    def test_real_estate_uses_the_same_universal_formula_as_technology(self):
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Real Estate"

        metrics = loader._compute_quality_metrics("REITCO", _row(), ev_metrics=_EV_METRICS, margin_volatility=10.0)

        assert metrics["quality_score"] == self._expected_universal_score()

    def test_financial_services_uses_the_same_universal_formula_as_technology(self):
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Financial Services"

        metrics = loader._compute_quality_metrics("BANKCO", _row(), ev_metrics=_EV_METRICS, margin_volatility=10.0)

        assert metrics["quality_score"] == self._expected_universal_score()

    def test_utilities_uses_the_same_universal_formula_as_technology(self):
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Utilities"

        metrics = loader._compute_quality_metrics("UTILCO", _row(), ev_metrics=_EV_METRICS, margin_volatility=10.0)

        assert metrics["quality_score"] == self._expected_universal_score()

    def test_unknown_or_missing_sector_also_uses_universal_formula(self):
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: None

        metrics = loader._compute_quality_metrics("UNKNOWNCO", _row(), ev_metrics=_EV_METRICS, margin_volatility=10.0)

        assert metrics["quality_score"] == self._expected_universal_score()

    def test_real_estate_missing_debt_and_volatility_still_scores_off_remaining_inputs(self):
        # debt_to_equity/roce_pct/margin_volatility unavailable - the universal formula's own
        # completeness floor (40% of 101) still clears off roe/roa/fcf_margin/asset_turnover/
        # gross_profitability alone, no sector-specific handling needed now that every sector
        # shares one formula.
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Real Estate"
        row = _row(long_term_debt=None)
        ev_metrics_no_debt = (None, 500_000.0, 3_000_000.0)  # (total_debt, total_cash, ebitda)

        metrics = loader._compute_quality_metrics("THINCO", row, ev_metrics=ev_metrics_no_debt, margin_volatility=None)

        assert metrics.get("debt_to_equity") is None
        assert metrics.get("margin_volatility") is None
        assert metrics.get("roce_pct") is None
        assert metrics.get("roe") is not None

        roe_curve = L._margin_curve(15.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)])
        roa_curve = L._margin_curve(10.0, [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
        fcf_curve = L._margin_curve(8.0, [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)])
        at_curve = L._margin_curve(133.33333333333331, [(30.0, 40.0), (80.0, 75.0), (150.0, 100.0)])
        gp_curve = L._margin_curve(53.333333333333336, [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)])
        expected = (roe_curve * 11 + roa_curve * 18 + fcf_curve * 15 + at_curve * 7 + gp_curve * 7) / (
            11 + 18 + 15 + 7 + 7
        )

        assert metrics["quality_score"] == expected
        assert metrics["quality_score_unavailable_reason"] is None

    def test_almost_nothing_available_reports_insufficient_completeness(self):
        # Genuine floor case: with everything nulled out, quality_score must be None.
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Real Estate"
        row = _row(
            stockholders_equity=None,
            total_assets=None,
            revenue=None,
            operating_income=None,
            cost_of_revenue=None,
            long_term_debt=None,
            net_income=None,
        )
        ev_metrics_empty = (None, None, None)

        metrics = loader._compute_quality_metrics("EMPTYCO", row, ev_metrics=ev_metrics_empty, margin_volatility=None)

        assert metrics.get("quality_score") is None
        assert metrics["quality_score_unavailable_reason"] == "insufficient_completeness"

    def test_debt_volatility_and_roce_clear_the_universal_floor(self):
        # net_income/total_assets/revenue nulled kills roe/roa/fcf_margin/gross_profitability/
        # asset_turnover, but roce_pct is independent of all three (it comes from
        # stockholders_equity/debt_for_roic/cash via invested_capital, untouched here) - so
        # debt_to_equity(18)+margin_volatility(7)+roce(18)=43 of the universal formula's 101
        # nominal weight clears its 40.0 floor. Under the old two-cluster architecture this
        # sector used to test, roce alone (1 of profitability_cluster's 5 inputs) failed that
        # cluster's own >=2/5 floor, so the composite came back None entirely - that
        # cluster-level gating no longer exists (see the class docstring), so this now scores.
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Financial Services"
        row = _row(net_income=None, total_assets=None, revenue=None)

        metrics = loader._compute_quality_metrics("SAFETYONLYCO", row, ev_metrics=_EV_METRICS, margin_volatility=10.0)

        assert metrics.get("debt_to_equity") is not None
        assert metrics.get("margin_volatility") is not None
        assert metrics.get("roce_pct") is not None
        assert metrics.get("roe") is None
        assert metrics.get("roa") is None
        assert metrics.get("fcf_margin") is None
        assert metrics.get("gross_profitability") is None

        roce_curve = L._margin_curve(15.0, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)])
        d2e_score = max(0.0, min(100.0, 100.0 - (0.2 / 2.0) * 100.0))
        mv_score = 100.0 - L._margin_curve(10.0, [(5.0, 20.0), (15.0, 60.0), (30.0, 100.0)])
        expected = (roce_curve * 18 + d2e_score * 18 + mv_score * 7) / (18 + 18 + 7)

        assert metrics["quality_score"] == expected
        assert metrics["quality_score_unavailable_reason"] is None


class TestGetSymbolSector:
    def test_caches_after_first_fetch(self):
        loader = _make_loader()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [("AAPL", "Technology"), ("JPM", "Financial Services")]
        # _get_symbol_sector lives in SectorIndustryCacheMixin (loaders/helpers/vqg_shared.py)
        # since the 20260908 extraction - patch DatabaseContext where it's actually called.
        with patch("loaders.helpers.vqg_shared.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = mock_cur

            assert loader._get_symbol_sector("AAPL") == "Technology"
            assert loader._get_symbol_sector("JPM") == "Financial Services"
            assert loader._get_symbol_sector("UNKNOWN") is None

        # Only one query for all 3 lookups - lazy-cached, not per-symbol.
        assert mock_ctx.call_count == 1

    def test_db_failure_fails_open_to_none(self):
        import psycopg2

        loader = _make_loader()
        with patch("loaders.helpers.vqg_shared.DatabaseContext") as mock_ctx:
            mock_ctx.side_effect = psycopg2.OperationalError("connection refused")

            assert loader._get_symbol_sector("AAPL") is None
