"""Regression test: AlgoConfig._detect_config_db_failure()'s partial-database-load-failure
branch (>75% of configs still at hardcoded defaults, but not literally all of them) must
actually alert a human via notify(), not just log a CRITICAL line.

BUG FOUND 2026-09-01 (/goal session): unlike the full-failure case (100% still at defaults,
which raises RuntimeError and is fail-fast/blocking in live mode), this partial-failure branch
only ever called logger.critical() - the same "computed but never delivered" alert gap already
found and fixed today in load_market_constituents.py and Phase 9's risk-alert path. A degraded
(not fully down) DB during live trading means the system silently keeps running on mostly-
hardcoded-default safety/position-sizing thresholds with nothing but a log line to catch it.
"""

from unittest.mock import patch

import pytest

from algo.infrastructure.config.main import AlgoConfig


def _make_config(db_count: int, default_count: int) -> AlgoConfig:
    config = AlgoConfig.__new__(AlgoConfig)
    sources: dict[str, str] = {}
    for i in range(db_count):
        sources[f"db_key_{i}"] = "database"
    for i in range(default_count):
        sources[f"default_key_{i}"] = "default"
    config._sources = sources
    return config


class TestPartialDatabaseLoadFailureAlerts:
    def test_over_75_percent_defaults_sends_warning_notify(self) -> None:
        """8/10 (80%) still at defaults - above the 75% partial-failure threshold."""
        config = _make_config(db_count=2, default_count=8)

        with patch("algo.reporting.notify") as mock_notify:
            config._detect_config_db_failure()

        mock_notify.assert_called_once()
        _, kwargs = mock_notify.call_args
        assert kwargs["severity"] == "warning"
        assert kwargs["title"] == "Partial Config Database Load Failure"
        assert "8/10" in kwargs["message"]
        assert kwargs["details"] == {"default_sources": 8, "total_sources": 10}

    def test_at_or_below_75_percent_defaults_does_not_notify(self) -> None:
        """7/10 (70%) still at defaults - below the threshold, healthy load."""
        config = _make_config(db_count=3, default_count=7)

        with patch("algo.reporting.notify") as mock_notify:
            config._detect_config_db_failure()

        mock_notify.assert_not_called()

    def test_all_defaults_raises_instead_of_notifying(self) -> None:
        """0 from database at all (100% defaults) is the pre-existing full-failure case -
        must still raise RuntimeError (fail-fast), not merely notify()."""
        config = _make_config(db_count=0, default_count=5)

        with (
            patch("algo.reporting.notify") as mock_notify,
            pytest.raises(RuntimeError, match="Database config load FAILED"),
        ):
            config._detect_config_db_failure()

        mock_notify.assert_not_called()

    def test_notify_failure_does_not_crash_config_loading(self) -> None:
        """A notification-delivery failure must be swallowed (logged), not propagate and
        abort config loading - alerting is best-effort here, not a governance gate, and
        config loading itself must never fail because notify() failed."""
        config = _make_config(db_count=2, default_count=8)

        with patch("algo.reporting.notify", side_effect=RuntimeError("smtp down")):
            # Must not raise despite notify() failing internally.
            config._detect_config_db_failure()
