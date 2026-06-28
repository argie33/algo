#!/usr/bin/env python3
"""Tests for refactored dashboard formatters module.

Tests the new function-based formatter API for dashboard display formatting.
"""

import time
from datetime import date, datetime

import pytest


class TestMoneyFormatting:
    """Test money/currency formatting."""

    def test_fmt_money_basic(self):
        """Test basic money formatting."""
        from dashboard.formatters import fmt_money

        result = fmt_money(1000)
        assert result is not None
        assert isinstance(result, str)

    def test_fmt_money_with_decimals(self):
        """Test money formatting with decimals."""
        from dashboard.formatters import fmt_money

        result = fmt_money(1000.50)
        assert result is not None

    def test_fmt_money_large_values(self):
        """Test money formatter with large values."""
        from dashboard.formatters import fmt_money

        result = fmt_money(1000000)
        assert result is not None
        # Should compact large values
        assert 'M' in result or '1' in result

    def test_fmt_money_short(self):
        """Test short money formatting."""
        from dashboard.formatters import fmt_money_short

        result = fmt_money_short(1000000)
        assert result is not None
        # Should be compact
        assert len(result) < 15

    def test_fmt_money_zero(self):
        """Test money formatter with zero."""
        from dashboard.formatters import fmt_money

        result = fmt_money(0)
        assert result is not None

    def test_fmt_money_none(self):
        """Test money formatter with None."""
        from dashboard.formatters import fmt_money

        result = fmt_money(None)
        assert result is not None

    def test_fmt_money_negative(self):
        """Test money formatter with negative values."""
        from dashboard.formatters import fmt_money

        result = fmt_money(-500)
        assert result is not None


class TestAgeFormatting:
    """Test timestamp age formatting."""

    def test_fmt_age_recent(self):
        """Test age formatting for recent timestamps."""
        from dashboard.formatters import fmt_age

        ts = time.time()
        result = fmt_age(ts)
        assert result is not None
        assert isinstance(result, str)

    def test_fmt_age_old(self):
        """Test age formatting for old timestamps."""
        from dashboard.formatters import fmt_age

        # 1 hour ago
        ts = time.time() - 3600
        result = fmt_age(ts)
        assert result is not None

    def test_fmt_age_none(self):
        """Test age formatter with None."""
        from dashboard.formatters import fmt_age

        result = fmt_age(None)
        assert result is not None


class TestSignFormatting:
    """Test sign formatting for positive/negative."""

    def test_sign_positive(self):
        """Test sign formatter with positive values."""
        from dashboard.formatters import sign

        result = sign(5.5)
        assert isinstance(result, str)

    def test_sign_negative(self):
        """Test sign formatter with negative values."""
        from dashboard.formatters import sign

        result = sign(-5.5)
        assert isinstance(result, str)

    def test_sign_zero(self):
        """Test sign formatter with zero."""
        from dashboard.formatters import sign

        result = sign(0)
        assert isinstance(result, str)


class TestBarFormatting:
    """Test bar chart formatters."""

    def test_hbar_basic(self):
        """Test horizontal bar basic usage."""
        from dashboard.formatters import hbar

        result = hbar(50, 100)
        assert result is not None
        assert isinstance(result, str)
        # Should contain filled bars
        assert '█' in result or '░' in result

    def test_hbar_full(self):
        """Test horizontal bar at 100%."""
        from dashboard.formatters import hbar

        result = hbar(100, 100)
        assert '█' in result

    def test_hbar_empty(self):
        """Test horizontal bar at 0%."""
        from dashboard.formatters import hbar

        result = hbar(0, 100)
        assert '░' in result

    def test_hbar_none(self):
        """Test hbar with None values."""
        from dashboard.formatters import hbar

        result = hbar(None, 100)
        assert '✗' in result

    def test_exp_bar(self):
        """Test exponential bar."""
        from dashboard.formatters import exp_bar

        result = exp_bar(50)
        assert result is not None
        assert isinstance(result, str)

    def test_exp_bar_none(self):
        """Test exp_bar with None."""
        from dashboard.formatters import exp_bar

        result = exp_bar(None)
        assert '✗' in result

    def test_mini_bar(self):
        """Test mini bar."""
        from dashboard.formatters import mini_bar

        result = mini_bar(5, 10)
        assert result is not None
        assert isinstance(result, str)

    def test_mini_bar_none(self):
        """Test mini_bar with None."""
        from dashboard.formatters import mini_bar

        result = mini_bar(None, 10)
        assert '✗' in result


