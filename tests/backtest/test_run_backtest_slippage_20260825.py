#!/usr/bin/env python3
"""Regression test: run_backtest() previously modeled every fill (entry and exit) as perfectly
costless - no bid/ask spread, market-impact cost, or execution-latency slippage anywhere (see
DEFAULT_SLIPPAGE_BPS's module-level comment and run_backtest()'s docstring). Fixed 2026-08-25 by
applying a conservative, explicit, configurable `slippage_bps` haircut to every entry (buy pays
more) and every exit (sell receives less).

This pins the direction and magnitude of that haircut for a plain buy -> sell_signal round trip,
and confirms slippage_bps=0 exactly reproduces the old (pre-fix) costless-fill behavior.
"""

from datetime import date
from typing import Any
from unittest.mock import patch

from algo.backtest.run_backtest import DEFAULT_SLIPPAGE_BPS, run_backtest

DAY1 = date(2026, 1, 5)
DAY2 = date(2026, 1, 6)
TRADING_DATES = [DAY1, DAY2]

RAW_ENTRY_PRICE = 100.0
RAW_EXIT_PRICE = 110.0


def _buy_signals(signal_date: date, min_composite: float) -> list[dict[str, Any]]:
    if signal_date == DAY1:
        return [
            {
                "symbol": "TEST",
                "entry_price": RAW_ENTRY_PRICE,
                "signal_quality_score": 80.0,
                "composite_score": 70.0,
            }
        ]
    return []


def _sell_signals(signal_date: date) -> set[str]:
    return {"TEST"} if signal_date == DAY2 else set()


def _prices_batch(symbols: list[str], target_date: date) -> dict[str, float]:
    price = RAW_ENTRY_PRICE if target_date == DAY1 else RAW_EXIT_PRICE
    return dict.fromkeys(symbols, price)


class TestRunBacktestSlippage:
    def test_default_slippage_haircuts_entry_and_exit(self) -> None:
        """Default DEFAULT_SLIPPAGE_BPS (5 bps/side): buy fills above the raw signal price,
        sell fills below the raw market price - both directions worse for the trader, never
        better, matching real bid/ask-crossing execution costs."""
        with (
            patch("algo.backtest.run_backtest._get_trading_dates", return_value=TRADING_DATES),
            patch("algo.backtest.run_backtest._get_daily_buy_signals", side_effect=_buy_signals),
            patch("algo.backtest.run_backtest._get_daily_sell_signals", side_effect=_sell_signals),
            patch("algo.backtest.run_backtest._get_prices_batch", side_effect=_prices_batch),
        ):
            results = run_backtest(
                start_date=DAY1,
                end_date=DAY2,
                initial_capital=100_000.0,
            )

        assert results["total_trades"] == 1
        trade = results["trades"][0]

        expected_entry = RAW_ENTRY_PRICE * (1 + DEFAULT_SLIPPAGE_BPS / 10_000)
        expected_exit = RAW_EXIT_PRICE * (1 - DEFAULT_SLIPPAGE_BPS / 10_000)

        assert trade["entry_price"] == round(expected_entry, 4)
        assert trade["exit_price"] == round(expected_exit, 4)
        # Slippage must never help the trader: entry fill is worse (higher) than the raw
        # signal price, exit fill is worse (lower) than the raw market price.
        assert trade["entry_price"] > RAW_ENTRY_PRICE
        assert trade["exit_price"] < RAW_EXIT_PRICE

    def test_zero_slippage_reproduces_costless_fills(self) -> None:
        """slippage_bps=0 must exactly reproduce the old zero-cost-fill behavior - proves the
        haircut is purely additive, not a change to the underlying fill-price logic."""
        with (
            patch("algo.backtest.run_backtest._get_trading_dates", return_value=TRADING_DATES),
            patch("algo.backtest.run_backtest._get_daily_buy_signals", side_effect=_buy_signals),
            patch("algo.backtest.run_backtest._get_daily_sell_signals", side_effect=_sell_signals),
            patch("algo.backtest.run_backtest._get_prices_batch", side_effect=_prices_batch),
        ):
            results = run_backtest(
                start_date=DAY1,
                end_date=DAY2,
                initial_capital=100_000.0,
                slippage_bps=0.0,
            )

        trade = results["trades"][0]
        assert trade["entry_price"] == RAW_ENTRY_PRICE
        assert trade["exit_price"] == RAW_EXIT_PRICE
