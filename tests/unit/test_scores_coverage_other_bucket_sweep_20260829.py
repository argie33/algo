"""Regression test for the 2026-08-29 "Other" bucket sweep (goal session, coverage-
categorization audit): live-queried lambda/api/routes/scores.py's own _get_scores_coverage()
output and found 8 reason strings covering 6,974 of the "Other (errors / excluded)" bucket's
7,268 live rows (96%) had never been wired into _COVERAGE_CATEGORY_RULES - the same silent-
fallthrough bug class as test_scores_coverage_8k_no_filings_categorization_20260821.py and its
neighbors.

Largest single contributor: the whole-sentence growth_metrics.reason
"Insufficient historical data: ... could not be computed" (2,240 rows) - a full sentence, not a
snake_case code, so _categorize_reason's `base = reason.split(":")[0]` never matched anything;
needed a startswith rule, not a set-literal entry.

After this fix, live re-query of _get_scores_coverage() confirmed "Other (errors / excluded)"
dropped from 7,268 to 114 rows (98.4% reduction) with the removed rows landing exactly where
expected: +198 Missing SEC/XBRL data, +2,419 Insufficient history, +4,537 Legitimate / not
applicable.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


class TestGrowthUndefinedFamily:
    """load_value_quality_growth_metrics.py's _growth_reason() has 4 branches - sign_change
    was already mapped; share_count_discontinuity/immaterial_prior_year_base were not."""

    def test_growth_undefined_share_count_discontinuity_is_legitimate(self):
        assert (
            scores_mod._categorize_reason("growth_undefined_share_count_discontinuity") == "Legitimate / not applicable"
        )

    def test_immaterial_prior_year_base_is_legitimate(self):
        assert scores_mod._categorize_reason("immaterial_prior_year_base") == "Legitimate / not applicable"


class TestFpiSharesExcludedDomesticOnly:
    def test_fpi_shares_excluded_domestic_only_is_legitimate(self):
        assert scores_mod._categorize_reason("fpi_shares_excluded_domestic_only") == "Legitimate / not applicable"


class TestNegativeCapitalEmployed:
    def test_negative_capital_employed_is_legitimate(self):
        # Same "ratio mathematically undefined" family as negative_invested_capital/
        # negative_book_value, just for ROCE instead of ROIC/P-B.
        assert scores_mod._categorize_reason("negative_capital_employed") == "Legitimate / not applicable"


class TestCompanyInfoSecSharesOutstandingReasons:
    """load_company_info_sec.py's 3 shares_outstanding_unavailable_reason values - the FPI one
    (fpi_shares_excluded_domestic_only) is a permanent exemption, the other 2 are real SEC data
    gaps."""

    def test_no_annual_report_filing_is_missing_sec_data(self):
        assert scores_mod._categorize_reason("no_annual_report_filing") == "Missing SEC/XBRL data"

    def test_shares_outstanding_not_in_xbrl_or_filing_text_is_missing_sec_data(self):
        assert scores_mod._categorize_reason("shares_outstanding_not_in_xbrl_or_filing_text") == "Missing SEC/XBRL data"


class TestInsufficientCompleteness:
    def test_insufficient_completeness_is_insufficient_history(self):
        assert scores_mod._categorize_reason("insufficient_completeness") == "Insufficient history"


class TestInsufficientHistoricalDataSentence:
    """The whole-sentence growth_metrics.reason marker, not a snake_case code - exercises the
    startswith rule, not the set-literal lookup."""

    def test_full_sentence_categorizes_as_insufficient_history(self):
        reason = "Insufficient historical data: book_value_growth, eps_growth_1y, eps_growth_3y, eps_growth_5y, revenue_growth_1y, revenue_growth_3y, revenue_growth_5y could not be computed"
        assert scores_mod._categorize_reason(reason) == "Insufficient history"

    def test_prefix_alone_is_sufficient(self):
        assert (
            scores_mod._categorize_reason("Insufficient historical data: x could not be computed")
            == "Insufficient history"
        )
