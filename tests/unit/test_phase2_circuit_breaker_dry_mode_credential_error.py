"""Regression test: a market-circuit-breaker credential error in "dry" mode must be treated
the same as "paper" mode (log a warning, skip the check, continue) - not escalate to a full
Phase 2 halt.

BUG FOUND 2026-08-11: the paper-mode leniency branch used `execution_mode == "paper"` and the
halt branch used `execution_mode != "paper"` - both missed "dry". "paper" and "dry" are both
LOCAL-only modes that never touch Alpaca (same convention used in executor.py's credential-fetch
handling, and confirmed a few lines below in this same file: the account-freeze check comment
says it's "a no-op for local/paper/dry-run development"). So a credential error hit while running
in this system's default outside-market-hours dry-run mode incorrectly halted the whole phase
instead of getting dry mode's intended graceful skip.
"""

from unittest.mock import MagicMock, patch

from algo.orchestrator.phase2_circuit_breakers import run as phase2_run


def _clean_cb_result():
    return {
        "halted": False,
        "halt_reasons": [],
        "checks": {
            "vix": {"halted": False, "reason": "VIX ok"},
        },
    }


def _run_with_market_cb_error(execution_mode: str, reason: str = "401 credential error"):
    with (
        patch("algo.risk.CircuitBreaker") as mock_cb,
        patch("algo.infrastructure.MarketEventHandler") as mock_meh,
    ):
        mock_cb.return_value.check_all.return_value = _clean_cb_result()
        mock_meh.return_value.check_market_circuit_breaker.return_value = {
            "error": True,
            "reason": reason,
        }
        alerts = MagicMock()
        return phase2_run(
            config={"execution_mode": execution_mode},
            run_date=None,
            dry_run=(execution_mode != "auto"),
            alerts=alerts,
            verbose=False,
            log_phase_result_fn=MagicMock(),
        )


class TestPhase2CircuitBreakerDryModeCredentialError:
    def test_credential_error_in_dry_mode_does_not_halt(self):
        result = _run_with_market_cb_error("dry")
        assert result.halted is False, (
            "A market circuit breaker credential error in dry mode must not halt Phase 2, same as paper mode"
        )

    def test_credential_error_in_paper_mode_does_not_halt(self):
        """Sanity check: the pre-existing paper-mode leniency must still work."""
        result = _run_with_market_cb_error("paper")
        assert result.halted is False

    def test_credential_error_in_auto_mode_still_halts(self):
        """Sanity check: live/auto mode must NOT get the lenient skip."""
        result = _run_with_market_cb_error("auto")
        assert result.halted is True
