#!/usr/bin/env python3
"""Regression test: run_backtest()'s Sharpe ratio used to be computed inline as
`avg_ret / std_ret * sqrt(252)` - the exact same raw-return-not-excess-return bug just fixed
in MetricsCalculator.calculate_sharpe_ratio() for live Sharpe (see the 2026-08-25 "Sharpe
ratio was raw-return" fix commit). run_backtest.py had independently drifted the same formula
and never subtracted a risk-free rate, and never computed Sortino/Calmar at all despite this
script's own reference_metrics.json baseline claiming values for both.

This test guards two things: (1) run_backtest()'s Sharpe/Sortino/Calmar are routed through
MetricsCalculator - the single canonical formula source - not a second inline reimplementation
that can drift; (2) a nonzero risk-free rate measurably lowers the reported Sharpe vs. the old
rf=0 behavior, on a real (mocked-DB) equity curve.
"""

from datetime import date, timedelta
from typing import Any
from unittest.mock import patch

from algo.backtest.run_backtest import _fetch_risk_free_rate_annual, run_backtest
from utils.metrics_calculator import MetricsCalculator


def _make_flat_signal_dates(n: int, start: date) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


class TestFetchRiskFreeRateAnnual:
    def test_returns_real_rate_as_decimal(self) -> None:
        with patch("algo.backtest.run_backtest.DatabaseContext") as mock_ctx:
            mock_cur = mock_ctx.return_value.__enter__.return_value
            mock_cur.fetchone.return_value = (4.5,)
            rate = _fetch_risk_free_rate_annual()
        assert rate == 0.045

    def test_falls_back_to_zero_when_unavailable(self) -> None:
        with patch("algo.backtest.run_backtest.DatabaseContext") as mock_ctx:
            mock_cur = mock_ctx.return_value.__enter__.return_value
            mock_cur.fetchone.return_value = None
            rate = _fetch_risk_free_rate_annual()
        assert rate == 0.0


class TestRunBacktestSharpeSortinoCalmarUseCanonicalFormulas:
    def _run_with_synthetic_equity_curve(self, risk_free_rate_annual: float) -> dict[str, Any]:
        """35 trading days, one symbol bought on day 0 and held throughout (never sold), with
        a real up-and-down daily price path so the equity curve has genuine variance
        (required for Sharpe/Sortino/Calmar to compute instead of raising/returning None)."""
        n = 35
        trading_dates = _make_flat_signal_dates(n, date(2026, 1, 5))
        prices = [100.0]
        for i in range(1, n):
            # deterministic oscillation with a slight downtrend, guarantees both positive and
            # negative daily returns (needed for Sortino's downside deviation) and nonzero std.
            prices.append(prices[-1] * (1 + (0.01 if i % 2 == 0 else -0.012)))

        buy_signal = [
            {
                "symbol": "TEST",
                "entry_price": prices[0],
                "signal_strength": 1.0,
                "signal_quality_score": 90.0,
                "entry_quality_score": 90.0,
                "composite_score": 80.0,
            }
        ]

        def fake_buy_signals(signal_date: date, min_composite: float) -> list[dict[str, Any]]:
            return buy_signal if signal_date == trading_dates[0] else []

        def fake_prices_batch(symbols: list[str], target_date: date) -> dict[str, float]:
            idx = trading_dates.index(target_date)
            return {"TEST": prices[idx]}

        with (
            patch("algo.backtest.run_backtest._get_trading_dates", return_value=trading_dates),
            patch("algo.backtest.run_backtest._get_daily_buy_signals", side_effect=fake_buy_signals),
            patch("algo.backtest.run_backtest._get_daily_sell_signals", return_value=set()),
            patch("algo.backtest.run_backtest._get_prices_batch", side_effect=fake_prices_batch),
            patch(
                "algo.backtest.run_backtest._fetch_risk_free_rate_annual",
                return_value=risk_free_rate_annual,
            ),
        ):
            return run_backtest(
                start_date=trading_dates[0],
                end_date=trading_dates[-1],
                initial_capital=100_000.0,
                max_positions=10,
                stop_loss_pct=99.0,  # never trigger, keep the position open the whole window
                profit_target_pct=9999.0,
                max_hold_days=9999,
            )

    def test_nonzero_risk_free_rate_lowers_sharpe_vs_zero(self) -> None:
        results_rf0 = self._run_with_synthetic_equity_curve(0.0)
        results_rf_real = self._run_with_synthetic_equity_curve(0.045)

        assert results_rf0["sharpe_ratio"] is not None
        assert results_rf_real["sharpe_ratio"] is not None
        assert results_rf_real["sharpe_ratio"] < results_rf0["sharpe_ratio"]

    def test_sortino_and_calmar_are_populated_and_match_metrics_calculator(self) -> None:
        results = self._run_with_synthetic_equity_curve(0.0)

        assert results["sortino_ratio"] is not None
        assert results["calmar_ratio"] is not None

        # Independently recompute from the equity curve to confirm run_backtest() didn't drift
        # from MetricsCalculator's own formulas (the exact bug class this fix closes).
        values = [p["value"] for p in results["equity_curve"]]
        daily_returns = [(values[i] - values[i - 1]) / values[i - 1] for i in range(1, len(values))]
        expected_sortino = MetricsCalculator.calculate_sortino_ratio(daily_returns, min_observations=2)
        expected_calmar = MetricsCalculator.calculate_calmar_ratio(values, min_observations=2)

        assert results["sortino_ratio"] == expected_sortino
        assert results["calmar_ratio"] == expected_calmar
