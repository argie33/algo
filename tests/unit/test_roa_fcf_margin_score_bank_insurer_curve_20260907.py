"""Regression test (2026-09-07, goal: stock_scores factor/composite sanity audit).

roa_score used the same industrial curve ((3.0,40),(8.0,80),(15.0,100)) for every sector, even
though a healthy depository bank's ROA (net_income/total_assets) is structurally ~1-1.5% by
construction (huge deposit-funded balance sheet denominator) - the industrial curve, calibrated
for asset-light industrial/services margins, floors real banks to a near-zero score regardless
of quality. Live-confirmed via JPM (real ROA=1.29%, quality_score=32.44 despite roe=15.74%/
strong fundamentals) and BAC/WFC/C/GS showing the same shape. This is the same "industrial curve
applied to a structurally-different balance-sheet-driven business" bug class as
debt_to_equity_score's bank/insurer curve fix (test_debt_to_equity_score_bank_insurer_curve_
20260907.py) - fixed the same way, branching on DEPOSITORY_BANK_INDUSTRIES/
INSURANCE_UNDERWRITER_INDUSTRIES.

fcf_margin_score is also excluded (not scored, but the raw fcf_margin metric is still
persisted) for depository banks specifically - free_cash_flow is dominated by loan/deposit
balance swings unrelated to real profitability (JPM live-confirmed fcf_margin=-81.00% in a
period BAC showed +11.15%, the same "deposit flows swamp cash flow" root cause
tie_out.py's cashflow_reconciliation check already exempts depository institutions from).
"""

from loaders.load_value_quality_growth_metrics import (
    DEPOSITORY_BANK_INDUSTRIES,
    INSURANCE_UNDERWRITER_INDUSTRIES,
    ValueQualityGrowthMetricsLoader,
)


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
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    return loader


