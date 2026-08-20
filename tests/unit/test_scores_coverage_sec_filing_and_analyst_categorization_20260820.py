"""Regression test for the 2026-08-20 coverage-categorization audit: several real,
actively-used *_unavailable_reason strings were never wired into
lambda/api/routes/scores.py's _COVERAGE_CATEGORY_RULES, so every symbol carrying them
silently fell through to "Other (errors / excluded)" - the same silent-fallthrough bug class
as test_scores_coverage_foreign_private_issuer_categorization.py and
test_scores_coverage_shares_outstanding_scale_mismatch_categorization.py.

- incomplete_sec_filing_income/balance/cashflow (load_sec_valuations.py,
  load_value_quality_growth_metrics.py): the filer's own SEC filing section is
  incomplete/inconsistent - "Missing SEC/XBRL data", same class as no_income_statement etc.
- no_sec_filings_found (load_earnings_calendar_sec.py): genuine no-SEC-filings-exist case
  (distinct from the old false-positive version of this reason, already fixed 2026-08-19 by
  widening _EARNINGS_BEARING_FORMS) - "Missing SEC/XBRL data".
- companyfacts_api_never_exposes_per_segment_revenue (utils/external/sec_xbrl_segments.py):
  permanent SEC API limitation - "Missing SEC/XBRL data" (same class as the other
  segment-data reasons already there).
- no_earnings_coverage / no_next_earnings_available (load_earnings_calendar.py): same
  underlying fact as no_analyst_coverage, just for a different table - "No analyst coverage".
- no_{period}_{statement_type}_data_in_sec_edgar_reit_or_special_entity
  (loaders/helpers/sec_base.py, built dynamically across 6 period x statement_type
  combinations): the same permanent "REIT/special entity has nothing to report" fact as the
  literal "reit_special_entity" reason already in "Legitimate / not applicable".
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_incomplete_sec_filing_reasons_categorize_as_missing_sec_data():
    for reason in (
        "incomplete_sec_filing_income",
        "incomplete_sec_filing_balance",
        "incomplete_sec_filing_cashflow",
        "no_sec_filings_found",
        "companyfacts_api_never_exposes_per_segment_revenue",
    ):
        assert scores_mod._categorize_reason(reason) == "Missing SEC/XBRL data", (
            f"{reason!r} categorized as {scores_mod._categorize_reason(reason)!r}, not 'Missing SEC/XBRL data'"
        )


def test_earnings_coverage_gaps_categorize_as_no_analyst_coverage():
    for reason in ("no_earnings_coverage", "no_next_earnings_available"):
        assert scores_mod._categorize_reason(reason) == "No analyst coverage", (
            f"{reason!r} categorized as {scores_mod._categorize_reason(reason)!r}, not 'No analyst coverage'"
        )


def test_reit_or_special_entity_reason_family_categorizes_as_legitimate():
    for period in ("annual", "quarterly"):
        for statement_type in ("income", "balance", "cashflow"):
            reason = f"no_{period}_{statement_type}_data_in_sec_edgar_reit_or_special_entity"
            assert scores_mod._categorize_reason(reason) == "Legitimate / not applicable", (
                f"{reason!r} categorized as {scores_mod._categorize_reason(reason)!r}, not "
                "'Legitimate / not applicable'"
            )
