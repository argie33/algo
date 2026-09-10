"""Regression test for the 2026-08-29 shipping-sector capex fix: symbols registered in
utils/external/sec_custom_xbrl_concepts.py's CUSTOM_CAPEX_CONCEPTS have their real
capex tagged under a filer-specific custom XBRL extension concept that SEC's companyfacts
API structurally never returns (confirmed live - see that module's docstring), so the
normal concept-list extraction leaves `capex` permanently NULL for them no matter how many
standard concepts get added to the list. ConsolidatedFinancialStatementsLoader.fetch_incremental()
now supplements those rows with a value fetched from the raw filed XBRL instance document.
"""

from datetime import date
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
    loader._sec_client.symbol_to_cik.return_value = "0001234567"
    return loader


class TestCustomExtensionCapexFallback:
    def test_registered_symbol_gets_custom_capex_injected_for_matching_fiscal_years(self):
        loader = _make_cashflow_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[
                    {"symbol": "DHT", "fiscal_year": 2025, "fiscal_period": "FY", "operating_cash_flow": 500_000_000},
                    {"symbol": "DHT", "fiscal_year": 2024, "fiscal_period": "FY", "operating_cash_flow": 300_000_000},
                ],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_capex",
                return_value={2025: 309_636_000.0, 2024: 96_883_000.0},
            ) as mock_fetch,
        ):
            rows = loader.fetch_incremental("DHT", since=None)

        mock_fetch.assert_called_once_with("DHT", loader._sec_client)
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["custom_extension_vessel_capex"] == 309_636_000.0
        assert by_year[2024]["custom_extension_vessel_capex"] == 96_883_000.0

    def test_unregistered_symbol_never_calls_fetch_custom_capex(self):
        loader = _make_cashflow_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "AAPL", "fiscal_year": 2025, "operating_cash_flow": 1}],
            ),
            patch("loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_capex") as mock_fetch,
        ):
            loader.fetch_incremental("AAPL", since=None)

        mock_fetch.assert_not_called()

    def test_income_statement_type_never_calls_fetch_custom_capex(self):
        """CUSTOM_CAPEX_CONCEPTS is a cashflow-only fallback - must not fire for income/
        balance statement fetches even for a registered symbol."""
        loader = _make_cashflow_loader()
        loader.statement_type = "income"
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "DHT", "fiscal_year": 2025, "revenue": 1}],
            ),
            patch("loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_capex") as mock_fetch,
        ):
            loader.fetch_incremental("DHT", since=None)

        mock_fetch.assert_not_called()

    def test_fiscal_year_with_no_custom_data_is_left_unmodified(self):
        loader = _make_cashflow_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "DHT", "fiscal_year": 2020, "operating_cash_flow": 1}],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks.fetch_custom_capex",
                return_value={2025: 309_636_000.0},  # No entry for 2020
            ),
        ):
            rows = loader.fetch_incremental("DHT", since=None)

        assert "custom_extension_vessel_capex" not in rows[0]


class TestCustomExtensionCapexFieldMappingFallbackOnly:
    def test_custom_extension_capex_field_maps_to_capex_column(self):
        config = get_cash_flow_config("annual")
        assert config["field_mapping"]["custom_extension_vessel_capex"] == "capex"

    def test_custom_extension_capex_is_fallback_only(self):
        """Must never overwrite a real capex value the normal SEC concept extraction
        already found - transform()'s _fallback_only_fields check depends on this."""
        loader = _make_cashflow_loader()
        assert "custom_extension_vessel_capex" in loader._fallback_only_fields
