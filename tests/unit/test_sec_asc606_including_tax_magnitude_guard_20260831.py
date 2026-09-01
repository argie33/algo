"""Regression test for the CHTR/HTLD/ANDE non-REIT ASC-606 revenue clobber bug found live
2026-08-31 (goal session: "get all the data we need" full-coverage audit).

The REIT/insurance/depository-institution fallback branches in sec_base.py's transform()
assume "the ASC-606 contract-revenue tag reports a narrow sub-line, not the real total" is an
industry-specific (SIC-coded) failure mode. Live-confirmed false via three ordinary, non-REIT/
insurance/bank filers:

- CHTR (Charter Communications, SIC 4841 cable): real "Revenues" $54.607B/$55.085B/$54.774B
  for FY2023-2025, but RevenueFromContractWithCustomerIncludingAssessedTax reports a much
  narrower same-year figure ($993M/$941M/$889M) that was silently winning via the general
  "last-listed-wins" priority chain - a ~61x understatement.
- HTLD (Heartland Express, SIC 4213 trucking): same shape via the same concept, $58.1M FY2025
  vs. a real ~$863M total.
- ANDE (Andersons, SIC 5153 grain/agribusiness): same shape via the sibling
  ExcludingAssessedTax concept instead, $1.531B FY2025 vs. real "Revenues"=$11.009B (~7x).

Fixed via a magnitude guard: "revenue" may never be shrunk by either ASC-606 concept once a
normal-priority concept (e.g. "revenues") has already populated it. The excluding_assessed_tax
side of the guard additionally checks a tracked `_revenue_source_sec_field` so it still
unconditionally overwrites including_assessed_tax's OWN value (even when smaller) per
test_load_financial_statements_revenue_precedence.py's existing precedence test - see
sec_base.py's comment on the guard for the full reasoning.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


def _make_loader() -> SecEdgarStatementLoader:
    loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
    loader.table_name = "annual_income_statement"
    loader.period = "annual"
    loader.statement_type = "income"
    loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
    loader._field_mapping = {
        "revenues": "revenue",
        "revenue_from_contract_with_customer_including_assessed_tax": "revenue",
        "revenue_from_contract_with_customer_excluding_assessed_tax": "revenue",
        "data_unavailable": "data_unavailable",
        "reason": "reason",
    }
    loader._fallback_only_fields = frozenset()
    loader._reit_only_fallback_fields = frozenset(
        {
            "revenue_from_contract_with_customer_including_assessed_tax",
            "revenue_from_contract_with_customer_excluding_assessed_tax",
        }
    )
    loader._reit_symbols = frozenset()
    loader._insurance_symbols = frozenset()
    loader._depository_institution_symbols = frozenset()
    return loader


def test_chtr_real_revenue_not_shrunk_by_narrow_asc606_including_tax_line() -> None:
    loader = _make_loader()
    row = {
        "symbol": "CHTR",
        "fiscal_year": 2025,
        "revenues": 54_774_000_000.0,
        "revenue_from_contract_with_customer_including_assessed_tax": 889_000_000.0,
    }

    transformed = loader.transform([row])

    assert transformed[0]["revenue"] == 54_774_000_000.0


def test_htld_real_revenue_not_shrunk_by_narrow_asc606_including_tax_line() -> None:
    loader = _make_loader()
    row = {
        "symbol": "HTLD",
        "fiscal_year": 2025,
        "revenues": 863_121_000.0,
        "revenue_from_contract_with_customer_including_assessed_tax": 58_100_000.0,
    }

    transformed = loader.transform([row])

    assert transformed[0]["revenue"] == 863_121_000.0


def test_non_reit_asc606_including_tax_still_wins_when_it_is_the_larger_current_total() -> None:
    """AAPL-shape case: "Revenues" is the stale/smaller tag, ASC-606 IncludingAssessedTax is
    the larger, current one. The magnitude guard must not block this - it only ever blocks a
    SMALLER incoming value, never a larger one."""
    loader = _make_loader()
    row = {
        "symbol": "AAPL",
        "fiscal_year": 2025,
        "revenues": 300_000_000_000.0,
        "revenue_from_contract_with_customer_including_assessed_tax": 391_000_000_000.0,
    }

    transformed = loader.transform([row])

    assert transformed[0]["revenue"] == 391_000_000_000.0


def test_asc606_including_tax_still_wins_when_nothing_populated_revenue_yet() -> None:
    loader = _make_loader()
    row = {
        "symbol": "TEST",
        "fiscal_year": 2025,
        "revenue_from_contract_with_customer_including_assessed_tax": 1_000_000.0,
    }

    transformed = loader.transform([row])

    assert transformed[0]["revenue"] == 1_000_000.0


def test_ande_real_revenue_not_shrunk_by_narrow_asc606_excluding_tax_line() -> None:
    loader = _make_loader()
    row = {
        "symbol": "ANDE",
        "fiscal_year": 2025,
        "revenues": 11_008_928_000.0,
        "revenue_from_contract_with_customer_excluding_assessed_tax": 1_531_075_000.0,
    }

    transformed = loader.transform([row])

    assert transformed[0]["revenue"] == 11_008_928_000.0


def test_excluding_tax_still_wins_over_including_tax_even_when_smaller() -> None:
    """Must NOT regress test_load_financial_statements_revenue_precedence.py's
    test_tax_exclusive_revenue_wins_when_both_concepts_reported: excluding_assessed_tax is
    deliberately preferred over including_assessed_tax regardless of magnitude."""
    loader = _make_loader()
    row = {
        "symbol": "TEST",
        "fiscal_year": 2025,
        "revenue_from_contract_with_customer_including_assessed_tax": 1_000_000.0,
        "revenue_from_contract_with_customer_excluding_assessed_tax": 900_000.0,
    }

    transformed = loader.transform([row])

    assert transformed[0]["revenue"] == 900_000.0


def test_excluding_tax_still_wins_when_it_is_the_larger_current_total() -> None:
    """AAPL-shape case via the excluding_assessed_tax concept."""
    loader = _make_loader()
    row = {
        "symbol": "AAPL",
        "fiscal_year": 2025,
        "revenues": 300_000_000_000.0,
        "revenue_from_contract_with_customer_excluding_assessed_tax": 391_000_000_000.0,
    }

    transformed = loader.transform([row])

    assert transformed[0]["revenue"] == 391_000_000_000.0
