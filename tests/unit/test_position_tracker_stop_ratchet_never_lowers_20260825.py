"""Direct unit test (2026-08-25, real-money-readiness goal session - closing a specific
test-coverage gap) for PositionTracker.update_position_with_retry()'s stop-ratchet logic:
`effective_stop = current_stop if current_stop >= new_stop_decimal else new_stop_price`.

This exact function had no direct unit test - only indirect coverage via
executor_exit_handler.py's higher-level partial-exit tests, which mock at a level that
doesn't necessarily exercise this module's own internal Decimal comparison. Calls the real
function with a mocked cursor and inspects the actual UPDATE parameters passed to
cur.execute(), rather than asserting from reading the source.
"""

from unittest.mock import MagicMock

from algo.trading.position_tracker import PositionTracker


def _make_tracker():
    return PositionTracker(alpaca_key=None, alpaca_secret=None, alpaca_base_url="https://paper-api.alpaca.markets")


def _mock_cursor(current_qty, current_stop, target_levels_hit=0):
    cur = MagicMock()
    cur.rowcount = 1
    # do_update() reads (quantity, current_stop_price) first, then (if not full_exit)
    # target_levels_hit - matches the real function's exact query order.
    cur.fetchone.side_effect = [
        (current_qty, current_stop),
        (target_levels_hit,),
    ]
    return cur


class TestStopRatchetNeverLowers:
    def test_new_stop_below_current_is_ignored_not_written(self):
        """A caller-proposed new_stop_price BELOW the position's current_stop_price must
        never lower the DB value - the position keeps its higher, already-raised stop."""
        tracker = _make_tracker()
        cur = _mock_cursor(current_qty=100, current_stop=45.00)

        success, message = tracker.update_position_with_retry(
            cur=cur,
            position_id=1,
            new_qty=50,
            new_stop_price=40.00,  # LOWER than current_stop (45.00) - must be ignored
            full_exit=False,
            exit_stage="target_1",
        )

        assert success is True, message
        update_call = [c for c in cur.execute.call_args_list if "UPDATE algo_positions" in c.args[0]]
        assert len(update_call) == 1
        sql, params = update_call[0].args
        # current_stop_price is the 4th %s in the partial-exit UPDATE (quantity, position_value,
        # target_levels_hit, current_stop_price, ...) - verify by value, not position, to stay
        # robust to column reordering.
        assert 45.00 in params, f"expected the preserved current_stop (45.00) in UPDATE params, got {params}"
        assert 40.00 not in params, f"the lower proposed stop (40.00) must never reach the UPDATE, got {params}"

    def test_new_stop_above_current_is_written(self):
        """A caller-proposed new_stop_price ABOVE the position's current_stop_price (a real
        stop raise) must be written through."""
        tracker = _make_tracker()
        cur = _mock_cursor(current_qty=100, current_stop=45.00)

        success, message = tracker.update_position_with_retry(
            cur=cur,
            position_id=1,
            new_qty=50,
            new_stop_price=50.00,  # HIGHER than current_stop (45.00) - a real raise
            full_exit=False,
            exit_stage="target_1",
        )

        assert success is True, message
        update_call = [c for c in cur.execute.call_args_list if "UPDATE algo_positions" in c.args[0]]
        sql, params = update_call[0].args
        assert 50.00 in params, f"expected the raised stop (50.00) in UPDATE params, got {params}"
        assert 45.00 not in params, f"the stale lower stop (45.00) must not remain in the write, got {params}"

    def test_equal_new_stop_keeps_existing_value(self):
        """Boundary case: new_stop_price exactly equal to current_stop_price must not raise
        an error and results in the same (unchanged) value being written - not a decrease."""
        tracker = _make_tracker()
        cur = _mock_cursor(current_qty=100, current_stop=45.00)

        success, message = tracker.update_position_with_retry(
            cur=cur,
            position_id=1,
            new_qty=50,
            new_stop_price=45.00,
            full_exit=False,
            exit_stage="target_1",
        )

        assert success is True, message
        update_call = [c for c in cur.execute.call_args_list if "UPDATE algo_positions" in c.args[0]]
        sql, params = update_call[0].args
        assert 45.00 in params