def _bank_row(net_income, total_assets, free_cash_flow, revenue):
    # Same 34-column shape as test_debt_to_equity_score_bank_insurer_curve_20260907.py's fixture.
    return (
        1_000_000_000.0,  # 0 stockholders_equity
        10_000_000_000.0,  # 1 total_liabilities
        total_assets,  # 2 total_assets
        net_income,  # 3 net_income
        revenue,  # 4 revenue
        None,  # 5 operating_income
        None,  # 6 current_assets
        None,  # 7 current_liabilities
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


class TestRoaScoreBankInsurerCurve:
    def test_bank_low_absolute_roa_scores_well_above_industrial_floor(self, monkeypatch):
        # JPM-shaped: net_income=$142.9M on total_assets=$11B -> roa=1.30%. Under the old
        # industrial curve ((3.0,40),...) this scores ~17.3; the bank curve
        # ((0.5,40),(1.0,75),(1.5,100)) scores it near the top of the range instead.
        loader = _make_loader(monkeypatch)
        loader._industry_cache = {"BANKCO": next(iter(DEPOSITORY_BANK_INDUSTRIES))}
        metrics = loader._compute_quality_metrics(
            "BANKCO", _bank_row(143_000_000.0, 11_000_000_000.0, 150_000_000.0, 1_500_000_000.0), ev_metrics=None
        )
        assert metrics["roa"] == round(143_000_000.0 / 11_000_000_000.0 * 100, 2) == 1.3
        old_industrial_score = loader._margin_curve(1.3, [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)])
        new_bank_score = loader._margin_curve(1.3, [(0.5, 40.0), (1.0, 75.0), (1.5, 100.0)])
        assert new_bank_score > old_industrial_score
        assert new_bank_score == 90.0  # 75 + (1.3-1.0)/(1.5-1.0)*(100-75)

    def test_insurer_roa_uses_its_own_curve(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        loader._industry_cache = {"INSURECO": next(iter(INSURANCE_UNDERWRITER_INDUSTRIES))}
        metrics = loader._compute_quality_metrics(
            "INSURECO", _bank_row(440_000_000.0, 11_000_000_000.0, 150_000_000.0, 1_500_000_000.0), ev_metrics=None
        )
        assert metrics["roa"] == 4.0
        # (1.0,40),(2.5,75),(5.0,100) -> 4.0 interpolates between (2.5,75) and (5.0,100)
        expected = 75.0 + (4.0 - 2.5) / (5.0 - 2.5) * (100.0 - 75.0)
        assert loader._margin_curve(4.0, [(1.0, 40.0), (2.5, 75.0), (5.0, 100.0)]) == expected

    def test_industrial_symbol_roa_curve_unchanged(self, monkeypatch):
        loader = _make_loader(monkeypatch)
        loader._industry_cache = {"INDCO": "Some Industrial Industry"}
        metrics = loader._compute_quality_metrics(
            "INDCO", _bank_row(330_000_000.0, 11_000_000_000.0, 150_000_000.0, 1_500_000_000.0), ev_metrics=None
        )
        assert metrics["roa"] == 3.0
        assert loader._margin_curve(3.0, [(3.0, 40.0), (8.0, 80.0), (15.0, 100.0)]) == 40.0


class TestFcfMarginScoreDepositoryBankExclusion:
    def test_bank_fcf_margin_value_persisted_but_not_used_in_quality_components(self, monkeypatch):
        import loaders.load_value_quality_growth_metrics as mod

        loader = _make_loader(monkeypatch)
        loader._industry_cache = {"BANKCO": next(iter(DEPOSITORY_BANK_INDUSTRIES))}
        loader._sector_cache = {"BANKCO": "Financial Services"}

        captured_calls = []
        original_weighted_avg = mod.ValueQualityGrowthMetricsLoader.__dict__["_weighted_avg"].__func__

        def spy_weighted_avg(components, min_weight_pct=0.0):
            captured_calls.append(components)
            return original_weighted_avg(components, min_weight_pct=min_weight_pct)

        monkeypatch.setattr(mod.ValueQualityGrowthMetricsLoader, "_weighted_avg", staticmethod(spy_weighted_avg))

        # deeply negative fcf_margin, JPM-shaped: fcf=-$1.2B on revenue=$1.5B -> -80%
        metrics = loader._compute_quality_metrics(
            "BANKCO", _bank_row(142_857_000.0, 11_000_000_000.0, -1_200_000_000.0, 1_500_000_000.0), ev_metrics=None
        )

        # raw fcf_margin still computed/persisted
        assert metrics["fcf_margin"] is not None
        assert metrics["fcf_margin"] < 0

        # profitability_cluster_score call (Financial Services branch: 5 components
        # [roe, roa, roce, fcf_margin, gross_profitability]) - the fcf_margin_score component
        # (index 3) must be None, not a punishing near-zero score.
        profitability_cluster_calls = [c for c in captured_calls if len(c) == 5]
        assert len(profitability_cluster_calls) == 1
        fcf_margin_score = profitability_cluster_calls[0][3][0]
        assert fcf_margin_score is None

    def test_non_bank_fcf_margin_still_scored(self, monkeypatch):
        import loaders.load_value_quality_growth_metrics as mod

        loader = _make_loader(monkeypatch)
        loader._industry_cache = {"INDCO": "Some Industrial Industry"}
        loader._sector_cache = {"INDCO": "Technology"}

        captured_calls = []
        original_weighted_avg = mod.ValueQualityGrowthMetricsLoader.__dict__["_weighted_avg"].__func__

        def spy_weighted_avg(components, min_weight_pct=0.0):
            captured_calls.append(components)
            return original_weighted_avg(components, min_weight_pct=min_weight_pct)

        monkeypatch.setattr(mod.ValueQualityGrowthMetricsLoader, "_weighted_avg", staticmethod(spy_weighted_avg))

        loader._compute_quality_metrics(
            "INDCO", _bank_row(150_000_000.0, 11_000_000_000.0, 150_000_000.0, 1_500_000_000.0), ev_metrics=None
        )

        # Universal (non-FS/RE) branch: quality_components has 8 entries, fcf_margin_score
        # at index 3.
        universal_calls = [c for c in captured_calls if len(c) == 8]
        assert len(universal_calls) == 1
        fcf_margin_score = universal_calls[0][3][0]
        assert fcf_margin_score is not None
