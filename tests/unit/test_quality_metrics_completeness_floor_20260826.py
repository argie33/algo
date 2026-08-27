"""Regression test (2026-08-26, quality-completeness pass): renormalizing quality_score's
weighted average over whichever components happen to be available let a single extreme raw
ratio drive the score to 100.00 when only 1-3 of the composite's 8 components were present.

Live-verified: 8 of 5191 symbols (ASA, BAR, BSEM, CRT, NRP, NRT, PBT, SBR - mostly oil/gas
royalty trusts with atypical capital structures, e.g. PBT/SBR's ROA of 761%/961%) hit
quality_score=100.00 from only 18-38% of the composite's total weight. Worse, GOVERNANCE's
70% data-completeness trading gate did NOT catch these - stock_scores.data_completeness only
checks whether quality_score is a real float, not how much of its own composite backed it, so
6 of the 8 were live-eligible for trading (data_completeness>=99.99%, data_unavailable=False).

Fixed with a completeness floor on the quality composite itself (_weighted_avg's min_weight_pct):
below 40% available weight (set just above NRP's 38%, the largest available-weight case found
live), quality_score is None with reason "insufficient_completeness" instead of a thin-sample
extrapolation - same "honest incomplete data, not fallback" pattern as this file's other
*_unavailable_reason fields.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


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


def _make_loader(monkeypatch):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(
    stockholders_equity=None,
    revenue=None,
    operating_income=None,
    free_cash_flow=None,
):
    # Same 34-column shape as test_quality_metrics_implausible_ratio_reason.py's fixture.
    return (
        stockholders_equity,  # 0
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        revenue,  # 4
        operating_income,  # 5
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        free_cash_flow,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
        None,  # 20 long_term_debt
        None,  # 21 cash_and_equivalents
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


class TestQualityScoreCompletenessFloor:
    def test_single_component_below_floor_reports_insufficient_completeness(self, monkeypatch):
        # Only ROA available (18% weight, matches the live PBT/SBR case) - below the 40% floor.
        loader = _make_loader(monkeypatch)
        row = _quality_row()  # net_income + total_assets only -> roa=7.14%

        metrics = loader._compute_quality_metrics("PBTLIKE", row, ev_metrics=None)

        assert metrics["roa"] is not None
        assert metrics.get("quality_score") is None
        assert metrics["quality_score_unavailable_reason"] == "insufficient_completeness"

    def test_two_components_still_below_floor_reports_insufficient_completeness(self, monkeypatch):
        # ROE + ROA available (11% + 18% = 29%, matches the live ASA/CRT case) - still below 40%.
        loader = _make_loader(monkeypatch)
        row = _quality_row(stockholders_equity=500_000_000.0)

        metrics = loader._compute_quality_metrics("ASALIKE", row, ev_metrics=None)

        assert metrics["roe"] is not None
        assert metrics["roa"] is not None
        assert metrics.get("quality_score") is None
        assert metrics["quality_score_unavailable_reason"] == "insufficient_completeness"

    def test_three_components_clearing_floor_produces_real_score(self, monkeypatch):
        # ROE + ROA + FCF Margin available (11% + 18% + 15% = 44%) - clears the 40% floor.
        loader = _make_loader(monkeypatch)
        row = _quality_row(
            stockholders_equity=500_000_000.0,
            revenue=1_000_000_000.0,
            free_cash_flow=100_000_000.0,
        )

        metrics = loader._compute_quality_metrics("REALSCORECO", row, ev_metrics=None)

        assert metrics["fcf_margin"] is not None
        assert metrics.get("quality_score") is not None
        assert 0.0 <= metrics["quality_score"] <= 100.0
        assert metrics["quality_score_unavailable_reason"] is None

    def test_zero_components_available_reports_insufficient_completeness(self, monkeypatch):
        # FIXED 2026-08-27 (goal: "get all the data for all the inputs" data-completeness
        # sweep): the original `0 < available_quality_weight < min_quality_weight_pct` gate
        # excluded exactly this case - zero components available - so it fell through to the
        # `else` branch and got reason=None instead of "insufficient_completeness", the only
        # one of the three outcomes (full score / partial-below-floor / nothing-at-all) with
        # no explanation. Live-confirmed 20 universe symbols (e.g. IBN, YICC, APMC) all-NULL
        # across every one of the 8 quality components.
        loader = _make_loader(monkeypatch)
        row = _quality_row()  # no stockholders_equity/revenue/operating_income/free_cash_flow
        # Override even the always-present net_income/total_assets inputs so ROA can't compute.
        row = tuple(None if i in (1, 2, 3) else v for i, v in enumerate(row))

        metrics = loader._compute_quality_metrics("NODATACO", row, ev_metrics=None)

        assert metrics.get("quality_score") is None
        assert metrics["quality_score_unavailable_reason"] == "insufficient_completeness"
