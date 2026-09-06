"""Regression test (goal session 2026-09-06, SEC/XBRL missing-data campaign) for four
shares-outstanding fallback-tier queries in sec_valuations_shares.py that read
annual_income_statement with NO `data_unavailable` filter at all - the same stray-value bug
class already fixed elsewhere in this cascade (see test_sec_valuations_excludes_data_unavailable_rows.py
and MEMORY.md's sec_xbrl_anchor_query_disclaimed_row_wrong_values_fixed_20260905): a row flagged
data_unavailable=TRUE can still carry a leftover non-NULL shares_outstanding_basic/diluted/dei
value that was never nulled when the row was flagged, so an unfiltered query silently picks it
up as if it were real, audited data.

These four queries were introduced by the 2026-09-05 file-size-ratchet decomposition of
load_sec_valuations.py into loaders/helpers/sec_valuations_shares.py - AFTER the original
finance-accuracy audit swept every anchor query for this exact bug class, so this newly-extracted
file was never covered by that sweep. Fixed by adding `AND data_unavailable IS NOT TRUE` to all
four (the "freshest fiscal year" override, the "older fiscal year" fallback, the diluted-shares
fallback, and the dei cover-page fallback).

A mocked cursor can't exercise Postgres's real WHERE evaluation, so - matching the sibling test's
approach - this asserts the query text itself still contains the exclusion clause, guarding
against a future edit reverting it.
"""

import inspect

from loaders.helpers.sec_valuations_shares import SharesOutstandingResolutionMixin


def _source() -> str:
    return inspect.getsource(SharesOutstandingResolutionMixin._resolve_shares_outstanding)


class TestSharesOutstandingQueriesExcludeDataUnavailable:
    def test_freshest_fiscal_year_override_query_excludes_data_unavailable(self) -> None:
        src = _source()
        assert "SELECT shares_outstanding_basic, fiscal_year FROM annual_income_statement" in src, (
            "freshest-fiscal-year override query text changed - update this test's anchor string"
        )
        idx = src.index("SELECT shares_outstanding_basic, fiscal_year FROM annual_income_statement")
        clause = src[idx : idx + 400]
        assert "data_unavailable IS NOT TRUE" in clause

    def test_older_fiscal_year_fallback_query_excludes_data_unavailable(self) -> None:
        src = _source()
        assert "SELECT shares_outstanding_basic FROM annual_income_statement" in src
        idx = src.index("SELECT shares_outstanding_basic FROM annual_income_statement")
        clause = src[idx : idx + 300]
        assert "data_unavailable IS NOT TRUE" in clause

    def test_diluted_shares_fallback_query_excludes_data_unavailable(self) -> None:
        src = _source()
        assert "SELECT shares_outstanding_diluted FROM annual_income_statement" in src
        idx = src.index("SELECT shares_outstanding_diluted FROM annual_income_statement")
        clause = src[idx : idx + 300]
        assert "data_unavailable IS NOT TRUE" in clause

    def test_dei_cover_page_fallback_query_excludes_data_unavailable(self) -> None:
        src = _source()
        assert "SELECT shares_outstanding_dei, fiscal_year FROM annual_income_statement" in src
        idx = src.index("SELECT shares_outstanding_dei, fiscal_year FROM annual_income_statement")
        clause = src[idx : idx + 400]
        assert "data_unavailable IS NOT TRUE" in clause
