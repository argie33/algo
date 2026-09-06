"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, sibling of
test_sec_valuations_etf_no_income_statement_reason_20260905.py): that fix only covered the
`not income_rows` branch (zero annual_income_statement rows at all). Live-confirmed IWM
(iShares Russell 2000 ETF, stock_symbols.etf='true') instead has a stray
annual_income_statement row that survives the `data_unavailable IS NOT TRUE` filter but
carries no real revenue/EPS/net_income - a different code path
(`ttm_revenue is None and ttm_eps_basic is None and _ttm_net_income is None`) that never
checked ETF status, so IWM fell through to the generic "income_statement_revenue_and_eps_null"
label instead of the same "Legitimate / not applicable" fact SPY/QQQ already get.
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
    the ETF-status fetchone() query added by this fix comes after."""

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


class TestSecValuationsEtfIncomeStubRowReason:
    def test_confirmed_etf_with_stub_row_reports_etf_no_sec_filings_reason(self):
        loader = _make_loader()
        with (
            patch.object(loader, "_get_total_cash_and_debt", return_value=(None, None)),
            patch.object(loader, "_compute_multi_year_eps_cagr", return_value=None),
        ):
            result = loader._fetch_income_statement_context(_FakeCursor(etf_value="true"), "IWM")

        assert result[0]["reason"] == "etf_no_sec_filings"
        assert result[0]["data_unavailable"] is True

    def test_non_etf_with_stub_row_keeps_generic_reason(self):
        loader = _make_loader()
        with (
            patch.object(loader, "_get_total_cash_and_debt", return_value=(None, None)),
            patch.object(loader, "_compute_multi_year_eps_cagr", return_value=None),
        ):
            result = loader._fetch_income_statement_context(_FakeCursor(etf_value="N"), "AADX")

        assert result[0]["reason"] == "income_statement_revenue_and_eps_null"
