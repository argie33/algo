"""Regression test: PHASE_8_TEST_MODE / ALLOW_OUTSIDE_MARKET_HOURS must never bypass the
market-hours guard when execution_mode="auto" (live trading with a real broker).

Neither env var is set by any deployed terraform/infra config (confirmed via full-repo
grep, 2026-08-23) - they're a local-testing mechanism only (see CLAUDE.md), documented for
exercising Phase 8 outside real market hours. But before this fix, nothing stopped either
from ALSO taking effect in execution_mode="auto" if either var were ever left set by human
error (a stale shell env, a copy-pasted .env file) - the guard would have been silently
bypassed for real order execution outside market hours. Fixed by forcing both flags off
whenever execution_mode == "auto", regardless of the env vars, with a loud CRITICAL log if
it would have mattered.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_entry_execution import run

_OUTSIDE_HOURS = datetime(2026, 8, 17, 20, 0)  # 8 PM ET, well outside market hours


def _base_kwargs(execution_mode: str):
    return {
        "config": {
            "execution_mode": execution_mode,
            "alpaca_paper_trading": execution_mode != "auto",
        },
        "run_date": date(2026, 8, 17),
        "dry_run": execution_mode != "auto",
        "verbose": False,
        "log_phase_result_fn": MagicMock(),
    }


def test_allow_outside_market_hours_does_not_bypass_guard_in_auto_mode(monkeypatch):
    monkeypatch.setenv("ALLOW_OUTSIDE_MARKET_HOURS", "true")

    with patch("algo.orchestrator.phase8_entry_execution.datetime") as mock_dt:
        mock_dt.now.return_value = _OUTSIDE_HOURS
        mock_dt.combine = datetime.combine

        result = run(**_base_kwargs("auto"))

    assert result.status == "blocked"
    assert "market hours" in (result.error or "").lower()


def test_phase_8_test_mode_does_not_bypass_guard_in_auto_mode(monkeypatch):
    monkeypatch.setenv("PHASE_8_TEST_MODE", "true")

    with patch("algo.orchestrator.phase8_entry_execution.datetime") as mock_dt:
        mock_dt.now.return_value = _OUTSIDE_HOURS
        mock_dt.combine = datetime.combine

        result = run(**_base_kwargs("auto"))

    assert result.status == "blocked"
    assert "market hours" in (result.error or "").lower()


def test_allow_outside_market_hours_still_works_normally_in_paper_mode(monkeypatch):
    """Sanity check: the override must still function for its intended purpose (local
    testing in paper/dry/review mode) - only auto mode is hardened against it."""
    monkeypatch.setenv("ALLOW_OUTSIDE_MARKET_HOURS", "true")

    with patch("algo.orchestrator.phase8_entry_execution.datetime") as mock_dt:
        mock_dt.now.return_value = _OUTSIDE_HOURS
        mock_dt.combine = datetime.combine

        result = run(**_base_kwargs("paper"))

    assert not (result.status == "blocked" and "market hours" in (result.error or "").lower())
