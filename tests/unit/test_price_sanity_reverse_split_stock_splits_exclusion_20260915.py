"""Regression tests for PriceSanityChecker.check_corporate_actions' 2026-09-15 changes
(algo/monitoring/data_patrol/checks/price_sanity.py):

(1) the check was drop-only - a reverse split (price jumps up) produced zero alert. A
    symmetric `rise_ratio` leg was added.
(2) the check re-logged the same confirmed-split symbols forever with no way to clear a
    finding once remediated - now excludes any (symbol, date) pair already recorded in
    `stock_splits` (via scripts/fix_missing_stock_splits.py).

No prior test exercised check_corporate_actions with mocked rows at all - added alongside the
change itself, same as this module's own /goal-tracked gap-closing pattern (see
test_data_patrol_quality_and_price_sanity_checks_20260908.py's own docstring).
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.price_sanity import PriceSanityChecker
from algo.monitoring.data_patrol.config import INFO, WARN, PatrolConfig


def _checker() -> PriceSanityChecker:
    return PriceSanityChecker(PatrolConfig())


class TestCheckCorporateActionsReverseSplitAndExclusion:
    def test_reverse_split_rise_flagged(self) -> None:
        # A reverse split candidate: +200% single-day move (unremediated, so the SQL's own
        # NOT EXISTS against stock_splits would keep it - simulated here by simply returning it).
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = [
            {"symbol": "ZZZ", "date": "2026-09-10", "close": 30.0, "prev": 10.0, "pct_change": 200.0},
        ]
        checker.check_corporate_actions(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == WARN
        samples = checker.results[0].details["samples"]
        assert samples[0]["symbol"] == "ZZZ"
        assert samples[0]["pct_change"] == 200.0

    def test_no_unremediated_moves_logs_info(self) -> None:
        # Query returns nothing - either no extreme move occurred, or every extreme move in the
        # lookback window is already recorded in stock_splits (excluded by the NOT EXISTS clause).
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = []
        checker.check_corporate_actions(cur)
        assert len(checker.results) == 1
        assert checker.results[0].severity == INFO
        assert "No unremediated extreme moves" in checker.results[0].message

    def test_message_mentions_both_drop_and_rise_thresholds(self) -> None:
        checker = _checker()
        cur = MagicMock()
        cur.fetchall.return_value = [
            {"symbol": "AAA", "date": "2026-09-10", "close": 5.0, "prev": 10.0, "pct_change": -50.0},
        ]
        checker.check_corporate_actions(cur)
        message = checker.results[0].message
        assert "%/" in message and "+" in message  # both drop_ratio and rise_ratio thresholds surfaced

    def test_get_corporate_actions_config_includes_rise_ratio(self) -> None:
        config = PatrolConfig()
        corp_cfg = config.get_corporate_actions_config()
        assert "rise_ratio" in corp_cfg
        assert corp_cfg["rise_ratio"] > 0


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
