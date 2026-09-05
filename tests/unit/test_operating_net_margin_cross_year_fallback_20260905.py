"""Regression test (2026-09-05, "SEC/XBRL missing data to zero" goal session): operating_margin
and net_margin's |ratio| > 1000 implausible-value bound had no cross-year fallback, unlike
roe/roa/asset_turnover/roic_pct/roce_pct (see `_find_plausible_cross_year_ratio`'s docstring).
Live DB audit found these two buckets are the LARGEST implausible_ratio residuals in
quality_metrics (241 operating_margin, 246 net_margin - larger than roic_pct's 176), yet neither
metric had ever been wired to the fallback pattern used for the smaller-count metrics.

`_find_plausible_cross_year_ratio` already computes net_income/revenue and (now) also
operating_income/revenue or */total_assets pairs, reusing the exact same same-year-coherent-pair
search as ROE/ROA - no new query shape, just a new `operating_income` column and wiring at the
two margin call sites.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


class _FakeCursor:
    def __init__(self, fallback_rows):
        self._fallback_rows = fallback_rows
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        # Other DB calls made during _compute_quality_metrics (symbol-gate lookups, etc.)
        # share this same fake DatabaseContext - only the cross-year fallback's own query
        # should see the crafted fallback row.
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


def _quality_row(
    stockholders_equity=100_000_000.0,
    total_assets=700_000_000.0,
    net_income=50_000_000.0,
    revenue=None,
    operating_income=None,
):
    # Same 33-column shape as test_quality_metrics_implausible_ratio_reason.py's fixture.
    return (
        stockholders_equity,  # 0
        200_000_000.0,  # 1 total_liabilities
        total_assets,  # 2
        net_income,  # 3
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
        None,  # 14 free_cash_flow
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


# Anchor: operating_income=35M / revenue=987K -> 3546% (same anchor as
# test_quality_metrics_implausible_ratio_reason.py's KARO operating_margin case).
_OPERATING_MARGIN_ANCHOR_KWARGS = {"operating_income": 35_000_000.0, "revenue": 987_000.0}

# Anchor: net_income=50M / revenue=987K -> 5067% (same anchor as that file's KARO net_margin case).
_NET_MARGIN_ANCHOR_KWARGS = {"revenue": 987_000.0}

# Older fiscal year, plausible pair for either margin: net_income=8M, total_assets=100M (unused),
# stockholders_equity=50M (unused), revenue=100M, operating_income=12M.
# operating_margin fallback ratio = 12M/100M*100 = 12% - plausible.
# net_margin fallback ratio = 8M/100M*100 = 8% - plausible.
_PLAUSIBLE_FALLBACK_ROW = (8_000_000.0, 100_000_000.0, 50_000_000.0, 100_000_000.0, 12_000_000.0)


class TestOperatingNetMarginCrossYearFallback:
    def test_operating_margin_uses_plausible_cross_year_fallback(self, monkeypatch):
        loader = _make_loader(monkeypatch, [_PLAUSIBLE_FALLBACK_ROW])
        row = _quality_row(**_OPERATING_MARGIN_ANCHOR_KWARGS)

        metrics = loader._compute_quality_metrics("KARO", row, ev_metrics=None)

        assert metrics["operating_margin"] == 12.0
        assert metrics.get("operating_margin_unavailable_reason") is None

    def test_operating_margin_falls_through_to_implausible_when_no_fallback_qualifies(self, monkeypatch):
        loader = _make_loader(monkeypatch, [])
        row = _quality_row(**_OPERATING_MARGIN_ANCHOR_KWARGS)

        metrics = loader._compute_quality_metrics("KARO", row, ev_metrics=None)

        assert metrics["operating_margin"] is None
        assert metrics["operating_margin_unavailable_reason"] == "implausible_ratio"

    def test_net_margin_uses_plausible_cross_year_fallback(self, monkeypatch):
        loader = _make_loader(monkeypatch, [_PLAUSIBLE_FALLBACK_ROW])
        row = _quality_row(**_NET_MARGIN_ANCHOR_KWARGS)

        metrics = loader._compute_quality_metrics("KARO", row, ev_metrics=None)

        assert metrics["net_margin"] == 8.0
        assert metrics.get("net_margin_unavailable_reason") is None

    def test_net_margin_falls_through_to_implausible_when_no_fallback_qualifies(self, monkeypatch):
        loader = _make_loader(monkeypatch, [])
        row = _quality_row(**_NET_MARGIN_ANCHOR_KWARGS)

        metrics = loader._compute_quality_metrics("KARO", row, ev_metrics=None)

        assert metrics["net_margin"] is None
        assert metrics["net_margin_unavailable_reason"] == "implausible_ratio"
