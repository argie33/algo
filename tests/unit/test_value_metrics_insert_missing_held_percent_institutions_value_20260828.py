"""Regression test: _insert_value_metrics must write held_percent_institutions itself, not
just its unavailable_reason column.

Found live 2026-08-28 in the same audit pass as the other 3 bugs with the same date suffix
(growth_metrics.book_value_growth, quality_metrics.quality_score, and 4 quality_metrics
earnings/quarterly fields - all "ON CONFLICT DO UPDATE SET clause never included a column" bug
class). This one is the most severe: held_percent_institutions_unavailable_reason WAS in the
INSERT column list/VALUES/ON CONFLICT SET, but held_percent_institutions itself - the actual
VALUE - was entirely absent from all three. Live-confirmed 0/5103 universe coverage despite
_build_value_metrics correctly fetching real values from positioning_metrics for the great
majority of symbols (e.g. CSIQ 79.27%, ON/CENX/BRKR 100%) - the value was computed correctly
every single loader run and then silently discarded before it ever reached the database.
"""

from unittest.mock import MagicMock

from loaders.load_value_quality_growth_metrics import ValueQualityGrowthMetricsLoader


def _row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "symbol": "TESTSYM",
        "pe_ratio": None,
        "pb_ratio": None,
        "ps_ratio": None,
        "peg_ratio": None,
        "dividend_yield": None,
        "fcf_yield": None,
        "data_unavailable": False,
        "updated_at": "2026-08-28",
        "held_percent_institutions": 79.27,
        "held_percent_institutions_unavailable_reason": None,
    }
    base.update(overrides)
    return base


class TestInsertValueMetricsWritesHeldPercentInstitutionsValue:
    def test_value_column_present_in_insert_and_update_clause(self) -> None:
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_value_metrics(mock_cur, _row())

        sql = mock_cur.execute.call_args[0][0]
        assert "held_percent_institutions" in sql
        assert "held_percent_institutions = EXCLUDED.held_percent_institutions" in sql, (
            "held_percent_institutions must be in the ON CONFLICT DO UPDATE SET clause, or a "
            "re-run on an existing row won't refresh it"
        )

    def test_column_count_matches_placeholder_and_param_count(self) -> None:
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_value_metrics(mock_cur, _row())

        sql, params = mock_cur.execute.call_args[0]
        start = sql.index("(", sql.index("INSERT INTO value_metrics")) + 1
        end = sql.index(")", start)
        columns = [c.strip() for c in sql[start:end].split(",")]
        assert len(columns) == sql.count("%s") == len(params)

    def test_real_value_lands_at_correct_position(self) -> None:
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_value_metrics(mock_cur, _row(held_percent_institutions=79.27))

        sql, params = mock_cur.execute.call_args[0]
        start = sql.index("(", sql.index("INSERT INTO value_metrics")) + 1
        end = sql.index(")", start)
        columns = [c.strip() for c in sql[start:end].split(",")]

        assert params[columns.index("held_percent_institutions")] == 79.27
        assert params[columns.index("held_percent_institutions_unavailable_reason")] is None

    def test_missing_value_writes_none_with_reason(self) -> None:
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        mock_cur = MagicMock()
        loader._insert_value_metrics(
            mock_cur,
            _row(
                held_percent_institutions=None, held_percent_institutions_unavailable_reason="no_resolved_13f_holdings"
            ),
        )

        sql, params = mock_cur.execute.call_args[0]
        start = sql.index("(", sql.index("INSERT INTO value_metrics")) + 1
        end = sql.index(")", start)
        columns = [c.strip() for c in sql[start:end].split(",")]

        assert params[columns.index("held_percent_institutions")] is None
        assert params[columns.index("held_percent_institutions_unavailable_reason")] == "no_resolved_13f_holdings"


class TestUnavailableMarkerIncludesHeldPercentInstitutions:
    """_unavailable_marker's value_metrics branch had the same two bugs: the value key was
    absent entirely, and the reason was hardcoded to None instead of specific_reason - unlike
    every sibling field in that dict."""

    def test_value_key_present_and_none(self) -> None:
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        marker = loader._unavailable_marker("value_metrics", "TESTSYM", reason="missing_sec_data")
        assert "held_percent_institutions" in marker
        assert marker["held_percent_institutions"] is None

    def test_reason_uses_specific_reason_not_hardcoded_none(self) -> None:
        loader = ValueQualityGrowthMetricsLoader.__new__(ValueQualityGrowthMetricsLoader)
        marker = loader._unavailable_marker("value_metrics", "TESTSYM", reason="missing_sec_data")
        assert marker["held_percent_institutions_unavailable_reason"] == "missing_sec_data"
