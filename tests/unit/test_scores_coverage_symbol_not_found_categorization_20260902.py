"""Regression test (2026-09-02, SEC/XBRL missing-data sweep): "symbol_not_found" was sitting
in "Other (errors / excluded)" as a bare set literal with no explanation. Repo-wide grep of
every write site (load_sec_segment_info.py's _handle_symbol_not_found and
load_current_reports_8k.py's CIK-lookup branch) shows both mean exactly "no SEC CIK found for
this symbol" - the identical fact "cik_not_found" already captures, just a different literal
from two specific loaders. Was mislabeled as an unexplained "Other" error (53 live
sec_segment_info rows + 17 live current_reports_8k rows).
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_symbol_not_found_categorizes_with_cik_not_found():
    assert scores_mod._categorize_reason("symbol_not_found") == "Missing SEC/XBRL data"
    assert scores_mod._categorize_reason("cik_not_found") == "Missing SEC/XBRL data"
