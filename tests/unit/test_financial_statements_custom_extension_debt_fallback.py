"""Regression test for the 2026-09-03 Berkshire Hathaway debt fix: BRK.A/BRK.B, registered
in utils/external/sec_custom_xbrl_concepts.py's CUSTOM_DEBT_CONCEPTS, have their real
combined debt tagged only across two entity-level-segment-dimensioned facts that SEC's
companyfacts API structurally never surfaces under a USD unit (confirmed live - see that
module's docstring), so the normal concept-list extraction leaves long_term_debt/
short_term_debt permanently NULL for them no matter how many standard concepts get added to
the list. ConsolidatedFinancialStatementsLoader.fetch_incremental() now supplements those
rows with a value fetched from the raw filed XBRL instance document, same mechanism as the
CUSTOM_CAPEX_CONCEPTS/CUSTOM_REVENUE_CONCEPTS fixes before it.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_balance_sheet_config


def _make_balance_loader() -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_balance_sheet_config("annual")
    loader.table_name = config["table_name"]
    loader.period = "annual"
    loader.statement_type = "balance"
    loader.is_symbol_based = True
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    loader._fallback_only_fields = config["fallback_only_fields"]
    loader._sec_client = MagicMock()
    loader._sec_client.symbol_to_cik.return_value = "0001067983"
    return loader


class TestCustomExtensionDebtFallback:
    def test_registered_symbol_gets_custom_debt_injected_for_matching_fiscal_years(self):
        loader = _make_balance_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[
                    {"symbol": "BRK.B", "fiscal_year": 2025, "total_assets": 1_222_176_000_000},
                    {"symbol": "BRK.B", "fiscal_year": 2024, "total_assets": 1_153_881_000_000},
                ],
            ),
            patch(
                "loaders.load_financial_statements.fetch_custom_debt",
                return_value={2025: 129_081_000_000.0},
            ) as mock_fetch,
        ):
            rows = loader.fetch_incremental("BRK.B", since=None)

        mock_fetch.assert_called_once_with("BRK.B", loader._sec_client)
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["custom_extension_total_debt"] == 129_081_000_000.0
        assert "custom_extension_total_debt" not in by_year[2024]

    def test_unregistered_symbol_never_calls_fetch_custom_debt(self):
        loader = _make_balance_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "AAPL", "fiscal_year": 2025, "total_assets": 1}],
            ),
            patch("loaders.load_financial_statements.fetch_custom_debt") as mock_fetch,
        ):
            loader.fetch_incremental("AAPL", since=None)

        mock_fetch.assert_not_called()

    def test_cashflow_statement_type_never_calls_fetch_custom_debt(self):
        """CUSTOM_DEBT_CONCEPTS is a balance-sheet-only fallback - must not fire for
        income/cashflow statement fetches even for a registered symbol."""
        loader = _make_balance_loader()
        loader.statement_type = "cashflow"
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[{"symbol": "BRK.B", "fiscal_year": 2025, "operating_cash_flow": 1}],
            ),
            patch("loaders.load_financial_statements.fetch_custom_debt") as mock_fetch,
        ):
            loader.fetch_incremental("BRK.B", since=None)

        mock_fetch.assert_not_called()


class TestCustomExtensionDebtFieldMappingFallbackOnly:
    def test_custom_extension_total_debt_field_maps_to_long_term_debt_column(self):
        config = get_balance_sheet_config("annual")
        assert config["field_mapping"]["custom_extension_total_debt"] == "long_term_debt"

    def test_custom_extension_total_debt_is_fallback_only(self):
        """Must never overwrite a real long_term_debt value the normal SEC concept
        extraction already found - transform()'s _fallback_only_fields check depends on
        this."""
        loader = _make_balance_loader()
        assert "custom_extension_total_debt" in loader._fallback_only_fields
