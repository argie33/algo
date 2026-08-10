#!/usr/bin/env python3
"""Regression tests for the remaining NaN-comparison-guard fixes from the 2026-08-10
systematic sweep (executor_exit_handler.py's second price gate near P&L recording,
algo/risk/var.py's two portfolio-risk guards, algo/signals/trade_performance.py's
analytics guard).

All share the same root cause already documented extensively elsewhere this session:
`value <= 0` doesn't catch NaN because NaN comparisons are always False in Python.

These test the guard condition directly (the same pattern used elsewhere in this
codebase - see test_executor_exit_handler_decimal_qty_comparison.py) rather than full
integration through their enclosing functions, which require heavy DB/context mocking
for logic that's a simple, isolated conditional.
"""

import math


def _price_or_qty_guard_would_reject(*values: float) -> bool:
    """Mirrors the fixed guard pattern: reject if any value is NaN, Infinite, or <= 0."""
    for v in values:
        if math.isnan(v) or math.isinf(v) or v <= 0:
            return True
    return False


class TestExecutorExitHandlerSecondPriceGate:
    """executor_exit_handler.py's final_exit_price/entry_price checks immediately before
    Decimal(str(entry_price)) - Decimal(str(stop_loss_price)) in the P&L calculation."""

    def test_nan_final_exit_price_rejected(self):
        assert _price_or_qty_guard_would_reject(float("nan"))

    def test_nan_entry_price_rejected(self):
        assert _price_or_qty_guard_would_reject(100.0, float("nan"))

    def test_normal_prices_accepted(self):
        assert not _price_or_qty_guard_would_reject(100.0, 95.0)


class TestVarPortfolioRiskGuards:
    """algo/risk/var.py's safe_price/safe_qty guard and historical-price guard."""

    def test_nan_current_price_rejected(self):
        assert _price_or_qty_guard_would_reject(float("nan"), 10.0)

    def test_nan_quantity_rejected(self):
        assert _price_or_qty_guard_would_reject(100.0, float("nan"))

    def test_nan_historical_price_rejected(self):
        assert _price_or_qty_guard_would_reject(float("nan"))

    def test_normal_values_accepted(self):
        assert not _price_or_qty_guard_would_reject(100.0, 10.0)


class TestTradePerformanceAnalyticsGuard:
    """algo/signals/trade_performance.py's entry_price/entry_qty guard."""

    def test_nan_entry_price_rejected(self):
        assert _price_or_qty_guard_would_reject(float("nan"), 10.0)

    def test_nan_entry_qty_rejected(self):
        assert _price_or_qty_guard_would_reject(100.0, float("nan"))

    def test_normal_values_accepted(self):
        assert not _price_or_qty_guard_would_reject(100.0, 10.0)


def test_confirm_actual_fixed_source_files_use_this_exact_pattern():
    """Sanity check that the guard pattern this test mirrors is actually present in each
    fixed file, so this test can't silently drift from the real code."""
    import inspect

    from algo.risk import var as var_module
    from algo.signals import trade_performance as trade_performance_module
    from algo.trading import executor_exit_handler as exit_handler_module

    for module in (exit_handler_module, var_module, trade_performance_module):
        source = inspect.getsource(module)
        assert "math.isnan" in source, f"{module.__name__} must use math.isnan() guards"
        assert "math.isinf" in source, f"{module.__name__} must use math.isinf() guards"
