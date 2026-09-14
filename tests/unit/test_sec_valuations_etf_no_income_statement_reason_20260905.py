"""Regression test (2026-09-05, goal: "implausible values" sweep follow-up):
SecValuationsLoader.fetch_incremental's "no annual_income_statement rows at all" early return
always used the generic "no_income_statement" reason, even for a confirmed ETF
(stock_symbols.etf = 'true') - which files N-1A/N-CSR under the Investment Company Act, not a
10-K, so it structurally has zero income-statement rows to find. Same "Legitimate / not
applicable" business-model fact as reit_special_entity/etf_trust_no_gaap_financials elsewhere
in this codebase, not a missing-SEC-data gap.

Live-confirmed SPY/QQQ/IWM - the universe's only active `etf = 'true'` symbols, all with zero
annual_income_statement rows and (for SPY) zero sec_valuations rows at all.
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    """Sequential fetchall/fetchone stand-in: first fetchall() is the income-statement query
    (always empty here), then _get_total_cash_and_debt's two fetchone() calls, then the new
    ETF-status fetchone() query added by this fix."""

    def __init__(self, etf_value):
        self._etf_value = etf_value

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        if "stock_symbols" in self._last_query:
            return (self._etf_value,) if self._etf_value is not None else None
        return None  # _get_total_cash_and_debt's cash/debt queries: no balance-sheet data either


class TestSecValuationsEtfNoIncomeStatementReason:
    def test_confirmed_etf_reports_etf_no_sec_filings_reason(self):
        loader = _make_loader()
        result = loader._fetch_income_statement_context(_FakeCursor(etf_value="true"), "SPY")

        assert result[0]["reason"] == "etf_no_sec_filings"
        assert result[0]["data_unavailable"] is True

    def test_non_etf_keeps_generic_no_income_statement_reason(self):
        loader = _make_loader()
        result = loader._fetch_income_statement_context(_FakeCursor(etf_value="N"), "AADX")

        assert result[0]["reason"] == "no_income_statement"

    def test_no_stock_symbols_row_keeps_generic_reason(self):
        loader = _make_loader()
        result = loader._fetch_income_statement_context(_FakeCursor(etf_value=None), "UNKNOWNCO")

        assert result[0]["reason"] == "no_income_statement"
