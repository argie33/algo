"""Regression test (2026-09-05, pre-live-money safety audit): roe_score had no negative-equity
guard even though debt_to_equity_score already floors negative D/E to 0 for the identical
reason (see loaders/helpers/vqg_quality.py's "floors to 0 rather than inverting into a
spuriously high score" comment on debt_to_equity_score).

_ratio_with_implausible_fallback only rejects denominator == 0 for ROE/ROA (unlike
asset_turnover, which passes denominator_must_be_positive=True). So a distressed company with
BOTH negative net_income and negative stockholders_equity computes a POSITIVE ROE
(e.g. -$50M / -$500M * 100 = 10.0%) that clears the |x|>1000 implausibility bound and looks like
a real, moderately-good margin to _margin_curve - which only floors genuinely negative values to
0, not this double-negative sign trap. That fed roe_score (11% of quality_score) as if a
negative-book-value company were a profitable one.

Fixed by flooring roe_score (and roa_score, for total_assets<=0 completeness) to 0.0 whenever
the denominator itself is non-positive, regardless of the computed ratio's sign.
"""

from loaders.helpers.vqg_quality_batch import QualityBatchMixin
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


def _distressed_row():
    # Same 34-column shape as test_quality_metrics_completeness_floor_20260826.py's fixture.
    # ROE (11%) + ROA (18%) + FCF Margin (15%) = 44%, clears the 40% completeness floor.
    return (
        -500_000_000.0,  # 0 stockholders_equity (negative book equity)
        900_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets (positive - ROA's own sign trap doesn't apply here)
        -50_000_000.0,  # 3 net_income (a real loss)
        1_000_000_000.0,  # 4 revenue
        None,  # 5 operating_income
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        None,  # 10 interest_expense
        None,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        100_000_000.0,  # 14 free_cash_flow
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


class TestQualityRoeNegativeEquityScoreFloor:
    def test_negative_over_negative_roe_ratio_is_still_positive(self, monkeypatch):
        # Confirms the sign trap is real: the raw ratio itself is unguarded and reads as a
        # plausible-looking positive 10.0%, not None/implausible.
        loader = _make_loader(monkeypatch)
        metrics = loader._compute_quality_metrics("DISTRESSEDCO", _distressed_row(), ev_metrics=None)

        assert metrics["roe"] == 10.0

    def test_negative_equity_floors_roe_score_component_to_zero(self, monkeypatch):
        # Isolates the actual quality_score composition call (8 components, the universal
        # non-financial-sector branch) and asserts the roe_score fed into it is exactly 0.0 -
        # not the ~50 _margin_curve([(10.0, 50.0), ...]) would otherwise give a genuine +10%
        # value, which is what metrics["roe"] equals here (see previous test).
        loader = _make_loader(monkeypatch)
        import loaders.load_value_quality_growth_metrics as mod

        captured_calls = []
        original_weighted_avg = QualityBatchMixin.__dict__["_weighted_avg"].__func__

        def spy_weighted_avg(components, min_weight_pct=0.0):
            captured_calls.append(components)
            return original_weighted_avg(components, min_weight_pct=min_weight_pct)

        monkeypatch.setattr(mod.ValueQualityGrowthMetricsLoader, "_weighted_avg", staticmethod(spy_weighted_avg))

        loader._compute_quality_metrics("DISTRESSEDCO", _distressed_row(), ev_metrics=None)

        quality_composition_call = next(c for c in captured_calls if len(c) == 8)
        roe_score = quality_composition_call[0][0]
        assert roe_score == 0.0
