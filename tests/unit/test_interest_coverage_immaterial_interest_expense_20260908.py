"""Regression test (2026-09-08, goal session: cross-ratio symmetry check sibling to the same-day
forward_pe $0.10-floor fix): interest_coverage's |ratio| > 1000 bound alone didn't catch every
near-zero-interest_expense blowup - live-confirmed SXTP FY2025 interest_expense=$7,805 vs
operating_income=-$7,758,579 (0.1% ratio) -> interest_coverage=-994.05, comfortably under the
1000 ceiling. Same "immaterial denominator produces a numerically valid but meaningless ratio"
class as pe_ratio/pb_ratio/ps_ratio/forward_pe's own fixed-dollar floors, but interest_expense is
an aggregate dollar figure (not per-share), so uses a relative-to-operating_income materiality
floor instead (interest_expense < 1% of |operating_income| is immaterial), same cross-year
fallback-or-exclude path as the pre-existing |ratio| > 1000 bound.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self, fallback_rows):
        self._fallback_rows = fallback_rows
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "ais.net_income" in self._last_query and "ais.revenue" in self._last_query:
            return self._fallback_rows
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, fallback_rows):
        self._fallback_rows = fallback_rows

    def __enter__(self):
        return _FakeCursor(self._fallback_rows)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, fallback_rows):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(fallback_rows))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


def _quality_row(operating_income=None, interest_expense=None, pretax_income=None):
    # Same 33-column shape as test_interest_coverage_cross_year_fallback_20260905.py's fixture.
    return (
        100_000_000.0,  # 0 stockholders_equity
        200_000_000.0,  # 1 total_liabilities
        700_000_000.0,  # 2 total_assets
        50_000_000.0,  # 3 net_income
        None,  # 4 revenue
        operating_income,  # 5
        150_000_000.0,  # 6 current_assets
        100_000_000.0,  # 7 current_liabilities
        2025,  # 8 fiscal_year
        None,  # 9 inventory
        interest_expense,  # 10
        None,  # 11 shares_outstanding
        None,  # 12 cost_of_revenue
        None,  # 13 operating_cash_flow
        None,  # 14 free_cash_flow
        None,  # 15 dividends_paid
        None,  # 16 earnings_per_share
        None,  # 17 prior_year_eps
        None,  # 18 prior_year_revenue
        None,  # 19 gross_profit
        None,  # 20 long_term_debt
        None,  # 21 cash_and_equivalents
        None,  # 22 income_tax_expense
        pretax_income,  # 23
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


# SXTP-shaped anchor: operating_income=-7,758,579 / interest_expense=7,805 = -994.05x, UNDER the
# 1000 ceiling but interest_expense is only 0.1% of |operating_income| - immaterial.
_IMMATERIAL_KWARGS = {"operating_income": -7_758_579.0, "interest_expense": 7_805.0, "pretax_income": None}

# A normal, materially-sized pair: interest_expense is 20% of |operating_income| - well above the
# 1% materiality floor, must compute directly without touching the fallback path at all.
_MATERIAL_KWARGS = {"operating_income": 5_000_000.0, "interest_expense": 1_000_000.0, "pretax_income": None}

_PLAUSIBLE_FALLBACK_ROW = (8_000_000.0, 100_000_000.0, 50_000_000.0, 100_000_000.0, 5_000_000.0, 1_000_000.0)


class TestInterestCoverageImmaterialInterestExpense:
    def test_immaterial_interest_expense_under_ceiling_excluded(self, monkeypatch):
        loader = _make_loader(monkeypatch, [])
        row = _quality_row(**_IMMATERIAL_KWARGS)

        metrics = loader._compute_quality_metrics("SXTP", row, ev_metrics=None)

        assert metrics["interest_coverage"] is None
        assert metrics["interest_coverage_unavailable_reason"] == "implausible_ratio"

    def test_immaterial_interest_expense_uses_cross_year_fallback(self, monkeypatch):
        loader = _make_loader(monkeypatch, [_PLAUSIBLE_FALLBACK_ROW])
        row = _quality_row(**_IMMATERIAL_KWARGS)

        metrics = loader._compute_quality_metrics("SXTP", row, ev_metrics=None)

        assert metrics["interest_coverage"] == 5.0
        assert metrics.get("interest_coverage_unavailable_reason") is None

    def test_materially_sized_interest_expense_unaffected(self, monkeypatch):
        loader = _make_loader(monkeypatch, [])
        row = _quality_row(**_MATERIAL_KWARGS)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["interest_coverage"] == 5.0
        assert metrics.get("interest_coverage_unavailable_reason") is None

    # NOTE (2026-09-08): the sibling fix to _find_plausible_cross_year_ratio itself (so a
    # chronically-immaterial-interest_expense filer can't have the fallback re-select an
    # equally immaterial OLDER year) is NOT restored here - loaders/load_value_quality_
    # growth_metrics.py is already past the file-size ratchet's 2000-line hard ceiling with
    # pre-existing baseline drift (committed HEAD already exceeds its own recorded baseline
    # by ~18 lines from an earlier, unrelated commit), so no further growth can land there
    # without a real extraction/refactor first. Anchor-year floor above still closes the
    # common case (SOR live-reconfirmed). Tracked as a known residual gap, not forgotten.
