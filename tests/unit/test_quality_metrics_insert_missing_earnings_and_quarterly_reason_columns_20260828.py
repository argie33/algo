"""Regression test: _insert_quality_metrics must write earnings_surprise_avg/eps_growth_
stability/earnings_beat_rate/consecutive_positive_quarters's *_unavailable_reason columns.

Found live 2026-08-28 in the same audit pass as the 3 sibling fixes with the same date suffix.
Root cause is the SAME bug class already fixed once for growth_metrics.book_value_growth_
unavailable_reason (see test_growth_metrics_book_value_growth_unavailable_reason_wired_
20260827.py's own docstring): the INSERT column list, VALUES placeholders, and ON CONFLICT DO
UPDATE SET clause all included earnings_surprise_avg/eps_growth_stability/earnings_beat_rate/
consecutive_positive_quarters (the VALUES), but never their _unavailable_reason counterparts -
so even though _unavailable_marker() and _compute_quality_metrics both correctly compute a real
reason for these fields upstream, it never reached the database. Live-confirmed 1546-3728 rows
per field (out of ~5100) had a real value/reason pair computed but silently dropped, permanently
frozen at whatever the column held before - indistinguishable from a genuine data gap.
"""

from typing import Any
from unittest.mock import MagicMock

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _row(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "symbol": "TESTSYM",
        "roe": None,
        "operating_margin": None,
        "net_margin": None,
        "debt_to_equity": None,
        "data_unavailable": False,
        "updated_at": "2026-08-28",
        "earnings_surprise_avg": None,
        "earnings_surprise_avg_unavailable_reason": "insufficient_history",
        "eps_growth_stability": None,
        "eps_growth_stability_unavailable_reason": "insufficient_history",
        "earnings_beat_rate": None,
        "earnings_beat_rate_unavailable_reason": "insufficient_history",
        "consecutive_positive_quarters": None,
        "consecutive_positive_quarters_unavailable_reason": "insufficient_history",
    }
    base.update(overrides)
    return base


class TestInsertQualityMetricsWritesEarningsAndQuarterlyReasons:
    def test_all_four_reason_columns_present_in_insert_and_update_clause(self) -> None:
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_quality_metrics(mock_cur, _row())

        sql = mock_cur.execute.call_args[0][0]
        for field in [
            "earnings_surprise_avg_unavailable_reason",
            "eps_growth_stability_unavailable_reason",
            "earnings_beat_rate_unavailable_reason",
            "consecutive_positive_quarters_unavailable_reason",
        ]:
            assert field in sql, f"{field} must be in the INSERT column list"
            assert f"{field} = EXCLUDED.{field}" in sql, (
                f"{field} must also be in the ON CONFLICT DO UPDATE SET clause, or a re-run on "
                "an existing row won't refresh it"
            )

    def test_column_count_matches_placeholder_and_param_count(self) -> None:
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_quality_metrics(mock_cur, _row())

        sql, params = mock_cur.execute.call_args[0]
        start = sql.index("(", sql.index("INSERT INTO quality_metrics")) + 1
        end = sql.index(")", start)
        columns = [c.strip() for c in sql[start:end].split(",")]
        assert len(columns) == sql.count("%s") == len(params)

    def test_reason_values_land_at_correct_position(self) -> None:
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_quality_metrics(
            mock_cur,
            _row(
                eps_growth_stability_unavailable_reason="growth_undefined_sign_change",
                earnings_beat_rate=0.75,
                earnings_beat_rate_unavailable_reason=None,
            ),
        )

        sql, params = mock_cur.execute.call_args[0]
        start = sql.index("(", sql.index("INSERT INTO quality_metrics")) + 1
        end = sql.index(")", start)
        columns = [c.strip() for c in sql[start:end].split(",")]

        assert params[columns.index("eps_growth_stability_unavailable_reason")] == "growth_undefined_sign_change"
        assert params[columns.index("earnings_beat_rate")] == 0.75
        assert params[columns.index("earnings_beat_rate_unavailable_reason")] is None
