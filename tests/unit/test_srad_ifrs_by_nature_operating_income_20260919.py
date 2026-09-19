"""Regression tests for the 2026-09-19 SRAD (Sportradar) operating_income fix.

SRAD presents its IFRS income statement "by nature" (Personnel expenses / Sport rights
expenses / Purchased services / Other operating expenses / D&A, rather than a "by
function" cost-of-sales/SG&A/R&D split). The pre-existing operating_income fallback
(revenue - cost_of_revenue - a narrow AdministrativeExpense sliver) ignored the two
dominant cost lines - "Personnel expenses" (ifrs-full:EmployeeBenefitsExpense) and
"Other operating expenses" (ifrs-full:OtherOperatingIncomeExpense) - overstating
operating_income up to 23.7x vs yfinance. A third dominant line, "Sport rights expenses",
is tagged under a filer-specific custom XBRL extension concept (srad:SportRightsExpenses,
EUR-denominated) invisible to companyfacts.

Fixture values match the real filed FY2024 20-F (CIK 0001836470, accession
0001410578-25-000399), verified live 2026-09-19.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_income_statement_config
from utils.external.sec_custom_xbrl_currency_duration import (
    CUSTOM_OPERATING_EXPENSE_CONCEPTS_CURRENCY_AWARE,
)
from utils.external.sec_income_statement_fallbacks import (
    _fill_operating_income_from_revenue_minus_ifrs_by_nature_expenses,
)


class TestSradRegisteredInCustomOperatingExpenseConcepts:
    def test_srad_registered(self) -> None:
        assert "SRAD" in CUSTOM_OPERATING_EXPENSE_CONCEPTS_CURRENCY_AWARE


class TestFillOperatingIncomeFromRevenueMinusIfrsByNatureExpenses:
    def test_computes_operating_income_from_by_nature_components(self) -> None:
        rows = [
            {
                "symbol": "SRAD",
                "fiscal_year": 2024,
                "revenues": 1_149_596_908.24,
                "cost_of_revenue": 182_411_486.04,
                "employee_benefits_expense": 363_269_822.14,
                "other_operating_income_expense": -97_175_241.02,
                "depreciation_and_amortization": 52_757_230.72,
            }
        ]
        _fill_operating_income_from_revenue_minus_ifrs_by_nature_expenses(rows)
        expected = 1_149_596_908.24 - 182_411_486.04 - 363_269_822.14 - 52_757_230.72 - 97_175_241.02
        assert rows[0]["operating_income_loss"] == expected
        assert "employee_benefits_expense" not in rows[0]
        assert "other_operating_income_expense" not in rows[0]

    def test_never_overwrites_a_real_operating_income_loss(self) -> None:
        rows = [
            {
                "symbol": "SRAD",
                "fiscal_year": 2024,
                "operating_income_loss": 100.0,
                "revenues": 1_000.0,
                "cost_of_revenue": 1.0,
                "employee_benefits_expense": 1.0,
                "depreciation_and_amortization": 1.0,
            }
        ]
        _fill_operating_income_from_revenue_minus_ifrs_by_nature_expenses(rows)
        assert rows[0]["operating_income_loss"] == 100.0

    def test_does_not_fire_without_employee_benefits_expense(self) -> None:
        rows = [{"symbol": "AAPL", "fiscal_year": 2024, "revenues": 1_000.0, "cost_of_revenue": 1.0}]
        _fill_operating_income_from_revenue_minus_ifrs_by_nature_expenses(rows)
        assert "operating_income_loss" not in rows[0]

    def test_does_not_fire_without_depreciation_and_amortization(self) -> None:
        rows = [
            {
                "symbol": "SOMEFILER",
                "fiscal_year": 2024,
                "revenues": 1_000.0,
                "cost_of_revenue": 1.0,
                "employee_benefits_expense": 1.0,
            }
        ]
        _fill_operating_income_from_revenue_minus_ifrs_by_nature_expenses(rows)
        assert "operating_income_loss" not in rows[0]

    def test_other_operating_income_expense_defaults_to_zero_when_absent(self) -> None:
        rows = [
            {
                "symbol": "SOMEFILER",
                "fiscal_year": 2024,
                "revenues": 1_000.0,
                "cost_of_revenue": 100.0,
                "employee_benefits_expense": 200.0,
                "depreciation_and_amortization": 50.0,
            }
        ]
        _fill_operating_income_from_revenue_minus_ifrs_by_nature_expenses(rows)
        assert rows[0]["operating_income_loss"] == 1_000.0 - 100.0 - 200.0 - 50.0


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
    loader._sec_client.symbol_to_cik.return_value = "0001836470"
    return loader


class TestApplyCustomIncomeExtensionsStagesSportRightsKeyNegated:
    def test_custom_sport_rights_expense_staged_negated(self) -> None:
        loader = _make_income_loader()
        with (
            patch.object(
                ConsolidatedFinancialStatementsLoader.__mro__[1],
                "fetch_incremental",
                return_value=[
                    {
                        "symbol": "SRAD",
                        "fiscal_year": 2024,
                        "fiscal_period": "FY",
                        "operating_income_loss": 453_983_128.32,
                    },
                ],
            ),
            patch(
                "loaders.helpers.financial_statements_custom_extension_fallbacks."
                "fetch_custom_operating_expense_currency_aware",
                return_value={2024: 366_048_000.0},
            ) as mock_fetch,
        ):
            rows = loader.fetch_incremental("SRAD", since=None)

        mock_fetch.assert_called_once_with("SRAD", loader._sec_client)
        assert rows[0]["custom_extension_sport_rights_expenses"] == -366_048_000.0


class TestTransformSubtractsCustomSportRightsExpenseFromOperatingIncome:
    def test_real_transform_subtracts_sport_rights_from_operating_income(self) -> None:
        loader = _make_income_loader()
        raw_rows = [
            {
                "symbol": "SRAD",
                "fiscal_year": 2024,
                "fiscal_period": "FY",
                "operating_income_loss": 453_983_128.32,
                "custom_extension_sport_rights_expenses": -366_048_000.0,
            }
        ]
        transformed = loader.transform(raw_rows)
        assert transformed[0]["operating_income"] == 453_983_128.32 - 366_048_000.0

    def test_real_transform_never_overwrites_when_custom_value_absent(self) -> None:
        loader = _make_income_loader()
        raw_rows = [
            {"symbol": "AAPL", "fiscal_year": 2024, "fiscal_period": "FY", "operating_income_loss": 100_000_000.0}
        ]
        transformed = loader.transform(raw_rows)
        assert transformed[0]["operating_income"] == 100_000_000.0
