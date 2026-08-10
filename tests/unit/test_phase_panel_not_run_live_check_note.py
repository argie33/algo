"""Regression test: a phase header showing "NOT RUN" next to a detail line
reading "Status: TRIGGERED" (or similar) reads as self-contradictory.

Bug: _build_phase_execution_panel's header status comes from the last
orchestrator run's phase_results (was this phase reached in THAT run), while
the detail rows come from execution_health - a live, independent query of
each phase's underlying table (e.g. circuit_breaker_status), regardless of
whether this run reached that phase. When an earlier phase halts before
Phase 2 runs, the header correctly says "Circuit Breakers NOT RUN" while the
live detail can still say "Status: TRIGGERED" - confusing at exactly the
moment a trader needs to trust the dashboard most. A short note now
clarifies the detail rows are a live check, not from this run.
"""

from dashboard.panels.health import _build_phase_execution_panel
from tests.test_helpers.assertions import render_panel_to_text


def test_not_run_phase_with_live_data_shows_clarifying_note():
    execution_health = {
        "phase_2_circuit_breakers": {
            "any_triggered": True,
            "drawdown_pct": 12.0,
            "daily_loss_pct": 0.1,
            "weekly_loss_pct": 0.2,
            "vix_level": 18.0,
            "last_check": "2026-07-26",
        },
    }
    # Last run's phase_results has no entry for phase 2 (halted before reaching it).
    run = {"phase_results": [{"phase": "1", "status": "halted", "name": "data_check"}]}

    panel = _build_phase_execution_panel(execution_health, run)
    text = render_panel_to_text(panel)

    assert "Circuit Breakers" in text
    assert "NOT RUN" in text
    assert "TRIGGERED" in text
    assert "live check, not from this run" in text


def test_completed_phase_does_not_show_live_check_note():
    execution_health = {
        "phase_2_circuit_breakers": {
            "any_triggered": False,
            "drawdown_pct": 2.0,
            "daily_loss_pct": 0.0,
            "weekly_loss_pct": 0.0,
            "vix_level": 15.0,
            "last_check": "2026-07-26",
        },
    }
    run = {"phase_results": [{"phase": "2", "status": "ok", "name": "circuit_breakers"}]}

    panel = _build_phase_execution_panel(execution_health, run)
    text = render_panel_to_text(panel)

    assert "live check, not from this run" not in text
