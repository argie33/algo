"""Regression test (2026-09-11, goal: "SEC/XBRL missing data under 200" push): pe_ratio's
reason chain already checks RIC status right before the generic fallback (2026-09-06 fix,
whose own comment flags blank-check SPACs as "same fact" but never wires the gate in) - a
blank-check SPAC (SIC 6770, pre-merger shell) has no real operating business and no EPS
concept to tag, same structural fact as a RIC. Live-confirmed via BPAC (Bullpen Parlay
Acquisition Corp): real net_income on file, zero revenue, no EPS ever tagged, pe_ratio fell
through every branch to the generic "missing_sec_data" catch-all instead of the correct
"Legitimate / not applicable" bucket (fcf_yield/ev_ebitda already get this right for the same
symbol class - see test_fcf_yield_blank_check_recategorize_20260906.py).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader() -> ValueQualityGrowthMetricsLoader:
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _EpsQueryCursor:
    """Same shape as test_pe_ratio_never_tagged_eps_reason_20260902.py's helper: returns a
    real, positive, in-bounds EPS for the SELECT earnings_per_share query (so none of the
    volatility/tax/implausible/never-tagged/anchor-year branches above the new blank-check
    gate fire), empty for every other query this cascade runs."""

    def __init__(self, eps_row):
        self._eps_row = eps_row

    def execute(self, query, params=None):
        self.last_query = query

    def fetchone(self):
        if self.last_query and "SELECT earnings_per_share" in self.last_query:
            return self._eps_row
        return None

    def fetchall(self):
        return []


def _run(monkeypatch, symbol, blank_check_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    loader = _make_loader()
    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _DbCtx())
    monkeypatch.setattr(loader, "_get_registered_investment_company_symbols", lambda: frozenset(), raising=False)
    monkeypatch.setattr(loader, "_get_eps_absent_from_anchor_year_symbols", lambda: frozenset(), raising=False)
    monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: blank_check_symbols, raising=False)
    monkeypatch.setattr(loader, "_fetch_ttm_eps_from_quarterly", lambda s: None, raising=False)
    return loader._build_value_metrics(
        symbol,
        _FakeSecValRow({"pe_ratio": None, "pb_ratio": 3.3, "current_price": 10.19, "market_cap": 8_000_000.0}),
    )


class _DbCtx:
    def __enter__(self):
        return _EpsQueryCursor(eps_row=(2.5,))

    def __exit__(self, *exc):
        return False


class TestPeRatioBlankCheckRecategorize:
    def test_blank_check_symbol_reports_no_revenue_reported(self, monkeypatch):
        result = _run(monkeypatch, "BPAC", blank_check_symbols=frozenset({"BPAC"}))
        assert result["pe_ratio_unavailable_reason"] == "no_revenue_reported"

    def test_non_blank_check_keeps_generic_missing_sec_data_reason(self, monkeypatch):
        result = _run(monkeypatch, "NORMALCO", blank_check_symbols=frozenset({"BPAC"}))
        assert result["pe_ratio_unavailable_reason"] == "missing_sec_data"
