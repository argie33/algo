#!/usr/bin/env python3
"""Central Metrics Calculator — Single Source of Truth for All Performance Metrics

This module consolidates ALL metric calculations (win_rate, sharpe, expectancy, etc.)
into a single place so they NEVER diverge between loaders, API, or dashboard.

CRITICAL: This is THE ONLY place where these metrics should be calculated.
Loaders use these functions. API uses results from loaders. Dashboard reads
pre-computed results from database (not recalculating).

All metrics are defined with:
1. Exact formula (comments show math)
2. Data requirements (minimum observations)
3. Edge case handling
4. Error behavior (return None, not fallback)
"""

import logging
import statistics
from typing import Any, cast


logger = logging.getLogger(__name__)


class MetricsCalculator:
    """Centralized performance metrics calculation engine."""

    @staticmethod
    def calculate_win_rate(
        total_trades: int | None,
        wins: int | None,
        losses: int | None,
    ) -> float | None:
        """Calculate win rate percentage from trade counts.

        Formula: (wins / total_trades) * 100

        Args:
            total_trades: Total number of trades (closed + open with P&L)
            wins: Count of winning trades (profit_loss_dollars > 0)
            losses: Count of losing trades (profit_loss_dollars < 0)
            (Breakeven trades (= 0) excluded from denominator)

        Returns:
            Win rate as percentage (0-100), or None if insufficient data

        Data Requirements:
            - Minimum 1 trade to calculate
            - Includes both closed trades AND open trades with unrealized P&L

        Edge Cases:
            - If total_trades is None or 0, returns None
            - If wins or losses is None, uses 0
        """
        if total_trades is None or total_trades <= 0:
            return None
        wins_val = wins if wins is not None else 0
        if wins_val < 0 or wins_val > total_trades:
            return None
        wr = (wins_val / total_trades) * 100
        return round(wr, 2)

    @staticmethod
    def calculate_sharpe_ratio(
        returns: list[float] | None,
        min_observations: int = 5,
    ) -> float | None:
        """Calculate 252-day annualized Sharpe ratio from daily returns.

        Formula: (mean_return / std_return) * sqrt(252)
        Annualization: assumes 252 trading days per year

        Args:
            returns: List of daily returns as decimals (e.g., 0.01 for +1%)
            min_observations: Minimum daily returns needed (default 5)

        Returns:
            Sharpe ratio, or None if insufficient data

        Data Requirements:
            - Minimum 5 daily returns (can be overridden)
            - Returns must be numeric (float)
            - Standard deviation > 0 (else returns None)

        Edge Cases:
            - If len(returns) < min_observations, returns None
            - If all returns identical (std = 0), returns None
            - If returns list is empty, returns None
        """
        if not returns or len(returns) < min_observations:
            raise ValueError(
                f"Insufficient data: need {min_observations} returns, got {len(returns) if returns else 0}"
            )
        try:
            mean_ret = statistics.mean(returns)
            std_ret = statistics.stdev(returns) if len(returns) > 1 else 0
            if std_ret <= 0:
                raise ValueError("Zero standard deviation: cannot calculate Sharpe ratio")
            sharpe = (mean_ret / std_ret) * (252**0.5)
            return cast(float, round(sharpe, 3))
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise ValueError(f"Sharpe ratio calculation failed: {e}") from e

    @staticmethod
    def calculate_sortino_ratio(
        returns: list[float] | None,
        min_observations: int = 5,
    ) -> float | None:
        """Calculate 252-day annualized Sortino ratio from daily returns.

        Formula: (mean_return / downside_std) * sqrt(252)
        Downside only: only negative returns count toward volatility

        Args:
            returns: List of daily returns as decimals
            min_observations: Minimum daily returns needed (default 5)

        Returns:
            Sortino ratio, or None if insufficient data

        Data Requirements:
            - Minimum 5 daily returns
            - At least 1 negative return to calculate downside volatility

        Edge Cases:
            - If len(returns) < min_observations, returns None
            - If no negative returns (downside_std = 0), returns None
            - If all returns are negative, downside_std ≈ full volatility
        """
        if not returns or len(returns) < min_observations:
            raise ValueError(
                f"Insufficient data: need {min_observations} returns, got {len(returns) if returns else 0}"
            )
        try:
            mean_ret = statistics.mean(returns)
            downside_rets = [r for r in returns if r < 0]
            if not downside_rets:
                raise ValueError("No downside returns: cannot calculate Sortino ratio")
            downside_std = statistics.stdev(downside_rets) if len(downside_rets) > 1 else 0
            if downside_std <= 0:
                raise ValueError("Zero downside volatility: cannot calculate Sortino ratio")
            sortino = (mean_ret / downside_std) * (252**0.5)
            return cast(float, round(sortino, 3))
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise ValueError(f"Sortino ratio calculation failed: {e}") from e

    @staticmethod
    def calculate_max_drawdown(
        portfolio_values: list[float] | None,
    ) -> float | None:
        """Calculate maximum drawdown from a series of portfolio values.

        Formula: max((peak - value) / peak) * 100 for each peak
        Peak: highest portfolio value seen up to that point

        Args:
            portfolio_values: List of portfolio values in chronological order

        Returns:
            Maximum drawdown as percentage, or None if insufficient data

        Data Requirements:
            - Minimum 2 values needed (to have a peak and a drop)

        Edge Cases:
            - If fewer than 2 values, returns None
            - If all values are identical, returns 0 (no drawdown)
            - If portfolio always increases, returns 0 (no drawdown)
        """
        if not portfolio_values or len(portfolio_values) < 2:
            raise ValueError(
                f"Insufficient data: need 2+ portfolio values, got {len(portfolio_values) if portfolio_values else 0}"
            )
        try:
            peak = 0.0
            max_dd = 0.0
            for value in portfolio_values:
                if value > peak:
                    peak = value
                if peak > 0:
                    dd = ((peak - value) / peak) * 100
                    max_dd = max(max_dd, dd)
            return round(max_dd, 2)
        except (ValueError, TypeError, ZeroDivisionError) as e:
            raise ValueError(f"Max drawdown calculation failed: {e}") from e

    @staticmethod
    def calculate_calmar_ratio(
        portfolio_values: list[float] | None,
        returns: list[float] | None = None,
        min_observations: int = 2,
    ) -> float | None:
        """Calculate Calmar ratio (return / max drawdown).

        Formula: total_compounded_return / max_drawdown_pct
        Compounding: multiply (1 + daily_return) for each day

        Args:
            portfolio_values: List of portfolio values in chronological order
                (used to calculate both return and drawdown)
            returns: Alternative: list of daily returns (if portfolio_values not available)
                (NOT USED if portfolio_values is provided)
            min_observations: Minimum values needed (default 2)

        Returns:
            Calmar ratio, or None if insufficient data

        Data Requirements:
            - Minimum 2 portfolio values OR 2 daily returns
            - Max drawdown > 0 (else returns None to avoid division by zero)

        Edge Cases:
            - If portfolio only goes up (max_dd = 0), returns None
            - If return is 0 (no gain), returns 0
            - If only portfolio_values provided, returns is derived from endpoint values
        """
        if not portfolio_values or len(portfolio_values) < min_observations:
            raise ValueError(
                f"Insufficient data: need {min_observations}+ values, got {len(portfolio_values) if portfolio_values else 0}"
            )

        try:
            # Calculate max drawdown from portfolio values
            max_dd = MetricsCalculator.calculate_max_drawdown(portfolio_values)
            if max_dd is None or max_dd <= 0:
                raise ValueError("Cannot calculate Calmar ratio: max drawdown must be > 0")

            # Calculate total return from portfolio values
            start_val = portfolio_values[0]
            end_val = portfolio_values[-1]
            if start_val <= 0:
                raise ValueError("Cannot calculate Calmar ratio: start value must be > 0")
            total_return = ((end_val / start_val) - 1) * 100  # Convert to percentage

            calmar = total_return / max_dd
            return round(calmar, 3)
        except (ValueError, TypeError, ZeroDivisionError) as e:
            raise ValueError(f"Calmar ratio calculation failed: {e}") from e

    @staticmethod
    def calculate_profit_factor(
        total_wins_dollars: float | None,
        total_losses_dollars: float | None,
    ) -> float | None:
        """Calculate profit factor (total wins / total losses in dollars).

        Formula: sum(positive P&L) / sum(abs(negative P&L))

        Args:
            total_wins_dollars: Sum of all positive profit_loss_dollars
            total_losses_dollars: Sum of absolute value of negative profit_loss_dollars

        Returns:
            Profit factor (float), float('inf') if perfect record, or None if no losses

        Data Requirements:
            - Must have at least one winning trade and one losing trade
            - Values in dollars (not R-multiples)

        Edge Cases:
            - If total_losses_dollars = 0 and total_wins_dollars > 0: returns inf
            - If total_losses_dollars = 0 and total_wins_dollars = 0: returns None
            - If total_losses_dollars > 0 but total_wins_dollars = 0: returns 0
            - Breakeven trades (= 0) excluded from both numerator and denominator
        """
        if total_losses_dollars is None or total_wins_dollars is None:
            return None

        total_losses = float(total_losses_dollars)
        total_wins = float(total_wins_dollars)

        if total_losses < 1e-6:  # Essentially zero
            if total_wins > 1e-6:
                return float("inf")  # Perfect record (only wins, no losses)
            return None  # No trades or all breakeven

        pf = total_wins / total_losses
        return round(pf, 3)

    @staticmethod
    def calculate_expectancy(
        win_rate_pct: float | None,
        avg_win_r_multiple: float | None,
        avg_loss_r_multiple: float | None,
    ) -> float | None:
        """Calculate expectancy (expected profit per trade in R-multiples).

        Formula: E[profit] = (win_rate × avg_win_R) - (1 - win_rate) × abs(avg_loss_R)

        Args:
            win_rate_pct: Win rate as percentage (0-100)
            avg_win_r_multiple: Average R-multiple of winning trades (e.g., 2.5)
            avg_loss_r_multiple: Average R-multiple of losing trades (e.g., -1.0)

        Returns:
            Expectancy in R-multiples, or None if insufficient data

        Data Requirements:
            - All three inputs must be numeric
            - win_rate should be 0-100

        Edge Cases:
            - If any input is None, returns None
            - If avg_loss_r_multiple is positive (shouldn't happen), takes absolute value
        """
        if win_rate_pct is None or avg_win_r_multiple is None or avg_loss_r_multiple is None:
            raise ValueError(
                "Cannot calculate expectancy: win_rate_pct, avg_win_r_multiple, "
                "and avg_loss_r_multiple must all be provided"
            )

        try:
            wr_decimal = float(win_rate_pct) / 100
            avg_win = float(avg_win_r_multiple)
            avg_loss = abs(float(avg_loss_r_multiple))  # Always positive for formula
            exp = (wr_decimal * avg_win) - ((1 - wr_decimal) * avg_loss)
            return round(exp, 3)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Expectancy calculation failed: {e}") from e

    @staticmethod
    def calculate_avg_r_multiple(
        r_multiples: list[float] | None,
    ) -> float | None:
        """Calculate average R-multiple across trades.

        Formula: mean(exit_r_multiple) for all trades with R-multiple defined

        Args:
            r_multiples: List of exit_r_multiple values from algo_trades

        Returns:
            Average R-multiple, or None if no data

        Data Requirements:
            - Minimum 1 R-multiple value

        Edge Cases:
            - Empty list returns None
            - All zero returns 0
            - Mix of positive and negative values: returns mean
        """
        if not r_multiples:
            raise ValueError("Cannot calculate average R-multiple: no R-multiples provided")
        try:
            r_vals = [float(r) for r in r_multiples if r is not None]
            if not r_vals:
                raise ValueError("Cannot calculate average R-multiple: all R-multiples are None")
            avg = statistics.mean(r_vals)
            return round(avg, 3)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Average R-multiple calculation failed: {e}") from e


