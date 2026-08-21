"""Regression test: scripts/audit_unavailable_reasons.py must fall back to
updated_at/created_at when a table has no date/fiscal_year column, AND when the
higher-priority candidate column exists but is never populated.

Bug 1 (found 2026-08-18, live evidence): select_order_col() (formerly inline in main())
only recognized "date"/"fiscal_year" as a "latest row per symbol" ordering column. Any
table using "updated_at"/"created_at" instead - e.g. dividend_data, which has
symbol+created_at+updated_at but neither date nor fiscal_year - got "" back, which is
falsy, so the caller's `if "symbol" in cols and order_col:` branch never taken and the
query silently fell through to an un-deduplicated COUNT(*) over every historical row
instead of one snapshot per symbol. Live-caught: dividend_data's
"no_dividend_xbrl_concepts" reason reported 22,478 (all-history rows) when the real,
deduplicated distinct-symbol count is 3,097 - a 7x inflation in a diagnostic tool meant
to distinguish "widespread real bug" from "legitimate/rare" data gaps.

Bug 2 (found 2026-08-21, goal session: "is missing data really missing, or are we doing
it wrong again"): picking the first candidate that merely EXISTS (pre-2026-08-21
behavior) breaks when that column exists but is never populated for a given table -
live-confirmed on earnings_calendar, which has a `fiscal_year` column (ranked above
updated_at) that is NULL on all 450,856 rows. With no real sort key, `DISTINCT ON
(symbol) ORDER BY fiscal_year DESC` ties on every row and Postgres returns an arbitrary
one per symbol - this script reported 663 "fetch_error:RuntimeError" symbols when the
real count (ordering by the column that actually varies, updated_at) was 4; the picked
row for symbol A was a stale, already self-healed error from 9 days earlier while a
fresh real row from today sat right next to it. Fixed by querying each present
candidate's non-null count and picking the first that actually has data.
"""

from unittest.mock import MagicMock

from scripts.audit_unavailable_reasons import select_order_col


def _cur_with_counts(*counts: int) -> MagicMock:
    """Fake cursor whose fetchone() returns the given non-null counts, in the order
    select_order_col queries its candidates."""
    cur = MagicMock()
    cur.fetchone.return_value = counts
    return cur


def test_prefers_date_over_everything() -> None:
    cur = _cur_with_counts(100, 100, 100, 100)  # date, fiscal_year, updated_at, created_at all populated
    assert select_order_col(cur, "some_table", {"symbol", "date", "fiscal_year", "updated_at", "created_at"}) == "date"


def test_prefers_fiscal_year_over_updated_created_when_populated() -> None:
    cur = _cur_with_counts(100, 100, 100)  # fiscal_year, updated_at, created_at all populated
    assert (
        select_order_col(cur, "annual_income_statement", {"symbol", "fiscal_year", "updated_at", "created_at"})
        == "fiscal_year"
    )


def test_skips_fiscal_year_when_entirely_null() -> None:
    """The earnings_calendar case: fiscal_year column exists but is 0/450856 populated."""
    cur = _cur_with_counts(0, 100, 100)  # fiscal_year=0 non-null, updated_at/created_at populated
    assert (
        select_order_col(cur, "earnings_calendar", {"symbol", "fiscal_year", "updated_at", "created_at"})
        == "updated_at"
    )


def test_falls_back_to_updated_at_when_no_date_or_fiscal_year() -> None:
    # This is the exact dividend_data shape that triggered bug 1.
    cur = _cur_with_counts(100, 100)  # updated_at, created_at
    assert select_order_col(cur, "dividend_data", {"symbol", "created_at", "updated_at"}) == "updated_at"


def test_falls_back_to_created_at_when_only_that_exists() -> None:
    cur = _cur_with_counts(100)
    assert select_order_col(cur, "some_table", {"symbol", "created_at"}) == "created_at"


def test_returns_empty_string_when_no_candidate_column_exists() -> None:
    cur = _cur_with_counts()
    assert select_order_col(cur, "some_table", {"symbol"}) == ""


def test_falls_back_to_first_candidate_when_all_candidates_entirely_null() -> None:
    """Degenerate case: every candidate column exists but none is populated (e.g. an
    empty or freshly-created table). Must not raise - returns the highest-priority
    candidate as a last resort, matching the pre-fix contract's behavior of always
    returning *something* when a candidate column exists."""
    cur = _cur_with_counts(0, 0)
    assert select_order_col(cur, "some_table", {"symbol", "updated_at", "created_at"}) == "updated_at"
