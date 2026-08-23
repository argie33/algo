"""Regression test: verify_loaders_health.py's NULL-rate check must exclude rows already
explained by this codebase's own data_unavailable / {column}_unavailable_reason governance
convention, instead of flagging every raw NULL as a data-quality problem.

BUG FOUND (goal session, "before real money" audit, dig-into-the-logs pass, follow-up to the
market_exposure_pct dead-column fix): live-checked every remaining "High NULL rate" warning
this script produced - dividend_data.declaration_date (31.2%), sec_segment_metrics.segment_count
(37.3%), positioning_metrics/insider_holdings_sec ownership_pct (~25%), company_profile.short_name
(48.4%) - and found 100% of the NULLs in every single case were rows the loader had already
correctly marked data_unavailable=true (a legitimate FPI exemption, non-payer, no-disclosure,
etc.), not unexplained gaps. Fixed by excluding data_unavailable=true rows (and rows with a
populated {column}_unavailable_reason, for the suffix-convention tables) from the NULL count -
confirmed live: 25/34 -> 32/34 healthy loaders, 9 -> 2 warnings, with the 2 remaining being a
genuine staleness issue (load_naaim.py) and an already-assessed-legitimate row-count threshold
(load_buy_sell_daily.py), not tooling noise.
"""

from unittest.mock import MagicMock

from scripts.verify_loaders_health import verify_loader


def _run_verify_loader(table_columns, extra_where_capture):
    """table_columns: ordered list of (name,) tuples as information_schema would return them."""
    config = {
        "output_table": "some_table",
        "date_column": "date",
        "min_rows": 1,
        "critical": False,
    }
    cur = MagicMock()
    cur.fetchone.side_effect = [
        (True,),  # table exists
        (100,),  # row count
        (__import__("datetime").date.today(),),  # MAX(date)
        (0,),  # NULL count for col 1
        (0,),  # NULL count for col 2
        (30,),  # NULL count for col 3 (the one under test)
    ]
    cur.fetchall.return_value = table_columns
    conn = MagicMock()
    conn.cursor.return_value = cur

    verify_loader(conn, "some_loader.py", config)

    for c in cur.execute.call_args_list:
        if "COUNT(*)" in c.args[0] and "IS NULL" in c.args[0]:
            extra_where_capture.append(c.args[0])


class TestDataUnavailableFlagExcludedFromNullCount:
    def test_table_with_data_unavailable_column_excludes_it_from_null_check(self):
        """A table with a data_unavailable column must scope every NULL-count query to
        exclude rows already marked data_unavailable=true."""
        queries: list[str] = []
        _run_verify_loader(
            [("id",), ("some_field",), ("date",), ("data_unavailable",)],
            queries,
        )
        # 'some_field' is among the first 3 checked columns (id, some_field, date); its
        # NULL check must exclude data_unavailable=true rows.
        matching = [q for q in queries if "some_field IS NULL" in q]
        assert matching, f"expected a NULL-count query for some_field, got: {queries}"
        assert "data_unavailable IS NOT TRUE" in matching[0], (
            f"NULL-count query for a table with data_unavailable must exclude already-explained "
            f"rows, got: {matching[0]}"
        )

    def test_table_without_data_unavailable_column_is_unaffected(self):
        """A table with no data_unavailable column at all must not have that clause
        spuriously added (would be a SQL error against a real table)."""
        queries: list[str] = []
        _run_verify_loader(
            [("id",), ("date",), ("plain_field",)],
            queries,
        )
        matching = [q for q in queries if "plain_field IS NULL" in q]
        assert matching
        assert "data_unavailable" not in matching[0]

    def test_column_with_its_own_unavailable_reason_column_excludes_it(self):
        """The {column}_unavailable_reason suffix convention (used on quality_metrics/
        growth_metrics/value_metrics/etc.) must also be excluded, independent of whether
        the table has a table-wide data_unavailable column."""
        queries: list[str] = []
        _run_verify_loader(
            [("id",), ("date",), ("forward_pe",), ("forward_pe_unavailable_reason",)],
            queries,
        )
        forward_pe_queries = [q for q in queries if "forward_pe IS NULL" in q]
        assert forward_pe_queries, f"expected a NULL-count query for forward_pe, got: {queries}"
        assert "forward_pe_unavailable_reason IS NULL" in forward_pe_queries[0], (
            f"NULL-count query for a column with its own _unavailable_reason column must "
            f"exclude explained rows, got: {forward_pe_queries[0]}"
        )
