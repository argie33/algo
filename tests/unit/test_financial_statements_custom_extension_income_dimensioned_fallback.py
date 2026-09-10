"""Regression test for the 2026-09-03 DB (Deutsche Bank) fix: symbols registered in
utils/external/sec_custom_xbrl_concepts.py's CUSTOM_INCOME_DIMENSIONED_CONCEPTS have their
real net_income/basic_eps/diluted_eps tagged only under a single-explicitMember dimensioned
context that SEC's companyfacts API structurally never returns as a plain fact (confirmed
live - see that module's docstring), so the normal concept-list extraction leaves those
fields permanently NULL for them. ConsolidatedFinancialStatementsLoader.fetch_incremental()
now supplements those rows with values fetched from the raw filed XBRL instance document.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import (
    ConsolidatedFinancialStatementsLoader,
    get_income_statement_config,
)


def _make_income_loader() -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_income_statement_config("annual")
    loader.table_name = config["table_name"]
    loader.period = "annual"
    loader.statement_type = "income"
    loader.is_symbol_based = True
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    loader._fallback_only_fields = config["fallback_only_fields"]
    loader._sec_client = MagicMock()
    loader._sec_client.symbol_to_cik.return_value = "0001159508"
    return loader


class TestCustomExtensionIncomeDimensionedFallback:
    def test_registered_symbol_gets_all_three_fields_injected_for_matching_fiscal_years(self):
        loader = _make_income_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[
                    {"symbol": "DB", "fiscal_year": 2025, "fiscal_period": "FY", "revenue": 30_000_000_000},
                    {"symbol": "DB", "fiscal_year": 2024, "fiscal_period": "FY", "revenue": 29_000_000_000},
                ],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_income_dimensioned",
                return_value={
                    "custom_extension_net_income": {2025: 6_606_000_000.0, 2024: 4_342_000_000.0},
                    "custom_extension_eps_basic": {2025: 2.97, 2024: 1.89},
                    "custom_extension_eps_diluted": {2025: 2.93, 2024: 1.85},
                },
            ) as mock_fetch,
        ):
            rows = loader.fetch_incremental("DB", since=None)

        mock_fetch.assert_called_once_with("DB", loader._sec_client)
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["custom_extension_net_income"] == 6_606_000_000.0
        assert by_year[2025]["custom_extension_eps_basic"] == 2.97
        assert by_year[2025]["custom_extension_eps_diluted"] == 2.93
        assert by_year[2024]["custom_extension_net_income"] == 4_342_000_000.0

    def test_unregistered_symbol_never_calls_fetch_custom_income_dimensioned(self):
        loader = _make_income_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "AAPL", "fiscal_year": 2025, "revenue": 1}],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_income_dimensioned"
            ) as mock_fetch,
        ):
            loader.fetch_incremental("AAPL", since=None)

        mock_fetch.assert_not_called()

    def test_cashflow_statement_type_never_calls_fetch_custom_income_dimensioned(self):
        """CUSTOM_INCOME_DIMENSIONED_CONCEPTS is an income-statement-only fallback - must
        not fire for cashflow/balance statement fetches even for a registered symbol."""
        loader = _make_income_loader()
        loader.statement_type = "cashflow"
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "DB", "fiscal_year": 2025, "operating_cash_flow": 1}],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_income_dimensioned"
            ) as mock_fetch,
        ):
            loader.fetch_incremental("DB", since=None)

        mock_fetch.assert_not_called()

    def test_fiscal_year_with_no_custom_data_is_left_unmodified(self):
        loader = _make_income_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "DB", "fiscal_year": 2010, "revenue": 1}],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_income_dimensioned",
                return_value={"custom_extension_net_income": {2025: 6_606_000_000.0}},  # No entry for 2010
            ),
        ):
            rows = loader.fetch_incremental("DB", since=None)

        assert "custom_extension_net_income" not in rows[0]


class TestCustomExtensionIncomeDimensionedFieldMappingFallbackOnly:
    def test_custom_extension_fields_map_to_correct_columns(self):
        config = get_income_statement_config("annual")
        assert config["field_mapping"]["custom_extension_net_income"] == "net_income"
        assert config["field_mapping"]["custom_extension_eps_basic"] == "earnings_per_share"
        assert config["field_mapping"]["custom_extension_eps_diluted"] == "diluted_eps"

    def test_custom_extension_fields_are_fallback_only(self):
        """Must never overwrite a real value the normal SEC concept extraction already
        found - transform()'s _fallback_only_fields check depends on this."""
        loader = _make_income_loader()
        assert "custom_extension_net_income" in loader._fallback_only_fields
        assert "custom_extension_eps_basic" in loader._fallback_only_fields
        assert "custom_extension_eps_diluted" in loader._fallback_only_fields
