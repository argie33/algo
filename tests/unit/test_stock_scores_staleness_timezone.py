#!/usr/bin/env python3
"""Regression test for the 2026-07-27 load_stock_scores.py staleness-timezone fix.

validate_upstream_metrics_ready()'s per-table staleness check read MAX(updated_at) - a
`timestamp without time zone` column written via SQL CURRENT_TIMESTAMP - and mislabeled a
naive result as UTC via `.replace(tzinfo=timezone.utc)`. Same bug class already fixed in
algo/trading/pretrade_checks.py's re-entry cooldown and algo/risk/market_exposure.py's
cache-age check: a naive timestamp from this codebase's DB session convention
(utils/bulk_insert_manager.py) is in the session's local wall-clock timezone, not UTC.
Fixed to resolve the real session timezone via `SHOW timezone` instead of assuming UTC.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

from loaders.load_stock_scores import StockScoresLoader


def _cursor_for_table_sequence(naive_updated_at: datetime, session_tz: str = "America/Chicago") -> MagicMock:
    """Build a mock cursor whose execute/fetchone sequence matches
    validate_upstream_metrics_ready()'s per-table query order (coverage check, then
    staleness check) repeated for each of the 4 required_metric_tables, tracking every
    executed SQL string so the test can assert SHOW timezone was actually issued.

    Note: get_db_timezone() caches its result, so SHOW timezone is only called once."""
    cur = MagicMock()
    executed_sql: list[str] = []

    coverage_row = (100, 100)  # available_count, total_count - well above every min_coverage
    staleness_row = (naive_updated_at,)
    show_tz_row = (session_tz,)

    fetchone_results = []
    # First required metric table: coverage, staleness, SHOW timezone
    fetchone_results.append(coverage_row)
    fetchone_results.append(staleness_row)
    fetchone_results.append(show_tz_row)
    # Remaining 3 required metric tables: coverage, staleness (get_db_timezone cached)
    for _ in range(3):
        fetchone_results.append(coverage_row)
        fetchone_results.append(staleness_row)
    # Optional quality_metrics: coverage only
    fetchone_results.append(coverage_row)

    call_counter = [0]

    def _fetchone():
        if call_counter[0] < len(fetchone_results):
            result = fetchone_results[call_counter[0]]
            call_counter[0] += 1
            return result
        return None

    def _execute(sql: str, *args, **kwargs) -> None:
        executed_sql.append(sql)

    cur.execute.side_effect = _execute
    cur.fetchone.side_effect = _fetchone
    cur._executed_sql = executed_sql
    return cur


class TestStockScoresStalenessTimezone:
    def setup_method(self):
        """Clear the global timezone cache before each test."""
        import utils.db.timezone_utils

        utils.db.timezone_utils._DB_TZ_CACHE = None

    def test_naive_updated_at_resolves_real_session_timezone_not_utc(self):
        naive_updated_at = datetime(2026, 7, 25, 23, 0, 0)  # naive, no tzinfo
        cur = _cursor_for_table_sequence(naive_updated_at, session_tz="America/Chicago")

        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        loader = StockScoresLoader.__new__(StockScoresLoader)
        # Patch DatabaseContext in both modules to use the same mock
        with (
            patch("loaders.load_stock_scores.DatabaseContext", return_value=mock_db_context),
            patch("utils.db.timezone_utils.DatabaseContext", return_value=mock_db_context),
        ):
            loader.validate_upstream_metrics_ready()

        assert "SHOW timezone" in cur._executed_sql, (
            "staleness check must resolve the real DB session timezone instead of "
            "assuming the naive updated_at is already UTC"
        )

    def test_already_aware_updated_at_does_not_query_timezone(self):
        from datetime import timezone as tz

        aware_updated_at = datetime(2026, 7, 25, 23, 0, 0, tzinfo=tz.utc)

        # For aware timestamps, SHOW timezone is not queried, so we don't include it in fetchone results
        fetchone_results = [
            (100, 100),  # coverage table 1
            (aware_updated_at,),  # staleness table 1
        ] * 4 + [(100, 100)]  # coverage quality_metrics

        cur = MagicMock()
        executed_sql = []

        call_counter = [0]

        def _fetchone():
            if call_counter[0] < len(fetchone_results):
                result = fetchone_results[call_counter[0]]
                call_counter[0] += 1
                return result
            return None

        def _execute(sql: str, *args, **kwargs) -> None:
            executed_sql.append(sql)

        cur.execute.side_effect = _execute
        cur.fetchone.side_effect = _fetchone
        cur._executed_sql = executed_sql

        mock_db_context = MagicMock()
        mock_db_context.__enter__ = MagicMock(return_value=cur)
        mock_db_context.__exit__ = MagicMock(return_value=False)

        loader = StockScoresLoader.__new__(StockScoresLoader)
        with patch("loaders.load_stock_scores.DatabaseContext", return_value=mock_db_context):
            loader.validate_upstream_metrics_ready()

        assert "SHOW timezone" not in cur._executed_sql
