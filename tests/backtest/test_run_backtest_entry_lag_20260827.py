#!/usr/bin/env python3
"""Regression test: run_backtest() previously entered positions at the signal day's own close
(zero lag between signal detection and fill) - see run_backtest.py's module docstring "Entry
fill assumption" note for the live-DB evidence (n=104 closed local trades) that real Phase 8
entries land anywhere from same-day to 1-3 days after signal_date, never the instant a
breakout is detected. Fixed 2026-08-27 (real-money-readiness review): entries now fill one
trading day after the signal, at that later day's own price - not the signal day's price.

This pins that a signal fired on day N is NOT entered using day N's price even when day N's
price is available and would otherwise be picked up by the (unchanged) mark-to-market/entry
machinery - it must wait for day N+1.
"""

from datetime import date
from typing import Any
from unittest.mock import patch

from algo.backtest.run_backtest import run_backtest

DAY1_SIGNAL = date(2026, 2, 2)
DAY2_ENTRY_FILL = date(2026, 2, 3)
DAY3_NO_EVENT = date(2026, 2, 4)
TRADING_DATES = [DAY1_SIGNAL, DAY2_ENTRY_FILL, DAY3_NO_EVENT]

SIGNAL_DAY_PRICE = 50.0  # what the old (buggy) same-day-close logic would have used
NEXT_DAY_PRICE = 65.0  # what the new, lag-aware logic should actually use


def _buy_signals(
    signal_date: date, min_composite: float, rank_by: str = "signal_quality_score"
) -> list[dict[str, Any]]:
    if signal_date == DAY1_SIGNAL:
        return [
            {
                "symbol": "LAGTEST",
                "entry_price": SIGNAL_DAY_PRICE,  # must NOT be what the trade actually fills at
                "signal_quality_score": 90.0,
                "composite_score": 80.0,
            }
        ]
    return []


def _sell_signals(signal_date: date) -> set[str]:
    return set()  # never exits in this window - only entry timing is under test


def _prices_batch(symbols: list[str], target_date: date) -> dict[str, float]:
    price = SIGNAL_DAY_PRICE if target_date == DAY1_SIGNAL else NEXT_DAY_PRICE
    return dict.fromkeys(symbols, price)


class TestRunBacktestEntryLag:
    def test_entry_fills_one_day_after_signal_not_on_signal_day(self) -> None:
        with (
            patch("algo.backtest.run_backtest._get_trading_dates", return_value=TRADING_DATES),
            patch("algo.backtest.run_backtest._get_daily_buy_signals", side_effect=_buy_signals),
            patch("algo.backtest.run_backtest._get_daily_sell_signals", side_effect=_sell_signals),
            patch("algo.backtest.run_backtest._get_prices_batch", side_effect=_prices_batch),
        ):
            results = run_backtest(
                start_date=DAY1_SIGNAL,
                end_date=DAY3_NO_EVENT,
                initial_capital=100_000.0,
                slippage_bps=0.0,
                max_hold_days=60,
            )

        # No sell signal, target, or stop fires in this window, and max_hold_days is large -
        # the position is still open at the end and gets force-closed at the final date's price.
        assert results["total_trades"] == 1
        trade = results["trades"][0]

        # The trade must be costed at NEXT_DAY_PRICE (the day AFTER the signal), never at
        # SIGNAL_DAY_PRICE (the signal day's own close) - that's the exact bug this fixes.
        assert trade["entry_price"] == NEXT_DAY_PRICE
        assert trade["entry_price"] != SIGNAL_DAY_PRICE
        assert trade["trade_date"] == DAY2_ENTRY_FILL

    def test_no_entry_on_the_very_first_simulated_day(self) -> None:
        """The very first simulated day has no preceding trading day inside the window to
        source a lagged signal from - must not fabricate a zero-lag entry just because it's
        day 1, even though a real signal fires that same day."""
        single_day_window = [DAY1_SIGNAL]
        with (
            patch("algo.backtest.run_backtest._get_trading_dates", return_value=single_day_window),
            patch("algo.backtest.run_backtest._get_daily_buy_signals", side_effect=_buy_signals),
            patch("algo.backtest.run_backtest._get_daily_sell_signals", side_effect=_sell_signals),
            patch("algo.backtest.run_backtest._get_prices_batch", side_effect=_prices_batch),
        ):
            results = run_backtest(
                start_date=DAY1_SIGNAL,
                end_date=DAY2_ENTRY_FILL,  # only for the end_date > start_date validation -
                initial_capital=100_000.0,  # _get_trading_dates is mocked to a single day above
                slippage_bps=0.0,
            )

        # DAY1_SIGNAL's own buy signal exists (per _buy_signals) but there is no prev_sim_date
        # on the only simulated day - the lagged entry can never fire within this window.
        assert results["total_trades"] == 0
