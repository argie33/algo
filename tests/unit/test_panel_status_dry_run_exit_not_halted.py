"""Regression test: panel_status()'s per-phase badge loop must render Phase 6's benign
dry-run stub as a cautionary "skipped" badge, not the same yellow "~" (halted-looking)
badge as a genuine halt.

Same bug class as test_phase_panel_dry_run_exit_not_halted.py's
_build_phase_execution_panel fix and _build_results_panel's equivalent fix (see either
for the full write-up) - phase6_exit_execution.py's dry_run branch unconditionally
reports status="degraded" with summary "DRY-RUN: execution skipped (no real trades)",
which is indistinguishable from a genuine "halt"/"warn"/"degraded" status to a badge
renderer that only checks the raw status string. panel_status()'s phase-badge loop had
the identical unguarded `ps in ("halt", "halted", "warn", "degraded", "skipped")` check
with no dry-run exemption - missed when the other two call sites were fixed because this
one lives in a third, separate function.

panel_status() is not currently wired into any live dashboard screen (dead code, per
dashboard/renderers/pipeline.py not importing it) and requires many unrelated
preconditions (act/hlth/notifs/exec_hist all need specific non-empty shapes to avoid
early error-panel returns, "Activity log missing 'phases' field" errors, etc.) to fully
exercise end-to-end - not worth building a full mock harness for dead code. Uses this
file's existing source-inspection pattern instead (see
tests/unit/test_phase8_execution_failure_audit_gap.py's
test_sizer_blocked_and_liquidity_skips_are_persisted_to_audit_table for the same
approach applied elsewhere in this codebase).
"""

import inspect

from dashboard.panels import health as health_module


def test_panel_status_phase_badge_loop_exempts_dry_run_stub_from_halted_badge():
    source = inspect.getsource(health_module.panel_status)

    # Isolate the phase-badge loop (iterates run["phase_results"], builds phase_badges).
    loop_start = source.index("for p in phase_results:")
    loop_end = source.index('phase_badges.append(f"[{sc}]{si}[dim]{short}[/][/]")')
    loop_body = source[loop_start:loop_end]

    assert "is_dry_run_stub" in loop_body, (
        "panel_status()'s phase-badge loop must exempt the DRY-RUN stub before falling "
        "through to the generic halt/warn/degraded branch, matching "
        "_build_phase_execution_panel and _build_results_panel"
    )
    assert 'ps == "degraded"' in loop_body and "DRY-RUN" in loop_body

    # The exemption must gate the badge color/icon selection, not just exist unused.
    sc_expr = source[source.index("sc = (", loop_start) : source.index("si = (", loop_start)]
    si_expr = source[source.index("si = (", loop_start) : loop_end]
    assert "is_dry_run_stub" in sc_expr
    assert "is_dry_run_stub" in si_expr
