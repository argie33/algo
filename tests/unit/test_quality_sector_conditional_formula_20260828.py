"""Regression tests for two related Quality-pillar fixes (2026-08-28, goal session "figure out
the industry-best right formula" - see algo/research/quality_industry_leader_formula_comparison_
20260828.py for the full Fama-MacBeth evidence trail and MEMORY.md for the write-up):

1. SECTOR-CONDITIONAL FORMULA: Financial Services/Real Estate symbols now use a 7-input,
   two-cluster (profitability + safety) quality_score construction instead of the universal
   flat 8-input weighted average - asset_turnover_score is dropped for these two sectors only,
   confirmed via isolated testing to be the specific input responsible for their weaker Quality
   signal (Real Estate Spearman IC t=0.49 -> 2.35, Financial Services t=1.73 -> 3.31).

2. MARGIN VOLATILITY DEAD-CODE BUG: found by accident while building test #1's fixture -
   `margin_volatility_score` read `metrics.get("margin_volatility")` before that key was ever
   written into `metrics` (the write happens much later in the function), so it silently scored
   None for every single symbol despite being documented as a real, scored, 7%-weighted input.
   Fixed to read the `margin_volatility` parameter directly (the value the caller actually
   passed in). This affects ALL symbols, not just Financial Services/Real Estate.

Expected values below are independently derived using
`ValueQualityGrowthMetricsLoader._reconciliation_margin_curve` (the same standalone curve-score
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
        # _compute_quality_metrics, applied via _reconciliation_margin_curve - see module
        # docstring for why this isn't just copying one run's observed output.
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Technology"

        roe_curve = L._reconciliation_margin_curve(15.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)])
        roa_curve = L._reconciliation_margin_curve(10.0, [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
        roce_curve = L._reconciliation_margin_curve(15.0, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)])
        fcf_curve = L._reconciliation_margin_curve(8.0, [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)])
        gp_curve = L._reconciliation_margin_curve(53.333333333333336, [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)])
        d2e_score = max(0.0, min(100.0, 100.0 - (0.2 / 2.0) * 100.0))
        mv_score = 100.0 - L._reconciliation_margin_curve(10.0, [(5.0, 20.0), (15.0, 60.0), (30.0, 100.0)])
        at_curve = L._reconciliation_margin_curve(133.33333333333331, [(30.0, 40.0), (80.0, 75.0), (150.0, 100.0)])

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


class TestSectorConditionalFormula:
    """Financial Services/Real Estate use a 7-input, two-cluster construction that drops
    asset_turnover_score - everything else (universal formula, other sectors) is unchanged."""

    def _expected_cluster_score(self):
        roe_curve = L._reconciliation_margin_curve(15.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)])
        roa_curve = L._reconciliation_margin_curve(10.0, [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
        roce_curve = L._reconciliation_margin_curve(15.0, [(8.0, 40.0), (15.0, 75.0), (25.0, 100.0)])
        fcf_curve = L._reconciliation_margin_curve(8.0, [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)])
        gp_curve = L._reconciliation_margin_curve(53.333333333333336, [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)])
        d2e_score = max(0.0, min(100.0, 100.0 - (0.2 / 2.0) * 100.0))
        mv_score = 100.0 - L._reconciliation_margin_curve(10.0, [(5.0, 20.0), (15.0, 60.0), (30.0, 100.0)])

        profitability_cluster = (roe_curve + roa_curve + roce_curve + fcf_curve + gp_curve) / 5.0
        safety_cluster = (d2e_score + mv_score) / 2.0
        # WEIGHTS FIXED 2026-09-01: top-level cluster combination is now weighted by each
        # cluster's actual share of the universal branch's nominal weight (profitability 69 =
        # roe 11+roa 18+roce 18+fcf_margin 15+gross_profitability 7; safety 25 = debt_to_equity
        # 18+margin_volatility 7), not a flat 1.0/1.0 split - see that fix's own comment in
        # loaders/load_value_quality_growth_metrics.py for why (a flat split let a single thin
        # cluster like safety-only produce a full, undiscounted score - SBR/PBT/XP live-confirmed).
        return (profitability_cluster * 69.0 + safety_cluster * 25.0) / 94.0

    def test_real_estate_uses_cluster_formula_not_universal(self):
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Real Estate"

        metrics = loader._compute_quality_metrics("REITCO", _row(), ev_metrics=_EV_METRICS, margin_volatility=10.0)

        assert metrics["quality_score"] == self._expected_cluster_score()

    def test_financial_services_uses_cluster_formula_not_universal(self):
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Financial Services"

        metrics = loader._compute_quality_metrics("BANKCO", _row(), ev_metrics=_EV_METRICS, margin_volatility=10.0)

        assert metrics["quality_score"] == self._expected_cluster_score()

    def test_technology_still_uses_universal_8_input_formula(self):
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Technology"

        metrics = loader._compute_quality_metrics("TECHCO", _row(), ev_metrics=_EV_METRICS, margin_volatility=10.0)

        assert metrics["quality_score"] != self._expected_cluster_score()

    def test_unknown_or_missing_sector_falls_back_to_universal_formula(self):
        # _get_symbol_sector returning None (sector map fetch failed, or symbol not in
        # company_profile) must fail OPEN to the well-tested universal formula, not silently
        # misclassify or crash.
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: None

        metrics = loader._compute_quality_metrics("UNKNOWNCO", _row(), ev_metrics=_EV_METRICS, margin_volatility=10.0)

        assert metrics["quality_score"] != self._expected_cluster_score()

    def test_real_estate_missing_entire_safety_cluster_still_scores_off_profitability(self):
        # FIXED 2026-08-31 (goal: data-loading gap investigation): both debt_to_equity and
        # margin_volatility unavailable -> safety_cluster_score is None -> only 1 of 2
        # top-level cluster terms available. Previously required min_weight_pct=2.0 (BOTH
        # clusters present, 100% of the top-level weight) - far stricter than the universal
        # formula's own 40%-of-101 floor just below in the same function, and contradicting
        # this file's own "score what's available" convention (see the comment above
        # quality_components' construction) which only actually held for a PARTIAL cluster
        # gap, not a WHOLE one. Live-confirmed on real symbols (e.g. BAP/Credicorp, a real,
        # large, profitable Peruvian bank with 3/5 real profitability inputs but both safety
        # inputs missing) - 66 of 91 FS/RE symbols null on quality_score via
        # "insufficient_completeness" had exactly this shape: one well-populated cluster, one
        # entirely empty. Now: min_quality_weight_pct=1.0 (at least ONE cluster, which must
        # have already cleared its own internal completeness floor) - quality_score renders
        # off the profitability cluster alone, not silently discarded.
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Real Estate"
        # long_term_debt=None (row) + total_debt_ev=None (ev_metrics) removes debt_to_equity's
        # AND roce_pct's shared debt input without touching stockholders_equity (so roe stays
        # available) - margin_volatility=None removes the other safety-cluster input. Leaves
        # profitability_cluster with roe/roa/fcf_margin/gross_profitability (4/5, still well
        # above that cluster's own 40% floor) and safety_cluster completely empty (0/2).
        row = _row(long_term_debt=None)
        ev_metrics_no_debt = (None, 500_000.0, 3_000_000.0)  # (total_debt, total_cash, ebitda)

        metrics = loader._compute_quality_metrics("THINCO", row, ev_metrics=ev_metrics_no_debt, margin_volatility=None)

        assert metrics.get("debt_to_equity") is None
        assert metrics.get("margin_volatility") is None
        assert metrics.get("roce_pct") is None
        assert metrics.get("roe") is not None  # profitability cluster's other inputs intact

        roe_curve = L._reconciliation_margin_curve(15.0, [(10.0, 50.0), (20.0, 85.0), (40.0, 100.0)])
        roa_curve = L._reconciliation_margin_curve(10.0, [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
        fcf_curve = L._reconciliation_margin_curve(8.0, [(5.0, 40.0), (15.0, 75.0), (30.0, 100.0)])
        gp_curve = L._reconciliation_margin_curve(53.333333333333336, [(10.0, 40.0), (25.0, 75.0), (50.0, 100.0)])
        expected_profitability_only = (roe_curve + roa_curve + fcf_curve + gp_curve) / 4.0

        assert metrics["quality_score"] == expected_profitability_only
        assert metrics["quality_score_unavailable_reason"] is None

    def test_neither_cluster_populated_still_reports_insufficient_completeness(self):
        # Genuine floor case retained: if BOTH clusters come back empty, quality_score must
        # still be None - the fix above only stops discarding a real single-cluster signal,
        # it doesn't remove the floor entirely.
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

    def test_safety_cluster_alone_no_longer_produces_a_full_score(self):
        # REGRESSION for the bug the 2026-08-31 fix (min_quality_weight_pct 2.0->1.0, see the
        # test above) unintentionally reintroduced: a flat (cluster_score, 1.0)/(cluster_score,
        # 1.0) top-level split let the safety cluster ALONE - even fully populated with both its
        # own inputs - clear "at least one cluster present" and produce a full, undiscounted
        # quality_score off just debt_to_equity/margin_volatility, with zero profitability
        # signal at all. Live-confirmed on real symbols 2026-09-01: SBR (an Oil Royalty Trust,
        # vendor-classified "Financial Services" by legal/trust structure, not economics) scored
        # 97.13 off margin_volatility ALONE; PBT scored 87.52 the same way; XP (a real,
        # legitimately Financial-Services brokerage) scored 98.19, also off margin_volatility
        # alone. FIXED by weighting each cluster by its actual share of the universal branch's
        # nominal weight (profitability 69, safety 25, of 94 total) and gating on a proportional
        # 37.2 floor - safety alone (25 points) no longer clears it, matching the universal
        # branch's own "don't extrapolate a full score from a thin sample" principle.
        loader = _make_loader()
        loader._get_symbol_sector = lambda symbol: "Financial Services"
        # debt_to_equity = debt_for_roic / roic_stockholders_equity, where roic_stockholders_equity
        # comes straight from stockholders_equity and debt_for_roic prefers _EV_METRICS's
        # total_debt over row's long_term_debt - so stockholders_equity (and _EV_METRICS) must
        # stay real for debt_to_equity to survive while every profitability-cluster input dies:
        # net_income kills roe/roa, total_assets kills roa/roce/gross_profitability, revenue
        # kills fcf_margin (the same-fiscal-year DB fallback is neutralized by the autouse
        # _mock_db fixture returning no rows).
        row = _row(net_income=None, total_assets=None, revenue=None)

        metrics = loader._compute_quality_metrics("SAFETYONLYCO", row, ev_metrics=_EV_METRICS, margin_volatility=10.0)

        assert metrics.get("debt_to_equity") is not None
        assert metrics.get("margin_volatility") is not None
        assert metrics.get("roe") is None
        assert metrics.get("roa") is None
        assert metrics.get("fcf_margin") is None
        assert metrics.get("gross_profitability") is None
        assert metrics["quality_score"] is None
        assert metrics["quality_score_unavailable_reason"] == "insufficient_completeness"


class TestGetSymbolSector:
    def test_caches_after_first_fetch(self):
        loader = _make_loader()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [("AAPL", "Technology"), ("JPM", "Financial Services")]
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = mock_cur

            assert loader._get_symbol_sector("AAPL") == "Technology"
            assert loader._get_symbol_sector("JPM") == "Financial Services"
            assert loader._get_symbol_sector("UNKNOWN") is None

        # Only one query for all 3 lookups - lazy-cached, not per-symbol.
        assert mock_ctx.call_count == 1

    def test_db_failure_fails_open_to_none(self):
        import psycopg2

        loader = _make_loader()
        with patch("loaders.load_value_quality_growth_metrics.DatabaseContext") as mock_ctx:
            mock_ctx.side_effect = psycopg2.OperationalError("connection refused")

            assert loader._get_symbol_sector("AAPL") is None
