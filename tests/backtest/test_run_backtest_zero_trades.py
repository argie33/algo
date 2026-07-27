#!/usr/bin/env python3
"""Regression test: run_backtest()/main()'s summary logging crashed with an uncaught
TypeError on a backtest window that produces zero completed trades.

win_rate_pct, profit_factor, best_trade_pct, worst_trade_pct, avg_trade_return_pct, and
avg_holding_days are all legitimately None when total_trades == 0 (see run_backtest()'s own
`if total_trades > 0 else None` branches), and max_drawdown_pct is None when the equity curve
starts at a non-positive value. Formatting any of these with a numeric format spec
(f"{value:.1f}") raises TypeError on None - this used to crash run_backtest() itself (inside
its own completion log line) before it could even return results, so a strict/narrow backtest
window that legitimately finds no qualifying trades crashed instead of reporting "0 trades".
"""

from datetime import date
from unittest.mock import patch

from algo.backtest.run_backtest import run_backtest


class TestRunBacktestZeroTrades:
    def test_zero_trades_does_not_raise(self):
        """No buy signals ever fire -> total_trades=0 -> win_rate_pct/profit_factor/etc are
        all None. run_backtest() must complete and return results, not raise TypeError."""
        trading_dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]

        with (
            patch("algo.backtest.run_backtest._get_trading_dates", return_value=trading_dates),
            patch("algo.backtest.run_backtest._get_daily_buy_signals", return_value=[]),
            patch("algo.backtest.run_backtest._get_daily_sell_signals", return_value=set()),
            patch("algo.backtest.run_backtest._get_prices_batch", return_value={}),
        ):
            results = run_backtest(
                start_date=trading_dates[0],
                end_date=trading_dates[-1],
                initial_capital=100_000.0,
            )

        assert results["total_trades"] == 0
        assert results["win_rate_pct"] is None
        assert results["profit_factor"] is None
        assert results["best_trade_pct"] is None
        assert results["worst_trade_pct"] is None
        assert results["avg_trade_return_pct"] is None
        assert results["avg_holding_days"] is None
