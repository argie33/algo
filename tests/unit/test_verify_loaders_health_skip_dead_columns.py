"""Regression test: verify_loaders_health.py's generic NULL-rate check must not flag a
known-dead/superseded column as if it were a live data quality problem.

BUG FOUND (goal session, "before real money" audit, dig-into-the-logs pass): the NULL-rate
check inspects whichever 3 columns information_schema.columns happens to return first for a
table - for market_exposure_daily that's (id, date, market_exposure_pct), a column the
2026-08-20/22 exposure-model redesign superseded with `exposure_pct` and never wrote to
again. Live-confirmed: exposure_pct is 26/26 populated with real, varying values on the
exact same rows market_exposure_pct shows 0/26 (100% NULL) for - this script was raising a
false "market exposure is completely broken" WARNING on every run for a legacy field, not a
real data gap. Fixed via a per-loader "skip_null_check_columns" config list.
"""

from unittest.mock import MagicMock

from scripts.verify_loaders_health import LOADERS, verify_loader


class TestMarketExposureDeadColumnSkipped:
    def test_market_exposure_pct_is_in_the_skip_list(self):
        config = LOADERS["load_market_exposure_daily.py"]
        assert "market_exposure_pct" in config.get("skip_null_check_columns", ())

    def test_dead_column_never_reaches_the_null_count_query(self):
        """End-to-end: a table whose first 3 columns include the dead column must
        still get 3 REAL columns checked (skipping past it), and must never issue a
        NULL-count query against the skipped column at all."""
        config = {
            "output_table": "market_exposure_daily",
            "date_column": "date",
            "min_rows": 1,
            "critical": False,
            "skip_null_check_columns": ["market_exposure_pct"],
        }

        cur = MagicMock()
        # Query sequence verify_loader() issues, in order:
        # 1) table exists check
        # 2) row count
        # 3) MAX(date) staleness check
        # 4) information_schema.columns (returns id, date, market_exposure_pct, exposure_pct - dead column 3rd)
        # 5..7) NULL-count queries for whichever 3 columns survive the skip filter
        cur.fetchone.side_effect = [
            (True,),  # table exists
            (26,),  # row count
            (__import__("datetime").date.today(),),  # MAX(date) - always fresh, avoid staleness branch
            (0,),  # NULL count for column 1 (id)
            (0,),  # NULL count for column 2 (date)
            (0,),  # NULL count for column 3 (exposure_pct - the real live column)
        ]
        cur.fetchall.return_value = [
            ("id",),
            ("date",),
            ("market_exposure_pct",),  # dead column - must be skipped, not queried for NULLs
            ("exposure_pct",),  # real column - should be checked instead
        ]
        conn = MagicMock()
        conn.cursor.return_value = cur

        verify_loader(conn, "load_market_exposure_daily.py", config)

        null_count_queries = [
            c.args[0] for c in cur.execute.call_args_list if "IS NULL" in c.args[0] and "COUNT" in c.args[0]
        ]
        assert not any("market_exposure_pct" in q for q in null_count_queries), (
            f"skip_null_check_columns did not prevent a NULL-count query against the dead column: {null_count_queries}"
        )
        assert any("exposure_pct" in q and "market_exposure_pct" not in q for q in null_count_queries), (
            "expected the real exposure_pct column to be checked once the dead column was skipped"
        )
