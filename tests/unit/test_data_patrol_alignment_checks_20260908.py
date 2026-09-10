"""Regression tests for AlignmentChecker (algo/monitoring/data_patrol/checks/alignment.py).

Added 2026-09-08 (/goal score-sanity + CI tie-out completeness sweep): this checker's 5
methods - check_signal_source_alignment, check_signal_data_alignment, check_trade_alignment,
check_score_freshness, check_cross_table_alignment - were confirmed live/wired (called from
AlignmentChecker.run(), itself instantiated in base.py's DataPatrol.run()) but had zero
pytest coverage of any kind, unlike sibling checkers (score_ratio_outliers, tie_out,
statistical_anomaly all have dedicated test files). Mocking style follows
test_score_ratio_outlier_checker_20260907.py (MagicMock cursor, dict rows for DictCursor
compatibility - see test_data_patrol_dictrow_not_dict_subclass.py for why plain dicts are an
acceptable stand-in: they satisfy the same hasattr(row, "get"/"keys") duck-typing this module
checks for, same as a real DictRow).
"""

from datetime import date, timedelta
from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.alignment import AlignmentChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _checker() -> AlignmentChecker:
    return AlignmentChecker(PatrolConfig())


class TestSignalSourceAlignment:
    def test_sources_aligned_logs_info(self) -> None:
        cur = MagicMock()
        cur.fetchone.side_effect = [
            {"max_date": date(2026, 9, 8)},  # sqs max date
            {"max_date": date(2026, 9, 8)},  # buy_sell max date, not older
            {"sqs_count": 500, "buy_sell_count": 500},
        ]
        checker = _checker()
        checker.check_signal_source_alignment(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "info"

    def test_buy_sell_zero_symbols_is_error(self) -> None:
        cur = MagicMock()
        cur.fetchone.side_effect = [
            {"max_date": date(2026, 9, 8)},
            {"max_date": date(2026, 9, 8)},
            {"sqs_count": 500, "buy_sell_count": 0},
        ]
        checker = _checker()
        checker.check_signal_source_alignment(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "error"
        assert checker.results[0].details["buy_sell_count"] == 0

    def test_buy_sell_partial_coverage_is_warn(self) -> None:
        cur = MagicMock()
        cur.fetchone.side_effect = [
            {"max_date": date(2026, 9, 8)},
            {"max_date": date(2026, 9, 8)},
            {"sqs_count": 500, "buy_sell_count": 100},
        ]
        checker = _checker()
        checker.check_signal_source_alignment(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "warn"
        assert checker.results[0].details["coverage_pct"] == 20.0

    def test_no_sqs_data_yet_logs_info_and_returns(self) -> None:
        cur = MagicMock()
        cur.fetchone.side_effect = [{"max_date": None}]
        checker = _checker()
        checker.check_signal_source_alignment(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "info"
        assert cur.execute.call_count == 1

    def test_buy_sell_older_than_sqs_is_warn(self) -> None:
        cur = MagicMock()
        cur.fetchone.side_effect = [
            {"max_date": date(2026, 9, 8)},
            {"max_date": date(2026, 9, 5)},
        ]
        checker = _checker()
        checker.check_signal_source_alignment(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "warn"


class TestSignalDataAlignment:
    def test_all_signals_matched_logs_info(self) -> None:
        cur = MagicMock()
        cur.fetchone.return_value = {"total_signals": 42, "missing_price": 0, "missing_tech": 0}
        checker = _checker()
        checker.check_signal_data_alignment(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "info"

    def test_missing_price_or_tech_is_error(self) -> None:
        cur = MagicMock()
        cur.fetchone.return_value = {"total_signals": 42, "missing_price": 3, "missing_tech": 1}
        checker = _checker()
        checker.check_signal_data_alignment(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "error"
        assert checker.results[0].details["missing_price"] == 3

    def test_no_signals_in_window_skips_silently(self) -> None:
        cur = MagicMock()
        cur.fetchone.return_value = {"total_signals": 0, "missing_price": 0, "missing_tech": 0}
        checker = _checker()
        checker.check_signal_data_alignment(cur)
        assert checker.results == []


class TestTradeAlignment:
    def test_no_orphaned_trades_logs_info(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = []
        checker = _checker()
        checker.check_trade_alignment(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "info"

    def test_orphaned_trades_logged_as_error_with_samples(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = [
            {"trade_id": 1, "symbol": "ABC", "fill_date": date(2026, 9, 1)},
            {"trade_id": 2, "symbol": "XYZ", "fill_date": date(2026, 9, 2)},
        ]
        checker = _checker()
        checker.check_trade_alignment(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "error"
        assert checker.results[0].details["orphaned_trades"] == 2
        assert checker.results[0].details["sample"][0]["symbol"] == "ABC"

    def test_missing_table_is_skipped_not_crashed(self) -> None:
        import psycopg2

        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("relation algo_trades does not exist")
        checker = _checker()
        checker.check_trade_alignment(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "info"


class TestScoreFreshness:
    def test_trend_and_sqs_aligned_with_price_logs_info(self) -> None:
        cur = MagicMock()
        cur.fetchone.return_value = {
            "price_latest": date(2026, 9, 8),
            "trend_latest": date(2026, 9, 8),
            "sqs_latest": date(2026, 9, 8),
        }
        checker = _checker()
        checker.check_score_freshness(cur)
        assert len(checker.results) == 2
        assert all(r.severity == "info" for r in checker.results)

    def test_stale_trend_and_sqs_logs_warn_with_lag_days(self) -> None:
        cur = MagicMock()
        cur.fetchone.return_value = {
            "price_latest": date(2026, 9, 8),
            "trend_latest": date(2026, 9, 8) - timedelta(days=3),
            "sqs_latest": date(2026, 9, 8) - timedelta(days=1),
        }
        checker = _checker()
        checker.check_score_freshness(cur)
        assert len(checker.results) == 2
        assert all(r.severity == "warn" for r in checker.results)
        lag_by_name = {r.target_table: r.details["lag_days"] for r in checker.results}
        assert lag_by_name["trend_template_data"] == 3
        assert lag_by_name["signal_quality_scores"] == 1


class TestCrossTableAlignment:
    def test_all_tables_aligned_logs_info_for_each(self) -> None:
        cur = MagicMock()
        cur.fetchone.return_value = {"symbol_count": 5000}
        cur.fetchall.return_value = [
            {"tbl_name": "technical_data_daily", "cnt": 4900},
            {"tbl_name": "trend_template_data", "cnt": 4900},
            {"tbl_name": "stock_scores", "cnt": 4600},
        ]
        checker = _checker()
        checker.check_cross_table_alignment(cur)
        assert len(checker.results) == 3
        assert all(r.severity == "info" for r in checker.results)

    def test_low_coverage_table_flagged_at_configured_severity(self) -> None:
        cur = MagicMock()
        cur.fetchone.return_value = {"symbol_count": 5000}
        cur.fetchall.return_value = [
            {"tbl_name": "technical_data_daily", "cnt": 1000},  # 20% < 95% -> ERROR
            {"tbl_name": "trend_template_data", "cnt": 4900},
            {"tbl_name": "stock_scores", "cnt": 4600},
        ]
        checker = _checker()
        checker.check_cross_table_alignment(cur)
        tech_result = next(r for r in checker.results if r.target_table == "technical_data_daily")
        assert tech_result.severity == "error"

    def test_zero_baseline_symbols_warns_and_returns_early(self) -> None:
        cur = MagicMock()
        cur.fetchone.return_value = {"symbol_count": 0}
        checker = _checker()
        checker.check_cross_table_alignment(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == "warn"
        # Should not have gone on to run the per-table union query.
        assert cur.execute.call_count == 1


class TestRunExecutesAllFiveChecks:
    def test_run_invokes_all_five_methods_without_crashing(self) -> None:
        cur = MagicMock()
        # A single generic dict response satisfies every fetchone() call shape used above
        # (each method only reads the keys it cares about via .get()).
        cur.fetchone.return_value = {
            "max_date": date(2026, 9, 8),
            "sqs_count": 500,
            "buy_sell_count": 500,
            "total_signals": 10,
            "missing_price": 0,
            "missing_tech": 0,
            "price_latest": date(2026, 9, 8),
            "trend_latest": date(2026, 9, 8),
            "sqs_latest": date(2026, 9, 8),
            "symbol_count": 5000,
        }
        cur.fetchall.side_effect = [
            [],  # check_trade_alignment: no orphaned trades
            [
                {"tbl_name": "technical_data_daily", "cnt": 4900},
                {"tbl_name": "trend_template_data", "cnt": 4900},
                {"tbl_name": "stock_scores", "cnt": 4600},
            ],  # check_cross_table_alignment: per-table union counts
        ]
        checker = _checker()
        results = checker.run(cur)
        assert isinstance(results, list)
        assert all(r.severity != "error" for r in results)
