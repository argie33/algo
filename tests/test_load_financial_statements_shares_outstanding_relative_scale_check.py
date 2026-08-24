#!/usr/bin/env python3
"""Regression test for the 2026-08-21 fix (same session, follow-up to the absolute-floor
fix in test_load_financial_statements_shares_outstanding_scale_floor.py): the fixed
100,000-share floor only catches the "reported in thousands, never converted" XBRL scale
bug for SMALLER companies - a large-cap's real share count divided by 1000 can easily
still clear 100,000.

Bulk cross-check of annual_income_statement.earnings_per_share against
net_income/shares_outstanding_basic surfaced 891 rows where the implied EPS is ~1,000x
the reported EPS. Live-confirmed NTNX (Nutanix) FY2025 exactly this way:
shares_outstanding_basic=267,479 (passes the 100k floor) vs company_info_sec's
independently-extracted 270,320,509 (real value, ~1010x higher).

Fix: cross-check shares_outstanding_basic/diluted against company_info_sec.shares_outstanding
(the same independent source load_sec_valuations.py's own 20x scale-mismatch guard already
trusts) whenever available, in addition to the absolute floor.
"""

from unittest.mock import MagicMock, patch

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


def _patch_company_info_sec(rows):
    """rows: list of (symbol, shares_outstanding) tuples returned by the cross-check query."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cursor
    mock_ctx.__exit__.return_value = False
    return patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx)


class TestSharesOutstandingRelativeScaleCheck:
    def test_ntnx_shaped_thousands_scale_error_rejected(self):
        """NTNX-shaped fixture: shares_outstanding_basic clears the absolute 100k floor
        but disagrees with company_info_sec by ~1000x - must be rejected."""
        loader = _make_loader()
        raw_row = {
            "symbol": "NTNX",
            "fiscal_year": 2025,
            "revenues": 2_150_000_000,
            "weighted_average_number_of_shares_outstanding_basic": 267_479,
        }

        with _patch_company_info_sec([("NTNX", 270_320_509)]):
            transformed = loader.transform([raw_row])

        assert transformed[0].get("shares_outstanding_basic") is None

    def test_agreeing_value_not_rejected(self):
        """A shares_outstanding_basic value that genuinely agrees with company_info_sec
        (within 20x) must pass through untouched - the cross-check must not over-reject."""
        loader = _make_loader()
        raw_row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "revenues": 400_000_000_000,
            "weighted_average_number_of_shares_outstanding_basic": 15_500_000_000,
        }

        with _patch_company_info_sec([("AAPL", 15_400_000_000)]):
            transformed = loader.transform([raw_row])

        assert transformed[0]["shares_outstanding_basic"] == 15_500_000_000

    def test_no_reference_available_skips_relative_check(self):
        """When company_info_sec has no row for this symbol, the relative check must be a
        no-op (falls back to the absolute floor alone) rather than erroring."""
        loader = _make_loader()
        raw_row = {
            "symbol": "NOCIS",
            "fiscal_year": 2025,
            "revenues": 500_000_000,
            "weighted_average_number_of_shares_outstanding_basic": 50_000_000,
        }

        with _patch_company_info_sec([]):
            transformed = loader.transform([raw_row])

        assert transformed[0]["shares_outstanding_basic"] == 50_000_000

    def test_db_lookup_failure_is_non_fatal(self):
        """If the company_info_sec cross-check query itself fails, transform() must not
        crash - it should proceed using only the absolute floor."""
        loader = _make_loader()
        raw_row = {
            "symbol": "ERRSYM",
            "fiscal_year": 2025,
            "revenues": 500_000_000,
            "weighted_average_number_of_shares_outstanding_basic": 50_000_000,
        }

        with patch("loaders.load_financial_statements.DatabaseContext", side_effect=RuntimeError("db down")):
            transformed = loader.transform([raw_row])

        assert transformed[0]["shares_outstanding_basic"] == 50_000_000
