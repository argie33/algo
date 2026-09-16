#!/usr/bin/env python3
"""Regression test (2026-09-16, "fix data patrol/XBRL findings" goal session):
interest_expense/depreciation_expense/amortization_expense/research_development_expense/
goodwill_impairment_loss are always a cost/expense magnitude under GAAP, never a real
negative value - same debit-balance XBRL sign-flip bug already fixed for dividends_paid/
stock_based_compensation/common_stock_repurchased on the cashflow side
(test_load_financial_statements_dividends_common_stock_cash.py), just never extended to the
income-statement side.

tie_out_income_statement_nonnegative.py's own docstring found this live-verified before any
fix: 400 negative interest_expense, 51 negative depreciation_expense, 139 negative
amortization_expense, 24 negative research_development_expense, and 46 negative
goodwill_impairment_loss rows in annual_income_statement alone.
"""

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_income_statement_config


def _make_loader() -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_income_statement_config("annual")
    loader.table_name = config["table_name"]
    loader.period = "annual"
    loader.statement_type = "income"
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    return loader


def test_negative_interest_expense_normalized_to_positive_magnitude() -> None:
    loader = _make_loader()
    raw_row = {"symbol": "TEST", "fiscal_year": 2025, "interest_expense": -1_200_000}

    transformed = loader.transform([raw_row])

    assert transformed[0]["interest_expense"] == 1_200_000


def test_negative_depreciation_amortization_goodwill_rd_normalized_to_positive_magnitude() -> None:
    loader = _make_loader()
    raw_row = {
        "symbol": "TEST",
        "fiscal_year": 2025,
        "depreciation": -500_000,
        "amortization_of_intangibles": -250_000,
        "research_and_development_expense": -900_000,
        "goodwill_impairment_loss": -3_000_000,
    }

    transformed = loader.transform([raw_row])

    assert transformed[0]["depreciation_expense"] == 500_000
    assert transformed[0]["amortization_expense"] == 250_000
    assert transformed[0]["research_development_expense"] == 900_000
    assert transformed[0]["goodwill_impairment_loss"] == 3_000_000


def test_already_positive_magnitude_fields_left_unchanged() -> None:
    loader = _make_loader()
    raw_row = {
        "symbol": "TEST",
        "fiscal_year": 2025,
        "interest_expense": 1_200_000,
        "goodwill_impairment_loss": 3_000_000,
    }

    transformed = loader.transform([raw_row])

    assert transformed[0]["interest_expense"] == 1_200_000
    assert transformed[0]["goodwill_impairment_loss"] == 3_000_000
