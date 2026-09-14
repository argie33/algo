"""Regression test (2026-09-10, goal: "under 500" missing-XBRL push): a royalty-trust symbol
(_ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS, e.g. PBT) that ALSO matches
_get_no_recent_capex_symbols() (real operating_cash_flow, no capex-shaped concept in its 3
most recent fiscal years - true of every grantor trust, since it distributes royalty proceeds
and has no PP&E to capitalize) was falling through the fcf_margin/fcf_to_net_income/
free_cash_flow ternary chains to "capex_never_tagged_in_recent_filings" ("Missing SEC/XBRL
data") BEFORE reaching the end-of-function royalty-trust recategorize loop - and that loop's
own `_trust_source_reasons` set never included "capex_never_tagged_in_recent_filings" as a
source reason to override, unlike its RIC/ETF-trust/blank-check siblings (all fixed
2026-09-06/2026-09-10 for the identical fund/trust-shape reason). Same bug, fourth sibling
site.
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(net_income=50_000_000.0, free_cash_flow=None):
    row = [None] * 34
    row[2] = 700_000_000.0  # total_assets
    row[3] = net_income
    row[8] = 2025  # fiscal_year
    row[11] = 1_000_000.0  # shares_outstanding
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


def _make_loader(monkeypatch, no_recent_capex_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(no_recent_capex_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestRoyaltyTrustCapexNeverTaggedRecategorize:
    def test_trust_symbol_matching_capex_gate_gets_reit_special_entity(self, monkeypatch):
        # PBT is a real member of _ROYALTY_TRUST_NO_BALANCE_SHEET_SYMBOLS.
        loader = _make_loader(monkeypatch, no_recent_capex_symbols=frozenset({"PBT"}))
        metrics = loader._compute_quality_metrics("PBT", _quality_row(), ev_metrics=(None, None, None, None))

        for field in ("fcf_margin", "fcf_to_net_income", "free_cash_flow"):
            assert metrics[field] is None
            assert metrics[f"{field}_unavailable_reason"] == "reit_special_entity", (
                f"{field}_unavailable_reason was {metrics[f'{field}_unavailable_reason']!r}, "
                "expected the recategorize loop to override capex_never_tagged_in_recent_filings"
            )

    def test_non_trust_symbol_matching_capex_gate_keeps_specific_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, no_recent_capex_symbols=frozenset({"NORMALCO"}))
        metrics = loader._compute_quality_metrics(
            "NORMALCO", _quality_row(net_income=50_000_000.0), ev_metrics=(None, None, None, None)
        )

        assert metrics["fcf_margin_unavailable_reason"] == "capex_never_tagged_in_recent_filings"
