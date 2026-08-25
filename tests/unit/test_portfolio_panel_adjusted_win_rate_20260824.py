#!/usr/bin/env python3
"""Regression tests for dashboard/panels/portfolio.py's _calculate_adjusted_win_rate and
_get_actual_position_count - continuing the test-coverage-completeness sweep onto the
dashboard's displayed financial metrics (not just backend computation).

_calculate_adjusted_win_rate is deliberately asymmetric: it counts currently-losing OPEN
positions against the win rate (they're real, current risk) but does NOT credit currently-
winning OPEN positions as wins (unrealized gains can still reverse before close) - a
conservative-bias design, not a bug. Verified this is honestly disclosed to the user in both
UI locations that display it (an "(adj.)" label suffix, and an explicit "(+N open L)" count),
not silently presented as a plain win rate.
"""

import pytest

from dashboard.panels.portfolio import _calculate_adjusted_win_rate, _get_actual_position_count


def _pos(*pnls: float) -> dict:
    return {"items": [{"unrealized_pnl_pct": p} for p in pnls]}


class TestCalculateAdjustedWinRate:
    def test_closed_trades_only_no_open_positions(self):
        perf = {"w": 7, "l": 3}
        wr, wins, losses = _calculate_adjusted_win_rate(perf, None)
        assert wr == pytest.approx(70.0)
        assert wins == 7
        assert losses == 3

    def test_losing_open_position_counted_against_win_rate(self):
        """The asymmetric adjustment: a losing open position increases the loss count and
        lowers the win rate, even though the position hasn't closed yet."""
        perf = {"w": 7, "l": 3}
        pos = _pos(-2.5)  # one open position, losing
        wr, wins, losses = _calculate_adjusted_win_rate(perf, pos)
        assert wins == 7
        assert losses == 4  # 3 closed + 1 open loss
        assert wr == pytest.approx(7 / 11 * 100)

    def test_winning_open_position_not_credited_as_a_win(self):
        """The other half of the asymmetry: a winning open position must NOT be added to
        wins or the denominator - only closed wins count as wins."""
        perf = {"w": 7, "l": 3}
        pos = _pos(4.0)  # one open position, winning
        wr, wins, losses = _calculate_adjusted_win_rate(perf, pos)
        assert wins == 7
        assert losses == 3  # unchanged - the open winner isn't counted anywhere
        assert wr == pytest.approx(70.0)  # identical to the no-open-positions case

    def test_mixed_open_positions_only_losers_affect_denominator(self):
        perf = {"w": 7, "l": 3}
        pos = _pos(4.0, -1.0, -3.0, 2.5)  # 1 winner, 2 losers, 1 winner
        wr, wins, losses = _calculate_adjusted_win_rate(perf, pos)
        assert wins == 7
        assert losses == 5  # 3 closed + 2 open losses (winners ignored)
        assert wr == pytest.approx(7 / 12 * 100)

    def test_no_trades_at_all_returns_none_not_zero(self):
        """Zero total trades must return None (undefined), not a misleading 0%."""
        perf = {"w": 0, "l": 0}
        wr, wins, losses = _calculate_adjusted_win_rate(perf, None)
        assert wr is None
        assert wins == 0
        assert losses == 0

    def test_perf_none_raises_rather_than_masking_with_zeros(self):
        with pytest.raises(ValueError, match="Performance data unavailable"):
            _calculate_adjusted_win_rate(None, None)

    def test_perf_error_marker_raises(self):
        with pytest.raises(ValueError, match="Performance data unavailable"):
            _calculate_adjusted_win_rate({"_error": "API 500"}, None)

    def test_position_error_marker_does_not_crash_falls_back_to_closed_only(self):
        perf = {"w": 5, "l": 2}
        pos = {"_error": "positions API down"}
        wr, wins, losses = _calculate_adjusted_win_rate(perf, pos)
        assert wins == 5
        assert losses == 2
        assert wr == pytest.approx(5 / 7 * 100)


class TestGetActualPositionCount:
    def test_uses_actual_count_when_positions_available(self):
        pos = _pos(1.0, -1.0, 2.0)
        assert _get_actual_position_count(snapshot_count=1, pos=pos) == 3

    def test_falls_back_to_snapshot_count_when_positions_unavailable(self):
        assert _get_actual_position_count(snapshot_count=4, pos=None) == 4

    def test_falls_back_to_snapshot_count_on_position_error(self):
        assert _get_actual_position_count(snapshot_count=4, pos={"_error": "down"}) == 4
