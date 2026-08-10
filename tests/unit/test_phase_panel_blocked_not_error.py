"""Regression test: Phase 8 correctly blocked by a safety guard (market-hours,
stale-signal, or pending-order guard) must render as a cautionary badge, not as
a red ERROR - it's a guard working exactly as designed, not a crash.

Bug: _build_phase_execution_panel's status if/elif chain had no branch for
status_str == "blocked", so it fell through to the same treatment as an
unrecognized status, and the module's HALTED_STATES/PHASE_HALTED_STATES
constants (consumed by _format_phase_badge and the phase-count tallies) didn't
include "blocked" either. Confirmed live: every local dry-run outside market
hours logs Phase 8 with status="blocked" (see PhaseResult.ok in
algo/orchestrator/phase_result.py, which already treats "blocked" as a
successful outcome) - before this fix the dashboard badge for that phase
rendered identically to a genuine phase crash.
"""

from dashboard.panels.health import (
    HALTED_STATES,
    PHASE_HALTED_STATES,
    _build_phase_execution_panel,
    _format_phase_badge,
)
from dashboard.utilities import Y
from tests.test_helpers.assertions import render_panel_to_text


def test_blocked_phase_shows_guard_badge_not_error():
    execution_health = {
        "phase_8_entry_execution": {"last_check": "2026-07-27"},
    }
    run = {
        "phase_results": [
            {"phase": "8", "status": "blocked", "name": "entry_execution", "summary": "market hours guard"},
        ]
    }

    panel = _build_phase_execution_panel(execution_health, run)
    text = render_panel_to_text(panel)

    assert "BLOCKED (guard)" in text
    assert "ERROR" not in text


def test_blocked_in_halted_states_constants():
    assert "blocked" in HALTED_STATES
    assert "blocked" in PHASE_HALTED_STATES


def test_format_phase_badge_blocked_is_yellow_not_red():
    color, icon = _format_phase_badge("blocked")
    assert color == Y
    assert icon != "✗"
