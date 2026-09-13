"""Regression test for the 2026-09-13 widening of _sweep_derive_missing_q4()
(loaders/helpers/financial_statements_q4_sweeps.py) - goal session: quarterly-revenue-identity
backlog, QCOM live-confirmed.

The original guard only re-derived Q4 revenue/net_income when the existing Q4 row was NULL or
data_unavailable=TRUE. Live-confirmed via QCOM: a stale Q4 row (revenue=$12,252,000,000, an
exact duplicate of that fiscal year's own Q1 value - a leftover artifact of a since-fixed
quarter-labeling bug, not a real Q4 result) sat untouched through a full reload of corrected
Q1-Q3 data, because it was neither NULL nor data_unavailable=TRUE - the sweep silently
protected a provably wrong value from ever being corrected.

Fix: also re-fire whenever the stored Q4 revenue is DISTINCT FROM a freshly computed
FY-(Q1+Q2+Q3) derivation - safe because this identity is exact (not a heuristic, per this
method's own docstring), so any mismatch means the stored value is wrong, regardless of how it
got there.
"""

from unittest.mock import MagicMock, patch

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader


def _make_loader(statement_type: str = "income", period: str = "quarterly") -> ConsolidatedFinancialStatementsLoader:
    return ConsolidatedFinancialStatementsLoader(statement_type=statement_type, period=period)


def _mock_write_context(rowcount: int = 1) -> tuple[MagicMock, MagicMock]:
    mock_cur = MagicMock()
    mock_cur.rowcount = rowcount
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False
    return mock_ctx, mock_cur


class TestQ4SweepSelfHealsStaleNonNullValue:
    def test_derive_sql_refires_on_stale_but_present_q4_value(self) -> None:
        loader = _make_loader(statement_type="income", period="quarterly")
        mock_ctx, mock_cur = _mock_write_context()

        with patch("loaders.load_financial_statements.DatabaseContext", return_value=mock_ctx):
            loader.post_run()

        sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        derive_sqls = [s for s in sqls if "revenue = derived.revenue" in s]
        assert len(derive_sqls) == 1
        sql = derive_sqls[0]

        # The original NULL/data_unavailable guard must still be present (never-write cases
        # that already worked before this widening must keep working).
        assert "q4x.revenue IS NULL" in sql
        assert "q4x.data_unavailable = TRUE" in sql
        # The new self-healing condition: re-derive whenever the stored value disagrees with
        # a fresh FY-(Q1+Q2+Q3) computation, not only when it's missing outright.
        assert "q4x.revenue IS DISTINCT FROM (a.revenue - (q1.revenue + q2.revenue + q3.revenue))" in sql
        # Still bounded by the non-negative-derived-revenue guard - unchanged from before.
        assert "(a.revenue - (q1.revenue + q2.revenue + q3.revenue)) >= 0" in sql
