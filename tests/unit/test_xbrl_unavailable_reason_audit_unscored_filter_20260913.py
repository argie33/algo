"""Regression test for the 2026-09-13 bug fix in scripts/xbrl_unavailable_reason_audit.py's
_headline_symbols(): it was missing xbrl_scored_headline_count.py's own _UNSCORED_TABLES/
_UNSCORED_FACTORS skip, so it counted symbols missing already-descoped/display-only factors
(e.g. positioning_metrics, value_metrics.peg_ratio) as part of the live "Missing SEC/XBRL
data" headline - live-caught inflating the count from the tracked headline's own 126 to 1045
for the exact same live data, despite this function's own docstring claiming identical reused
logic to xbrl_scored_headline_count.py's main().
"""

from unittest.mock import MagicMock, patch


def _make_cursor(rows_by_table: dict[str, list[tuple[str, str]]]) -> MagicMock:
    """A cursor whose fetchall() result depends on which table the most recent
    `FROM "{table}"` query targeted - two queries happen per table (the information_schema
    column-existence probe, then the DISTINCT ON data query)."""
    cur = MagicMock()
    state: dict[str, str | None] = {"table": None}

    def execute(sql: str, params: tuple[str, ...] | None = None) -> None:
        if "information_schema.columns" in sql:
            assert params is not None
            state["table"] = params[0]
        else:
            for table in rows_by_table:
                if f'FROM "{table}"' in sql:
                    state["table"] = table
                    break

    def fetchall() -> list[tuple[str, ...]]:
        table = state["table"]
        if table is None:
            return []
        if "information_schema" in str(cur.execute.call_args[0][0]):
            return [("symbol",), ("fiscal_year",)]
        return list(rows_by_table.get(table, []))

    cur.execute.side_effect = execute
    cur.fetchall.side_effect = fetchall
    return cur


class TestHeadlineSymbolsUnscoredFilter:
    def test_skips_unscored_table_positioning_metrics(self) -> None:
        from scripts import xbrl_unavailable_reason_audit as mod

        reason_columns = [("positioning_metrics", "reason"), ("value_metrics", "pe_ratio_unavailable_reason")]
        rows_by_table = {
            "positioning_metrics": [("AAA", "some_reason")],
            "value_metrics": [("BBB", "no_income_statement")],
        }
        cur = _make_cursor(rows_by_table)

        with (
            patch("scripts.xbrl_scored_headline_count._find_reason_columns", return_value=reason_columns),
            patch("utils.loaders.helpers.get_active_symbols", return_value=["AAA", "BBB"]),
            patch(
                "routes.scores_handlers.coverage_classification._categorize_reason",
                return_value="Missing SEC/XBRL data",
            ),
        ):
            out = mod._headline_symbols(cur)

        assert "AAA" not in out, "positioning_metrics is in _UNSCORED_TABLES and must be skipped"
        assert "BBB" in out

    def test_skips_unscored_factor_value_metrics_peg_ratio(self) -> None:
        from scripts import xbrl_unavailable_reason_audit as mod

        reason_columns = [
            ("value_metrics", "peg_ratio_unavailable_reason"),
            ("value_metrics", "pe_ratio_unavailable_reason"),
        ]
        rows_by_table = {"value_metrics": [("CCC", "some_reason")]}
        cur = _make_cursor(rows_by_table)

        with (
            patch("scripts.xbrl_scored_headline_count._find_reason_columns", return_value=reason_columns),
            patch("utils.loaders.helpers.get_active_symbols", return_value=["CCC"]),
            patch(
                "routes.scores_handlers.coverage_classification._categorize_reason",
                return_value="Missing SEC/XBRL data",
            ),
        ):
            out = mod._headline_symbols(cur)

        # Both reason columns share the same underlying table/rows in this fixture; only the
        # scored pe_ratio column should contribute, not the unscored peg_ratio one.
        assert "CCC" in out
        tables_and_factors = out["CCC"]
        assert not any(column == "peg_ratio_unavailable_reason" for _table, column, _reason in tables_and_factors)
        assert any(column == "pe_ratio_unavailable_reason" for _table, column, _reason in tables_and_factors)
