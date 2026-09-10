"""Regression test for SecEdgarStatementLoader._no_data_reason (loaders/helpers/sec_base.py).

FIXED 2026-09-09 (goal session: "958 Missing SEC/XBRL data is a real problem", user pushback
on prior sessions treating this count as explained/acceptable). Live-traced GGAL/BBAR/SUPV/
TGS/TKC (Argentine banks/gas/telecom) and HEPS (Turkish e-commerce): these filers tag real,
current balance-sheet/cash-flow facts under ifrs-full, but ONLY in a hyperinflationary local
currency (ARS/TRY) - the aggregation layer correctly refuses those facts (no reliable FX
rate), but when EVERY concept for a statement type is currency-rejected, the aggregation
returns a fully empty row list, which previously fell into the generic
"no_..._data_in_sec_edgar_reit_or_special_entity" reason - factually wrong for a bank,
telecom, or media company. _no_data_reason() now checks has_unsupported_currency_only_fact()
before falling back to the generic reason.
"""

from unittest.mock import patch

from loaders.helpers.sec_base import SecEdgarStatementLoader


def _make_loader(statement_type: str = "balance", period: str = "annual") -> SecEdgarStatementLoader:
    loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
    loader.statement_type = statement_type
    loader.period = period
    loader._sec_client = object()  # never actually touched - has_unsupported_currency_only_fact is mocked
    return loader


class TestNoDataReasonCurrencyOnlyFact:
    def test_currency_only_fact_returns_specific_reason(self) -> None:
        loader = _make_loader("balance")
        with patch(
            "utils.external.sec_statements_shared.has_unsupported_currency_only_fact",
            return_value=True,
        ):
            assert loader._no_data_reason("GGAL") == "unsupported_currency_no_fx_rate"

    def test_no_currency_only_fact_falls_back_to_generic_reason(self) -> None:
        loader = _make_loader("balance")
        with patch(
            "utils.external.sec_statements_shared.has_unsupported_currency_only_fact",
            return_value=False,
        ):
            assert loader._no_data_reason("WATR") == "no_annual_balance_data_in_sec_edgar_reit_or_special_entity"

    def test_currency_check_exception_falls_back_to_generic_reason(self) -> None:
        """A failed currency check (e.g. no local companyfacts cache) must not crash the
        loader - fail open to the pre-fix generic reason, same fail-safe posture as every
        other best-effort classification helper in this codebase."""
        loader = _make_loader("balance")
        with patch(
            "utils.external.sec_statements_shared.has_unsupported_currency_only_fact",
            side_effect=RuntimeError("network error"),
        ):
            assert loader._no_data_reason("XYZ") == "no_annual_balance_data_in_sec_edgar_reit_or_special_entity"

    def test_cashflow_statement_type_uses_ocf_concepts(self) -> None:
        loader = _make_loader("cashflow")
        with patch(
            "utils.external.sec_statements_shared.has_unsupported_currency_only_fact",
            return_value=True,
        ) as mock_check:
            reason = loader._no_data_reason("GGAL")

        assert reason == "unsupported_currency_no_fx_rate"
        call_args = mock_check.call_args
        assert call_args.args[2] == ["NetCashProvidedByUsedInOperatingActivities"]
        assert call_args.args[3] == ["CashFlowsFromUsedInOperatingActivities"]

    def test_income_statement_type_uses_revenue_and_net_income_concepts(self) -> None:
        loader = _make_loader("income")
        with patch(
            "utils.external.sec_statements_shared.has_unsupported_currency_only_fact",
            return_value=False,
        ) as mock_check:
            reason = loader._no_data_reason("XYZ")

        assert reason == "no_annual_income_data_in_sec_edgar_reit_or_special_entity"
        call_args = mock_check.call_args
        assert call_args.args[2] == ["Revenues", "NetIncomeLoss"]
        assert call_args.args[3] == ["RevenueFromContractWithCustomerExcludingAssessedTax", "ProfitLoss"]

    def test_quarterly_period_reflected_in_generic_reason(self) -> None:
        loader = _make_loader("balance", period="quarterly")
        with patch(
            "utils.external.sec_statements_shared.has_unsupported_currency_only_fact",
            return_value=False,
        ):
            assert loader._no_data_reason("WATR") == "no_quarterly_balance_data_in_sec_edgar_reit_or_special_entity"
