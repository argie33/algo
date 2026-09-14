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
        cur.fetchall.return_value = [{"symbol": "AAA"}, {"symbol": "BBB"}]
        checker.check_null_anomalies(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == ERROR
        assert checker.results[0].details["today_nulls"] == 500

    def test_null_pct_above_threshold_wires_flagged_symbols(self) -> None:
        # ADDED 2026-09-14 (goal: DataPatrol coverage audit follow-up) - this check only ever
        # computed an aggregate percentage, never identifying which symbols carry the NULL
        # close, so quarantine.py's fail-safe (an ERROR finding needs flagged_symbols to be
        # quarantinable) meant a real hit here halted the whole pipeline instead of excluding
        # just the affected symbols.
        checker = _quality_checker()
        cur = MagicMock()
        cur.fetchone.return_value = {"today_nulls": 500, "today_total": 5000}
        cur.fetchall.return_value = [{"symbol": "AAA"}, {"symbol": "BBB"}]
        checker.check_null_anomalies(cur)
        flagged = checker.results[0].details["flagged_symbols"]
        assert {f["symbol"] for f in flagged} == {"AAA", "BBB"}
        assert all(f["reason"] == "NULL close on the latest trading date" for f in flagged)

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
        # (symbol, date, negative, bad_high, bad_low) - matches check_ohlc_sanity's tuple
        # query shape (widened 2026-09-13 to scan full history, not just the latest date -
        # see that check's own module comment)
        cur.fetchall.return_value = [
            ("AAA", "2026-09-01", True, False, False),
            ("BBB", "2026-09-01", True, False, False),
            ("CCC", "2026-09-01", True, False, False),
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
            ("XXX", "2026-09-01", False, True, False),
            ("YYY", "2026-09-01", False, False, True),
        ]
        checker.check_ohlc_sanity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == ERROR
        assert checker.results[0].details["bad_high"] == 1
        assert checker.results[0].details["bad_low"] == 1
        flagged = {f["symbol"]: f["reason"] for f in checker.results[0].details["flagged_symbols"]}
        assert flagged == {"XXX": "high < open/close/low", "YYY": "low > open/close/high"}


class TestCheckIsolatedSpikeCorruption:
    def test_confirmed_spike_logs_error_with_flagged_symbols(self) -> None:
        """ADDED 2026-09-13 (goal: quarantine-coverage audit) - check_isolated_spike_corruption
        already named the exact corrupted symbol per `confirmed` entry but never wired it into
        `flagged_symbols`, so a hit halted the whole pipeline instead of quarantining just the
        affected symbols. Regression-guards the fix.
        """
        checker = _price_sanity_checker()
        cur = MagicMock()
        cur.fetchall.side_effect = [
            [("ZZZ",)],
            [
                ("2026-01-01", 1.0, 1000000, "sec"),
                ("2026-01-02", 500.0, 5, "yfinance"),
                ("2026-01-03", 1.0, 1000000, "sec"),
            ],
        ]
        checker.check_isolated_spike_corruption(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == ERROR
        flagged = checker.results[0].details["flagged_symbols"]
        assert {f["symbol"] for f in flagged} == {"ZZZ"}
        assert "spike" in flagged[0]["reason"]

    def test_no_spike_logs_info(self) -> None:
        checker = _price_sanity_checker()
        cur = MagicMock()
        cur.fetchall.side_effect = [[]]
        checker.check_isolated_spike_corruption(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO
        assert "flagged_symbols" not in (checker.results[0].details or {})


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
