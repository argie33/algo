"""Regression test for a real-money-readiness gap in phase6_exit_execution.py's tighten_stop
and RAISE_STOP blocks: the broker sync call (trade_executor.order_manager.sync_bracket_stop_loss)
used to run with the RAW candidate value (action["new_stop"] / rec["new_stop_recommended"]),
computed earlier in the Phase 5/3 -> 6 pipeline from a current_stop_price snapshot that can go
stale by the time this write executes. The sibling DB write already guards against ever
LOWERING current_stop_price via GREATEST(current_stop_price, %s) - but the broker sync call ran
BEFORE that guard, with the un-resolved value. Under a race with another path (e.g. ExitEngine's
own breakeven/chandelier raise) already having committed a HIGHER current_stop_price for this
same position earlier in the same run, this could push a stop to the broker LOWER than what's
already resting there - independent of the DB's own monotonic guarantee.

Fixed: both blocks now re-read current_stop_price under the advisory lock they already hold,
resolve the value to sync as max(db_current, candidate), and use that SAME resolved value for
both the broker sync call and the subsequent DB write.

phase6_exit_execution.py's run() is too large/DB-heavy to unit-test end to end (same precedent
as test_phase6_tighten_stop_syncs_broker_before_write_20260906.py) - verified via source
inspection: a SELECT current_stop_price must appear between the alpaca_order_id lookup and the
sync_bracket_stop_loss call, and sync_bracket_stop_loss/the UPDATE must both be called with the
resolved variable, not the raw action/rec value.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = (REPO_ROOT / "algo" / "orchestrator" / "phase6_exit_execution.py").read_text(encoding="utf-8")

TIGHTEN_MARKER = 'elif action["action"] == "tighten_stop":'
RAISE_STOP_MARKER = 'elif rec["action"] == "RAISE_STOP" and rec.get("new_stop_recommended") is not None:'


def _tighten_block() -> str:
    start = SOURCE.index(TIGHTEN_MARKER)
    end = SOURCE.index("except (RuntimeError, ValueError, TypeError) as e:", start)
    return SOURCE[start:end]


def _raise_stop_block() -> str:
    start = SOURCE.index(RAISE_STOP_MARKER)
    end = SOURCE.index("except (RuntimeError, ValueError, TypeError) as e:", start)
    return SOURCE[start:end]


class TestTightenStopSyncsResolvedNotRawValue:
    def test_current_stop_price_reread_before_broker_sync(self):
        block = _tighten_block()
        select_idx = block.index("SELECT current_stop_price FROM algo_positions")
        sync_idx = block.index("sync_bracket_stop_loss(")
        assert select_idx < sync_idx, (
            "current_stop_price must be re-read under the advisory lock BEFORE the broker "
            "sync call, so the synced value reflects any higher stop another path already "
            "committed this run."
        )

    def test_broker_sync_uses_resolved_stop_not_raw_action_value(self):
        block = _tighten_block()
        sync_call_idx = block.index("sync_bracket_stop_loss(")
        call_region = block[sync_call_idx : sync_call_idx + 200]
        assert "resolved_stop" in call_region
        assert 'action["new_stop"]' not in call_region.split(")")[0], (
            "the broker sync must be called with the resolved (max of DB-current and "
            'candidate) value, not the raw, possibly-stale action["new_stop"]'
        )

    def test_db_write_also_uses_resolved_stop(self):
        block = _tighten_block()
        update_idx = block.index("UPDATE algo_positions SET current_stop_price = GREATEST")
        update_region = block[update_idx : update_idx + 300]
        assert "resolved_stop" in update_region


class TestRaiseStopSyncsResolvedNotRawValue:
    def test_current_stop_price_reread_before_broker_sync(self):
        block = _raise_stop_block()
        select_idx = block.index("SELECT current_stop_price FROM algo_positions")
        sync_idx = block.index("sync_bracket_stop_loss(")
        assert select_idx < sync_idx

    def test_broker_sync_uses_resolved_stop_not_raw_rec_value(self):
        block = _raise_stop_block()
        sync_call_idx = block.index("sync_bracket_stop_loss(")
        call_region = block[sync_call_idx : sync_call_idx + 200]
        assert "resolved_stop" in call_region
        assert 'rec["new_stop_recommended"]' not in call_region.split(")")[0]

    def test_db_write_also_uses_resolved_stop(self):
        block = _raise_stop_block()
        update_idx = block.index("UPDATE algo_positions SET current_stop_price = GREATEST")
        update_region = block[update_idx : update_idx + 300]
        assert "resolved_stop" in update_region
