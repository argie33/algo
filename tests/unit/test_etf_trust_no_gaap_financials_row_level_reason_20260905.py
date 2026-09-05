"""Regression test: `etf_symbols`-registered physical commodity/currency/crypto trusts (GLD,
SLV, IAU, GBTC, ETHE, the FXA-class currency trusts, ...) file a "Statement of Assets and
Liabilities" with no GAAP stockholders_equity concept, so the row-level "all core ratios
missing" early return must recognize them via _get_etf_trust_no_stockholders_equity_symbols()
and stamp "etf_trust_no_gaap_financials" (a "Legitimate / not applicable" reason) instead of
falling through to the generic "missing_sec_data"/"no_recent_balance_sheet_data_reported"
buckets both counted as "Missing SEC/XBRL data" in /api/scores/coverage.

Live-verified 2026-09-05 (goal session: "SEC/XBRL missing data to zero" sweep): 32 universe
`etf_symbols` tickers hit this exact shape.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _empty_quality_row(fiscal_year=2024):
    # 34-column shape (index 33 = prior_year_gross_profit) - everything None except fiscal_year,
    # so every one of the 7 core ratios comes out None and the row-level early return fires.
    row = [None] * 34
    row[8] = fiscal_year
    return row


class _FakeCursor:
    def __init__(self, etf_trust_symbols):
        self._etf_trust_symbols = etf_trust_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "etf_symbols" in self._last_query:
            return [(s,) for s in self._etf_trust_symbols]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, etf_trust_symbols=frozenset()):
        self._etf_trust_symbols = etf_trust_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._etf_trust_symbols)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, etf_trust_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(etf_trust_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestEtfTrustNoGaapFinancialsRowLevelReason:
    def test_etf_trust_symbol_gets_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, etf_trust_symbols=frozenset({"GLD"}))

        metrics = loader._compute_quality_metrics("GLD", _empty_quality_row(), ev_metrics=None)

        assert metrics["data_unavailable"] is True
        assert metrics["reason"] == "etf_trust_no_gaap_financials"
        # Propagates to every field, not just the 7 checked in the early-return condition.
        assert metrics["roe_unavailable_reason"] == "etf_trust_no_gaap_financials"
        assert metrics["debt_to_equity_unavailable_reason"] == "etf_trust_no_gaap_financials"
        assert metrics["gross_profitability_unavailable_reason"] == "etf_trust_no_gaap_financials"

    def test_symbol_not_in_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, etf_trust_symbols=frozenset({"GLD"}))

        metrics = loader._compute_quality_metrics("NORMALCO", _empty_quality_row(), ev_metrics=None)

        assert metrics["data_unavailable"] is True
        assert metrics["reason"] == "missing_sec_data"
        assert metrics["roe_unavailable_reason"] == "missing_sec_data"
