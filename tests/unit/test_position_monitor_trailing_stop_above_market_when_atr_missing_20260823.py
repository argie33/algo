"""Regression test for a 2026-08-23 fix in
algo/monitoring/position_monitor.py::_compute_trailing_stop().

The "room to breathe" cap (`cur_price - ATR`) was the ONLY thing keeping every stop
candidate <= cur_price, and it only ran inside `if atr is not None and atr > 0`. Outside
that block (ATR temporarily unavailable - a real, reachable data gap), `entry_price` is
added to `candidates` unconditionally whenever `target_hits >= 1`, with no upper bound.

Real, plausible sequence this breaks: a position hits its first profit target (target_hits=1,
entry_price added as "at least breakeven"), then price pulls back below entry before ATR
data is next refreshed. `entry_price > cur_price` in that window, so the old code could
return a stop ABOVE the current market price - a live stop-sell order with a trigger above
market executes essentially immediately upon submission, not as an actual protective stop.

The caller (review_positions -> _evaluate_position) already has a defensive
`if proposed_stop > cur_price: clamp` catch for exactly this (confirmed via its own ERROR-level
log line, evidence this is a real, previously-encountered condition, not purely theoretical) -
but per the same "don't rely on accidental caller-side correctness" principle already applied to
position_sizer.py's max_position_size_pct fix, this function's own contract should hold
unconditionally. Fixed by filtering every candidate to `< cur_price` regardless of ATR
availability, with a safe fallback (`cur_price - 0.01`) if that empties the list.
"""

from unittest.mock import MagicMock

from algo.monitoring.position_monitor import PositionMonitor


def _call(**overrides):
    kwargs = {
        "entry_price": 100.0,
        "active_stop": 85.0,
        "cur_price": 110.0,
        "atr": 2.0,
        "sma_50": 105.0,
        "target_hits": 0,
    }
    kwargs.update(overrides)
    return PositionMonitor._compute_trailing_stop(MagicMock(), **kwargs)


class TestTrailingStopNeverExceedsMarketWhenAtrMissing:
    def test_entry_price_candidate_capped_when_price_pulls_back_below_entry_no_atr(self):
        """Hit T1 (target_hits=1, entry_price=100 added as breakeven candidate), then price
        pulls back to 95 with ATR unavailable (None) - must NOT return a stop >= 95."""
        result = _call(
            entry_price=100.0,
            active_stop=85.0,
            cur_price=95.0,
            atr=None,
            sma_50=None,
            target_hits=1,
        )
        assert result < 95.0, f"Stop {result} must be strictly below current price 95.0, never at or above it"
        assert result == 85.0  # active_stop itself is already the correct, safe answer here

    def test_no_valid_candidate_falls_back_to_just_under_market(self):
        """Degenerate case: active_stop itself also >= cur_price (stale/imported position) and
        ATR unavailable - must still produce a safe result just under market, not raise or
        return an above-market value."""
        result = _call(
            entry_price=100.0,
            active_stop=99.0,  # gets clamped to cur_price - 0.01 = 94.99 by the earlier guard
            cur_price=95.0,
            atr=None,
            sma_50=None,
            target_hits=1,
        )
        assert result < 95.0

    def test_normal_atr_present_path_unaffected(self):
        """Sanity check: the fix must not change behavior when ATR is present - the existing
        ATR-based cap already guaranteed candidates < cur_price in that case."""
        result = _call(
            entry_price=100.0,
            active_stop=90.0,
            cur_price=110.0,
            atr=2.0,
            sma_50=105.0,
            target_hits=0,
        )
        assert result < 110.0
        assert isinstance(result, float)
