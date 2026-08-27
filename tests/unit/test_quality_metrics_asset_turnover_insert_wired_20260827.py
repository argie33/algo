"""Regression test: quality_metrics.asset_turnover must actually be written by
_insert_quality_metrics().

Found live 2026-08-27: asset_turnover was added to quality_score's composite (scored, 7 of
113 nominal weight) and to the `metrics` dict `_compute_quality_metrics()` builds, and
migration 1241 added the DB column - but the INSERT/ON CONFLICT UPDATE column list in
_insert_quality_metrics() was never updated to include it. Same bug class as
ebitda_unavailable_reason's 2026-07-27 incident (see
test_quality_metrics_ebitda_unavailable_reason_wired.py) - a computed value that silently
never reaches the database. Confirmed live: after a full scores refresh (5100/5100 loaded, 0
failed), `SELECT count(asset_turnover) FROM quality_metrics` was 0 of 5191 rows despite
quality_score itself (which the missing field feeds into) being populated for 4974 rows.
"""

from unittest.mock import MagicMock

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _row(asset_turnover=85.5, asset_turnover_unavailable_reason=None):
    return {
        "symbol": "TSLA",
        "roe": 10.0,
        "roa": 5.0,
        "operating_margin": 8.0,
        "net_margin": 7.0,
        "debt_to_equity": 0.5,
        "data_unavailable": False,
        "reason": None,
        "updated_at": "2026-08-27",
        "asset_turnover": asset_turnover,
        "asset_turnover_unavailable_reason": asset_turnover_unavailable_reason,
    }


class TestInsertQualityMetricsWritesAssetTurnover:
    def test_column_present_in_insert_statement(self):
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_quality_metrics(mock_cur, _row())

        sql = mock_cur.execute.call_args[0][0]
        assert "asset_turnover" in sql, (
            "asset_turnover must be in the INSERT column list - omitting it means the "
            "column never gets updated and stays permanently NULL"
        )
        assert "asset_turnover = EXCLUDED.asset_turnover" in sql, (
            "must also be in the ON CONFLICT DO UPDATE SET clause, or a re-run on an "
            "existing row still won't populate it"
        )
        assert "asset_turnover_unavailable_reason = EXCLUDED.asset_turnover_unavailable_reason" in sql

    def _column_order(self, sql: str) -> list[str]:
        start = sql.index("(", sql.index("INSERT INTO quality_metrics")) + 1
        end = sql.index(")", start)
        return [c.strip() for c in sql[start:end].split(",")]

    def test_real_value_writes_at_correct_position(self):
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_quality_metrics(mock_cur, _row(asset_turnover=85.5, asset_turnover_unavailable_reason=None))

        sql, params = mock_cur.execute.call_args[0]
        columns = self._column_order(sql)
        assert len(columns) == len(params), "column list and params tuple must be the same length"
        assert params[columns.index("asset_turnover")] == 85.5
        assert params[columns.index("asset_turnover_unavailable_reason")] is None

    def test_missing_value_writes_reason_at_correct_position(self):
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_quality_metrics(
            mock_cur, _row(asset_turnover=None, asset_turnover_unavailable_reason="missing_sec_data")
        )

        sql, params = mock_cur.execute.call_args[0]
        columns = self._column_order(sql)
        assert params[columns.index("asset_turnover")] is None
        assert params[columns.index("asset_turnover_unavailable_reason")] == "missing_sec_data"
