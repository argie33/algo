"""Regression test: quality_metrics.ebitda_unavailable_reason must actually be written.

Found live 2026-07-27: migration 124 added this column and one-time-backfilled it to
'missing_sec_data' for rows where ebitda was NULL at the time, but
_insert_quality_metrics()'s INSERT/ON CONFLICT UPDATE never included the column in its
column list or VALUES tuple - so every subsequent write updated `ebitda` with a real,
fresh value while leaving `ebitda_unavailable_reason` permanently frozen at its
migration-time value. Confirmed live: TSLA had a real ebitda of $4.355B and a correct
ebitda_margin, but ebitda_unavailable_reason='missing_sec_data' regardless - every API/
dashboard consumer reading that reason field would incorrectly treat real EBITDA data as
unavailable for essentially the whole universe (100% of quality_metrics rows).
"""

from unittest.mock import MagicMock

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _row(ebitda=4_355_000_000.0, ebitda_unavailable_reason=None):
    return {
        "symbol": "TSLA",
        "roe": 10.0,
        "roa": 5.0,
        "operating_margin": 8.0,
        "net_margin": 7.0,
        "debt_to_equity": 0.5,
        "data_unavailable": False,
        "reason": None,
        "updated_at": "2026-07-27",
        "ebitda": ebitda,
        "ebitda_unavailable_reason": ebitda_unavailable_reason,
        "ebitda_margin": 4.59,
    }


class TestInsertQualityMetricsWritesEbitdaUnavailableReason:
    def test_column_present_in_insert_statement(self):
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_quality_metrics(mock_cur, _row())

        sql = mock_cur.execute.call_args[0][0]
        assert "ebitda_unavailable_reason" in sql, (
            "ebitda_unavailable_reason must be in the INSERT column list - omitting it means "
            "the column never gets updated and stays frozen at whatever it was before"
        )
        assert "ebitda_unavailable_reason = EXCLUDED.ebitda_unavailable_reason" in sql, (
            "must also be in the ON CONFLICT DO UPDATE SET clause, or a re-run on an "
            "existing row still won't refresh it"
        )

    def _column_order(self, sql: str) -> list[str]:
        # Column list is the parenthesized block right after "INSERT INTO quality_metrics".
        start = sql.index("(", sql.index("INSERT INTO quality_metrics")) + 1
        end = sql.index(")", start)
        return [c.strip() for c in sql[start:end].split(",")]

    def test_real_ebitda_writes_none_reason_at_correct_position(self):
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_quality_metrics(mock_cur, _row(ebitda=4_355_000_000.0, ebitda_unavailable_reason=None))

        sql, params = mock_cur.execute.call_args[0]
        columns = self._column_order(sql)
        assert len(columns) == len(params), "column list and params tuple must be the same length"
        idx = columns.index("ebitda_unavailable_reason")
        assert params[idx] is None
        assert params[columns.index("ebitda")] == 4_355_000_000.0

    def test_missing_ebitda_writes_missing_sec_data_reason_at_correct_position(self):
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_quality_metrics(mock_cur, _row(ebitda=None, ebitda_unavailable_reason="missing_sec_data"))

        sql, params = mock_cur.execute.call_args[0]
        columns = self._column_order(sql)
        idx = columns.index("ebitda_unavailable_reason")
        assert params[idx] == "missing_sec_data"
        assert params[columns.index("ebitda")] is None
