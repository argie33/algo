"""Regression test: phase6_exit_execution.py's tighten_stop and RAISE_STOP broker-sync calls
must push the MAX of the live current_stop_price and the (possibly stale) candidate value -
never the raw candidate directly.

REAL-MONEY-READINESS FINDING (2026-09-10, position-sizing/trailing-stop re-audit): the DB write
in both blocks already resolves staleness via `GREATEST(current_stop_price, %s)` (see
test_phase6_stop_raise_writes_are_monotonic.py), but `sync_bracket_stop_loss` - the call that
actually updates the live broker order - used to receive the raw, unresolved candidate
(action["new_stop"] / rec["new_stop_recommended"]) BEFORE that resolution happened. A stale
candidate (computed from an active_stop snapshot read earlier in the Phase 5->6 pipeline, that
some other path such as ExitEngine's own breakeven/chandelier raise had already superseded with
a higher value earlier in the same run) could therefore be pushed to Alpaca as a LOWER stop than
what the DB correctly ends up holding - the exact "wrong stop wins" risk-management regression
GREATEST() was meant to prevent, just relocated to the layer that actually protects real money.

Fixed by reading current_stop_price under the same advisory lock immediately before the broker
sync, resolving to the max in Python, and syncing/writing that resolved value everywhere - never
the raw candidate.

phase6_exit_execution.py's run() is too large/DB-heavy to unit-test end to end (see
test_phase6_stop_raise_writes_are_monotonic.py's precedent) - verified via source inspection:
in both blocks, a SELECT current_stop_price must appear (and a resolved_stop computed) BEFORE
sync_bracket_stop_loss is called, and sync_bracket_stop_loss must be called with resolved_stop,
not the raw candidate variable.
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


class TestPhase6BrokerStopSyncUsesResolvedValue:
    def test_tighten_stop_resolves_current_stop_price_before_broker_sync(self):
        block = _tighten_block()
        select_idx = block.index("SELECT current_stop_price FROM algo_positions")
        sync_idx = block.index("sync_bracket_stop_loss")
        assert select_idx < sync_idx, (
            "tighten_stop must read the live current_stop_price and resolve against it "
            "BEFORE calling sync_bracket_stop_loss - otherwise a stale candidate can be "
            "pushed to the broker as a lower stop than the DB will end up holding"
        )

    def test_tighten_stop_syncs_the_resolved_value_not_the_raw_candidate(self):
        block = _tighten_block()
        assert (
            "sync_bracket_stop_loss(\n                                        alpaca_order_id, resolved_stop\n" in block
        ), (
            "tighten_stop's sync_bracket_stop_loss call must pass resolved_stop (the max of "
            "current_stop_price and the candidate), not the raw action['new_stop'] candidate"
        )
        assert (
            'sync_bracket_stop_loss(\n                                        alpaca_order_id, action["new_stop"]\n'
            not in block
        )

    def test_raise_stop_resolves_current_stop_price_before_broker_sync(self):
        block = _raise_stop_block()
        select_idx = block.index("SELECT current_stop_price FROM algo_positions")
        sync_idx = block.index("sync_bracket_stop_loss")
        assert select_idx < sync_idx, (
            "RAISE_STOP must read the live current_stop_price and resolve against it BEFORE "
            "calling sync_bracket_stop_loss - otherwise a stale candidate can be pushed to "
            "the broker as a lower stop than the DB will end up holding"
        )

    def test_raise_stop_syncs_the_resolved_value_not_the_raw_candidate(self):
        block = _raise_stop_block()
        assert (
            "sync_bracket_stop_loss(\n                                        alpaca_order_id, resolved_stop\n" in block
        ), (
            "RAISE_STOP's sync_bracket_stop_loss call must pass resolved_stop (the max of "
            "current_stop_price and the candidate), not the raw rec['new_stop_recommended'] "
            "candidate"
        )
        assert (
            'sync_bracket_stop_loss(\n                                        alpaca_order_id, rec["new_stop_recommended"]\n'
            not in block
        )

    def test_both_updates_write_resolved_stop_not_the_raw_candidate(self):
        """The DB write must use the SAME resolved_stop value that was just synced to the
        broker, not re-derive it independently - otherwise the DB and broker could still
        diverge even after the sync-ordering fix."""
        assert SOURCE.count("GREATEST(current_stop_price, %s) WHERE id = %s", 0) >= 1
        assert '(resolved_stop, action["position_id"])' in SOURCE
        assert 'resolved_stop,\n                                            rec["position_id"],' in SOURCE
