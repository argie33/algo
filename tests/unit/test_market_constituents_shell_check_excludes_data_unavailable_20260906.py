"""Regression test (goal session 2026-09-06, SEC/XBRL missing-data campaign) for
load_market_constituents.py's SIC=6770 blank-check-shell reconciliation query: the
NOT EXISTS (... annual_income_statement ... revenue > 0 ...) check had no data_unavailable
filter at all, same stray-value bug class fixed across the rest of this cascade.

A disclaimed row's leftover stray non-NULL revenue value would make the EXISTS subquery match,
wrongly treating a symbol as having real reported revenue and skipping it from deactivation -
i.e. a genuine blank-check shell could stay active in the universe because of a stray value on
a row SEC itself flagged as unreliable. Fixed by requiring
`ais.data_unavailable IS NOT TRUE` alongside the existing revenue > 0 check.

A mocked cursor can't exercise Postgres's real WHERE evaluation, so - matching this cascade's
established sibling tests - this asserts the query text itself contains the exclusion clause.
"""

from pathlib import Path

_SOURCE = Path("loaders/load_market_constituents.py").read_text(encoding="utf-8")


class TestShellReconciliationExcludesDataUnavailable:
    def test_revenue_existence_check_excludes_data_unavailable(self) -> None:
        anchor = "SELECT 1 FROM annual_income_statement ais"
        assert anchor in _SOURCE
        idx = _SOURCE.index(anchor)
        clause = _SOURCE[idx : idx + 300]
        assert "ais.data_unavailable IS NOT TRUE" in clause
