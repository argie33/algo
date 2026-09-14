"""Regression tests for CikSharedIssuerFinancialsLeakChecker (algo/monitoring/data_patrol/
checks/cik_shared_issuer_financials_leak.py) - added 2026-09-13 (goal session: DataPatrol
comprehensiveness audit follow-up). Proactive, systemic version of the GRN/Barclays bug
(grn_barclays_etn_misattribution_fixed_20260913): a CIK shared by many active tickers (an
ETF/ETN/trust-sponsor pattern) where a minority of those tickers nonetheless have real
extracted financial-statement data.
"""

from unittest.mock import MagicMock, patch

from algo.monitoring.data_patrol.checks.cik_shared_issuer_financials_leak import (
    CikSharedIssuerFinancialsLeakChecker,
    _load_symbol_to_cik,
)
from algo.monitoring.data_patrol.config import INFO, WARN, PatrolConfig


def _checker() -> CikSharedIssuerFinancialsLeakChecker:
    return CikSharedIssuerFinancialsLeakChecker(PatrolConfig())


class TestLoadSymbolToCik:
    def test_missing_file_returns_empty_dict(self) -> None:
        with patch("builtins.open", side_effect=OSError("no such file")):
            assert _load_symbol_to_cik() == {}


class TestCheckCikSharedIssuerFinancialsLeak:
    def test_grn_shaped_minority_leak_flagged(self) -> None:
        """The exact real-world shape that motivated this check: Barclays' CIK covers 9
        active tickers, only GRN (the one that slipped through ETF detection) has extracted
        financials - a minority leak inside a large shared-CIK group."""
        checker = _checker()
        cur = MagicMock()
        barclays_cik = "0001358071"
        symbols = ["GRN", "DJP", "VXX", "VXZ", "ATMP", "TAPR", "GBUG", "BWVTF", "JJETF"]
        cur.fetchall.side_effect = [
            [{"symbol": s} for s in symbols],  # active stock_symbols
            [{"symbol": "GRN"}],  # symbols_with_financials
        ]
        with patch(
            "algo.monitoring.data_patrol.checks.cik_shared_issuer_financials_leak._load_symbol_to_cik",
            return_value=dict.fromkeys(symbols, barclays_cik),
        ):
            checker.check_cik_shared_issuer_financials_leak(cur)
        assert len(checker.results) == 1
        result = checker.results[0]
        assert result.severity == WARN
        examples = result.details["examples"]
        assert len(examples) == 1
        assert examples[0]["symbol"] == "GRN"
        assert examples[0]["cik"] == barclays_cik
        assert examples[0]["group_size"] == 9

    def test_dual_class_pair_below_group_size_threshold_not_flagged(self) -> None:
        """A CIK with only 2 tickers (an ordinary dual-class structure, both legitimately
        having the same real financials) must never qualify - below _MIN_GROUP_SIZE."""
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.side_effect = [
            [{"symbol": "BRK.A"}, {"symbol": "BRK.B"}],
        ]
        with patch(
            "algo.monitoring.data_patrol.checks.cik_shared_issuer_financials_leak._load_symbol_to_cik",
            return_value={"BRK.A": "0001067983", "BRK.B": "0001067983"},
        ):
            checker.check_cik_shared_issuer_financials_leak(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO
        assert "no CIK groups" in checker.results[0].message
        # Never even queries for financials - short-circuits on group size alone.
        cur.execute.assert_called_once()

    def test_majority_have_financials_not_flagged(self) -> None:
        """If most symbols in a large shared-CIK group have real financials, that's not this
        bug's signature (a genuinely operating holding-company shape, not an ETF-family leak) -
        must not be flagged even though the group qualifies by size."""
        checker = _checker()
        cur = MagicMock()
        symbols = ["AAA", "BBB", "CCC", "DDD"]
        cur.fetchall.side_effect = [
            [{"symbol": s} for s in symbols],
            [{"symbol": s} for s in ("AAA", "BBB", "CCC")],  # 3 of 4 = majority
        ]
        with patch(
            "algo.monitoring.data_patrol.checks.cik_shared_issuer_financials_leak._load_symbol_to_cik",
            return_value=dict.fromkeys(symbols, "0000000099"),
        ):
            checker.check_cik_shared_issuer_financials_leak(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO
        assert "no minority-symbol" in checker.results[0].message

    def test_no_ticker_cache_logs_info(self) -> None:
        checker = _checker()
        cur = MagicMock()
        with patch(
            "algo.monitoring.data_patrol.checks.cik_shared_issuer_financials_leak._load_symbol_to_cik",
            return_value={},
        ):
            checker.check_cik_shared_issuer_financials_leak(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO
        cur.execute.assert_not_called()

    def test_db_error_logged_not_raised(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.execute.side_effect = ValueError("boom")
        with patch(
            "algo.monitoring.data_patrol.checks.cik_shared_issuer_financials_leak._load_symbol_to_cik",
            return_value={"GRN": "0001358071"},
        ):
            checker.check_cik_shared_issuer_financials_leak(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == WARN
        assert "failed" in checker.results[0].message
