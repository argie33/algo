#!/usr/bin/env python3
"""Regression test (2026-08-18, missing factor inputs audit): dividends_paid must fall back
to "DividendsCommonStockCash"/"DividendsCommonStock" when none of the "PaymentsOf*Dividend*"
concepts are reported - live-confirmed on ACGL (Arch Capital)/FRT (Federal Realty)/VSH
(Vishay), all real, currently-paying dividend stocks that never tag any "PaymentsOf*" dividend
concept at all. 19 confirmed real dividend payers universe-wide had NULL dividends_paid in
every annual_cash_flow row before this fix.

Unlike "PaymentsOf*" (always-positive by XBRL convention), "DividendsCommonStockCash" carries
a debit-balance definition and live-confirmed flips sign by filing vintage for the exact same
real dividend program (VSH: negative 2014-2017, positive 2019-2025) - transform() must take the
absolute value so a sign flip can't silently produce a negative payout_ratio/dividend figure
downstream.
"""

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_cash_flow_config


def _make_loader() -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_cash_flow_config("annual")
    loader.table_name = config["table_name"]
    loader.period = "annual"
    loader.statement_type = "cashflow"
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    return loader


def test_dividends_common_stock_cash_used_when_no_payments_of_dividends_concept() -> None:
    loader = _make_loader()
    raw_row = {
        "symbol": "ACGL",
        "fiscal_year": 2025,
        "net_cash_provided_by_used_in_operating_activities": 5_000_000_000,
        "dividends_common_stock_cash": 1_900_000_000,
    }

    transformed = loader.transform([raw_row])

    assert transformed[0]["dividends_paid"] == 1_900_000_000


def test_dividends_common_stock_cash_negative_sign_normalized_to_positive() -> None:
    # Live-confirmed on VSH: pre-2018 filings tag this concept negative for the same real
    # dividend program that later years tag positive.
    loader = _make_loader()
    raw_row = {
        "symbol": "VSH",
        "fiscal_year": 2016,
        "net_cash_provided_by_used_in_operating_activities": 200_000_000,
        "dividends_common_stock_cash": -36_725_000,
    }

    transformed = loader.transform([raw_row])

    assert transformed[0]["dividends_paid"] == 36_725_000


def test_payments_of_dividends_still_wins_when_both_concepts_present() -> None:
    loader = _make_loader()
    raw_row = {
        "symbol": "TEST",
        "fiscal_year": 2025,
        "net_cash_provided_by_used_in_operating_activities": 200_000_000,
        # Insertion order matches sec_statements.get_cash_flow()'s concept-list order:
        # DividendsCommonStockCash is fetched (and would appear in the dict) before
        # PaymentsOfDividends, so the standard/more-reliable concept's value wins on
        # overwrite.
        "dividends_common_stock_cash": 10_500_000,
        "payments_of_dividends": 10_000_000,
    }

    transformed = loader.transform([raw_row])

    assert transformed[0]["dividends_paid"] == 10_000_000
