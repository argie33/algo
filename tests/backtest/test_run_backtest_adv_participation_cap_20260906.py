"""Regression test for run_backtest()'s opt-in ADV participation-rate cap
(max_pct_of_adv_dollars), added 2026-09-06 (real-money-readiness TCA/backtest-parity audit).

FINDING: live position_sizer.py enforces max_pct_of_adv_dollars (a candidate position can't
exceed N% of the symbol's own 20-day average dollar volume) but the backtest never modeled
it at all - a backtest could simulate a position size live trading would never actually be
allowed to take on a thin name, overstating achievable backtested returns for that subset of
trades.

This pins: (1) default behavior (max_pct_of_adv_dollars=None) is completely unchanged; (2)
setting it shrinks a position that would otherwise exceed the ADV-derived ceiling; (3) a
symbol with no resolvable ADV reading is not capped (fails open, same as the live check).
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
        return [{"symbol": "THINCO", "entry_price": ENTRY_PRICE, "signal_quality_score": 90.0, "composite_score": 80.0}]
    return []


def _sell_signals(signal_date: date) -> set[str]:
    return set()


def _prices_batch(symbols: list[str], target_date: date) -> dict[str, float]:
    return dict.fromkeys(symbols, ENTRY_PRICE)


def _prices_batch_with_range(symbols: list[str], target_date: date) -> dict[str, tuple[float, float, float]]:
    return {symbol: (price, price, price) for symbol, price in _prices_batch(symbols, target_date).items()}


def _run(max_pct_of_adv_dollars, avg_dollar_vol, position_size_pct=10.0, initial_capital=100_000.0):
    def _adv_batch(symbols: list[str], as_of_date: date) -> dict[str, float]:
        return {} if avg_dollar_vol is None else dict.fromkeys(symbols, avg_dollar_vol)

    with (
        patch("algo.backtest.run_backtest._get_trading_dates", return_value=TRADING_DATES),
        patch("algo.backtest.run_backtest._get_daily_buy_signals", side_effect=_buy_signals),
        patch("algo.backtest.run_backtest._get_daily_sell_signals", side_effect=_sell_signals),
        patch("algo.backtest.run_backtest._get_prices_batch", side_effect=_prices_batch),
        patch("algo.backtest.run_backtest._get_prices_batch_with_range", side_effect=_prices_batch_with_range),
        patch("algo.backtest.run_backtest._get_avg_dollar_volume_batch", side_effect=_adv_batch),
    ):
        return run_backtest(
            start_date=DAY1_SIGNAL,
            end_date=DAY3_NO_EVENT,
            initial_capital=initial_capital,
            slippage_bps=0.0,
            max_hold_days=60,
            position_size_pct=position_size_pct,
            max_pct_of_adv_dollars=max_pct_of_adv_dollars,
        )


class TestRunBacktestAdvParticipationCap:
    def test_default_none_is_unchanged_flat_fraction_sizing(self) -> None:
        # ADV never fetched/applied when the cap is disabled (default).
        results = _run(max_pct_of_adv_dollars=None, avg_dollar_vol=1_000_000.0, position_size_pct=10.0)
        trade = results["trades"][0]
        assert trade["entry_quantity"] == 100  # 10% of $100k / $100 entry, uncapped

    def test_adv_cap_shrinks_position_when_thin(self) -> None:
        # Flat-fraction cap wants 100 shares ($10k). ADV cap: 5% of $10,000 avg dollar volume
        # = $500 -> floor(500/100) = 5 shares, well below the flat-fraction cap.
        results = _run(max_pct_of_adv_dollars=5.0, avg_dollar_vol=10_000.0, position_size_pct=10.0)
        trade = results["trades"][0]
        assert trade["entry_quantity"] == 5
        assert trade["entry_quantity"] < 100

    def test_adv_cap_does_not_bind_when_liquidity_is_ample(self) -> None:
        # 5% of a $50M avg dollar volume ($2.5M) is nowhere near the flat-fraction cap
        # ($10k) - the flat-fraction cap should still be the binding constraint.
        results = _run(max_pct_of_adv_dollars=5.0, avg_dollar_vol=50_000_000.0, position_size_pct=10.0)
        trade = results["trades"][0]
        assert trade["entry_quantity"] == 100

    def test_missing_adv_reading_fails_open_not_rejected(self) -> None:
        # No resolvable 20-day window (new listing/data gap) - must not be capped or
        # rejected, same fail-open convention as the live check.
        results = _run(max_pct_of_adv_dollars=5.0, avg_dollar_vol=None, position_size_pct=10.0)
        trade = results["trades"][0]
        assert trade["entry_quantity"] == 100
