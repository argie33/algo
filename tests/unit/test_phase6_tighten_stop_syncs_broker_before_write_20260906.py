"""Regression test: phase6_exit_execution.py's tighten_stop action (driven by
exposure_policy.py's tighten_winners_at_r) writes algo_positions.current_stop_price
directly via SQL without ever syncing the tightened price to the live broker bracket
order - the sibling RAISE_STOP action (see
test_phase6_raise_stop_syncs_broker_before_write_20260824.py) was already fixed to call
trade_executor.order_manager.sync_bracket_stop_loss() before writing, but this action
bypassed that fix entirely (same duplicate-logic-in->1-place bug class flagged
throughout memory - real-money-readiness audit, found 2026-09-06). That meant an
exposure-driven stop tighten only ever updated our own DB's belief about the stop; the
bracket order's stop-loss leg resting at the broker stayed at its original, wider price,
so a fast adverse move between orchestrator runs could blow through the stop we thought
we'd tightened with nothing live at the exchange to catch it.

phase6_exit_execution.py's run() is too large/DB-heavy to unit-test end to end (see
test_phase6_stop_raise_writes_are_monotonic.py's identical precedent) - verified via
source inspection instead: the broker sync call must appear before the UPDATE
statement, and a failed sync must raise before the UPDATE can run.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = (REPO_ROOT / "algo" / "orchestrator" / "phase6_exit_execution.py").read_text(encoding="utf-8")

TIGHTEN_MARKER = 'elif action["action"] == "tighten_stop":'
UPDATE_MARKER = "UPDATE algo_positions SET current_stop_price = GREATEST(current_stop_price, %s) WHERE id = %s"


def _tighten_block() -> str:
    start = SOURCE.index(TIGHTEN_MARKER)
    # Bounded to this action's own except clause, not the sibling RAISE_STOP block further down.
    end = SOURCE.index("except (RuntimeError, ValueError, TypeError) as e:", start)
    return SOURCE[start:end]


class TestPhase6TightenStopSyncsBrokerBeforeWrite:
    def test_tighten_stop_block_calls_sync_bracket_stop_loss(self):
        block = _tighten_block()
        assert "sync_bracket_stop_loss" in block, (
            "phase6_exit_execution.py's tighten_stop action must call "
            "trade_executor.order_manager.sync_bracket_stop_loss() before writing "
            "current_stop_price - otherwise an exposure-driven stop tighten never "
            "reaches the live broker order."
        )

    def test_sync_call_precedes_the_stop_price_update_in_source_order(self):
        block = _tighten_block()
        sync_idx = block.index("sync_bracket_stop_loss")
        update_idx = block.index(UPDATE_MARKER)
        assert sync_idx < update_idx, (
            "sync_bracket_stop_loss() must be called BEFORE the current_stop_price UPDATE "
            "in the tighten_stop block - fail closed, don't record a tighten the broker "
            "hasn't actually confirmed"
        )

    def test_failed_sync_raises_before_reaching_the_update(self):
        block = _tighten_block()
        sync_call_idx = block.index("sync_bracket_stop_loss")
        guard_region = block[sync_call_idx : sync_call_idx + 400]
        assert 'if not sync_result.get("success")' in guard_region
        assert "raise RuntimeError" in guard_region, (
            "a failed broker sync must raise (caught by this block's existing except clause "
            "and persisted as tighten_stop_failed), not silently fall through to the UPDATE"
        )
