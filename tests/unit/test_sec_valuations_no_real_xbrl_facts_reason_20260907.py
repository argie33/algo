"""Regression test (2026-09-07, goal: "SEC/XBRL missing data to zero" sweep, sibling of
test_sec_valuations_etf_income_stub_row_reason_20260906.py): live-reconfirmed via SEC's own
companyfacts API that AIIR/WATR/RPGL/VRXA/PSQL/IMC/BIOT have zero real us-gaap/ifrs-full XBRL
facts ever (only `ffd` fee-disclosure facts, or no companyfacts entry at all) - a real,
permanent, non-SEC-XBRL-reporting entity, same class "no_xbrl_filings" already exists for
elsewhere in coverage_category_rules.py. Before this fix these symbols fell through to the
generic "income_statement_revenue_and_eps_null" label (implying a fixable extraction gap)
instead of the correct "Legitimate / not applicable" fact.
"""

from unittest.mock import patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


def _stub_income_row():
    # (fiscal_year, revenue, net_income, earnings_per_share, operating_income, pretax_income,
    #  depreciation_expense, amortization_expense, shares_outstanding_basic,
    #  income_tax_expense, is_foreign_private_issuer, sic_code, interest_expense)
    return (2025, None, None, None, None, None, None, None, None, None, False, None, None)


class _FakeCursor:
    """First fetchall() is the income-statement query (one stub row, all-null financials);
    the ETF-status fetchone() query added by the sibling fix comes after."""

    def __init__(self, etf_value):
        self._etf_value = etf_value
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return [_stub_income_row()]

    def fetchone(self):
        if "stock_symbols" in self._last_query:
            return (self._etf_value,) if self._etf_value is not None else None
        return None


class TestSecValuationsNoRealXbrlFactsReason:
    def test_verified_no_xbrl_facts_symbol_reports_no_xbrl_filings_reason(self):
        loader = _make_loader()
        with (
            patch.object(loader, "_get_total_cash_and_debt", return_value=(None, None)),
            patch.object(loader, "_compute_multi_year_eps_cagr", return_value=None),
        ):
            result = loader._fetch_income_statement_context(_FakeCursor(etf_value="N"), "AIIR")

        assert result[0]["reason"] == "no_xbrl_filings"
        assert result[0]["data_unavailable"] is True

    def test_unverified_symbol_with_stub_row_keeps_generic_reason(self):
        loader = _make_loader()
        with (
            patch.object(loader, "_get_total_cash_and_debt", return_value=(None, None)),
            patch.object(loader, "_compute_multi_year_eps_cagr", return_value=None),
        ):
            result = loader._fetch_income_statement_context(_FakeCursor(etf_value="N"), "AADX")

        assert result[0]["reason"] == "income_statement_revenue_and_eps_null"
