"""Regression tests for the 2026-08-21 goal-session findings (user question: "is missing
data really missing, or are we doing it wrong again? what about implausible values?"):

1. _coverage_order_col picked the first *existing* candidate column (date/fiscal_year/
   updated_at/created_at) without checking it was ever populated. earnings_calendar has a
   `fiscal_year` column (never populated - the loader uses eps_estimate/actual_eps, not
   fiscal_year) that outranked `updated_at`. With every row tied on NULL fiscal_year,
   `DISTINCT ON (symbol) ORDER BY fiscal_year DESC` returned an arbitrary row per symbol
   instead of the real latest one - live-reproduced: symbol A had a fresh real row from
   today (updated_at 2026-08-21 06:10, eps_estimate populated) but the report picked a
   stale, already self-healed fetch_error row from 9 days earlier instead. This inflated
   the live "Scores Data Coverage" dashboard's earnings_calendar gap count by more than
   2x (1,379 reported vs. 645 real, live-verified against the local DB).

2. Three real reason strings (no_sic_code_available/sic_code_unmapped from
   load_company_profile.py, currency_conversion_bug_remediation_20260819 - an orphaned
   remediation marker with zero remaining code references) were never wired into
   _COVERAGE_CATEGORY_RULES and fell through to "Other (errors / excluded)" (248 live
   rows combined) despite having clear, legitimate root causes.
"""

import importlib
from unittest.mock import MagicMock

scores_mod = importlib.import_module("lambda.api.routes.scores")


def _cur_with_counts(*counts: int) -> MagicMock:
    cur = MagicMock()
    cur.fetchone.return_value = counts
    return cur


class TestCoverageOrderColSkipsUnpopulatedColumns:
    def test_skips_fiscal_year_when_entirely_null(self):
        """The earnings_calendar case: fiscal_year exists but 0 rows have it set."""
        cur = _cur_with_counts(0, 100, 100)  # fiscal_year=0, updated_at/created_at populated
        order_col = scores_mod._coverage_order_col(
            cur, "earnings_calendar", {"symbol", "fiscal_year", "updated_at", "created_at"}
        )
        assert order_col == "updated_at"

    def test_still_prefers_fiscal_year_when_populated(self):
        """Real statement tables (annual/quarterly_income_statement, sec_segment_info)
        have fiscal_year on every row - must not regress those."""
        cur = _cur_with_counts(100, 100, 100)
        order_col = scores_mod._coverage_order_col(
            cur, "annual_income_statement", {"symbol", "fiscal_year", "updated_at", "created_at"}
        )
        assert order_col == "fiscal_year"


class TestPreviouslyUnmappedReasonsCategorized:
    def test_sic_classification_gaps_categorize_as_missing_sec_xbrl(self):
        for reason in ("no_sic_code_available", "sic_code_unmapped:7200"):
            assert scores_mod._categorize_reason(reason) == "Missing SEC/XBRL data", (
                f"{reason!r} categorized as {scores_mod._categorize_reason(reason)!r}"
            )

    def test_currency_conversion_remediation_marker_categorizes_as_missing_sec_xbrl(self):
        assert scores_mod._categorize_reason("currency_conversion_bug_remediation_20260819") == "Missing SEC/XBRL data"
