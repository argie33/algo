"""Regression test: ev_revenue/ps_ratio_unavailable_reason must distinguish a structurally
pre-revenue company (no revenue reported in its 3 most recent fiscal years) from a real SEC
extraction gap, reusing the same _get_no_recent_revenue_symbols() check already built for
ebitda_margin.

Found live 2026-08-18 (goal: "no SEC data" audit, continuation of the ebitda_margin fix): 1,299
universe symbols have ev_revenue "missing_sec_data"; several (RVMD, OKLO, SENEB, CRAI, CNTN) have
a real, non-NULL enterprise_value in sec_valuations, meaning the actual blocker is revenue, not
EV. RVMD (Revolution Medicines, clinical-stage biotech) is genuinely pre-revenue. CRAI (CRA
International, ~$750M/year real revenue) turned out to be a separate, already-fixed anchor-row
bug (a same-year-substitute fallback in load_sec_valuations.py, 723 symbols) - this fix only
covers the genuinely-pre-revenue subset, correctly leaving CRAI-style propagation-lag cases as
the generic "missing_sec_data" until that fix's data lands.
"""

from unittest.mock import patch

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _make_loader():
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class _FakeSecValRow:
    """Minimal stand-in for a psycopg2 DictRow: supports sec_val_row[2] (data_unavailable flag,
    positional) and dict(sec_val_row) (mapping protocol) simultaneously."""

    def __init__(self, mapping):
        self._mapping = mapping

    def __getitem__(self, key):
        if key == 2:
            return False
        return self._mapping[key]

    def keys(self):
        return self._mapping.keys()


class _RecordingCursor:
    def __init__(self, queries, no_recent_revenue_symbols):
        self._queries = queries
        self._no_recent_revenue = no_recent_revenue_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query
        self._queries.append(query)

    def fetchone(self):
        return None

    def fetchall(self):
        if "annual_income_statement" in self._last_query and "revenue" in self._last_query:
            return [(s,) for s in self._no_recent_revenue]
        return []


def _run(monkeypatch, no_recent_revenue_symbols=frozenset(), **sec_val_fields):
    import loaders.load_value_quality_growth_metrics as mod

    queries: list = []
    cursor = _RecordingCursor(queries, no_recent_revenue_symbols)

    class _FakeDatabaseContext:
        def __enter__(self):
            return cursor

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext())
    loader = _make_loader()
    with patch.object(loader, "_get_analyst_forward_eps", return_value=None):
        return loader._build_value_metrics("RVMD", _FakeSecValRow(sec_val_fields))


class TestEvRevenuePsRatioNoRevenueReason:
    def test_ev_revenue_propagates_no_revenue_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            no_recent_revenue_symbols=frozenset({"RVMD"}),
            pe_ratio=None,
            pb_ratio=None,
            ps_ratio=None,
            ev_revenue=None,
            enterprise_value=39_646_439_648.0,
            market_cap=40_307_380_648.0,
            fcf_yield=15.0,
        )

        assert result["ev_revenue_unavailable_reason"] == "no_revenue_reported"
        assert result["ps_ratio_unavailable_reason"] == "no_revenue_reported"

    def test_symbol_not_in_no_recent_set_keeps_generic_reason(self, monkeypatch):
        # ev_revenue is None, but the symbol isn't a confirmed pre-revenue company (e.g. CRAI's
        # anchor-row propagation-lag case) - must stay the generic "missing_sec_data".
        result = _run(
            monkeypatch,
            no_recent_revenue_symbols=frozenset(),
            pe_ratio=None,
            pb_ratio=None,
            ps_ratio=None,
            ev_revenue=None,
            enterprise_value=1_057_920_703.47,
            market_cap=1_075_149_703.47,
            fcf_yield=15.0,
        )

        assert result["ev_revenue_unavailable_reason"] == "missing_sec_data"
        assert result["ps_ratio_unavailable_reason"] == "missing_sec_data"

    def test_real_ev_revenue_still_populates_with_no_reason(self, monkeypatch):
        result = _run(
            monkeypatch,
            no_recent_revenue_symbols=frozenset({"RVMD"}),
            pe_ratio=None,
            pb_ratio=None,
            ps_ratio=5.5,
            ev_revenue=8.2,
            enterprise_value=39_646_439_648.0,
            market_cap=40_307_380_648.0,
            fcf_yield=15.0,
        )

        assert result["ev_revenue"] == 8.2
        assert result.get("ev_revenue_unavailable_reason") is None
        assert result["ps_ratio"] == 5.5
        assert result.get("ps_ratio_unavailable_reason") is None