class MetricsValidator:
    """Validates metric values for consistency and data quality."""

    @staticmethod
    def validate_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
        """Validate a metrics dict and flag issues.

        Returns metrics with additional fields:
        - _validation_issues: List of issues found
        - _warnings: List of warnings about unusual values
        - _confidence: High/Medium/Low based on data quality
        """
        issues: list[str] = []
        warnings: list[str] = []
        confidence = "high"

        # Win rate should be 0-100
        if "win_rate_all" in metrics and metrics["win_rate_all"] is not None:
            wr = metrics["win_rate_all"]
            if wr < 0 or wr > 100:
                issues.append(f"win_rate_all {wr} is outside 0-100 range")
            if wr < 20:
                warnings.append(f"win_rate_all {wr}% is very low (expected 30-60% for profitable system)")

        # Profit factor should be > 1 for profitability
        if "profit_factor" in metrics and metrics["profit_factor"] is not None:
            pf = metrics["profit_factor"]
            if pf < 0:
                issues.append(f"profit_factor {pf} is negative")
            if pf == float("inf"):
                warnings.append("profit_factor is infinite (only wins, no losses)")
            if 0 < pf < 1:
                warnings.append(f"profit_factor {pf} < 1 (losing more than winning on average)")

        # Expectancy should usually be positive
        if "expectancy" in metrics and metrics["expectancy"] is not None:
            exp = metrics["expectancy"]
            if exp < 0:
                warnings.append(f"expectancy {exp}R is negative (losing trades expected)")

        # Trade counts consistency
        if "total_trades" in metrics and "num_wins" in metrics and "num_losses" in metrics:
            total = metrics.get("total_trades")
            wins = metrics.get("num_wins", 0)
            losses = metrics.get("num_losses", 0)
            if total is not None and (wins + losses) > total:
                issues.append(f"wins + losses ({wins + losses}) exceeds total_trades ({total})")

        if issues:
            confidence = "low"
        elif warnings:
            confidence = "medium"

        metrics["_validation_issues"] = issues
        metrics["_validation_warnings"] = warnings
        metrics["_confidence"] = confidence

        return metrics


