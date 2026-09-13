"""Regression tests for ReverseMergerShellChecker (algo/monitoring/data_patrol/checks/
reverse_merger_shell.py) - added 2026-09-13 /goal session after live-confirming AXIL Brands,
Inc. (CIK 0001718500, formerly "Reviv3 Procare Co" until 2024-02-13) shows a ~10x revenue
jump (FY2022 $2.34M -> FY2023 $23.5M) spanning its own SEC-recorded rename - a reverse-merger
shell splicing two unrelated businesses' financials under one CIK.
"""

import json
from unittest.mock import MagicMock, patch

from algo.monitoring.data_patrol.checks.reverse_merger_shell import (
    ReverseMergerShellChecker,
    _latest_rename_year,
    _load_symbol_to_cik,
)
from algo.monitoring.data_patrol.config import INFO, WARN, PatrolConfig


def _checker() -> ReverseMergerShellChecker:
    return ReverseMergerShellChecker(PatrolConfig())


class TestLoadSymbolToCik:
    def test_missing_file_returns_empty_dict(self) -> None:
        with patch("algo.monitoring.data_patrol.checks.reverse_merger_shell._TICKER_CACHE_FILE") as p:
            p.__str__.return_value = "/does/not/exist.json"
            with patch("builtins.open", side_effect=OSError("no such file")):
                assert _load_symbol_to_cik() == {}


class TestLatestRenameYear:
    def test_no_former_names_returns_none(self, tmp_path) -> None:
        cache_dir = tmp_path
        (cache_dir / "0000000001.json").write_text(json.dumps({"data": {"formerNames": []}}))
        with patch(
            "algo.monitoring.data_patrol.checks.reverse_merger_shell._SUBMISSIONS_CACHE_DIR",
            cache_dir,
        ):
            assert _latest_rename_year("0000000001") is None

    def test_former_names_returns_latest_to_year(self, tmp_path) -> None:
        cache_dir = tmp_path
        (cache_dir / "0001718500.json").write_text(
            json.dumps(
                {
                    "data": {
                        "formerNames": [
                            {"name": "Reviv3 Procare Co", "from": "2017-10-06", "to": "2024-02-13"},
                        ]
                    }
                }
            )
        )
        with patch(
            "algo.monitoring.data_patrol.checks.reverse_merger_shell._SUBMISSIONS_CACHE_DIR",
            cache_dir,
        ):
            assert _latest_rename_year("0001718500") == 2024


class TestCheckReverseMergerRevenueDiscontinuity:
    def test_axil_shaped_discontinuity_flagged(self) -> None:
        """The exact real-world shape that motivated this check: rename effective 2024, but
        the real revenue jump lands one fiscal year earlier (2022->2023) - the window scan
        (not an exact-boundary check) is what catches this.
        """
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = [
            {"symbol": "AXIL", "fiscal_year": 2021, "revenue": 1633609},
            {"symbol": "AXIL", "fiscal_year": 2022, "revenue": 2336257},
            {"symbol": "AXIL", "fiscal_year": 2023, "revenue": 23521027},
            {"symbol": "AXIL", "fiscal_year": 2024, "revenue": 27498539},
        ]
        with (
            patch(
                "algo.monitoring.data_patrol.checks.reverse_merger_shell._load_symbol_to_cik",
                return_value={"AXIL": "0001718500"},
            ),
            patch(
                "algo.monitoring.data_patrol.checks.reverse_merger_shell._latest_rename_year",
                return_value=2024,
            ),
        ):
            checker.check_reverse_merger_revenue_discontinuity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == WARN
        examples = checker.results[0].details["examples"]
        assert examples[0]["symbol"] == "AXIL"
        assert examples[0]["ratio"] >= 5.0

    def test_ordinary_rename_no_discontinuity_not_flagged(self) -> None:
        """A same-business rename (Alcoa->Arconic->Howmet-shaped: steady revenue across the
        boundary) must not be flagged.
        """
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = [
            {"symbol": "HWM", "fiscal_year": 2019, "revenue": 10_000_000},
            {"symbol": "HWM", "fiscal_year": 2020, "revenue": 10_500_000},
            {"symbol": "HWM", "fiscal_year": 2021, "revenue": 10_800_000},
        ]
        with (
            patch(
                "algo.monitoring.data_patrol.checks.reverse_merger_shell._load_symbol_to_cik",
                return_value={"HWM": "0000004281"},
            ),
            patch(
                "algo.monitoring.data_patrol.checks.reverse_merger_shell._latest_rename_year",
                return_value=2020,
            ),
        ):
            checker.check_reverse_merger_revenue_discontinuity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_no_ticker_cache_logs_info(self) -> None:
        checker = _checker()
        cur = MagicMock()
        with patch(
            "algo.monitoring.data_patrol.checks.reverse_merger_shell._load_symbol_to_cik",
            return_value={},
        ):
            checker.check_reverse_merger_revenue_discontinuity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO
        cur.execute.assert_not_called()

    def test_symbol_not_in_ticker_cache_skipped(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = [
            {"symbol": "UNKNOWN", "fiscal_year": 2022, "revenue": 1_000_000},
            {"symbol": "UNKNOWN", "fiscal_year": 2023, "revenue": 50_000_000},
        ]
        with patch(
            "algo.monitoring.data_patrol.checks.reverse_merger_shell._load_symbol_to_cik",
            return_value={"OTHER": "0000000002"},
        ):
            checker.check_reverse_merger_revenue_discontinuity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO

    def test_db_error_logged_not_raised(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.execute.side_effect = ValueError("boom")
        with patch(
            "algo.monitoring.data_patrol.checks.reverse_merger_shell._load_symbol_to_cik",
            return_value={"AXIL": "0001718500"},
        ):
            checker.check_reverse_merger_revenue_discontinuity(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == WARN
        assert "failed" in checker.results[0].message
