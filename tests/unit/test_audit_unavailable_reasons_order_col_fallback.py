"""Regression test: scripts/audit_unavailable_reasons.py must fall back to
updated_at/created_at when a table has no date/fiscal_year column.

Bug (found 2026-08-18, live evidence): select_order_col() (formerly inline in main())
only recognized "date"/"fiscal_year" as a "latest row per symbol" ordering column. Any
table using "updated_at"/"created_at" instead - e.g. dividend_data, which has
symbol+created_at+updated_at but neither date nor fiscal_year - got "" back, which is
falsy, so the caller's `if "symbol" in cols and order_col:` branch never taken and the
query silently fell through to an un-deduplicated COUNT(*) over every historical row
instead of one snapshot per symbol. Live-caught: dividend_data's
"no_dividend_xbrl_concepts" reason reported 22,478 (all-history rows) when the real,
deduplicated distinct-symbol count is 3,097 - a 7x inflation in a diagnostic tool meant
to distinguish "widespread real bug" from "legitimate/rare" data gaps.
"""

from scripts.audit_unavailable_reasons import select_order_col


def test_prefers_date_over_everything() -> None:
    assert select_order_col({"symbol", "date", "fiscal_year", "updated_at", "created_at"}) == "date"


def test_prefers_fiscal_year_over_updated_created() -> None:
    assert select_order_col({"symbol", "fiscal_year", "updated_at", "created_at"}) == "fiscal_year"


def test_falls_back_to_updated_at_when_no_date_or_fiscal_year() -> None:
    # This is the exact dividend_data shape that triggered the bug.
    assert select_order_col({"symbol", "created_at", "updated_at"}) == "updated_at"


def test_falls_back_to_created_at_when_only_that_exists() -> None:
    assert select_order_col({"symbol", "created_at"}) == "created_at"


def test_returns_empty_string_when_no_candidate_column_exists() -> None:
    assert select_order_col({"symbol"}) == ""
