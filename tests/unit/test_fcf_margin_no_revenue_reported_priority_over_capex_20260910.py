"""Regression test (2026-09-10, goal: "under 500" missing-XBRL push): fcf_margin's reason
chain already checked _get_no_recent_revenue_symbols()/_get_never_tagged_revenue_symbols()
(the generic "no_revenue_reported" gate), but positioned it AFTER
"capex_never_tagged_in_recent_filings" - so a symbol matching BOTH (a pre-revenue company
with real, negative operating_cash_flow but no revenue and no capex - the common shape for
clinical-stage pharma/biotech, e.g. live-confirmed ACTU/ACXP/ADIL/ANTX/ANVS/AVBP/AVXL/BIVI/
GALT and ~35 similar tickers) landed on "capex_never_tagged_in_recent_filings" ("Missing
SEC/XBRL data") even though revenue - not capex - is the actual binding constraint: fcf_margin
= free_cash_flow / revenue is mathematically undefined without revenue regardless of whether
capex/FCF could ever be computed. "no_revenue_reported" ("Legitimate / not applicable") is
the more accurate label and must win when both gates match.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(net_income=None, revenue=None, free_cash_flow=None):
    row = [None] * 34
    row[2] = 700_000_000.0  # total_assets
    row[3] = net_income
    row[4] = revenue
    row[8] = 2025  # fiscal_year
    row[11] = 25_000_000.0  # shares_outstanding
    row[14] = free_cash_flow
    return row


class _FakeCursor:
    def __init__(self, no_recent_capex_symbols, never_tagged_revenue_symbols):
        self._no_recent_capex = no_recent_capex_symbols
        self._never_tagged_revenue = never_tagged_revenue_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "COUNT(capex)" in self._last_query:
            return [(s,) for s in self._no_recent_capex]
        if "ELSE revenue END" in self._last_query:
            return [(s,) for s in self._never_tagged_revenue]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_capex_symbols=frozenset(), never_tagged_revenue_symbols=frozenset()):
        self._no_recent_capex = no_recent_capex_symbols
        self._never_tagged_revenue = never_tagged_revenue_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_capex, self._never_tagged_revenue)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, no_recent_capex_symbols=frozenset(), never_tagged_revenue_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(
        mod,
        "DatabaseContext",
        _FakeDatabaseContext(no_recent_capex_symbols, never_tagged_revenue_symbols),
    )
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestFcfMarginNoRevenueReportedPriorityOverCapex:
    def test_pre_revenue_symbol_matching_both_gates_gets_no_revenue_reported(self, monkeypatch):
        # PREBIO: real negative operating_cash_flow (via net_income proxy in this simplified
        # fixture), no revenue ever tagged, no capex ever tagged - matches both gates.
        loader = _make_loader(
            monkeypatch,
            no_recent_capex_symbols=frozenset({"PREBIO"}),
            never_tagged_revenue_symbols=frozenset({"PREBIO"}),
        )
        row = _quality_row(net_income=-20_000_000.0, revenue=None, free_cash_flow=None)

        metrics = loader._compute_quality_metrics("PREBIO", row, ev_metrics=None)

        assert metrics["fcf_margin"] is None
        assert metrics["fcf_margin_unavailable_reason"] == "no_revenue_reported", (
            f"fcf_margin_unavailable_reason was {metrics['fcf_margin_unavailable_reason']!r}, "
            "expected no_revenue_reported to win over capex_never_tagged_in_recent_filings"
        )

    def test_real_revenue_symbol_matching_only_capex_gate_keeps_capex_reason(self, monkeypatch):
        # A real operating company (has revenue) that only matches the capex gate must keep
        # the specific capex reason - this reorder must not regress that population.
        loader = _make_loader(
            monkeypatch,
            no_recent_capex_symbols=frozenset({"REALCO"}),
            never_tagged_revenue_symbols=frozenset(),
        )
        row = _quality_row(net_income=50_000_000.0, revenue=500_000_000.0, free_cash_flow=None)

        metrics = loader._compute_quality_metrics("REALCO", row, ev_metrics=None)

        assert metrics["fcf_margin_unavailable_reason"] == "capex_never_tagged_in_recent_filings"
