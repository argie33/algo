"""Regression tests for QualityChecker.check_null_anomalies/check_ohlc_sanity
(algo/monitoring/data_patrol/checks/quality.py) and PriceSanityChecker.check_sequence_continuity
(algo/monitoring/data_patrol/checks/price_sanity.py) - 2026-09-08 /goal CI-gap sweep found these
three methods had zero pytest coverage despite being live-wired into their checkers' run().
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.price_sanity import PriceSanityChecker
from algo.monitoring.data_patrol.checks.quality import QualityChecker
from algo.monitoring.data_patrol.config import CRIT, ERROR, INFO, WARN, PatrolConfig


def _quality_checker() -> QualityChecker:
    return QualityChecker(PatrolConfig())


def _price_sanity_checker() -> PriceSanityChecker:
    return PriceSanityChecker(PatrolConfig())


class TestCheckNullAnomalies:
    def test_null_pct_within_threshold_logs_info(self) -> None:
        checker = _quality_checker()
        cur = MagicMock()
        cur.fetchone.return_value = {"today_nulls": 2, "today_total": 5000}
        checker.check_null_anomalies(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_null_pct_above_threshold_logs_error(self) -> None:
        checker = _quality_checker()
        cur = MagicMock()
        cur.fetchone.return_value = {"today_nulls": 500, "today_total": 5000}
        checker.check_null_anomalies(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == ERROR
        assert checker.results[0].details["today_nulls"] == 500

    def test_zero_total_today_skips_silently(self) -> None:
        checker = _quality_checker()
        cur = MagicMock()
        cur.fetchone.return_value = {"today_nulls": None, "today_total": 0}
        checker.check_null_anomalies(cur)
        assert checker.results == []

    def test_db_error_logged_not_raised(self) -> None:
        import psycopg2

        checker = _quality_checker()
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("connection lost")
        checker.check_null_anomalies(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == ERROR


class TestCheckOhlcSanity:
    def test_valid_ohlc_logs_info(self) -> None:
        checker = _quality_checker()
        cur = MagicMock()
        cur.fetchall.return_value = []
        checker.check_ohlc_sanity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_negative_prices_logs_critical_with_flagged_symbols(self) -> None:
        checker = _quality_checker()
        cur = MagicMock()
        # (symbol, negative, bad_high, bad_low) - matches check_ohlc_sanity's tuple query shape
        cur.fetchall.return_value = [
            ("AAA", True, False, False),
            ("BBB", True, False, False),
            ("CCC", True, False, False),
        ]
        checker.check_ohlc_sanity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == CRIT
        assert checker.results[0].details["negative_count"] == 3
        flagged = checker.results[0].details["flagged_symbols"]
        assert {f["symbol"] for f in flagged} == {"AAA", "BBB", "CCC"}
        assert all(f["reason"] == "negative OHLC price" for f in flagged)

    def test_high_low_violation_logs_error_with_flagged_symbols(self) -> None:
        checker = _quality_checker()
        cur = MagicMock()
        cur.fetchall.return_value = [
            ("XXX", False, True, False),
            ("YYY", False, False, True),
        ]
        checker.check_ohlc_sanity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == ERROR
        assert checker.results[0].details["bad_high"] == 1
        assert checker.results[0].details["bad_low"] == 1
        flagged = {f["symbol"]: f["reason"] for f in checker.results[0].details["flagged_symbols"]}
        assert flagged == {"XXX": "high < open/close/low", "YYY": "low > open/close/high"}


class TestCheckSequenceContinuity:
    def test_contiguous_sequence_logs_info(self) -> None:
        checker = _price_sanity_checker()
        cur = MagicMock()
        cur.fetchall.return_value = []
        checker.check_sequence_continuity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_gap_detected_logs_warn(self) -> None:
        checker = _price_sanity_checker()
        cur = MagicMock()
        cur.fetchall.return_value = [
            {"date": "2026-09-02", "prev": "2026-08-28", "gap_days": 5},
        ]
        checker.check_sequence_continuity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == WARN
        assert checker.results[0].details["gaps"][0]["days"] == 5

    def test_malformed_row_skipped_without_crashing(self) -> None:
        checker = _price_sanity_checker()
        cur = MagicMock()
        # A row missing expected keys/indices - .get()/indexing should raise and be caught
        # per-row, not crash the whole check.
        cur.fetchall.return_value = [object()]
        checker.check_sequence_continuity(cur)
        # Falls into the "gaps" branch (truthy list) but with an empty gap_list after the
        # per-row extraction failure is swallowed.
        assert len(checker.results) == 1
        assert checker.results[0].details["gaps"] == []
