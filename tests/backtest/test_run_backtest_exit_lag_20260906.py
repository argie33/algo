#!/usr/bin/env python3
"""Regression test: run_backtest() previously exited on a SELL signal at the signal day's own
close (zero lag) - the identical bug class the 2026-08-27 entry-lag fix addressed for BUY
signals, but explicitly left unchecked for exits at the time (see run_backtest.py's own
docstring, which called this out as "a symmetric look at exit lag was not done"). Fixed
2026-09-06: a SELL signal fired on day N is now filled one trading day later, at day N+1's
price - matching the entry-lag model exactly. Price-triggered exits (profit target/stop
loss/max hold) are level-based, not signal-based, and remain same-day by design.
"""

from datetime import date
from typing import Any
from unittest.mock import patch

from algo.backtest.run_backtest import run_backtest

DAY1_ENTRY = date(2026, 2, 2)
DAY2_SELL_SIGNAL = date(2026, 2, 3)
DAY3_EXIT_FILL = date(2026, 2, 4)
DAY4_NO_EVENT = date(2026, 2, 5)
TRADING_DATES = [DAY1_ENTRY, DAY2_SELL_SIGNAL, DAY3_EXIT_FILL, DAY4_NO_EVENT]

ENTRY_PRICE = 100.0
SIGNAL_DAY_PRICE = 105.0  # what the old (buggy) same-day-close exit logic would have used
NEXT_DAY_PRICE = 110.0  # what the new, lag-aware logic should actually use
FINAL_PRICE = 111.0


def _buy_signals(
    signal_date: date, min_composite: float, rank_by: str = "signal_quality_score"
) -> list[dict[str, Any]]:
    if signal_date == DAY1_ENTRY:
        return [
            {
                "symbol": "EXITLAGTEST",
                "entry_price": ENTRY_PRICE,
                "signal_quality_score": 90.0,
                "composite_score": 80.0,
            }
        ]
    return []


def _sell_signals(signal_date: date) -> set[str]:
    if signal_date == DAY2_SELL_SIGNAL:
        return {"EXITLAGTEST"}
    return set()


def _prices_batch(symbols: list[str], target_date: date) -> dict[str, float]:
    price_by_date = {
        DAY1_ENTRY: ENTRY_PRICE,
        DAY2_SELL_SIGNAL: SIGNAL_DAY_PRICE,
        DAY3_EXIT_FILL: NEXT_DAY_PRICE,
        DAY4_NO_EVENT: FINAL_PRICE,
    }
    return dict.fromkeys(symbols, price_by_date[target_date])


def _prices_batch_with_range(symbols: list[str], target_date: date) -> dict[str, tuple[float, float, float]]:
    return {symbol: (price, price, price) for symbol, price in _prices_batch(symbols, target_date).items()}


class TestRunBacktestExitLag:
    def test_sell_signal_exit_fills_one_day_after_signal_not_on_signal_day(self) -> None:
        with (
            patch("algo.backtest.run_backtest._get_trading_dates", return_value=TRADING_DATES),
            patch("algo.backtest.run_backtest._get_daily_buy_signals", side_effect=_buy_signals),
            patch("algo.backtest.run_backtest._get_daily_sell_signals", side_effect=_sell_signals),
            patch("algo.backtest.run_backtest._get_prices_batch", side_effect=_prices_batch),
            patch("algo.backtest.run_backtest._get_prices_batch_with_range", side_effect=_prices_batch_with_range),
        ):
            results = run_backtest(
                start_date=DAY1_ENTRY,
                end_date=DAY4_NO_EVENT,
                initial_capital=100_000.0,
                slippage_bps=0.0,
                profit_target_pct=1000.0,  # never fires - isolate sell-signal exit timing only
                stop_loss_pct=1000.0,
                max_hold_days=60,
            )

        assert results["total_trades"] == 1
        trade = results["trades"][0]

        # The exit must fill at NEXT_DAY_PRICE (the day AFTER the sell signal fired), never at
        # SIGNAL_DAY_PRICE (the signal day's own close) - that's the exact bug this fixes.
        assert trade["exit_price"] == NEXT_DAY_PRICE
        assert trade["exit_price"] != SIGNAL_DAY_PRICE
        assert trade["exit_date"] == DAY3_EXIT_FILL
        assert trade["exit_reason"] == "sell_signal"
