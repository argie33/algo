"""Regression test: growth_metrics.book_value_growth_unavailable_reason must actually be written.

Found live 2026-08-27 during a Growth-pillar data-completeness sweep: migration 1242 added
book_value_growth (now the Growth pillar's sole scoring input) plus a matching
book_value_growth_unavailable_reason column, and _compute_growth_metrics correctly computes a
reason (insufficient_history / growth_undefined_sign_change / growth_undefined_share_count_
discontinuity) whenever the value comes back NULL - but _insert_growth_metrics()'s ON CONFLICT
DO UPDATE SET clause never included the reason column (every sibling *_unavailable_reason column
did), so a re-run on an existing row - the case for virtually the whole universe, since
growth_metrics rows predate this migration - updates book_value_growth itself with a fresh value
while leaving book_value_growth_unavailable_reason permanently frozen at NULL. Live-confirmed:
1382 universe symbols had book_value_growth NULL with no reason recorded at all, including cases
that clearly hit the sign-change guard (e.g. AIBZ: BVPS flips negative-to-positive year over
year) - same "reason silently never refreshes" bug class as
test_quality_metrics_ebitda_unavailable_reason_wired.py.
"""

from unittest.mock import MagicMock

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _row(book_value_growth=None, book_value_growth_unavailable_reason=None):
    return {
        "symbol": "AIBZ",
        "revenue_growth_1y": None,
        "eps_growth_1y": -63.7,
        "book_value_growth": book_value_growth,
        "data_unavailable": False,
        "reason": None,
        "updated_at": "2026-08-27",
        "book_value_growth_unavailable_reason": book_value_growth_unavailable_reason,
    }


class TestInsertGrowthMetricsWritesBookValueGrowthUnavailableReason:
    def test_column_present_in_insert_and_update_clause(self):
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_growth_metrics(mock_cur, _row())

        sql = mock_cur.execute.call_args[0][0]
        assert "book_value_growth_unavailable_reason" in sql, (
            "book_value_growth_unavailable_reason must be in the INSERT column list - omitting "
            "it means the column never gets updated and stays frozen at whatever it was before"
        )
        assert "book_value_growth_unavailable_reason = EXCLUDED.book_value_growth_unavailable_reason" in sql, (
            "must also be in the ON CONFLICT DO UPDATE SET clause, or a re-run on an "
            "existing row still won't refresh it"
        )

    def _column_order(self, sql: str) -> list[str]:
        start = sql.index("(", sql.index("INSERT INTO growth_metrics")) + 1
        end = sql.index(")", start)
        return [c.strip() for c in sql[start:end].split(",")]

    def test_sign_change_reason_writes_at_correct_position(self):
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_growth_metrics(
            mock_cur, _row(book_value_growth=None, book_value_growth_unavailable_reason="growth_undefined_sign_change")
        )

        sql, params = mock_cur.execute.call_args[0]
        columns = self._column_order(sql)
        assert len(columns) == len(params), "column list and params tuple must be the same length"
        idx = columns.index("book_value_growth_unavailable_reason")
        assert params[idx] == "growth_undefined_sign_change"
        assert params[columns.index("book_value_growth")] is None

    def test_real_value_writes_none_reason_at_correct_position(self):
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_growth_metrics(mock_cur, _row(book_value_growth=4.2, book_value_growth_unavailable_reason=None))

        sql, params = mock_cur.execute.call_args[0]
        columns = self._column_order(sql)
        idx = columns.index("book_value_growth_unavailable_reason")
        assert params[idx] is None
        assert params[columns.index("book_value_growth")] == 4.2
