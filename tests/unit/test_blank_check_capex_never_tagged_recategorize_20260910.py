"""Regression test (2026-09-10, goal: "under 500" missing-XBRL push): a pre-merger
blank-check SPAC (SIC 6770) that ALSO matches _get_no_recent_capex_symbols() (real
operating_cash_flow, no capex-shaped concept in its 3 most recent fiscal years - true of
every blank-check shell, since it has no real operating business to capitalize anything
for) was falling through the fcf_margin/fcf_to_net_income/free_cash_flow ternary chains to
"capex_never_tagged_in_recent_filings" ("Missing SEC/XBRL data") BEFORE reaching the
end-of-function blank-check recategorize loop - and that loop's own
`_blank_check_source_reasons` set never included "capex_never_tagged_in_recent_filings" as
a source reason to override, unlike its RIC/ETF-trust siblings (both fixed 2026-09-06 for
the identical fund/trust-shape reason). So the loop's `metrics.get(_reason_key) in
_blank_check_source_reasons` check silently missed these rows and left them mislabeled.

Live-confirmed via company_info_sec.sic_description join: 11 active-universe blank-check
symbols (AFJK/ALDF/CAES/CUB/GTEN/NBRG/NOEM/SBXD/TACO/TWLV and siblings) stuck on this exact
mislabel for fcf_margin alone as of 2026-09-10.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(net_income=5_000_000.0, revenue=None, free_cash_flow=None):
    row = [None] * 34
    row[0] = 250_000_000.0  # stockholders_equity
    row[1] = 5_000_000.0  # total_liabilities
    row[2] = 255_000_000.0  # total_assets
    row[3] = net_income
    row[4] = revenue
    row[6] = 250_000_000.0  # current_assets
    row[7] = 5_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[14] = free_cash_flow
    return row


class _FakeCursor:
    def __init__(self, no_recent_capex_symbols):
        self._no_recent_capex = no_recent_capex_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "COUNT(capex)" in self._last_query:
            return [(s,) for s in self._no_recent_capex]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, no_recent_capex_symbols=frozenset()):
        self._no_recent_capex = no_recent_capex_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._no_recent_capex)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, blank_check_symbols=frozenset(), no_recent_capex_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(no_recent_capex_symbols))
    loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
    monkeypatch.setattr(loader, "_get_blank_check_symbols", lambda: blank_check_symbols)
    return loader


class TestBlankCheckCapexNeverTaggedRecategorize:
    def test_blank_check_symbol_matching_capex_gate_gets_no_revenue_reported(self, monkeypatch):
        loader = _make_loader(
            monkeypatch,
            blank_check_symbols=frozenset({"SPACX"}),
            no_recent_capex_symbols=frozenset({"SPACX"}),
        )
        metrics = loader._compute_quality_metrics("SPACX", _quality_row(), ev_metrics=(None, None, None, None))

        for field in ("fcf_margin", "fcf_to_net_income", "free_cash_flow"):
            assert metrics[field] is None
            assert metrics[f"{field}_unavailable_reason"] == "no_revenue_reported", (
                f"{field}_unavailable_reason was {metrics[f'{field}_unavailable_reason']!r}, "
                "expected the recategorize loop to override capex_never_tagged_in_recent_filings"
            )

    def test_non_blank_check_symbol_matching_capex_gate_keeps_specific_reason(self, monkeypatch):
        # A real operating company hitting the capex gate (not blank-check) must keep the
        # honest, specific reason - the recategorize loop must not fire for it.
        loader = _make_loader(
            monkeypatch,
            blank_check_symbols=frozenset({"SPACX"}),
            no_recent_capex_symbols=frozenset({"NORMALCO"}),
        )
        metrics = loader._compute_quality_metrics(
            "NORMALCO", _quality_row(revenue=500_000_000.0), ev_metrics=(None, None, None, None)
        )

        assert metrics["fcf_margin_unavailable_reason"] == "capex_never_tagged_in_recent_filings"
