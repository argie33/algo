"""Regression test for two 2026-07-27 fixes in Orchestrator._final_report(), both live-
reproduced by running scripts/run_local_orchestrator.py with ORCHESTRATOR_DRY_RUN=true (the
normal way to exercise Phase 8's guards outside market hours): a healthy local dry-run
(Phase 6 dry-run stub + Phase 8 blocked by the market-hours guard + Phase 9 succeeding) was
reported as OrchestratorFailure=1/overall_status="degraded" in CloudWatch-style metrics,
even though this exact combination is what a correct, non-broken run looks like pre-market.

Two independent bugs combined to cause this:

1. Phase 6 uses status="degraded" both for its benign, unconditional dry-run stub
   ("DRY-RUN: execution skipped (no real trades)") and for genuine per-item exit-execution
   errors. any_degraded used to be true for both, so the elif chain always took the "real
   degraded" branch before ever reaching the already-written "blocked guard is fine" logic.

2. Even when that logic IS reached, `phase_8_blocked = any(p["status"] == "blocked" and
   p.get("phase") == 8 for p in self.phase_results.values())` checked a "phase" key that
   log_phase_result() never sets on the inner dict (it only sets name/status/summary) - so
   `p.get("phase")` was always None and phase_8_blocked was permanently False, meaning the
   "ok if Phase 9 succeeded" outcome could never be reached regardless of fix #1.
"""

from unittest.mock import MagicMock, patch

from algo.orchestration.orchestrator import Orchestrator


def _fake_self(phase_results):
    self = object.__new__(Orchestrator)
    self.phase_results = phase_results
    self.run_id = "test-run"
    self.run_date = __import__("datetime").date(2026, 7, 27)
    self.execution_tracker = MagicMock()
    self.dry_run = True
    self.run_start = 0.0
    return self


HEALTHY_DRY_RUN_PHASES = {
    1: {"name": "all_tables_fresh", "status": "ok", "summary": "fresh"},
    2: {"name": "circuit_breakers", "status": "ok", "summary": "all clear"},
    3: {"name": "position_monitor", "status": "ok", "summary": "16 positions updated"},
    4: {"name": "reconciliation", "status": "ok", "summary": "16 positions verified"},
    5: {"name": "exposure_policy", "status": "ok", "summary": "no actions"},
    6: {"name": "exit_execution", "status": "degraded", "summary": "DRY-RUN: exit execution skipped (no real trades placed)"},
    7: {"name": "signal_generation", "status": "ok", "summary": "17 signals qualified"},
    8: {
        "name": "entry_execution",
        "status": "blocked",
        "summary": "[PHASE 8 MARKET HOURS GUARD] Cannot execute entries outside market hours.",
    },
    9: {"name": "reconciliation", "status": "ok", "summary": "Portfolio state: 71885.26 | Status: ok"},
}


def _run_final_report(phase_results):
    fake_self = _fake_self(dict(phase_results))
    with (
        patch("algo.orchestration.orchestrator.DatabaseContext"),
        patch("algo.reporting.MetricsPublisher"),
    ):
        return Orchestrator._final_report(fake_self)


class TestFinalReportBlockedDryRunCombo:
    def test_healthy_dry_run_with_market_hours_block_reports_success(self):
        """The core bug: this exact phase mix (real, live-reproduced) must be success=True,
        not a false OrchestratorFailure alarm."""
        result = _run_final_report(HEALTHY_DRY_RUN_PHASES)
        assert result["success"] is True, (
            "a dry-run stub (Phase 6) plus an expected market-hours block (Phase 8) with "
            "Phase 9 succeeding must report success, not a false failure"
        )

    def test_genuine_exit_execution_errors_still_report_failure(self):
        """Sanity check: the fix must not blanket-ignore real Phase 6 problems - only the
        literal dry-run stub text is exempted."""
        phases = dict(HEALTHY_DRY_RUN_PHASES)
        phases[6] = {
            "name": "exit_execution",
            "status": "degraded",
            "summary": "3 exit orders failed: insufficient buying power",
        }
        result = _run_final_report(phases)
        assert result["success"] is False

    def test_phase_8_blocked_recognized_by_dict_key_not_missing_field(self):
        """Isolates bug #2: even with only Phase 8 blocked (no Phase 6 involvement), the
        blocked-guard-is-healthy branch must actually trigger 'ok', not fall through to
        'degraded' because phase_8_blocked could never become True."""
        phases = {
            n: p for n, p in HEALTHY_DRY_RUN_PHASES.items() if n != 6
        }  # drop Phase 6 entirely - isolate bug #2
        result = _run_final_report(phases)
        assert result["success"] is True

    def test_block_on_a_different_phase_does_not_falsely_pass(self):
        """Guards against a too-broad fix: if some OTHER phase were ever blocked instead of
        Phase 8 specifically, this should not be silently waved through as healthy."""
        phases = dict(HEALTHY_DRY_RUN_PHASES)
        phases[8] = {"name": "entry_execution", "status": "ok", "summary": "entered 2 positions"}
        phases[5] = {"name": "exposure_policy", "status": "blocked", "summary": "unexpected block"}
        result = _run_final_report(phases)
        assert result["success"] is False

    def test_dry_run_stub_console_flag_reads_skip_not_degrad(self, caplog):
        """The overall success=True fix above only covers the aggregated run outcome -
        the per-phase line printed to the console still read '[DEGRAD] Phase 6:
        exit_execution' for the exact same benign dry-run stub, which looks like a real
        exit-execution failure to anyone scanning the report by eye (confirmed live: this
        is what triggered a false alarm reading a real dry-run log). It must display the
        same [SKIP] flag used for other intentional non-executions, not [DEGRAD]."""
        import logging

        with caplog.at_level(logging.INFO):
            _run_final_report(HEALTHY_DRY_RUN_PHASES)
        phase_6_lines = [r.message for r in caplog.records if "Phase 6:" in r.message]
        assert len(phase_6_lines) == 1
        assert "[SKIP]" in phase_6_lines[0]
        assert "[DEGRAD]" not in phase_6_lines[0]

    def test_genuine_exit_execution_errors_still_display_degrad_flag(self, caplog):
        """Sanity check mirroring test_genuine_exit_execution_errors_still_report_failure:
        the console-flag fix must not blanket-hide a real Phase 6 problem either - only
        the literal 'DRY-RUN' stub summary gets remapped to [SKIP]."""
        import logging

        phases = dict(HEALTHY_DRY_RUN_PHASES)
        phases[6] = {
            "name": "exit_execution",
            "status": "degraded",
            "summary": "3 exit orders failed: insufficient buying power",
        }
        with caplog.at_level(logging.INFO):
            _run_final_report(phases)
        phase_6_lines = [r.message for r in caplog.records if "Phase 6:" in r.message]
        assert len(phase_6_lines) == 1
        assert "[DEGRAD]" in phase_6_lines[0]
