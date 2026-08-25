#!/usr/bin/env python3
"""Central Metrics Calculator - Single Source of Truth for All Performance Metrics

This module consolidates ALL metric calculations (win_rate, sharpe, expectancy, etc.)
into a single place so they NEVER diverge between loaders, API, or dashboard.

CRITICAL: This is THE ONLY place where these metrics should be calculated.
Loaders use these functions. API uses results from loaders. Dashboard reads
pre-computed results from database (not recalculating).

All metrics are defined with:
1. Exact formula (comments show math)
2. Data requirements (minimum observations)
3. Edge case handling
4. Error behavior: no silent fallbacks. Most calculators (Sharpe, Sortino, max drawdown,
   Calmar, avg R-multiple) raise ValueError on insufficient/degenerate data. A few
   (win_rate, profit_factor) return a `{'data_unavailable': True, 'reason': ...}` marker
   dict instead, since those are expected to hit "no trades yet" during account ramp-up
   and callers branch on the reason; expectancy returns None for the same ramp-up case.
   Check each function's own docstring for which behavior applies.
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
    ) -> float | dict[str, Any]:
        """Calculate win rate percentage from trade counts.

        Formula: (wins / (wins + losses)) * 100

        Args:
            total_trades: Total number of trades (closed + open with P&L) - used only for
                the minimum-data check below, NOT as the win-rate denominator
            wins: Count of winning trades (profit_loss_dollars > 0)
            losses: Count of losing trades (profit_loss_dollars < 0)
            (Breakeven trades (= 0) and unclassifiable trades excluded from denominator)

        Returns:
            Win rate as percentage (0-100), or marker dict if insufficient data:
            {
                'data_unavailable': True,
                'reason': 'insufficient_trades' | 'missing_win_count' | 'no_decisive_trades'
            }

        Data Requirements:
            - Minimum 1 trade to calculate
            - Includes both closed trades AND open trades with unrealized P&L

        Edge Cases:
            - If total_trades is None or 0, returns unavailable marker
            - If wins is None, raises ValueError (cannot calculate without win count)
            - If wins + losses is 0 (all breakeven/unclassifiable), returns unavailable marker
        """
        if total_trades is None or total_trades <= 0:
            logger.warning(f"Cannot calculate win rate: insufficient trades (total_trades={total_trades})")
            return {"data_unavailable": True, "reason": "insufficient_trades"}
        if wins is None:
            raise ValueError("Cannot calculate win rate: wins count is None")
        if losses is None:
            raise ValueError("Cannot calculate win rate: losses count is None")
        if wins < 0 or losses < 0 or wins + losses > total_trades:
            logger.warning(
                f"Cannot calculate win rate: invalid win/loss counts (wins={wins}, losses={losses}, total={total_trades})"
            )
            return {"data_unavailable": True, "reason": "invalid_trade_counts"}
        decisive = wins + losses
        if decisive <= 0:
            logger.warning(f"Cannot calculate win rate: no decisive trades (wins={wins}, losses={losses})")
            return {"data_unavailable": True, "reason": "no_decisive_trades"}
        wr = (wins / decisive) * 100
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
            Sharpe ratio (float). Never returns None - raises ValueError on insufficient
            or degenerate data instead.

        Data Requirements:
            - Minimum 5 daily returns (can be overridden)
            - Returns must be numeric (float)
            - Standard deviation > 0 (else raises ValueError)

        Edge Cases:
            - If len(returns) < min_observations, raises ValueError
            - If all returns identical (std = 0), raises ValueError
            - If returns list is empty, raises ValueError
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

        Formula: (mean_return / downside_deviation) * sqrt(252)
        Downside deviation (Sortino & van der Meer 1991 convention, target=0):
            sqrt(sum(min(r, 0)**2 for r in returns) / N) computed over ALL N returns, not
            just the negative ones, and measured from 0 (the target), not from the negative
            subset's own mean.

        FIXED (goal, 2026-08-24): the prior implementation computed
        statistics.stdev([r for r in returns if r < 0]) - the sample standard deviation of
        ONLY the negative returns around THEIR OWN mean, using n-1 of that subset as the
        denominator. That is a different, systematically smaller quantity than downside
        deviation: it discards every zero/positive day from the denominator entirely (understating
        N) and measures spread around the average loss rather than magnitude below zero
        (discarding the average loss itself). On a real mixed-sign return series this inflated
        the reported Sortino ratio by 30%+ (hand-verified: 14.76 vs the correct 11.00 on the
        same 10-return series) - not a rounding difference, a wrong statistic entirely.

        Args:
            returns: List of daily returns as decimals
            min_observations: Minimum daily returns needed (default 5)

        Returns:
            Sortino ratio (float). Never returns None - raises ValueError on insufficient
            or degenerate data instead.

        Data Requirements:
            - Minimum 5 daily returns
            - At least 1 negative return to calculate downside deviation

        Edge Cases:
            - If len(returns) < min_observations, raises ValueError
            - If no negative returns (downside_deviation = 0), raises ValueError
        """
        if not returns or len(returns) < min_observations:
            raise ValueError(
                f"Insufficient data: need {min_observations} returns, got {len(returns) if returns else 0}"
            )
        try:
            mean_ret = statistics.mean(returns)
            sum_sq_downside = sum(min(r, 0.0) ** 2 for r in returns)
            if sum_sq_downside <= 0:
                raise ValueError("No downside returns: cannot calculate Sortino ratio")
            downside_deviation = (sum_sq_downside / len(returns)) ** 0.5
            sortino = (mean_ret / downside_deviation) * (252**0.5)
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
            Maximum drawdown as percentage (float). Never returns None - raises
            ValueError on insufficient data instead.

        Data Requirements:
            - Minimum 2 values needed (to have a peak and a drop)
            - All values must be numeric (float/int)
            - Values are expected to be in the portfolio's currency/unit

        Edge Cases:
            - If fewer than 2 values, raises ValueError
            - If all values are identical, returns 0 (no drawdown)
            - If portfolio always increases, returns 0 (no drawdown)
        """
        if not portfolio_values or len(portfolio_values) < 2:
            raise ValueError(
                f"Insufficient data: need 2+ portfolio values, got {len(portfolio_values) if portfolio_values else 0}"
            )
        try:
            # CRITICAL: Initialize peak to None, not 0.0, to detect if all values are negative
            peak: float | None = None
            max_dd = 0.0
            for value in portfolio_values:
                if not isinstance(value, (int, float)):
                    raise ValueError(f"Portfolio value must be numeric, got {type(value).__name__}: {value}")
                # Initialize peak on first iteration
                if peak is None:
                    peak = value
                elif value > peak:
                    peak = value

                # Only calculate drawdown if peak is set and positive
                # SAFETY: Prevent silent fallback to zero on negative values
                if peak is not None and peak > 0:
                    dd = ((peak - value) / peak) * 100
                    max_dd = max(max_dd, dd)
                elif peak is not None and peak <= 0:
                    logger.warning(
                        f"[DATA_QUALITY] Max drawdown calculation: peak value {peak} is <= 0, "
                        "cannot calculate meaningful drawdown. Returning 0."
                    )
            return round(max_dd, 2)
        except (ValueError, TypeError, ZeroDivisionError) as e:
            raise ValueError(f"Max drawdown calculation failed: {e}") from e

    @staticmethod
    def calculate_calmar_ratio(
        portfolio_values: list[float] | None,
        returns: list[float] | None = None,
        min_observations: int = 2,
    ) -> float | None:
        """Calculate Calmar ratio (annualized return / max drawdown).

        Formula: annualized_return_pct / max_drawdown_pct
        Annualization: CAGR-style, (end_val/start_val)**(252/n_periods) - 1, using the same
        252-trading-days/year convention already used for Sharpe/Sortino annualization in
        this module - n_periods = len(portfolio_values) - 1 (the number of daily steps
        actually observed), not the calendar-day span.

        FIXED (goal, 2026-08-24): this used to return raw endpoint-to-endpoint total return
        (unannualized) despite this method's own name and its caller's docstring
        (algo/reporting/performance.py's calmar_ratio()) both explicitly promising
        "annualized return / abs(max drawdown)". For a true ~252-trading-day window the two
        happen to be close (a full year's total return IS approximately its own annualized
        rate), which is why this went unnoticed - but the caller's own docstring explicitly
        supports a "ramp-up" path with as few as 5 snapshots, where a raw ~1-week total
        return reported as "the annualized Calmar ratio" is wrong by roughly a factor of 50
        (252/5), not a rounding difference.

        Args:
            portfolio_values: List of portfolio values in chronological order
                (used to calculate both return and drawdown)
            returns: Alternative: list of daily returns, used only if portfolio_values is
                not provided - compounded into a synthetic base-100 value series
                ([100, 100*(1+r0), 100*(1+r0)*(1+r1), ...]) so the same drawdown/CAGR math
                applies either way. Ignored if portfolio_values is provided.
            min_observations: Minimum values needed (default 2)

        Returns:
            Calmar ratio (float). Never returns None - raises ValueError on insufficient
            or degenerate data instead.

        Data Requirements:
            - Minimum 2 portfolio values OR 2 daily returns
            - Max drawdown > 0 (else raises ValueError to avoid division by zero)

        Edge Cases:
            - If portfolio only goes up (max_dd = 0), raises ValueError
            - If return is 0 (no gain), returns 0
            - If only portfolio_values provided, returns is derived from endpoint values
        """
        if not portfolio_values and returns:
            synthesized = [100.0]
            for r in returns:
                synthesized.append(synthesized[-1] * (1.0 + r))
            portfolio_values = synthesized

        if not portfolio_values or len(portfolio_values) < min_observations:
            raise ValueError(
                f"Insufficient data: need {min_observations}+ values, got {len(portfolio_values) if portfolio_values else 0}"
            )

        try:
            # Calculate max drawdown from portfolio values
            max_dd = MetricsCalculator.calculate_max_drawdown(portfolio_values)
            if max_dd is None or max_dd <= 0:
                raise ValueError("Cannot calculate Calmar ratio: max drawdown must be > 0")

            # Calculate annualized (CAGR) return from portfolio values
            start_val = portfolio_values[0]
            end_val = portfolio_values[-1]
            if start_val <= 0:
                raise ValueError("Cannot calculate Calmar ratio: start value must be > 0")
            n_periods = len(portfolio_values) - 1
            if end_val <= 0:
                raise ValueError("Cannot calculate Calmar ratio: end value must be > 0")
            annualized_return = cast(float, (end_val / start_val) ** (252.0 / n_periods) - 1) * 100

            calmar = annualized_return / max_dd
            return round(calmar, 3)
        except (ValueError, TypeError, ZeroDivisionError) as e:
            raise ValueError(f"Calmar ratio calculation failed: {e}") from e

    @staticmethod
    def calculate_profit_factor(
        total_wins_dollars: float | None,
        total_losses_dollars: float | None,
    ) -> float | dict[str, Any]:
        """Calculate profit factor (total wins / total losses in dollars).

        Formula: sum(positive P&L) / sum(abs(negative P&L))

        Args:
            total_wins_dollars: Sum of all positive profit_loss_dollars
            total_losses_dollars: Sum of absolute value of negative profit_loss_dollars

        Returns:
            Profit factor (float), float('inf') if perfect record, or marker dict:
            {
                'data_unavailable': True,
                'reason': 'missing_data' | 'no_trades'
            }

        Data Requirements:
            - Must have at least one winning trade and one losing trade
            - Values in dollars (not R-multiples)

        Edge Cases:
            - If total_losses_dollars = 0 and total_wins_dollars > 0: returns inf
            - If total_losses_dollars = 0 and total_wins_dollars = 0: returns unavailable marker
            - If total_losses_dollars > 0 but total_wins_dollars = 0: returns 0
            - Breakeven trades (= 0) excluded from both numerator and denominator
        """
        if total_losses_dollars is None or total_wins_dollars is None:
            logger.warning(
                f"Cannot calculate profit factor: missing data "
                f"(wins={total_wins_dollars}, losses={total_losses_dollars})"
            )
            return {"data_unavailable": True, "reason": "missing_data"}

        total_losses = float(total_losses_dollars)
        total_wins = float(total_wins_dollars)

        if total_losses < 1e-6:  # Essentially zero
            if total_wins > 1e-6:
                return float("inf")  # Perfect record (only wins, no losses)
            logger.warning("Cannot calculate profit factor: no trades or all breakeven")
            return {"data_unavailable": True, "reason": "no_trades"}

        pf = total_wins / total_losses
        return round(pf, 3)

    @staticmethod
    def calculate_expectancy(
        win_rate_pct: float | None,
        avg_win_r_multiple: float | None,
        avg_loss_r_multiple: float | None,
    ) -> float | None:
        """Calculate expectancy (expected profit per trade in R-multiples).

        Formula: E[profit] = (win_rate x avg_win_R) - (1 - win_rate) x abs(avg_loss_R)

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
            logger.debug(
                f"Expectancy calculation cannot proceed - insufficient data: "
                f"win_rate_pct={win_rate_pct}, avg_win_r={avg_win_r_multiple}, avg_loss_r={avg_loss_r_multiple}. "
                f"This is normal for ramp-up accounts without both winning and losing trades yet."
            )
            return None

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
            Average R-multiple (float). Never returns None - raises ValueError if no
            data instead.

        Data Requirements:
            - Minimum 1 R-multiple value

        Edge Cases:
            - Empty list raises ValueError
            - All-None list raises ValueError
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
            wins = metrics.get("num_wins")
            losses = metrics.get("num_losses")
            if wins is None:
                issues.append("num_wins is None but required for trade consistency check")
            elif losses is None:
                issues.append("num_losses is None but required for trade consistency check")
            elif total is not None and (wins + losses) > total:
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
def calculate_win_rate(*args: Any, **kwargs: Any) -> float | dict[str, Any]:
    """See MetricsCalculator.calculate_win_rate"""
    return MetricsCalculator.calculate_win_rate(*args, **kwargs)


def calculate_sharpe_ratio(*args: Any, **kwargs: Any) -> float | None:
    """See MetricsCalculator.calculate_sharpe_ratio"""
    return MetricsCalculator.calculate_sharpe_ratio(*args, **kwargs)


def calculate_sortino_ratio(*args: Any, **kwargs: Any) -> float | None:
    """See MetricsCalculator.calculate_sortino_ratio"""
    return MetricsCalculator.calculate_sortino_ratio(*args, **kwargs)


def calculate_max_drawdown(*args: Any, **kwargs: Any) -> float | None:
    """See MetricsCalculator.calculate_max_drawdown"""
    return MetricsCalculator.calculate_max_drawdown(*args, **kwargs)


def calculate_calmar_ratio(*args: Any, **kwargs: Any) -> float | None:
    """See MetricsCalculator.calculate_calmar_ratio"""
    return MetricsCalculator.calculate_calmar_ratio(*args, **kwargs)


def calculate_profit_factor(*args: Any, **kwargs: Any) -> float | dict[str, Any]:
    """See MetricsCalculator.calculate_profit_factor"""
    return MetricsCalculator.calculate_profit_factor(*args, **kwargs)


def calculate_expectancy(*args: Any, **kwargs: Any) -> float | None:
    """See MetricsCalculator.calculate_expectancy"""
    return MetricsCalculator.calculate_expectancy(*args, **kwargs)


def calculate_avg_r_multiple(*args: Any, **kwargs: Any) -> float | None:
    """See MetricsCalculator.calculate_avg_r_multiple"""
    return MetricsCalculator.calculate_avg_r_multiple(*args, **kwargs)
