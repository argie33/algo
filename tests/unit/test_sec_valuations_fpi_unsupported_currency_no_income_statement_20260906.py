"""Regression test (2026-09-06, sibling fix to 9e26b3d02/6111c0b4f): SecValuationsLoader.
fetch_incremental's "no annual_income_statement rows at all" early return always used the
generic "no_income_statement" reason, even for a foreign private issuer whose revenue/
net_income facts all exist only under an unsupported (non-major, non-USD) currency - so
_aggregate_concepts never created any annual_income_statement row for them at all (a
currency-skipped concept never touches `rows.setdefault`, unlike the all-NULL-but-present-row
case those two prior commits cover).

Live-confirmed GGAL/BSAC/TKC/EDN/SUPV/TGS/TEO hitting this exact shape.
"""

from unittest.mock import MagicMock, patch

from loaders.load_sec_valuations import SecValuationsLoader


def _make_loader() -> SecValuationsLoader:
    return SecValuationsLoader.__new__(SecValuationsLoader)


class _FakeCursor:
    """Sequential fetchall/fetchone stand-in, same shape as the ETF sibling test's own
    _FakeCursor: first fetchall() is the income-statement query (always empty here), then
    _get_total_cash_and_debt's two fetchone() calls, then the ETF-status query, then (only
    when is_fpi=True) this fix's new is_foreign_private_issuer query."""

    def __init__(self, is_fpi: bool):
        self._is_fpi = is_fpi
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query

    def fetchall(self):
        return []

    def fetchone(self):
        if "stock_symbols" in self._last_query:
            return ("N",)  # not an ETF
        if "company_info_sec" in self._last_query:
            return (self._is_fpi,)
        return None  # _get_total_cash_and_debt's cash/debt queries: no balance-sheet data


class TestSecValuationsFpiUnsupportedCurrencyNoIncomeStatement:
    def test_fpi_with_only_rejected_currency_fact_gets_specific_reason(self) -> None:
        loader = _make_loader()
        fake_facts = {
            "facts": {
                "ifrs-full": {
                    "Revenue": {"units": {"ARS": [{"val": 100_000_000_000, "fy": 2025}]}},
                },
            }
        }
        fake_client = MagicMock()
        fake_client.get_company_facts.return_value = fake_facts

        with patch("utils.external.sec_edgar_client.SecEdgarClient", return_value=fake_client):
            result = loader._fetch_income_statement_context(_FakeCursor(is_fpi=True), "GGAL")

        assert result[0]["reason"] == "unsupported_currency_no_fx_rate"
        assert result[0]["data_unavailable"] is True

    def test_fpi_with_real_usd_fact_keeps_generic_reason(self) -> None:
        loader = _make_loader()
        fake_facts = {
            "facts": {
                "us-gaap": {
                    "Revenues": {"units": {"USD": [{"val": 500_000_000, "fy": 2025}]}},
                },
            }
        }
        fake_client = MagicMock()
        fake_client.get_company_facts.return_value = fake_facts

        with patch("utils.external.sec_edgar_client.SecEdgarClient", return_value=fake_client):
            result = loader._fetch_income_statement_context(_FakeCursor(is_fpi=True), "SOMEFPI")

        assert result[0]["reason"] == "no_income_statement"

    def test_non_fpi_never_triggers_currency_check(self) -> None:
        loader = _make_loader()
        fake_client = MagicMock()

        with patch("utils.external.sec_edgar_client.SecEdgarClient", return_value=fake_client):
            result = loader._fetch_income_statement_context(_FakeCursor(is_fpi=False), "NEWCO")

        fake_client.get_company_facts.assert_not_called()
        assert result[0]["reason"] == "no_income_statement"
