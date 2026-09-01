"""Regression test: Phase 8 must proactively alert when every attempted entry fails.

Real-money-readiness pass (round 3, 2026-09-01): if the Alpaca broker is unreachable or
erroring for an extended period during Phase 8 (entry execution), every execute_trade() call
fails and failed_count accumulates - already handled per-symbol without crashing (no entries
placed), but the ONLY signal this ever produced was a logger.critical() line, which nobody may
ever read in real time. Same "computed but never delivered" bug class already found 3x this
session (position_sync/reconciliation/database_health_monitor - see
real_money_readiness_parallel_review_20260901 in memory): a "degraded" phase status alone
doesn't page anyone - orchestrator.py's log_phase_result() only records it and publishes to the
dashboard EventHub, no proactive alert. This pins that Phase 8 now sends a real alert when
0 entries succeeded and at least 2 were attempted (broker-outage signature), and that the
orchestrator actually wires its AlertManager through to Phase 8's run().
"""

import inspect

from algo.orchestrator import phase8_entry_execution as p8


def test_run_accepts_an_alerts_parameter():
    sig = inspect.signature(p8.run)
    assert "alerts" in sig.parameters
    assert sig.parameters["alerts"].default is None


def test_all_entries_failed_triggers_a_position_alert_not_just_a_log():
    source = inspect.getsource(p8.run)
    branch = source.split("if failed_count > 0:", 1)[1]

    assert "alerts.send_position_alert(" in branch
    assert "PHASE8_ALL_ENTRIES_FAILED" in branch
    # Gated on a real outage signature (zero successes among 2+ attempts), not on any single
    # isolated rejection among an otherwise-healthy batch of entries.
    assert "executed_count == 0" in branch
    assert "failed_count >= 2" in branch


def test_alert_send_is_best_effort_non_blocking():
    """A failure to send the alert itself must never crash Phase 8 - matches this file's
    established convention (e.g. halt_flag_manager._alert_halt_detected) for alert calls that
    sit downstream of an already-completed, safety-critical decision."""
    source = inspect.getsource(p8.run)
    branch = source.split("PHASE8_ALL_ENTRIES_FAILED", 1)[1].split("def ", 1)[0]

    assert "except Exception as alert_err:" in branch
    assert "non-blocking" in branch.lower()


def test_orchestrator_wires_its_alert_manager_into_phase8():
    """The alerts= parameter Phase 8 now accepts is useless unless the orchestrator actually
    passes its real AlertManager instance through - pin the call site too."""
    from algo.orchestration import orchestrator as orch_mod

    source = inspect.getsource(orch_mod.Orchestrator._executor_phase_8)
    assert "alerts=self.alerts" in source