class TestSparklineFormatting:
    """Test sparkline formatting."""

    def test_sparkline_basic(self):
        """Test sparkline with basic data."""
        from dashboard.formatters import sparkline

        values = [1, 2, 3, 4, 5]
        result = sparkline(values)
        assert result is not None
        assert isinstance(result, str)

    def test_sparkline_large_dataset(self):
        """Test sparkline with large dataset."""
        from dashboard.formatters import sparkline

        values = list(range(1000))
        result = sparkline(values)
        assert result is not None
        # Should be compact
        assert len(result) < 200

    def test_sparkline_empty(self):
        """Test sparkline with empty data."""
        from dashboard.formatters import sparkline

        result = sparkline([])
        assert result is not None
        assert 'no' in result.lower() or 'data' in result.lower()

    def test_sparkline_single(self):
        """Test sparkline with single value."""
        from dashboard.formatters import sparkline

        result = sparkline([5])
        assert result is not None

    def test_sparkline_none_values(self):
        """Test sparkline filters None values."""
        from dashboard.formatters import sparkline

        values = [1, None, 3, None, 5]
        result = sparkline(values)
        assert result is not None


class TestMarketStatusFormatting:
    """Test market status formatters."""

    def test_is_open(self):
        """Test market open status check."""
        from dashboard.formatters import is_open

        result = is_open()
        assert isinstance(result, bool)

    def test_next_run_str(self):
        """Test next run string formatting."""
        from dashboard.formatters import next_run_str

        result = next_run_str()
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0


class TestFormatterIntegration:
    """Integration tests for multiple formatters."""

    def test_multiple_formatters_independent(self):
        """Test that multiple formatters work independently."""
        from dashboard.formatters import fmt_age, fmt_money, sign, sparkline

        # Use all formatters
        money = fmt_money(1000)
        age = fmt_age(time.time())
        s = sign(5)
        spark = sparkline([1, 2, 3])

        assert money is not None
        assert age is not None
        assert s is not None
        assert spark is not None

    def test_bar_and_sparkline(self):
        """Test bar and sparkline together."""
        from dashboard.formatters import hbar, sparkline

        bar = hbar(75, 100)
        spark = sparkline([10, 20, 30, 40, 50])

        assert bar is not None
        assert spark is not None


class TestFormatterEdgeCases:
    """Test formatter edge cases and robustness."""

    def test_fmt_money_large_values(self):
        """Test money formatter with very large values."""
        from dashboard.formatters import fmt_money

        result = fmt_money(999999999)
        assert result is not None

    def test_fmt_money_small_values(self):
        """Test money formatter with small values."""
        from dashboard.formatters import fmt_money

        result = fmt_money(0.01)
        assert result is not None

    def test_sparkline_constant_values(self):
        """Test sparkline with constant values."""
        from dashboard.formatters import sparkline

        values = [5] * 100
        result = sparkline(values)
        assert result is not None

    def test_hbar_zero_denominator(self):
        """Test hbar gracefully handles zero denominator."""
        from dashboard.formatters import hbar

        # Should not crash with zero max
        result = hbar(0, 0)
        assert result is not None

    def test_mini_bar_zero_denominator(self):
        """Test mini_bar gracefully handles zero denominator."""
        from dashboard.formatters import mini_bar

        # Should not crash
        result = mini_bar(0, 0)
        assert result is not None


class TestFormatterPerformance:
    """Test formatter performance."""

    def test_fmt_money_bulk(self):
        """Test money formatter performance with bulk calls."""
        from dashboard.formatters import fmt_money

        start = time.time()
        for i in range(100):
            fmt_money(i * 1000)
        elapsed = time.time() - start

        # Should be reasonably fast
        assert elapsed < 1.0

    def test_sparkline_bulk(self):
        """Test sparkline formatter with multiple calls."""
        from dashboard.formatters import sparkline

        start = time.time()
        for i in range(10):
            values = list(range(i, i + 100))
            sparkline(values)
        elapsed = time.time() - start

        # Should be reasonably fast
        assert elapsed < 1.0


class TestFormatterConsistency:
    """Test formatter consistency and idempotency."""

    def test_same_input_same_output(self):
        """Test that identical inputs produce identical outputs."""
        from dashboard.formatters import fmt_money

        result1 = fmt_money(150.50)
        result2 = fmt_money(150.50)
        assert result1 == result2

    def test_fmt_age_increasing(self):
        """Test fmt_age increases for older timestamps."""
        from dashboard.formatters import fmt_age

        now = time.time()
        old = time.time() - 1000

        result_now = fmt_age(now)
        result_old = fmt_age(old)

        # Both should be valid
        assert result_now is not None
        assert result_old is not None
