#!/usr/bin/env python3
"""Regression: run_backtest.py previously had NO way to simulate live's actual exit chain
(hard stop -> breakeven floor -> chandelier/21-EMA trail -> time exit) - only a single fixed
stop-loss/profit-target all-or-nothing exit. See run_backtest.py's module docstring "EXIT MODE"
section for the full real-money-readiness finding this `--exit-mode live_trail` addition
closes: live currently has `use_scale_out_targets=false` (migration 1273), so this pure-trail
chain - not a T1/T2/T3 scale-out - is what live actually runs today.

These tests pin the core behaviors of `exit_mode="live_trail"` using a synthetic, fully
controlled OHLC/ATR price path (via `_load_symbol_ohlc_with_atr`, mocked - not a real DB) so the
expected stop/exit level at each step can be hand-computed and asserted exactly, independent of
`algo/backtest/live_exit_trail.py`'s own formula correctness (covered separately by that
module's own alignment with exit_position_context.py).
"""

from datetime import date
from typing import Any
from unittest.mock import patch

import pandas as pd

from algo.backtest.run_backtest import run_backtest

SIGNAL_DAY = date(2026, 3, 2)
ENTRY_DAY = date(2026, 3, 3)  # ohlc row 0 - entry_idx
DAY_B = date(2026, 3, 4)  # ohlc row 1
DAY_C = date(2026, 3, 5)  # ohlc row 2
DAY_D = date(2026, 3, 6)  # ohlc row 3
DAY_E = date(2026, 3, 9)  # ohlc row 4

ENTRY_PRICE = 100.0
STOP_LOSS_PCT = 8.0  # init_stop = 92.0, risk = 8.0/share


def _buy_signals(
    signal_date: date, min_composite: float, rank_by: str = "signal_quality_score"
) -> list[dict[str, Any]]:
    if signal_date == SIGNAL_DAY:
        return [
            {"symbol": "LIVETRAIL", "entry_price": ENTRY_PRICE, "signal_quality_score": 90.0, "composite_score": 80.0}
        ]
    return []


def _sell_signals(signal_date: date) -> set[str]:
    return set()


def _make_prices_batch(fill_price: float):
    def _prices_batch(symbols: list[str], target_date: date) -> dict[str, float]:
        return dict.fromkeys(symbols, fill_price)

    return _prices_batch


def _make_prices_batch_with_range(fill_price: float):
    def _prices_batch_with_range(symbols: list[str], target_date: date) -> dict[str, tuple[float, float, float]]:
        return dict.fromkeys(symbols, (fill_price, fill_price, fill_price))

    return _prices_batch_with_range


def _ohlc_df(rows: list[tuple[date, float, float, float, float]]) -> pd.DataFrame:
    """rows: (date, high, low, close, atr_14)."""
    return pd.DataFrame(rows, columns=["date", "high", "low", "close", "atr_14"])


