"""Regression test for a 2026-09-07 real-money-readiness audit fix to run_backtest.py.

BEFORE: the position-management loop only fetched `close` from price_daily
(_get_prices_batch), so a stop-loss or profit-target that was breached intraday and then
recovered by close was missed ENTIRELY - not just mispriced, but never detected as an exit
at all. AFTER: _get_prices_batch_with_range() also fetches the day's high/low (already
stored in price_daily's own OHLC bar), and the exit-decision loop checks the day's actual
low against the stop level (and high against the target level), not just the close.

This test proves the specific failure mode: a position closes UP on the day (+1%, nowhere
near the 8% stop) but the day's LOW breached the stop level intraday before recovering -
under the old close-only logic this position would incorrectly stay open.
"""

from datetime import date
from typing import Any
from unittest.mock import patch

from algo.backtest.run_backtest import run_backtest

DAY1 = date(2024, 1, 2)
DAY2 = date(2024, 1, 3)
DAY3 = date(2024, 1, 4)

BUY_SIGNAL = [{"symbol": "TEST", "signal_quality_score": 90, "composite_score": 80.0}]


def _run(day3_ohlc: tuple[float, float, float]) -> dict[str, Any]:
    """day3_ohlc = (close, high, low) for TEST on DAY3, the day the position is open."""
    with (
        patch("algo.backtest.run_backtest._get_trading_dates", return_value=[DAY1, DAY2, DAY3]),
        patch("algo.backtest.run_backtest._get_daily_sell_signals", return_value=set()),
        # Only signal entry once (from DAY1, filled on DAY2) - DAY2's own signal must NOT
        # re-trigger a fresh entry on DAY3 after the original position has already exited
        # intraday, which would otherwise confound "trades" with an unrelated end-of-backtest
        # liquidation of a second, newly-opened position.
        patch(
            "algo.backtest.run_backtest._get_daily_buy_signals",
            side_effect=lambda signal_date, min_composite, rank_by="signal_quality_score": (
                BUY_SIGNAL if signal_date == DAY1 else []
            ),
        ),
        patch("algo.backtest.run_backtest._get_prices_batch", return_value={"TEST": 100.0}),
        patch(
            "algo.backtest.run_backtest._get_prices_batch_with_range",
            side_effect=lambda symbols, target_date: (
                {"TEST": (100.0, 100.0, 100.0)} if target_date == DAY2 else {"TEST": day3_ohlc}
            ),
        ),
    ):
        return run_backtest(
            start_date=DAY1,
            end_date=DAY3,
            initial_capital=100_000.0,
            max_positions=10,
            stop_loss_pct=8.0,
            profit_target_pct=20.0,
        )


class TestIntradayStopLossDetection:
    def test_stop_loss_detected_from_low_even_though_close_recovered(self) -> None:
        # Entry ~$100 (+5bps slippage). Stop level = entry_price * 0.92 ~= $92.05.
        # DAY3 closes at $101 (+1%, nowhere near the 8% stop) but the day's LOW was $88 -
        # a real intraday stop-out that a close-only check would completely miss.
        result = _run(day3_ohlc=(101.0, 101.0, 88.0))

        trades = result["trades"]
        assert len(trades) == 1, f"expected exactly one completed (stopped-out) trade, got: {trades}"
        assert trades[0]["exit_reason"] == "stop_loss"
        assert trades[0]["exit_date"] == DAY3

    def test_profit_target_detected_from_high_even_though_close_pulled_back(self) -> None:
        # Target level = entry_price * 1.20 ~= $120.06. DAY3 closes at $105 (+5%, nowhere near
        # the 20% target) but the day's HIGH was $125 - a real intraday target hit a
        # close-only check would completely miss.
        result = _run(day3_ohlc=(105.0, 125.0, 105.0))

        trades = result["trades"]
        assert len(trades) == 1, f"expected exactly one completed (target-hit) trade, got: {trades}"
        assert trades[0]["exit_reason"] == "profit_target"

    def test_no_false_positive_when_the_day_never_crosses_either_level(self) -> None:
        # Close, high, and low all comfortably inside the stop/target band - the position must
        # NOT be reported as stopped-out or target-hit. DAY3 is the backtest's last day, so it
        # still gets force-closed at end-of-window (expected, unrelated to this fix) - the
        # point here is that exit_reason must be "end_of_backtest", not a false "stop_loss"/
        # "profit_target" from a level neither the close nor the (tight) day range crossed.
        result = _run(day3_ohlc=(102.0, 103.0, 99.0))

        trades = result["trades"]
        assert len(trades) == 1
        assert trades[0]["exit_reason"] == "end_of_backtest"

    def test_stop_takes_priority_when_both_levels_crossed_same_day(self) -> None:
        # Daily OHLC alone can't tell which of stop/target happened first within the day -
        # this backtest deliberately assumes the conservative (stop-first) ordering rather
        # than the optimistic (target-first) one.
        result = _run(day3_ohlc=(102.0, 125.0, 88.0))

        trades = result["trades"]
        assert len(trades) == 1
        assert trades[0]["exit_reason"] == "stop_loss"
