"""Regression test: _build_phase_badges_from_audit() must render Phase 6's benign
dry-run stub as a cautionary "skipped" badge, not the same yellow "~" (halted-looking)
badge as a genuine halt.

Same bug class as test_phase_panel_dry_run_exit_not_halted.py's
_build_phase_execution_panel fix, _build_results_panel's equivalent fix, and
_build_phase_badges_and_metrics's equivalent fix (see any for the full write-up) -
phase6_exit_execution.py's dry_run branch unconditionally reports status="degraded"
with summary "DRY-RUN: execution skipped (no real trades)", which is indistinguishable
from a genuine "halt"/"warn"/"degraded" status to a badge renderer that only checks the
raw status string.

_build_phase_badges_from_audit() is reached live from panel_algo_health() (wired into
dashboard/renderers/pipeline.py) whenever the run data comes from the "act"/non-exec_log
source rather than the primary exec_log path - a real, reachable fallback branch, not
dead code. It calls _format_phase_badge(status), which only receives the raw status
string with no summary text and so can never apply the dry-run exemption itself - the
exemption has to live in the caller, exactly as it already does in
_build_phase_badges_and_metrics. This call site was missed when the other four were
fixed because it lives in a fifth, structurally separate function reached via a
different data-source branch.

Verified via: python -m pytest tests/unit/test_phase_badges_from_audit_dry_run_not_halted.py -q
"""

from dashboard.panels.health import _build_phase_badges_from_audit
from dashboard.utilities import DIM, R, Y


def test_phase6_dry_run_stub_gets_dim_skipped_badge_not_halted_badge():
    phases_list = [
        {
            "action_type": "phase_6_exit_execution",
            "status": "degraded",
            "summary": "DRY-RUN: execution skipped (no real trades) - would have: 0 exits, 0 stop-raises",
        }
    ]

    badges = _build_phase_badges_from_audit(phases_list)

    assert len(badges) == 1
    assert f"[{DIM}]" in badges[0], f"dry-run stub must render dim/skipped, got: {badges[0]}"
    assert f"[{Y}]" not in badges[0], f"dry-run stub must NOT render as halted (yellow), got: {badges[0]}"
    assert "⊘" in badges[0]
    assert "~" not in badges[0]


def test_genuine_phase6_halt_still_gets_halted_badge():
    """The fix must not swallow a real halt - only the DRY-RUN false positive."""
    phases_list = [
        {
            "action_type": "phase_6_exit_execution",
            "status": "halted",
            "summary": "Position monitor data unavailable - halting exit execution",
        }
    ]

    badges = _build_phase_badges_from_audit(phases_list)

    assert len(badges) == 1
    assert f"[{Y}]" in badges[0], f"a genuine halt must still render yellow/halted, got: {badges[0]}"
    assert "~" in badges[0]


def test_genuine_error_status_still_gets_error_badge():
    phases_list = [
        {
            "action_type": "phase_6_exit_execution",
            "status": "error",
            "summary": "Unhandled exception during exit execution",
        }
    ]

    badges = _build_phase_badges_from_audit(phases_list)

    assert len(badges) == 1
    assert f"[{R}]" in badges[0], f"a genuine error must still render red, got: {badges[0]}"
    assert "✗" in badges[0]