class TestLiveTrailExitMode:
    def test_breakeven_then_stop_exits_at_breakeven_not_initial_stop(self) -> None:
        """Price runs up past move_be_at_r (1.0R), raising the stop to breakeven - a large ATR
        keeps the chandelier trail well below breakeven so it never overrides it - then drops
        through breakeven. Must exit at the $100 breakeven level, not the original $92 stop."""
        trading_dates = [SIGNAL_DAY, ENTRY_DAY, DAY_B, DAY_C, DAY_D]
        ohlc = _ohlc_df(
            [
                (ENTRY_DAY, 101.0, 99.0, 100.0, 5.0),
                (DAY_B, 112.0, 108.0, 110.0, 5.0),  # r_close=1.25R >= 1.0 -> breakeven + chandelier gate
                (DAY_C, 115.0, 110.0, 112.0, 5.0),  # chandelier candidate=115-15=100, not > 100 (breakeven holds)
                (DAY_D, 95.0, 80.0, 85.0, 5.0),  # low=80 <= active_stop(100) -> STOP at breakeven, not 92
            ]
        )
        with (
            patch("algo.backtest.run_backtest._get_trading_dates", return_value=trading_dates),
            patch("algo.backtest.run_backtest._get_daily_buy_signals", side_effect=_buy_signals),
            patch("algo.backtest.run_backtest._get_daily_sell_signals", side_effect=_sell_signals),
            patch("algo.backtest.run_backtest._get_prices_batch", side_effect=_make_prices_batch(ENTRY_PRICE)),
            patch(
                "algo.backtest.run_backtest._get_prices_batch_with_range",
                side_effect=_make_prices_batch_with_range(ENTRY_PRICE),
            ),
            patch("algo.backtest.run_backtest._load_symbol_ohlc_with_atr", return_value=ohlc),
        ):
            results = run_backtest(
                start_date=SIGNAL_DAY,
                end_date=DAY_D,
                initial_capital=100_000.0,
                slippage_bps=0.0,
                stop_loss_pct=STOP_LOSS_PCT,
                max_hold_days=60,
                exit_mode="live_trail",
            )

        assert results["total_trades"] == 1
        trade = results["trades"][0]
        assert trade["exit_reason"] == "stop"
        assert trade["exit_price"] == 100.0, "must exit at the breakeven-raised stop, not the original $92 stop"
        assert trade["exit_date"] == DAY_D

    def test_hard_stop_before_any_tier_exits_at_initial_stop(self) -> None:
        """Price drops straight through the initial stop before ever reaching move_be_at_r -
        must exit at the original $92 stop, not some other level."""
        trading_dates = [SIGNAL_DAY, ENTRY_DAY, DAY_B]
        ohlc = _ohlc_df(
            [
                (ENTRY_DAY, 101.0, 99.0, 100.0, 5.0),
                (DAY_B, 95.0, 85.0, 90.0, 5.0),  # r_close=-1.25R, no breakeven; low=85 <= init_stop(92) -> STOP
            ]
        )
        with (
            patch("algo.backtest.run_backtest._get_trading_dates", return_value=trading_dates),
            patch("algo.backtest.run_backtest._get_daily_buy_signals", side_effect=_buy_signals),
            patch("algo.backtest.run_backtest._get_daily_sell_signals", side_effect=_sell_signals),
            patch("algo.backtest.run_backtest._get_prices_batch", side_effect=_make_prices_batch(ENTRY_PRICE)),
            patch(
                "algo.backtest.run_backtest._get_prices_batch_with_range",
                side_effect=_make_prices_batch_with_range(ENTRY_PRICE),
            ),
            patch("algo.backtest.run_backtest._load_symbol_ohlc_with_atr", return_value=ohlc),
        ):
            results = run_backtest(
                start_date=SIGNAL_DAY,
                end_date=DAY_B,
                initial_capital=100_000.0,
                slippage_bps=0.0,
                stop_loss_pct=STOP_LOSS_PCT,
                max_hold_days=60,
                exit_mode="live_trail",
            )

        assert results["total_trades"] == 1
        trade = results["trades"][0]
        assert trade["exit_reason"] == "stop"
        assert trade["exit_price"] == 92.0
        assert trade["exit_date"] == DAY_B

    def test_time_exit_fires_at_max_hold_days_when_price_never_triggers_stop_or_trail(self) -> None:
        """Price sits flat above the stop and below 1R the whole time - no stop, no breakeven,
        no chandelier gate ever engages - must still exit via the time-based rule once
        max_hold_days is reached, priced at that day's close."""
        trading_dates = [SIGNAL_DAY, ENTRY_DAY, DAY_B, DAY_C]
        ohlc = _ohlc_df(
            [
                (ENTRY_DAY, 101.0, 99.0, 100.0, 5.0),
                (DAY_B, 103.0, 99.0, 102.0, 5.0),  # r_close=0.25R, under 1.0R gate
                (DAY_C, 104.0, 100.0, 103.0, 5.0),  # days_held=2 >= max_hold_days=2 -> TIME exit
            ]
        )
        with (
            patch("algo.backtest.run_backtest._get_trading_dates", return_value=trading_dates),
            patch("algo.backtest.run_backtest._get_daily_buy_signals", side_effect=_buy_signals),
            patch("algo.backtest.run_backtest._get_daily_sell_signals", side_effect=_sell_signals),
            patch("algo.backtest.run_backtest._get_prices_batch", side_effect=_make_prices_batch(ENTRY_PRICE)),
            patch(
                "algo.backtest.run_backtest._get_prices_batch_with_range",
                side_effect=_make_prices_batch_with_range(ENTRY_PRICE),
            ),
            patch("algo.backtest.run_backtest._load_symbol_ohlc_with_atr", return_value=ohlc),
        ):
            results = run_backtest(
                start_date=SIGNAL_DAY,
                end_date=DAY_C,
                initial_capital=100_000.0,
                slippage_bps=0.0,
                stop_loss_pct=STOP_LOSS_PCT,
                max_hold_days=2,
                exit_mode="live_trail",
            )

        assert results["total_trades"] == 1
        trade = results["trades"][0]
        assert trade["exit_reason"] == "time"
        assert trade["exit_price"] == 103.0
        assert trade["exit_date"] == DAY_C

    def test_insufficient_price_history_rejects_entry_instead_of_crashing(self) -> None:
        """A symbol with no resolvable OHLC/ATR history (None from _load_symbol_ohlc_with_atr,
        e.g. < 300 rows) must be skipped as a rejected entry, not raise or silently enter with
        no exit plan."""
        trading_dates = [SIGNAL_DAY, ENTRY_DAY, DAY_B]
        with (
            patch("algo.backtest.run_backtest._get_trading_dates", return_value=trading_dates),
            patch("algo.backtest.run_backtest._get_daily_buy_signals", side_effect=_buy_signals),
            patch("algo.backtest.run_backtest._get_daily_sell_signals", side_effect=_sell_signals),
            patch("algo.backtest.run_backtest._get_prices_batch", side_effect=_make_prices_batch(ENTRY_PRICE)),
            patch(
                "algo.backtest.run_backtest._get_prices_batch_with_range",
                side_effect=_make_prices_batch_with_range(ENTRY_PRICE),
            ),
            patch("algo.backtest.run_backtest._load_symbol_ohlc_with_atr", return_value=None),
        ):
            results = run_backtest(
                start_date=SIGNAL_DAY,
                end_date=DAY_B,
                initial_capital=100_000.0,
                slippage_bps=0.0,
                stop_loss_pct=STOP_LOSS_PCT,
                max_hold_days=60,
                exit_mode="live_trail",
            )

        assert results["total_trades"] == 0

    def test_invalid_exit_mode_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="exit_mode"):
            run_backtest(
                start_date=SIGNAL_DAY,
                end_date=DAY_B,
                initial_capital=100_000.0,
                exit_mode="not_a_real_mode",
            )
