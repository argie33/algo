"""Regression test for a 2026-09-07 real-money-readiness audit fix: CircuitBreaker.check_all()
must acquire the same ALGO_POSITIONS_LOCK_ID/ALGO_TRADES_LOCK_ID advisory locks every writer to
those tables (executor.py, phase9_reconciliation.py, phase6_exit_execution.py) already uses,
before reading them for drawdown/daily-loss/total-risk - and must release them even when a
check raises.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.risk.circuit_breaker import CircuitBreaker

CONFIG = {
    "halt_drawdown_pct": -10.0,
    "max_daily_loss_pct": 2.0,
    "max_consecutive_losses": 3,
    "max_total_risk_pct": 4.0,
    "vix_max_threshold": 35.0,
    "max_weekly_loss_pct": 5.0,
    "max_positions_per_sector": 5,
    "sector_drawdown_halt_pct": -12.0,
    "min_win_rate_pct": 40.0,
    "daily_profit_cap_pct": 10.0,
    "re_engage_recovery_pct": 5.0,
    "re_engage_min_days": 3,
    "require_ftd_to_re_engage": False,
    "max_data_staleness_days": 2,
}


def _all_pass_cb() -> CircuitBreaker:
    cb = CircuitBreaker(config=dict(CONFIG))
    for key in cb._checks:
        cb._checks[key] = lambda current_date, cur: {"halted": False, "reason": ""}
    return cb


class TestCircuitBreakerAcquiresLocks:
    def test_acquires_and_releases_both_locks_on_success(self) -> None:
        cb = _all_pass_cb()
        cur = MagicMock()
        cur.fetchone.return_value = None
        cur.fetchall.return_value = []
        cur.rowcount = 0

        with (
            patch("algo.risk.circuit_breaker.DatabaseContext") as mock_db_ctx,
            patch("algo.risk.circuit_breaker.acquire_advisory_lock") as mock_acquire,
            patch("algo.risk.circuit_breaker.release_advisory_lock") as mock_release,
        ):
            mock_db_ctx.return_value.__enter__.return_value = cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = cb.check_all(current_date=date(2026, 9, 7))

        assert result["halted"] is False
        assert mock_acquire.call_count == 2
        assert mock_release.call_count == 2
        locked_ids = {call.args[1] for call in mock_acquire.call_args_list}
        released_ids = {call.args[1] for call in mock_release.call_args_list}
        assert locked_ids == released_ids

    def test_releases_locks_even_when_a_check_raises(self) -> None:
        """Locks must not be left held (leaking into a pooled/reused connection) just because
        a check raised - the release lives in a `finally`, not only the success path."""
        cb = _all_pass_cb()
        cb._checks["daily_loss"] = lambda current_date, cur: (_ for _ in ()).throw(ValueError("simulated bad config"))
        cur = MagicMock()
        cur.fetchone.return_value = None
        cur.fetchall.return_value = []
        cur.rowcount = 0

        with (
            patch("algo.risk.circuit_breaker.DatabaseContext") as mock_db_ctx,
            patch("algo.risk.circuit_breaker.acquire_advisory_lock") as mock_acquire,
            patch("algo.risk.circuit_breaker.release_advisory_lock") as mock_release,
        ):
            mock_db_ctx.return_value.__enter__.return_value = cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = cb.check_all(current_date=date(2026, 9, 7))

        # The per-check inner handler catches the ValueError and fails that ONE check closed
        # (halted=True overall), not a full method-level abort - locks must still be released.
        assert result["halted"] is True
        assert mock_acquire.call_count == 2
        assert mock_release.call_count == 2

    def test_lock_acquisition_failure_fails_closed_not_raises(self) -> None:
        """A lock timeout/failure must be caught by check_all()'s own outer exception handler
        and converted into a halt, not propagate as an uncaught RuntimeError."""
        cb = _all_pass_cb()
        cur = MagicMock()
        cur.fetchone.return_value = None
        cur.fetchall.return_value = []
        cur.rowcount = 0

        with (
            patch("algo.risk.circuit_breaker.DatabaseContext") as mock_db_ctx,
            patch(
                "algo.risk.circuit_breaker.acquire_advisory_lock",
                side_effect=RuntimeError("Failed to acquire advisory lock for algo_positions within 30s timeout"),
            ),
        ):
            mock_db_ctx.return_value.__enter__.return_value = cur
            mock_db_ctx.return_value.__exit__.return_value = False
            result = cb.check_all(current_date=date(2026, 9, 7))

        assert result["halted"] is True
        assert any("advisory lock" in r.lower() for r in result["halt_reasons"])
