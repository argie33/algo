"""Regression test (2026-09-05, goal: "SEC/XBRL missing data to zero" follow-up):
accruals_ratio_unavailable_reason/ocf_to_net_income_unavailable_reason never checked the
registered-investment-company gate (_get_registered_investment_company_symbols(), already used
by fcf_margin/fcf_yield's identical chains elsewhere in this file).

A RIC (closed-end fund/investment trust) files a "Statement of Changes in Net Assets" instead of
a conventional cash-flow statement, leaving it with ZERO fiscal_year>0 rows in
annual_cash_flow at all - too sparse to match _get_no_recent_operating_cash_flow_symbols()'s
own "3 most recent real years all lack OCF" pattern (which needs at least some real
fiscal_year>0 rows to rank against), so it fell through THAT gate too and landed on generic
"missing_sec_data" despite having real, multi-year annual_balance_sheet total_assets on file
(proving it's an established filer, not just too new).

Live-confirmed GGN (GAMCO Global Gold, Natural Resources & Income Trust): entity_type='other'/
sic_code=NULL, real total_assets 2022-2025, a single fiscal_year=0 placeholder row in
annual_cash_flow with data_unavailable=TRUE - matches
_get_registered_investment_company_symbols() exactly. A live DB scan found 14 universe symbols
hitting this exact shape for ocf_to_net_income (IGI/TY/ASA/GAM/GGN/GGT/GLU/PIM/PMM/GNT/HQH/PPT/
NXP/SOR).
"""

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _quality_row(net_income=50_000_000.0, operating_cash_flow=None, total_assets=700_000_000.0):
    # 34-column shape (index 33 = prior_year_gross_profit), same as the sibling
    # test_operating_cash_flow_accruals_ratio_reason_gate_20260902.py file.
    row = [None] * 34
    row[0] = 100_000_000.0  # stockholders_equity
    row[1] = 200_000_000.0  # total_liabilities
    row[2] = total_assets
    row[3] = net_income
    row[6] = 150_000_000.0  # current_assets
    row[7] = 100_000_000.0  # current_liabilities
    row[8] = 2025  # fiscal_year
    row[13] = operating_cash_flow
    return row


class _FakeCursor:
    """Serves a real match only to the RIC gate's distinctive query (entity_type/sic_code
    filter), empty for every other gate query this loader may run."""

    def __init__(self, ric_symbols):
        self._ric_symbols = ric_symbols
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        if "entity_type" in self._last_query and "sic_code" in self._last_query:
            return [(s,) for s in self._ric_symbols]
        return []

    def fetchone(self):
        return None


class _FakeDatabaseContext:
    def __init__(self, ric_symbols=frozenset()):
        self._ric_symbols = ric_symbols

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return _FakeCursor(self._ric_symbols)

    def __exit__(self, *exc):
        return False


def _make_loader(monkeypatch, ric_symbols=frozenset()):
    import loaders.load_value_quality_growth_metrics as mod

    monkeypatch.setattr(mod, "DatabaseContext", _FakeDatabaseContext(ric_symbols))
    return ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)


class TestAccrualsRatioOcfToNetIncomeRicGap:
    def test_ggn_shaped_ric_reports_registered_investment_company_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        row = _quality_row(operating_cash_flow=None)

        metrics = loader._compute_quality_metrics("GGN", row, ev_metrics=None)

        assert metrics["operating_cash_flow"] is None
        assert metrics["accruals_ratio"] is None
        assert metrics["accruals_ratio_unavailable_reason"] == "registered_investment_company_no_xbrl"
        assert metrics["ocf_to_net_income"] is None
        assert metrics["ocf_to_net_income_unavailable_reason"] == "registered_investment_company_no_xbrl"

    def test_non_ric_with_no_matching_gate_keeps_generic_reason(self, monkeypatch):
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        row = _quality_row(operating_cash_flow=None)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["accruals_ratio_unavailable_reason"] == "missing_sec_data"
        assert metrics["ocf_to_net_income_unavailable_reason"] == "missing_sec_data"

    def test_real_ocf_still_computes_normally_for_a_non_ric(self, monkeypatch):
        loader = _make_loader(monkeypatch, ric_symbols=frozenset({"GGN"}))
        row = _quality_row(net_income=50_000_000.0, operating_cash_flow=60_000_000.0, total_assets=700_000_000.0)

        metrics = loader._compute_quality_metrics("NORMALCO", row, ev_metrics=None)

        assert metrics["accruals_ratio"] is not None
        assert metrics.get("accruals_ratio_unavailable_reason") is None
        assert metrics["ocf_to_net_income"] is not None
        assert metrics.get("ocf_to_net_income_unavailable_reason") is None
