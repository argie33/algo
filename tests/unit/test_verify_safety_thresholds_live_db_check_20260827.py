#!/usr/bin/env python3
"""Regression test for scripts/verify_safety_thresholds.py's check_live_db_thresholds().

Added 2026-08-27 (real-money-readiness review): the script's own docstring says checks 1/2
"Neither requires a live database" - they only ever exercise AlgoConfig.DEFAULTS (the in-code
fallback) and a synthetic zero-injection, never the actual live algo_config table this system
trades against. A clean run of the original script could report SUCCESS while the live DB
itself held a corrupted/zeroed critical threshold, as long as AlgoConfig's own code-level
DEFAULTS and fail-closed gate were intact. check_live_db_thresholds() closes that gap by
querying the real table directly. This file was also the first test coverage of any kind for
verify_safety_thresholds.py - no prior test file existed for this GOVERNANCE.md-mandated
pre-deployment gate.
"""

from unittest.mock import MagicMock, patch

import pytest

from scripts.verify_safety_thresholds import CRITICAL_KEYS, check_live_db_thresholds


def _mock_db_returning(rows: dict[str, str]) -> MagicMock:
    mock_ctx = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = list(rows.items())
    mock_ctx.return_value.__enter__.return_value = mock_cursor
    return mock_ctx


def _all_healthy_rows() -> dict[str, str]:
    """One sane, non-zero, in-range value per CRITICAL_KEYS entry."""
    return {
        "min_signal_quality_score": "82",
        "min_completeness_score": "70",
        "halt_drawdown_pct": "-10",
        "max_daily_loss_pct": "2.0",
        "vix_max_threshold": "35.0",
        "min_volume_ma_50d": "300000",
        "min_avg_daily_dollar_volume": "500000",
        "earnings_blackout_days_before": "2",
        "earnings_blackout_days_after": "1",
        "base_risk_pct": "0.75",
        "max_position_size_pct": "4.75",
    }


class TestCheckLiveDbThresholds:
    def test_all_healthy_values_pass_clean(self) -> None:
        with patch("utils.db.context.DatabaseContext", _mock_db_returning(_all_healthy_rows())):
            failures, db_reachable = check_live_db_thresholds()

        assert db_reachable is True
        assert failures == []

    def test_zero_value_flagged(self) -> None:
        rows = _all_healthy_rows()
        rows["max_daily_loss_pct"] = "0.0"
        with patch("utils.db.context.DatabaseContext", _mock_db_returning(rows)):
            failures, db_reachable = check_live_db_thresholds()

        assert db_reachable is True
        assert any("ZERO in LIVE DB" in f and "max_daily_loss_pct" in f for f in failures)

    def test_missing_key_flagged(self) -> None:
        rows = _all_healthy_rows()
        del rows["halt_drawdown_pct"]
        with patch("utils.db.context.DatabaseContext", _mock_db_returning(rows)):
            failures, db_reachable = check_live_db_thresholds()

        assert db_reachable is True
        assert any("MISSING FROM LIVE DB" in f and "halt_drawdown_pct" in f for f in failures)

    def test_non_numeric_value_flagged(self) -> None:
        rows = _all_healthy_rows()
        rows["base_risk_pct"] = "not_a_number"
        with patch("utils.db.context.DatabaseContext", _mock_db_returning(rows)):
            failures, db_reachable = check_live_db_thresholds()

        assert db_reachable is True
        assert any("NON-NUMERIC" in f and "base_risk_pct" in f for f in failures)

    def test_out_of_declared_range_flagged(self) -> None:
        rows = _all_healthy_rows()
        # VALIDATION_SCHEMA declares min_signal_quality_score in [1, 100] - 500 is a real,
        # non-zero, syntactically valid number that should still be caught as unsafe.
        rows["min_signal_quality_score"] = "500"
        with patch("utils.db.context.DatabaseContext", _mock_db_returning(rows)):
            failures, db_reachable = check_live_db_thresholds()

        assert db_reachable is True
        assert any("OUT OF DECLARED RANGE" in f and "min_signal_quality_score" in f for f in failures)

    def test_unreachable_db_reported_not_raised(self) -> None:
        mock_ctx = MagicMock(side_effect=RuntimeError("connection refused"))
        with patch("utils.db.context.DatabaseContext", mock_ctx):
            failures, db_reachable = check_live_db_thresholds()

        assert db_reachable is False
        assert any("DB UNREACHABLE" in f for f in failures)

    def test_every_critical_key_has_a_healthy_fixture_value(self) -> None:
        """Sanity check on the fixture itself: if CRITICAL_KEYS ever grows, this test's
        fixture must grow with it, or the 'all healthy' test would silently stop covering
        the new key (it would just show up as MISSING, not caught as a fixture bug)."""
        assert set(_all_healthy_rows().keys()) == set(CRITICAL_KEYS)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
