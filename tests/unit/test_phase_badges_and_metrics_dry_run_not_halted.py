"""Regression test: _build_phase_badges_and_metrics() (panel_algo_health's phase-badge
builder, wired live into dashboard/renderers/pipeline.py) must exempt Phase 6's benign
DRY-RUN stub from the halted-looking yellow "~" badge, same as the 3 other call sites
already fixed 2026-08-10 (_build_phase_execution_panel, _build_results_panel, the
dead-code panel_status). This is a 4th, previously-missed instance, found by auditing
every HALTED_STATES/_format_phase_badge call site in the file rather than assuming the
first 3 fixes were exhaustive.

_format_phase_badge() alone can never fix this: it only receives the raw status string,
with no summary text to distinguish "degraded" (genuine issue) from "degraded" + a literal
"DRY-RUN" summary (Phase 6's dry_run branch, unconditional, before any real exit logic runs).
"""

from dashboard.panels.health import _build_phase_badges_and_metrics


def _phase(name, status, summary=""):
    return {"name": name, "status": status, "summary": summary, "data": None}


class TestPhaseBadgesDryRunNotHalted:
    def test_phase6_dry_run_stub_renders_dim_skip_not_yellow_halt(self):
        phase_results = [
            _phase("phase_6_exit_execution", "degraded", "DRY-RUN: execution skipped (no real trades)"),
        ]

        badges, _, _, _ = _build_phase_badges_and_metrics({}, phase_results)

        assert len(badges) == 1
        badge = badges[0]
        assert "⊘" in badge, f"dry-run stub must render the dim skip icon, got: {badge}"
        assert "~" not in badge, f"dry-run stub must NOT render the halted-looking badge, got: {badge}"

    def test_genuine_degraded_status_without_dry_run_summary_still_renders_halted(self):
        # Not exempted: a real degraded status (no "DRY-RUN" in the summary) must still
        # show the halted-looking badge - this exemption must not swallow real issues.
        phase_results = [
            _phase("phase_6_exit_execution", "degraded", "win-rate circuit breaker triggered"),
        ]

        badges, _, _, _ = _build_phase_badges_and_metrics({}, phase_results)

        assert "~" in badges[0], f"a genuine degraded status must still render as halted, got: {badges[0]}"

    def test_genuine_halt_status_still_renders_halted(self):
        phase_results = [_phase("phase_6_exit_execution", "halted", "circuit breaker: max drawdown exceeded")]

        badges, _, _, _ = _build_phase_badges_and_metrics({}, phase_results)

        assert "~" in badges[0]
        assert "⊘" not in badges[0]
