"""Regression test: Phase 8's total-portfolio-risk cap (max_total_risk_pct) must be enforced
as a running tally within a single run, not just checked once before the entry loop.

REAL-MONEY-READINESS FINDING (2026-09-10, position-sizing/trailing-stop re-audit): unlike
remaining_buying_power (correctly decremented per-accepted-entry within a run - see
test_phase8_buying_power_proactive_block_20260825.py), the pre-loop
_calculate_current_total_risk_pct() check was a single snapshot taken once before the loop
and never decremented as entries were accepted. The `elif available_capacity_pct < 1.0:`
branch only ever logged "Will size positions conservatively to stay within limit" - no code
anywhere actually enforced that. Concrete scenario: available_capacity_pct=1.5% (just above
the 0.3% hard block), 5 available position slots, ~1% base_risk_pct per entry -> up to +5%
new risk could be added in one run against a 4% total limit, undetected until the NEXT
reconciliation cycle's circuit breaker (CB4) caught the overshoot after the fact.

Fixed by remaining_risk_capacity_pct: the same "running total within this run" shape
remaining_buying_power already uses, decremented in the entry loop as each candidate's own
sizer-computed risk_dollars (converted to %-of-portfolio) clears
_check_risk_capacity_sufficient().
"""

from pathlib import Path

from algo.orchestrator.phase8_entry_execution import _check_risk_capacity_sufficient

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = (REPO_ROOT / "algo" / "orchestrator" / "phase8_entry_execution.py").read_text(encoding="utf-8")


class TestCheckRiskCapacitySufficient:
    def test_candidate_within_remaining_capacity_passes(self):
        ok, reason = _check_risk_capacity_sufficient(1.5, 1.0)
        assert ok is True
        assert reason is None

    def test_candidate_exactly_at_remaining_capacity_passes(self):
        ok, reason = _check_risk_capacity_sufficient(1.0, 1.0)
        assert ok is True
        assert reason is None

    def test_candidate_exceeding_remaining_capacity_blocks(self):
        ok, reason = _check_risk_capacity_sufficient(0.5, 1.0)
        assert ok is False
        assert reason is not None
        assert "0.50" in reason
        assert "1.00" in reason

    def test_zero_remaining_capacity_blocks_any_positive_risk(self):
        ok, reason = _check_risk_capacity_sufficient(0.0, 0.01)
        assert ok is False
        assert reason is not None


class TestRiskCapacityWiredIntoEntryLoop:
    """Source-inspection tests (this function's run() is too large/DB-heavy to unit-test end
    to end - see test_phase6_stop_raise_writes_are_monotonic.py's precedent for this same
    class of test in a sibling phase file)."""

    def test_remaining_risk_capacity_pct_initialized_from_pre_loop_snapshot(self):
        assert "remaining_risk_capacity_pct: float = available_capacity_pct" in SOURCE, (
            "remaining_risk_capacity_pct must be initialized from the pre-loop "
            "available_capacity_pct snapshot so the running tally starts from the same "
            "authoritative baseline the one-time guard already computed"
        )

    def test_entry_loop_calls_check_risk_capacity_sufficient(self):
        assert "_check_risk_capacity_sufficient(" in SOURCE, (
            "the entry loop must call _check_risk_capacity_sufficient() for each candidate - "
            "otherwise the running risk-capacity tally is tracked but never enforced"
        )

    def test_entry_loop_decrements_remaining_risk_capacity_pct_on_acceptance(self):
        assert "remaining_risk_capacity_pct -= candidate_risk_pct" in SOURCE, (
            "an accepted candidate must decrement remaining_risk_capacity_pct - otherwise "
            "later candidates in the same run are checked against a stale, too-generous "
            "budget that never reflects earlier acceptances this run"
        )

    def test_no_dead_conservative_sizing_log_with_zero_enforcement_remains(self):
        """The old branch claimed 'Will size positions conservatively to stay within limit'
        with zero code anywhere actually doing that - must not silently reappear now that
        real enforcement exists."""
        assert "Will size positions conservatively to stay within limit" not in SOURCE, (
            "found the old misleading log line that implied conservative sizing without any "
            "enforcement behind it - the real enforcement (remaining_risk_capacity_pct) "
            "replaces this, not coexists with it"
        )

    def test_rejection_reason_uses_insufficient_risk_capacity_category(self):
        assert '"insufficient_risk_capacity"' in SOURCE, (
            "a candidate blocked by the running risk-capacity tally must be logged to "
            "algo_signal_rejections with a distinct reason category, not silently merged "
            "into an unrelated rejection reason"
        )
