"""Regression test for QualityChecker.check_zero_or_identical()'s zero_data finding
(algo/monitoring/data_patrol/checks/quality.py).

FIXED 2026-09-13 (goal: quarantine-coverage audit): this finding already computes `new_zeros`
as an explicit set of the specific symbols that newly went to zero OHLC/volume, but never
wired that into `flagged_symbols` - so an ERROR here halted the WHOLE pipeline (per
quarantine.py's opt-in contract: "Any CRIT/ERROR finding without a non-empty flagged_symbols
list is NOT quarantinable") instead of quarantining just the newly-zero symbols. Same class
as isolated_spike_corruption's own 2026-09-13 fix (see price_sanity.py) and
trade_alignment's (see test_data_patrol_alignment_checks_20260908.py).
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.monitoring.data_patrol.checks.quality import QualityChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _checker() -> QualityChecker:
    return QualityChecker(PatrolConfig())


class TestZeroDataFlaggedSymbols:
    def test_new_zero_symbols_wired_to_flagged_symbols(self) -> None:
        checker = _checker()
        threshold = checker.config.get_quality_config()["zero_symbols_error"]
        new_symbols = [f"NEWZERO{i}" for i in range(threshold + 1)]

        cur = MagicMock()
        cur.fetchone.return_value = (date(2026, 9, 12),)
        cur.fetchall.side_effect = [
            [(s,) for s in new_symbols],  # today's zero symbols
            [],  # yesterday's zero symbols (none - all of today's are new)
            [],  # identical-OHLC symbols (unrelated finding in the same method)
        ]

        with patch(
            "algo.infrastructure.market_calendar.MarketCalendar.get_previous_trading_day",
            return_value=date(2026, 9, 11),
        ):
            checker.check_zero_or_identical(cur)

        error_results = [r for r in checker.results if r.severity == "error" and r.check_name == "zero_data"]
        assert len(error_results) == 1
        flagged = error_results[0].details["flagged_symbols"]
        assert {f["symbol"] for f in flagged} == set(new_symbols)
        assert all("reason" in f for f in flagged)
