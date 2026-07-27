#!/usr/bin/env python3
"""Regression test: income-statement revenue must fall back through every SEC revenue
concept the loader fetches, with the tax-exclusive ASC-606 concept (the standard
net-revenue measure) always winning when more than one is reported.

Previously "RevenueFromContractWithCustomerIncludingAssessedTax" was fetched from SEC
(present in sec_statements.get_income_statement()'s concept list) but never mapped to
the "revenue" output column in load_financial_statements.py's field_mapping - a filer
reporting only the tax-inclusive tag (e.g. some telecom/utility filers that pass
through excise tax) got no revenue value at all, with the fetched data silently
discarded as an "unmapped SEC field" debug log line.
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


def test_tax_inclusive_revenue_used_when_only_concept_reported() -> None:
    loader = _make_loader()
    raw_row = {
        "symbol": "TEST",
        "fiscal_year": 2025,
        "revenue_from_contract_with_customer_including_assessed_tax": 1_000_000,
    }

    transformed = loader.transform([raw_row])

    assert transformed[0]["revenue"] == 1_000_000


def test_tax_exclusive_revenue_wins_when_both_concepts_reported() -> None:
    loader = _make_loader()
    raw_row = {
        "symbol": "TEST",
        "fiscal_year": 2025,
        # Insertion order matches sec_statements.get_income_statement()'s concept-list
        # order: tax-inclusive is fetched (and would appear in the dict) before
        # tax-exclusive, so tax-exclusive's value must be the one that survives.
        "revenue_from_contract_with_customer_including_assessed_tax": 1_000_000,
        "revenue_from_contract_with_customer_excluding_assessed_tax": 900_000,
    }

    transformed = loader.transform([raw_row])

    assert transformed[0]["revenue"] == 900_000


def test_legacy_revenues_concept_still_works_alone() -> None:
    loader = _make_loader()
    raw_row = {"symbol": "TEST", "fiscal_year": 2025, "revenues": 500_000}

    transformed = loader.transform([raw_row])

    assert transformed[0]["revenue"] == 500_000
