"""Regression test: a physical commodity/currency/crypto trust (GLD/GLDM/IAU/GBTC/BITW/the
FXA-class currency trusts/WEAT/TAGS-class commodity-pool ETFs - see
_get_etf_trust_no_stockholders_equity_symbols()'s own docstring) has no CapitalExpenditures
XBRL concept either (it holds bullion/currency/crypto, not PP&E), so fcf_margin/
fcf_to_net_income's capex dependency lands on "capex_never_tagged_in_recent_filings" - but
that reason was never added to `_etf_trust_broad_source_reasons`, and fcf_margin/
fcf_to_net_income were never added to `_etf_trust_broad_recategorize_fields`, so the
recategorization loop that correctly relabels total_cash/interest_coverage/etc for this exact
population never fired for these two fields - same "fix landed at one call site, never wired
into the sibling" gap class as test_fcf_margin_capex_never_tagged_reason_20260905.py's own
AIG case.

Live-confirmed 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep) via 4 active-universe
etf_symbols tickers (BITW, GLDM, TAGS, WEAT) stuck on "capex_never_tagged_in_recent_filings"
(Missing SEC/XBRL data) for fcf_margin and/or fcf_to_net_income instead of
"etf_trust_no_gaap_financials" (Legitimate / not applicable) - the same relabel their
total_cash/interest_coverage/etc siblings already correctly get in this exact code path.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(net_income=50_000_000.0, revenue=500_000_000.0, free_cash_flow=None):
    # Real total_assets/total_liabilities/current_assets/current_liabilities so current_ratio/
    # quick_ratio/gross_margin etc compute normally - only stockholders_equity is absent,
    # exactly the "Statement of Assets and Liabilities" shape these trusts file - so the row
    # does NOT hit the whole-row "every core ratio is None" early return, and instead falls
    # through to the per-field broad-recategorize loop this fix targets.
    row = [None] * 34
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = 700_000_000.0  # total_assets
    row[3] = net_income
    row[4] = revenue
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[14] = free_cash_flow
    return row


class _FakeCursor:
    def __init__(self, etf_trust_symbols, no_recent_capex_symbols):
        self._etf_trust_symbols = etf_trust_symbols
        self._no_recent_capex = no_recent_capex_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "etf_symbols" in self._last_query:
            return [(s,) for s in self._etf_trust_symbols]
        if "COUNT(capex)" in self._last_query:
            return [(s,) for s in self._no_recent_capex]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, etf_trust_symbols=frozenset(), no_recent_capex_symbols=frozenset()):
        self._etf_trust_symbols = etf_trust_symbols
        self._no_recent_capex = no_recent_capex_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._etf_trust_symbols, self._no_recent_capex)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, etf_trust_symbols=frozenset(), no_recent_capex_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(etf_trust_symbols, no_recent_capex_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestEtfTrustFcfMarginCapexReasonRecategorized:
    def test_etf_trust_symbol_recategorizes_fcf_margin(self, monkeypatch):
        loader = _make_loader(
            monkeypatch, etf_trust_symbols=frozenset({"GLDM"}), no_recent_capex_symbols=frozenset({"GLDM"})
        )
        row = _quality_row(free_cash_flow=None)

        metrics = loader._compute_quality_metrics("GLDM", row, ev_metrics=None)

        assert metrics["fcf_margin"] is None
        assert metrics["fcf_margin_unavailable_reason"] == "etf_trust_no_gaap_financials"
        assert metrics["fcf_to_net_income_unavailable_reason"] == "etf_trust_no_gaap_financials"

    def test_non_etf_trust_symbol_keeps_specific_capex_reason(self, monkeypatch):
        loader = _make_loader(
            monkeypatch, etf_trust_symbols=frozenset({"GLDM"}), no_recent_capex_symbols=frozenset({"AIG"})
        )
        row = _quality_row(free_cash_flow=None)

        metrics = loader._compute_quality_metrics("AIG", row, ev_metrics=None)

        # Not in the etf_trust gate, so the un-recategorized reason from the sibling fix
        # (test_fcf_margin_capex_never_tagged_reason_20260905.py) must still apply unchanged.
        assert metrics["fcf_margin_unavailable_reason"] == "capex_never_tagged_in_recent_filings"

    def test_real_fcf_margin_still_computes_normally_for_etf_trust_symbol(self, monkeypatch):
        loader = _make_loader(
            monkeypatch, etf_trust_symbols=frozenset({"GLDM"}), no_recent_capex_symbols=frozenset({"GLDM"})
        )
        row = _quality_row(free_cash_flow=60_000_000.0)

        metrics = loader._compute_quality_metrics("GLDM", row, ev_metrics=None)

        assert metrics["fcf_margin"] is not None
        assert metrics.get("fcf_margin_unavailable_reason") is None
