"""Regression test: Phase 6's benign dry-run stub must render as a cautionary
"skipped" badge, not as "HALTED" - it's phase6_exit_execution.py's dry_run branch
deliberately declining to place real orders, not a real halt or exit-execution error.

Bug: phase6_exit_execution.py's dry_run branch unconditionally reports
status="degraded" with summary "DRY-RUN: execution skipped (no real trades)",
before any real per-item exit-execution logic runs - so this exact summary text
can never coexist with a genuine exit error (errors > 0 also reports "degraded",
but with a different summary). algo/orchestration/orchestrator.py's _final_report()
already exempts this literal "DRY-RUN" stub from both its console [DEGRAD] flag and
its overall success/failure calculation (see that file's 2026-07-27 fix), but
_build_phase_execution_panel() - the dashboard panel that is the primary way this
system is actually observed via `python -m dashboard --local` - independently re-derives
its badge from the raw status string with no equivalent exemption, so it showed
"~ HALTED" for Exit Execution on every single local dry-run.
"""

from tests.test_helpers.assertions import render_panel_to_text

from dashboard.panels.health import _build_phase_execution_panel


def test_dry_run_exit_stub_shows_skipped_badge_not_halted():
    execution_health = {
        "phase_6_exit_execution": {"last_check": "2026-07-27"},
    }
    run = {
        "phase_results": [
            {
                "phase": "6",
                "status": "degraded",
                "name": "exit_execution",
                "summary": "DRY-RUN: execution skipped (no real trades)",
            },
        ]
    }

    panel = _build_phase_execution_panel(execution_health, run)
    text = render_panel_to_text(panel)

    assert "SKIPPED (dry-run)" in text
    assert "HALTED" not in text


def test_genuine_phase6_degraded_still_shows_halted():
    """Sanity check mirroring the orchestrator.py fix's own sanity test: the exemption
    must not blanket-hide a real Phase 6 problem - only the literal DRY-RUN stub summary
    is exempted."""
    execution_health = {
        "phase_6_exit_execution": {"last_check": "2026-07-27"},
    }
    run = {
        "phase_results": [
            {
                "phase": "6",
                "status": "degraded",
                "name": "exit_execution",
                "summary": "3 position(s) failed exit/stop evaluation this run",
            },
        ]
    }

    panel = _build_phase_execution_panel(execution_health, run)
    text = render_panel_to_text(panel)

    assert "HALTED" in text
    assert "SKIPPED (dry-run)" not in text
