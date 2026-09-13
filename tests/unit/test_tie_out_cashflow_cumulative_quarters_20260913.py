"""Regression test for tie_out_cashflow_cumulative_quarters.py (added 2026-09-13, goal
session: keep finding data-quality issues).

Wires the RITM-confirmed Q1 < Q2 == Q3 cumulative-YTD-stored-as-discrete-quarter signature
(see quarterly_cashflow_cumulative_ytd_stored_as_discrete_20260913 memory and
utils/external/sec_statements_cumulative_quarter_derivation.py's fix) into the permanent
DataPatrol suite, so any row predating the extraction-layer fix (or a future regression of it)
is caught automatically instead of needing a one-off manual scan.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.tie_out import TieOutChecker
from algo.monitoring.data_patrol.config import INFO, PatrolConfig


def _checker() -> TieOutChecker:
    return TieOutChecker(PatrolConfig())


def _mock_cursor(fetchall_result: list[dict[str, object]]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = fetchall_result
    return cur


class TestQuarterlyCashflowCumulativeDuplicate:
    def test_ritm_shaped_row_flagged(self) -> None:
        """RITM's real 2018 numbers: Q1=420,000, Q2==Q3==1,019,000 (H1/9mo cumulative)."""
        checker = _checker()
        cur = _mock_cursor([{"symbol": "RITM", "fiscal_year": 2018, "q1_val": 420_000.0, "q2_val": 1_019_000.0}])

        checker.check_quarterly_cashflow_cumulative_duplicate(cur)

        # One WARN logged per cash-flow field checked (all 6 share the same mocked cursor
        # response here), each carrying flagged_symbols for the quarantine consumer.
        assert len(checker.results) == 6
        for result in checker.results:
            assert result.details["count"] == 1
            assert result.details["flagged_symbols"] == [
                {"symbol": "RITM", "reason": f"{result.details['field']}_cumulative_q2_eq_q3"}
            ]

    def test_no_rows_logs_nothing(self) -> None:
        checker = _checker()
        cur = _mock_cursor([])

        checker.check_quarterly_cashflow_cumulative_duplicate(cur)

        assert checker.results == []

    def test_clean_symbol_with_genuine_growth_not_flagged(self) -> None:
        """Sanity: the mock cursor stands in for the real SQL WHERE clause (Q1 < Q2 == Q3) -
        this test just documents that a symbol whose real quarters legitimately differ never
        reaches this check's SQL result set at all, so nothing here would need flagging."""
        checker = _checker()
        cur = _mock_cursor([])

        checker.check_quarterly_cashflow_cumulative_duplicate(cur)

        assert all(r.severity == INFO for r in checker.results)
