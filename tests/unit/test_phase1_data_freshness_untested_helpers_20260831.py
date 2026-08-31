"""Coverage test for 3 genuinely zero-coverage functions in
algo/orchestrator/phase1_data_freshness.py, found via the same objective coverage-analysis pass
as commits 5b4ae35ce/8e3479e5d/d242f84aa/79ed3b3 (14.40% file-wide coverage, dominated by one
huge run() orchestration function - not a good unit-test target; these three self-contained
helpers are).

- _cleanup_stuck_database_sessions(): kills idle-in-transaction Postgres sessions holding locks
  on data_loader_status - its own docstring documents the exact "Monday brittleness" cascade
  bug this exists to prevent (a stuck Friday session blocks every loader INSERT all weekend).
- _check_failsafe_retry_result(): Phase 1's halt-decision gate after failsafe loader retries -
  directly controls whether trading proceeds or halts for the day.
- _validate_config(): fail-closed config extraction, explicitly documented as having "no
  hardcoded fallbacks for trading safety decisions."
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.orchestrator.phase1_data_freshness import (
    _check_failsafe_retry_result,
    _cleanup_stuck_database_sessions,
    _validate_config,
)


class TestCleanupStuckDatabaseSessions:
    def test_returns_zero_when_no_stuck_sessions(self):
        cur = MagicMock()
        cur.fetchall.return_value = []
        with patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            killed = _cleanup_stuck_database_sessions()
        assert killed == 0

    def test_kills_each_stuck_session_and_counts_successes(self):
        cur = MagicMock()
        now = MagicMock()
        now.timestamp.return_value = 0.0
        cur.fetchall.return_value = [(111, "app_user", now), (222, "app_user", now)]
        # fetchone() is called once per pg_terminate_backend() - both succeed.
        cur.fetchone.side_effect = [(True,), (True,)]
        with (
            patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as MockDB,
            patch("algo.orchestrator.phase1_data_freshness.time.time", return_value=3600.0),
        ):
            MockDB.return_value.__enter__.return_value = cur
            killed = _cleanup_stuck_database_sessions()
        assert killed == 2

    def test_does_not_count_a_pid_that_could_not_be_terminated(self):
        cur = MagicMock()
        now = MagicMock()
        now.timestamp.return_value = 0.0
        cur.fetchall.return_value = [(111, "app_user", now)]
        cur.fetchone.return_value = (False,)  # pg_terminate_backend returned false - already gone
        with (
            patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as MockDB,
            patch("algo.orchestrator.phase1_data_freshness.time.time", return_value=3600.0),
        ):
            MockDB.return_value.__enter__.return_value = cur
            killed = _cleanup_stuck_database_sessions()
        assert killed == 0

    def test_one_pid_terminate_exception_does_not_block_the_rest(self):
        cur = MagicMock()
        now = MagicMock()
        now.timestamp.return_value = 0.0
        cur.fetchall.return_value = [(111, "app_user", now), (222, "app_user", now)]

        # Call sequence: 1) SELECT stuck sessions, 2) terminate PID 111 (raises),
        # 3) terminate PID 222 (succeeds).
        def execute_side_effect(sql):
            if "111" in sql:
                raise RuntimeError("permission denied")

        cur.execute.side_effect = execute_side_effect
        cur.fetchone.return_value = (True,)
        with (
            patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as MockDB,
            patch("algo.orchestrator.phase1_data_freshness.time.time", return_value=3600.0),
        ):
            MockDB.return_value.__enter__.return_value = cur
            # A terminate error on one PID must not crash the whole cleanup pass, and the
            # other PID must still be counted as successfully killed.
            killed = _cleanup_stuck_database_sessions()
        assert killed == 1

    def test_query_failure_is_caught_and_returns_zero(self):
        with patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.side_effect = RuntimeError("connection refused")
            killed = _cleanup_stuck_database_sessions()
        assert killed == 0


class TestCheckFailsafeRetryResult:
    def _good_result(self, **overrides):
        result = {
            "incomplete_loaders": [],
            "retried": [],
            "recovered": [],
            "still_failing": [],
            "halt_required": False,
        }
        result.update(overrides)
        return result

    def test_returns_none_when_nothing_still_failing(self):
        result = _check_failsafe_retry_result(self._good_result(), log_phase_result_fn=MagicMock())
        assert result is None

    def test_raises_on_missing_required_keys(self):
        with pytest.raises(RuntimeError, match="missing keys"):
            _check_failsafe_retry_result({"incomplete_loaders": []}, log_phase_result_fn=MagicMock())

    def test_halts_when_price_daily_still_failing(self):
        cur = MagicMock()
        cur.fetchone.return_value = (45.0,)
        log_fn = MagicMock()
        with patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.return_value = cur
            result = _check_failsafe_retry_result(
                self._good_result(still_failing=["price_daily"]), log_phase_result_fn=log_fn
            )
        assert result is not None
        assert result.status == "halted"
        assert result.halted is True
        log_fn.assert_called_once()

    def test_halts_when_price_coverage_lookup_fails_reports_unknown(self):
        log_fn = MagicMock()
        with patch("algo.orchestrator.phase1_data_freshness.DatabaseContext") as MockDB:
            MockDB.return_value.__enter__.side_effect = RuntimeError("db down")
            result = _check_failsafe_retry_result(
                self._good_result(still_failing=["price_daily"]), log_phase_result_fn=log_fn
            )
        assert result is not None
        assert result.error is not None
        assert "unknown" in result.error

    def test_halts_when_halt_required_true_for_non_price_loaders(self):
        log_fn = MagicMock()
        result = _check_failsafe_retry_result(
            self._good_result(still_failing=["sector_ranking"], halt_required=True),
            log_phase_result_fn=log_fn,
        )
        assert result is not None
        assert result.status == "halted"
        log_fn.assert_called_once()

    def test_does_not_halt_when_still_failing_nonempty_but_halt_not_required(self):
        """still_failing has entries but halt_required=False and none are price tables -
        must proceed, not halt."""
        result = _check_failsafe_retry_result(
            self._good_result(still_failing=["some_minor_table"], halt_required=False),
            log_phase_result_fn=MagicMock(),
        )
        assert result is None


class TestValidateConfig:
    GOOD_CONFIG = {
        "phase1_min_coverage_pct": 95,
        "phase1_min_symbol_count": 4000,
        "phase1_recent_cutoff_days": 1,
        "phase1_prior_cutoff_days": 3,
        "phase1_halt_table_max_tolerance_days": 2,
    }

    def test_extracts_all_fields_from_valid_config(self):
        result = _validate_config(dict(self.GOOD_CONFIG))
        assert result == (95, 4000, 1, 3, 2)

    def test_raises_when_config_is_empty(self):
        with pytest.raises(RuntimeError, match="Config not provided"):
            _validate_config({})

    def test_raises_when_config_is_none(self):
        with pytest.raises(RuntimeError, match="Config not provided"):
            _validate_config(None)

    def test_raises_when_min_coverage_pct_missing(self):
        config = dict(self.GOOD_CONFIG)
        del config["phase1_min_coverage_pct"]
        with pytest.raises(RuntimeError, match="phase1_min_coverage_pct"):
            _validate_config(config)

    def test_raises_when_min_symbol_count_missing(self):
        config = dict(self.GOOD_CONFIG)
        del config["phase1_min_symbol_count"]
        with pytest.raises(RuntimeError, match="phase1_min_symbol_count"):
            _validate_config(config)

    def test_raises_when_a_timing_threshold_missing(self):
        config = dict(self.GOOD_CONFIG)
        del config["phase1_halt_table_max_tolerance_days"]
        with pytest.raises(RuntimeError, match="phase1_halt_table_max_tolerance_days"):
            _validate_config(config)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
