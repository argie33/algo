"""Regression test for the 2026-09-03 quarterly_row_orphaned_annual_duplicate categorization,
added alongside a one-time direct correction of 8 quarterly_income_statement Q1 rows
(AMTB/BGC/GPOR/KOP/PNR, symbol+fiscal_year pairs) hand-verified to be whole-annual-fact
duplicates from an old extraction bug.

See [[quarterly_duration_fact_comparative_fp_aliasing_residual_10sym_20260903]]: live
re-extraction confirmed the current code no longer produces a Q1 fact for these exact periods
at all, so a normal backfill can never reach and force-null them via the existing
_reject_stale_all_none_annual_row guard - a direct data correction was the only path, matching
`49b5569f8`'s original 293-symbol correction precedent.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_quarterly_row_orphaned_annual_duplicate_categorizes_as_missing_sec_data():
    assert scores_mod._categorize_reason("quarterly_row_orphaned_annual_duplicate") == "Missing SEC/XBRL data"
