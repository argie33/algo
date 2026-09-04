"""Regression test for the 2026-09-03 CMS dividends-paid fix: symbols registered in
utils/external/sec_custom_xbrl_concepts.py's CUSTOM_DIVIDEND_CONCEPTS have their real
dividends_paid tagged under a filer-specific custom XBRL extension concept that SEC's
companyfacts API structurally never returns (confirmed live - see that module's docstring),
so the normal concept-list extraction leaves `dividends_paid` permanently NULL for them no
matter how many standard concepts get added to the list. ConsolidatedFinancialStatementsLoader.
fetch_incremental() now supplements those rows with a value fetched from the raw filed XBRL
instance document.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import (
    ConsolidatedFinancialStatementsLoader,
    get_cash_flow_config,
)


def _make_cashflow_loader() -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_cash_flow_config("annual")
    loader.table_name = config["table_name"]
    loader.period = "annual"
    loader.statement_type = "cashflow"
    loader.is_symbol_based = True
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    loader._fallback_only_fields = config["fallback_only_fields"]
    loader._sec_client = MagicMock()
    loader._sec_client.symbol_to_cik.return_value = "0000811156"
    return loader


class TestCustomExtensionDividendsFallback:
    def test_registered_symbol_gets_custom_dividends_injected_for_matching_fiscal_years(self):
        loader = _make_cashflow_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[
                    {"symbol": "CMS", "fiscal_year": 2025, "operating_cash_flow": 2_000_000_000},
                    {"symbol": "CMS", "fiscal_year": 2024, "operating_cash_flow": 1_900_000_000},
                ],
            ),
            patch(
                "loaders.load_financial_statements.fetch_custom_dividends",
                return_value={2025: 663_000_000.0, 2024: 626_000_000.0},
            ) as mock_fetch,
        ):
            rows = loader.fetch_incremental("CMS", since=None)

        mock_fetch.assert_called_once_with("CMS", loader._sec_client)
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["custom_extension_dividends_paid"] == 663_000_000.0
        assert by_year[2024]["custom_extension_dividends_paid"] == 626_000_000.0

    def test_unregistered_symbol_never_calls_fetch_custom_dividends(self):
        loader = _make_cashflow_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "AAPL", "fiscal_year": 2025, "operating_cash_flow": 1}],
            ),
            patch("loaders.load_financial_statements.fetch_custom_dividends") as mock_fetch,
        ):
            loader.fetch_incremental("AAPL", since=None)

        mock_fetch.assert_not_called()

    def test_income_statement_type_never_calls_fetch_custom_dividends(self):
        """CUSTOM_DIVIDEND_CONCEPTS is a cashflow-only fallback - must not fire for income/
        balance statement fetches even for a registered symbol."""
        loader = _make_cashflow_loader()
        loader.statement_type = "income"
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "CMS", "fiscal_year": 2025, "revenue": 1}],
            ),
            patch("loaders.load_financial_statements.fetch_custom_dividends") as mock_fetch,
        ):
            loader.fetch_incremental("CMS", since=None)

        mock_fetch.assert_not_called()

    def test_fiscal_year_with_no_custom_data_is_left_unmodified(self):
        loader = _make_cashflow_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "CMS", "fiscal_year": 2010, "operating_cash_flow": 1}],
            ),
            patch(
                "loaders.load_financial_statements.fetch_custom_dividends",
                return_value={2025: 663_000_000.0},  # No entry for 2010
            ),
        ):
            rows = loader.fetch_incremental("CMS", since=None)

        assert "custom_extension_dividends_paid" not in rows[0]


class TestCustomExtensionDividendsFieldMappingFallbackOnly:
    def test_custom_extension_dividends_field_maps_to_dividends_paid_column(self):
        config = get_cash_flow_config("annual")
        assert config["field_mapping"]["custom_extension_dividends_paid"] == "dividends_paid"

    def test_custom_extension_dividends_is_fallback_only(self):
        """Must never overwrite a real dividends_paid value the normal SEC concept
        extraction already found - transform()'s _fallback_only_fields check depends on
        this."""
        loader = _make_cashflow_loader()
        assert "custom_extension_dividends_paid" in loader._fallback_only_fields
