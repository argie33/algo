#!/usr/bin/env python3
"""Regression test for the 2026-08-21 fix (goal session - broad shares_outstanding
cross-check audit, follow-up to the BRK.A/HEI dual-class fix): SEC's companyfacts REST
API does NOT always normalize a filer's inline-XBRL scale= attribute before exposing the
"val" field.

Live-confirmed against HUB Group's real companyfacts JSON (CIK 0000940942):
WeightedAverageNumberOfSharesOutstandingBasic for FY2025Q3 is tagged val=60066 - a real
share count in the tens of millions, reported "in thousands" but never multiplied back up.
~95 active symbols showed this exact ~1,000x-too-small pattern when cross-checked against
company_info_sec.shares_outstanding (an independently-extracted, unaffected source).

load_sec_valuations.py already has its own 20x cross-check against company_info_sec (added
2026-08-20 for the LARK/RPAY case) that happens to catch this before it reaches market_cap,
but the raw shares_outstanding_basic/diluted value stored in annual/quarterly_income_statement
was still confidently wrong. Fixed by rejecting implausibly small values (< 100,000, the same
MIN_PLAUSIBLE_SHARES_OUTSTANDING floor already used in load_company_info_sec.py) rather than
relying on a downstream consumer's guard to always be present.
"""

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_income_statement_config
from utils.bulk_insert_manager import BulkInsertManager


def _make_loader() -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_income_statement_config("annual")
    loader.table_name = config["table_name"]
    loader.period = "annual"
    loader.statement_type = "income"
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    # _record_explicit_null_rejection() (2026-08-23 fix) reads _bulk_insert_mgr.primary_key
    # and appends to _explicit_null_rejections - both normally set in __init__, which this
    # __new__()-based lightweight fixture bypasses.
    loader._bulk_insert_mgr = BulkInsertManager(config["table_name"], config["primary_key"])
    loader._explicit_null_rejections = []
    return loader


def test_implausibly_small_shares_outstanding_basic_rejected() -> None:
    """HUB Group-shaped fixture: a real filer's raw XBRL value reported in thousands,
    unconverted - must be nulled, not stored as-is."""
    loader = _make_loader()
    raw_row = {
        "symbol": "HUBG",
        "fiscal_year": 2025,
        "revenues": 4_500_000_000,
        "weighted_average_number_of_shares_outstanding_basic": 60_066,
    }

    transformed = loader.transform([raw_row])

    assert transformed[0]["shares_outstanding_basic"] is None


def test_implausibly_small_shares_outstanding_diluted_rejected() -> None:
    loader = _make_loader()
    raw_row = {
        "symbol": "JOUT",
        "fiscal_year": 2025,
        "revenues": 500_000_000,
        "weighted_average_number_of_diluted_shares_outstanding": 8_800,
    }

    transformed = loader.transform([raw_row])

    assert transformed[0]["shares_outstanding_diluted"] is None


def test_plausible_shares_outstanding_unaffected() -> None:
    """A real, correctly-scaled share count must pass through untouched."""
    loader = _make_loader()
    raw_row = {
        "symbol": "AAPL",
        "fiscal_year": 2025,
        "revenues": 400_000_000_000,
        "weighted_average_number_of_shares_outstanding_basic": 15_500_000_000,
    }

    transformed = loader.transform([raw_row])

    assert transformed[0]["shares_outstanding_basic"] == 15_500_000_000


def test_none_shares_outstanding_stays_none() -> None:
    """A filer that never tags this concept at all must stay None, not get flagged."""
    loader = _make_loader()
    raw_row = {"symbol": "NOCONCEPT", "fiscal_year": 2025, "revenues": 100_000_000}

    transformed = loader.transform([raw_row])

    assert transformed[0].get("shares_outstanding_basic") is None
