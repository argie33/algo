"""Regression test for run_backtest()'s opt-in risk-based position sizing (base_risk_pct),
added 2026-09-05 (real-money-readiness order-execution/financial-calc audit).

FINDING: the default sizing model (position_size_pct, a flat %-of-portfolio fraction) does not
match live position_sizer.py's risk-based formula (risk_dollars = portfolio_value *
base_risk_pct, shares = risk_dollars / (entry - stop)) - the two can diverge several-fold on
any trade whose stop distance differs from the fraction's "implied" distance. base_risk_pct
switches to the same formula, using entry_price*(stop_loss_pct/100) as risk_per_share (the same
stop distance this backtest's own stop-loss exit uses) - position_size_pct still applies as the
maximum cap either way.

This pins: (1) default behavior (base_risk_pct=None) is completely unchanged - same share
count as before this fix existed; (2) risk-based mode produces a smaller position when the
risk-based formula implies fewer shares than the flat-fraction cap; (3) risk-based mode is
still capped by position_size_pct, never exceeding it.
"""

from datetime import date
from typing import Any
from unittest.mock import patch

from algo.backtest.run_backtest import run_backtest

DAY1_SIGNAL = date(2026, 2, 2)
DAY2_ENTRY_FILL = date(2026, 2, 3)
DAY3_NO_EVENT = date(2026, 2, 4)
TRADING_DATES = [DAY1_SIGNAL, DAY2_ENTRY_FILL, DAY3_NO_EVENT]

ENTRY_PRICE = 100.0


def _buy_signals(
    signal_date: date, min_composite: float, rank_by: str = "signal_quality_score"
) -> list[dict[str, Any]]:
    if signal_date == DAY1_SIGNAL:
        return [
            {"symbol": "SIZETEST", "entry_price": ENTRY_PRICE, "signal_quality_score": 90.0, "composite_score": 80.0}
        ]
    return []


def _sell_signals(signal_date: date) -> set[str]:
    return set()


def _prices_batch(symbols: list[str], target_date: date) -> dict[str, float]:
    return dict.fromkeys(symbols, ENTRY_PRICE)


def _prices_batch_with_range(symbols: list[str], target_date: date) -> dict[str, tuple[float, float, float]]:
    return {symbol: (price, price, price) for symbol, price in _prices_batch(symbols, target_date).items()}


def _run(base_risk_pct, position_size_pct=10.0, stop_loss_pct=8.0, initial_capital=100_000.0):
    with (
        patch("algo.backtest.run_backtest._get_trading_dates", return_value=TRADING_DATES),
        patch("algo.backtest.run_backtest._get_daily_buy_signals", side_effect=_buy_signals),
        patch("algo.backtest.run_backtest._get_daily_sell_signals", side_effect=_sell_signals),
        patch("algo.backtest.run_backtest._get_prices_batch", side_effect=_prices_batch),
        patch("algo.backtest.run_backtest._get_prices_batch_with_range", side_effect=_prices_batch_with_range),
    ):
        return run_backtest(
            start_date=DAY1_SIGNAL,
            end_date=DAY3_NO_EVENT,
            initial_capital=initial_capital,
            slippage_bps=0.0,
            max_hold_days=60,
            position_size_pct=position_size_pct,
            stop_loss_pct=stop_loss_pct,
            base_risk_pct=base_risk_pct,
        )


class TestRunBacktestRiskBasedSizing:
    def test_default_none_is_unchanged_flat_fraction_sizing(self) -> None:
        results = _run(base_risk_pct=None, position_size_pct=10.0, initial_capital=100_000.0)
        trade = results["trades"][0]
        # Flat fraction: 10% of $100k = $10k / $100 entry = 100 shares.
        assert trade["entry_quantity"] == 100

    def test_risk_based_sizing_shrinks_position_below_flat_fraction_cap(self) -> None:
        # risk_dollars = $100k * 0.75% = $750; risk_per_share = $100 * 8% = $8;
        # risk-based shares = 750/8 = 93 (floor) - below the 100-share flat-fraction cap.
        results = _run(base_risk_pct=0.75, position_size_pct=10.0, stop_loss_pct=8.0, initial_capital=100_000.0)
        trade = results["trades"][0]
        assert trade["entry_quantity"] == 93
        assert trade["entry_quantity"] < 100  # strictly smaller than the flat-fraction default

    def test_risk_based_sizing_never_exceeds_the_position_size_cap(self) -> None:
        # A generous base_risk_pct (10%) with a tight stop (1%) implies far more shares than
        # the flat position_size_pct cap allows - the cap must still bind.
        results = _run(base_risk_pct=10.0, position_size_pct=5.0, stop_loss_pct=1.0, initial_capital=100_000.0)
        trade = results["trades"][0]
        # Cap: 5% of $100k = $5k / $100 entry = 50 shares - risk-based alone would want far more.
        assert trade["entry_quantity"] == 50