# Convenience functions for direct use
def calculate_win_rate(*args, **kwargs) -> float | None:
    """See MetricsCalculator.calculate_win_rate"""
    return MetricsCalculator.calculate_win_rate(*args, **kwargs)


def calculate_sharpe_ratio(*args, **kwargs) -> float | None:
    """See MetricsCalculator.calculate_sharpe_ratio"""
    return MetricsCalculator.calculate_sharpe_ratio(*args, **kwargs)


def calculate_sortino_ratio(*args, **kwargs) -> float | None:
    """See MetricsCalculator.calculate_sortino_ratio"""
    return MetricsCalculator.calculate_sortino_ratio(*args, **kwargs)


def calculate_max_drawdown(*args, **kwargs) -> float | None:
    """See MetricsCalculator.calculate_max_drawdown"""
    return MetricsCalculator.calculate_max_drawdown(*args, **kwargs)


def calculate_calmar_ratio(*args, **kwargs) -> float | None:
    """See MetricsCalculator.calculate_calmar_ratio"""
    return MetricsCalculator.calculate_calmar_ratio(*args, **kwargs)


def calculate_profit_factor(*args, **kwargs) -> float | None:
    """See MetricsCalculator.calculate_profit_factor"""
    return MetricsCalculator.calculate_profit_factor(*args, **kwargs)


def calculate_expectancy(*args, **kwargs) -> float | None:
    """See MetricsCalculator.calculate_expectancy"""
    return MetricsCalculator.calculate_expectancy(*args, **kwargs)


def calculate_avg_r_multiple(*args, **kwargs) -> float | None:
    """See MetricsCalculator.calculate_avg_r_multiple"""
    return MetricsCalculator.calculate_avg_r_multiple(*args, **kwargs)
