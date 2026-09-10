"""Regression test for a real-money-readiness audit finding: run_backtest()'s results dict
had no genuine avg_win/avg_loss (average P&L of winning trades / average P&L of losing
trades) - save_results() wrote avg_trade_return_pct (the blended average across ALL trades)
into backtest_runs.avg_win, and worst_trade_pct (a single trade, not an average) into
avg_loss. Neither matches what those columns mean anywhere else in this codebase (e.g.
algo/infrastructure/reconciliation_analytics.py's avg_win_pct/avg_loss_pct, or
utils/metrics_calculator.py's calculate_expectancy(), which documents avg_loss as "Always
positive for formula" - the convention this fix follows). No current consumer reads
backtest_runs.avg_win/avg_loss, so this had no live behavioral impact, but it was genuinely
wrong data under standard, unambiguous column names.

Fix: compute real avg_win_pct (mean profit_loss_pct of winning trades) and avg_loss_pct
(mean profit_loss_pct of losing trades, as a positive magnitude) and use those instead.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.backtest.run_backtest import run_backtest, save_results


def _signal(symbol: str, close: float, sma_50: float = 90.0) -> dict:
    return {
        "symbol": symbol,
        "entry_price": close,
        "high": close,
        "low": close,
        "sma_50": sma_50,
        "signal_strength": 1.0,
        "buylevel": close,
        "stoplevel": close * 0.9,
        "signal_quality_score": 50.0,
        "entry_quality_score": 50.0,
        "composite_score": 60.0,
        "rs_percentile": 50.0,
    }


class TestAvgWinAvgLossGenuinelyComputed:
    def test_avg_win_pct_only_averages_winners_not_all_trades(self):
        """Two winners (+20%, +10%) and one loser (-8%): avg_win_pct must be the average of
        just the two winners (15%), not the blended average of all three trades (~7.3%)."""
        trading_dates = [date(2026, 1, d) for d in range(5, 12)]

        buy_signals_by_date = {
            trading_dates[0]: [_signal("AAA", 100.0), _signal("BBB", 100.0), _signal("CCC", 100.0)],
        }

        prices_by_date = {
            trading_dates[1]: {"AAA": 100.0, "BBB": 100.0, "CCC": 100.0},
            trading_dates[2]: {"AAA": 120.0, "BBB": 110.0, "CCC": 92.0},
        }

        def fake_buy_signals(signal_date, min_composite, rank_by="signal_quality_score"):
            return buy_signals_by_date.get(signal_date, [])

        def fake_prices_batch(symbols, target_date):
            # Forward-fill: use the most recent defined price on-or-before target_date,
            # matching real price_daily's "date <= target" semantics for an open position
            # that must be mark-to-marketed every remaining simulated day.
            result = {}
            for s in symbols:
                last_known = None
                for d in trading_dates:
                    if d > target_date:
                        break
                    if s in prices_by_date.get(d, {}):
                        last_known = prices_by_date[d][s]
                if last_known is not None:
                    result[s] = last_known
            return result

        def fake_prices_batch_with_range(symbols, target_date):
            return {s: (p, p, p) for s, p in fake_prices_batch(symbols, target_date).items()}

        with (
            patch("algo.backtest.run_backtest._get_trading_dates", return_value=trading_dates),
            patch("algo.backtest.run_backtest._get_daily_buy_signals", side_effect=fake_buy_signals),
            patch("algo.backtest.run_backtest._get_daily_sell_signals", return_value=set()),
            patch("algo.backtest.run_backtest._get_prices_batch", side_effect=fake_prices_batch),
            patch("algo.backtest.run_backtest._get_prices_batch_with_range", side_effect=fake_prices_batch_with_range),
        ):
            results = run_backtest(
                start_date=trading_dates[0],
                end_date=trading_dates[-1],
                initial_capital=100_000.0,
                max_positions=10,
                profit_target_pct=15.0,
                stop_loss_pct=8.0,
                slippage_bps=0.0,
            )

        assert results["total_trades"] == 3
        assert results["winning_trades"] == 2
        assert results["losing_trades"] == 1
        # AAA hits its 15% profit target (entered day 2, exited day 3 at +15%); BBB stays
        # open (10% < 15% target, not stopped) until forced end-of-backtest close; CCC hits
        # its 8% stop loss. avg_win_pct must average only the winning trades' actual P&L.
        assert results["avg_win_pct"] is not None
        assert results["avg_loss_pct"] is not None
        winner_pcts = [t["profit_loss_pct"] for t in results["trades"] if t["profit_loss_pct"] > 0]
        loser_pcts = [t["profit_loss_pct"] for t in results["trades"] if t["profit_loss_pct"] <= 0]
        expected_avg_win = sum(winner_pcts) / len(winner_pcts)
        expected_avg_loss = abs(sum(loser_pcts) / len(loser_pcts))
        assert abs(results["avg_win_pct"] - expected_avg_win) < 0.01
        assert abs(results["avg_loss_pct"] - expected_avg_loss) < 0.01
        # The bug this test pins: avg_win_pct must NOT equal the blended all-trades average
        # (this scenario has only one loser, so avg_loss_pct coincidentally equals
        # abs(worst_trade_pct) here - the distinct-from-worst-trade case is covered by the
        # winner-average assertions above and by construction, not a separate assert here).
        assert results["avg_win_pct"] != results["avg_trade_return_pct"]

    def test_zero_losers_avg_loss_pct_is_none_not_a_winner_value(self):
        """No losing trades at all -> avg_loss_pct must be None, not accidentally reuse a
        winner's value or the old worst_trade_pct proxy (which would be a winning trade's
        P&L, not a loss)."""
        trading_dates = [date(2026, 1, d) for d in range(5, 9)]
        buy_signals_by_date = {trading_dates[0]: [_signal("AAA", 100.0)]}
        prices_by_date = {
            trading_dates[1]: {"AAA": 100.0},
            trading_dates[2]: {"AAA": 120.0},
        }

        with (
            patch("algo.backtest.run_backtest._get_trading_dates", return_value=trading_dates),
            patch(
                "algo.backtest.run_backtest._get_daily_buy_signals",
                side_effect=lambda d, m, rank_by="signal_quality_score": buy_signals_by_date.get(d, []),
            ),
            patch("algo.backtest.run_backtest._get_daily_sell_signals", return_value=set()),
            patch(
                "algo.backtest.run_backtest._get_prices_batch",
                side_effect=lambda syms, d: {
                    s: prices_by_date.get(d, {})[s] for s in syms if s in prices_by_date.get(d, {})
                },
            ),
            patch(
                "algo.backtest.run_backtest._get_prices_batch_with_range",
                side_effect=lambda syms, d: {
                    s: (prices_by_date.get(d, {})[s],) * 3 for s in syms if s in prices_by_date.get(d, {})
                },
            ),
        ):
            results = run_backtest(
                start_date=trading_dates[0],
                end_date=trading_dates[-1],
                initial_capital=100_000.0,
                profit_target_pct=15.0,
                stop_loss_pct=8.0,
                slippage_bps=0.0,
            )

        assert results["losing_trades"] == 0
        assert results["avg_loss_pct"] is None


class TestSaveResultsWritesAvgWinAvgLossNotProxies:
    def test_save_results_inserts_avg_win_pct_and_avg_loss_pct_values(self):
        """save_results()'s INSERT must bind avg_win_pct/avg_loss_pct into the avg_win/
        avg_loss columns, not avg_trade_return_pct/worst_trade_pct."""
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (42,)
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value = mock_cur
        mock_ctx.__exit__.return_value = False

        results = {
            "strategy_name": "test_strategy",
            "start_date": date(2026, 1, 1),
            "end_date": date(2026, 2, 1),
            "initial_capital": 100_000.0,
            "final_capital": 110_000.0,
            "total_return_pct": 10.0,
            "annualized_return_pct": 12.0,
            "max_drawdown_pct": -5.0,
            "sharpe_ratio": 1.2,
            "win_rate_pct": 66.7,
            "profit_factor": 2.0,
            "total_trades": 3,
            "winning_trades": 2,
            "losing_trades": 1,
            "avg_trade_return_pct": 7.33,
            "avg_win_pct": 15.0,
            "avg_loss_pct": 8.0,
            "best_trade_pct": 20.0,
            "worst_trade_pct": -8.0,
            "trades": [],
        }

        with patch("algo.backtest.run_backtest.DatabaseContext", return_value=mock_ctx):
            save_results(results)

        insert_call = mock_cur.execute.call_args_list[0]
        params = insert_call[0][1]
        # Column order: ..., win_rate, profit_factor, num_trades, num_winning_trades,
        # num_losing_trades, avg_win, avg_loss, largest_win, largest_loss
        avg_win_param, avg_loss_param = params[-4], params[-3]
        assert avg_win_param == 15.0, f"expected avg_win column bound to avg_win_pct (15.0), got {avg_win_param}"
        assert avg_loss_param == 8.0, f"expected avg_loss column bound to avg_loss_pct (8.0), got {avg_loss_param}"
