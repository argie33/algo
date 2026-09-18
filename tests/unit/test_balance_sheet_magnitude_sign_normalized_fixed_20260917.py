#!/usr/bin/env python3
"""Regression test (2026-09-17, "fix data patrol/XBRL findings" goal session):
accounts_receivable/goodwill/operating_lease_liability/accounts_payable/current_liabilities/
total_liabilities are always a magnitude under GAAP, never a real negative value - same
debit/credit-balance XBRL sign-flip bug already fixed for the income-statement side
(test_income_statement_magnitude_sign_normalized_fixed_20260916.py), just never extended to
the balance-sheet side.

data_patrol_backlog_report.py's own *_nonnegative checks found this live-verified before any
fix: 25 rows total across annual_balance_sheet/quarterly_balance_sheet, including well-covered
large filers (ETR FY2009 current_liabilities, RELX FY2018 operating_lease_liability) where a
sign-tagging error is far more plausible than the underlying economics.
"""

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_balance_sheet_config


def _make_loader() -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_balance_sheet_config("annual")
    loader.table_name = config["table_name"]
    loader.period = "annual"
    loader.statement_type = "balance"
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    return loader


def test_negative_balance_sheet_magnitude_fields_normalized_to_positive() -> None:
    loader = _make_loader()
    raw_row = {
        "symbol": "TEST",
        "fiscal_year": 2025,
        "accounts_receivable_net_current": -1_000_000,
        "goodwill": -4_214_000,
        "operating_lease_liability": -460_800_000,
        "accounts_payable_current": -949_758_000,
        "liabilities_current": -3_501_219_000,
        "liabilities": -4_597_978_900,
    }

    transformed = loader.transform([raw_row])

    assert transformed[0]["accounts_receivable"] == 1_000_000
    assert transformed[0]["goodwill"] == 4_214_000
    assert transformed[0]["operating_lease_liability"] == 460_800_000
    assert transformed[0]["accounts_payable"] == 949_758_000
    assert transformed[0]["current_liabilities"] == 3_501_219_000
    assert transformed[0]["total_liabilities"] == 4_597_978_900


def test_already_positive_balance_sheet_magnitude_fields_left_unchanged() -> None:
    loader = _make_loader()
    raw_row = {
        "symbol": "TEST",
        "fiscal_year": 2025,
        "goodwill": 4_214_000,
        "liabilities": 4_597_978_900,
    }

    transformed = loader.transform([raw_row])

    assert transformed[0]["goodwill"] == 4_214_000
    assert transformed[0]["total_liabilities"] == 4_597_978_900
