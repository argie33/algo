"""Regression test (2026-09-11, goal: "SEC/XBRL missing data under 200" push, same-day sibling
to the dcf_fcf blank-check call-ordering fix): SecValuationsLoader.fetch_incremental's "no
annual_income_statement rows at all" early return checks ETF status and FPI-currency-rejection
before falling back to the generic "no_income_statement" reason, but never checked blank-check
(SIC "Blank Checks") status - despite the identical structural fact (no real operating business)
already being relabeled "no_revenue_reported" for the sibling "all key valuation metrics NULL"
whole-row case. Live-confirmed 13 active symbols (APMC/CCCT/CGCF/EWAV/FTRA/GCGR/GHXI/IPVV/LTGR/
RACD/SHOT/WLCO/YICC) stuck on "no_income_statement" ("Missing SEC/XBRL data") instead of the
correct "no_revenue_reported" ("Legitimate / not applicable").
"""

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    def __init__(self, is_blank_check: bool):
        self._is_blank_check = is_blank_check
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        if "stock_symbols" in self._last_query:
            return ("N",)  # not an ETF
        if "sic_description" in self._last_query:
            return (1,) if self._is_blank_check else None
        if "is_foreign_private_issuer" in self._last_query:
            return (False,)
        return None  # _get_total_cash_and_debt's cash/debt queries: no balance-sheet data


class TestSecValuationsBlankCheckNoIncomeStatement:
    def test_blank_check_symbol_gets_no_revenue_reported(self) -> None:
        loader = _make_loader()

        result = loader._fetch_income_statement_context(_FakeCursor(is_blank_check=True), "SPACX")

        assert result[0]["reason"] == "no_revenue_reported"
        assert result[0]["data_unavailable"] is True

    def test_non_blank_check_keeps_generic_reason(self) -> None:
        loader = _make_loader()

        result = loader._fetch_income_statement_context(_FakeCursor(is_blank_check=False), "REALCO")

        assert result[0]["reason"] == "no_income_statement"
