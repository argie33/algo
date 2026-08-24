"""Regression test: phase6_exit_execution.py's RAISE_STOP action (driven by
position_monitor.py's own trailing-stop recommendation) writes algo_positions.
current_stop_price directly via SQL - a second, independent write site from
executor_exit_handler.py's ExitHandler._raise_stop_only, which
[[order_types_and_stop_loss_architecture_audit_20260824]] fixed to sync a raised stop
to the live broker bracket order before recording it in our own DB. This RAISE_STOP
site bypassed that fix entirely (same duplicate-logic-in->1-place bug class flagged
throughout memory), so a stop trailed via position_monitor.py's recommendation path
still only ever updated our own belief, never the resting broker order.

phase6_exit_execution.py's run() is too large/DB-heavy to unit-test end to end (see
test_phase6_stop_raise_writes_are_monotonic.py's identical precedent for this exact
file/class of change) - verified via source inspection instead: the broker sync call
must appear before the UPDATE statement, and a failed sync must raise before the
UPDATE can run.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = (REPO_ROOT / "algo" / "orchestrator" / "phase6_exit_execution.py").read_text(encoding="utf-8")


class TestPhase6RaiseStopSyncsBrokerBeforeWrite:
    def test_raise_stop_block_calls_sync_bracket_stop_loss(self):
        assert "sync_bracket_stop_loss" in SOURCE, (
            "phase6_exit_execution.py's RAISE_STOP action must call "
            "trade_executor.order_manager.sync_bracket_stop_loss() before writing "
            "current_stop_price - otherwise a stop trailed via position_monitor.py's "
            "recommendation never reaches the live broker order."
        )

    def test_sync_call_precedes_the_stop_price_update_in_source_order(self):
        raise_stop_marker = 'elif rec["action"] == "RAISE_STOP" and rec.get("new_stop_recommended") is not None:'
        update_marker = (
            'UPDATE algo_positions SET current_stop_price = GREATEST(current_stop_price, %s) "\n'
            '                                        "WHERE id = %s AND status = %s'
        )
        raise_stop_idx = SOURCE.index(raise_stop_marker)
        # Search only within the RAISE_STOP block, not the earlier sibling tighten_stop block.
        block = SOURCE[raise_stop_idx:]
        sync_idx = block.index("sync_bracket_stop_loss")
        update_idx = block.index(update_marker)
        assert sync_idx < update_idx, (
            "sync_bracket_stop_loss() must be called BEFORE the current_stop_price UPDATE "
            "in the RAISE_STOP block - fail closed, don't record a raise the broker hasn't "
            "actually confirmed"
        )

    def test_failed_sync_raises_before_reaching_the_update(self):
        raise_stop_marker = 'elif rec["action"] == "RAISE_STOP" and rec.get("new_stop_recommended") is not None:'
        block = SOURCE[SOURCE.index(raise_stop_marker) :]
        sync_call_idx = block.index("sync_bracket_stop_loss")
        # The nearest `if not sync_result.get("success")` after the call must raise, not just log.
        guard_region = block[sync_call_idx : sync_call_idx + 400]
        assert 'if not sync_result.get("success")' in guard_region
        assert "raise RuntimeError" in guard_region, (
            "a failed broker sync must raise (caught by this block's existing except clause "
            "and persisted as stop_raise_failed), not silently fall through to the UPDATE"
        )
