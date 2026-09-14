"""Regression test for the BENF (Beneficient) revenue-substitution bug (2026-09-14,
quarantine-backlog continuation).

Live-confirmed via BENF's real SEC companyfacts JSON: BENF is a trust-structure filer whose
real annual "Revenues" legitimately goes negative from fair-value losses (-$98.696M for
FY2024). resolve_revenue_total_candidate correctly rejects that negative value (revenue is
never negative in this schema's convention), but before this fix it did so silently - leaving
`row["revenue"]` unset - which let sec_base.py's fallback-only single-line concepts
(InterestIncomeOperating/InterestAndDividendIncomeOperating) treat "revenue" as genuinely
missing and substitute their own much-smaller positive sub-line ($457,000) as if it were the
total, understating a real ~$99M loss as if BENF had almost no revenue at all.

Fix: a rejected negative candidate now records a "negative_total_rejected" marker in
`revenue_total_source[db_field]` so sec_base.py's fallback-only check (loaders/helpers/
sec_base.py, same read site as the `db_field in row` check) can tell a genuine total already
exists for this filer/year and must not let a partial sub-line stand in for it.
"""

from loaders.helpers.sec_revenue_total_resolution import resolve_revenue_total_candidate


class TestRevenueTotalNegativeRejectedMarker:
    def test_negative_value_sets_rejection_marker_but_not_row(self):
        row: dict[str, object] = {}
        best: dict[str, float] = {}
        source: dict[str, str] = {}

        resolve_revenue_total_candidate("revenues", -98_696_000.0, "revenue", row, best, source)

        assert "revenue" not in row
        assert "revenue" not in best
        assert source["revenue"] == "negative_total_rejected"

    def test_marker_does_not_block_a_later_real_positive_candidate(self):
        """A negative "revenues" fact followed by a real positive revenue-family concept
        (e.g. a filer tagging both "revenues" and "sales_revenue_net" for the same year) must
        still let the positive candidate win normally - the marker is not a permanent lock."""
        row: dict[str, object] = {}
        best: dict[str, float] = {}
        source: dict[str, str] = {}

        resolve_revenue_total_candidate("revenues", -98_696_000.0, "revenue", row, best, source)
        resolve_revenue_total_candidate("sales_revenue_net", 5_000_000.0, "revenue", row, best, source)

        assert row["revenue"] == 5_000_000.0
        assert source["revenue"] == "sales_revenue_net"

    def test_marker_does_not_get_set_for_non_numeric_value(self):
        """A missing/non-numeric candidate (the ordinary "concept not tagged" case) must not
        be confused with a genuine rejected-negative-total - only a real negative number sets
        the marker."""
        row: dict[str, object] = {}
        best: dict[str, float] = {}
        source: dict[str, str] = {}

        resolve_revenue_total_candidate("revenues", None, "revenue", row, best, source)

        assert "revenue" not in row
        assert "revenue" not in source
