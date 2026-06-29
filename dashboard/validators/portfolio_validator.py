"""Portfolio Data Validator - Reject silent None defaults and incomplete data.

CRITICAL: Dashboard panels aggregate None values silently, which become fake data
in calculations (sum of Nones = 0, averages collapse, etc).

This validator ensures portfolio metrics are explicit about missing data instead
of silently aggregating None values.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PortfolioDataValidator:
    """Validates portfolio data for completeness before rendering."""

    # Metrics that are CRITICAL for portfolio dashboard - must not be None
    CRITICAL_METRICS = {
        "total_portfolio_value": "Portfolio value is required",
        "total_cash": "Cash position is required",
        "cash_available": "Available cash is required",
        "unrealized_pnl": "Unrealized P&L is required for position tracking",
        "unrealized_pnl_pct": "Unrealized P&L percent is required",
        "daily_return_pct": "Daily return is required for performance tracking",
    }

    # Metrics that are important but optional (display as "--" if missing)
    OPTIONAL_METRICS = {
        "cumulative_return_pct": "Cumulative return calculation",
        "max_drawdown_pct": "Max drawdown requires historical data",
        "profit_factor": "Profit factor requires trade data",
        "expectancy": "Expectancy requires trade analysis",
        "sharpe": "Sharpe ratio requires performance history",
    }

    @staticmethod
    def validate_portfolio_data(portfolio: dict[str, Any]) -> tuple[bool, str]:
        """Validate portfolio dict has all critical metrics.

        Returns:
            (is_valid, message)
        """
        if not portfolio:
            return False, "Portfolio data is None/empty"

        missing_critical = []
        for metric, reason in PortfolioDataValidator.CRITICAL_METRICS.items():
            value = portfolio.get(metric)
            if value is None:
                missing_critical.append(f"{metric} ({reason})")

        if missing_critical:
            return (
                False,
                f"Portfolio data incomplete - missing critical metrics: {'; '.join(missing_critical)}. "
                f"These must be calculated before rendering dashboard.",
            )

        # Validate reasonable ranges
        pv = portfolio.get("total_portfolio_value")
        if pv is not None and pv <= 0:
            return (
                False,
                f"Portfolio value {pv} is invalid (must be positive). "
                f"Data corruption detected.",
            )

        cash = portfolio.get("total_cash")
        if cash is not None and cash < 0 and pv and cash < -pv * 2:
            return (
                False,
                f"Cash {cash} is dramatically negative relative to portfolio {pv}. "
                f"May indicate liquidation or data error.",
            )

        # Check for silent aggregation of None values
        performance_metrics = [
            portfolio.get("cumulative_return_pct"),
            portfolio.get("daily_return_pct"),
            portfolio.get("max_drawdown_pct"),
            portfolio.get("profit_factor"),
            portfolio.get("expectancy"),
        ]
        none_count = sum(1 for m in performance_metrics if m is None)
        if none_count > len(performance_metrics) * 0.5:
            logger.warning(
                f"Portfolio data has {none_count}/{len(performance_metrics)} metrics missing. "
                f"Dashboard will show partial information."
            )

        return True, "Portfolio data valid"

    @staticmethod
    def validate_position_data(positions: list[dict[str, Any]]) -> tuple[bool, str]:
        """Validate each position has required fields.

        Returns:
            (is_valid, message)
        """
        if not positions:
            return True, "No positions (empty list acceptable)"

        critical_fields = [
            "symbol",
            "quantity",
            "avg_entry_price",
            "current_price",
            "position_value",
            "unrealized_pnl",
            "unrealized_pnl_pct",
        ]

        invalid_positions = []
        for idx, pos in enumerate(positions):
            missing = [f for f in critical_fields if pos.get(f) is None]
            if missing:
                invalid_positions.append(
                    f"Position {idx} ({pos.get('symbol', 'UNKNOWN')}): missing {', '.join(missing)}"
                )

        if invalid_positions:
            return (
                False,
                f"Invalid position data: {'; '.join(invalid_positions)}. "
                f"Positions must have all required fields.",
            )

        return True, "All positions valid"

    @staticmethod
    def validate_performance_metrics(perf: dict[str, Any]) -> tuple[bool, str]:
        """Validate performance metrics are reasonable.

        Returns:
            (is_valid, message)
        """
        if not perf:
            return True, "No performance data"

        # Reasonable ranges for performance metrics
        checks = {
            "win_rate": (0.0, 1.0, "Win rate must be 0-100%"),
            "profit_factor": (0.0, None, "Profit factor must be positive"),
            "sharpe": (-10.0, 10.0, "Sharpe ratio should be -10 to +10"),
            "sortino": (-10.0, 10.0, "Sortino ratio should be -10 to +10"),
            "calmar": (-5.0, 5.0, "Calmar ratio should be -5 to +5"),
        }

        issues = []
        for metric, (min_val, max_val, _reason) in checks.items():
            value = perf.get(metric)
            if value is None:
                continue  # Optional metric
            if min_val is not None and value < min_val:
                issues.append(f"{metric}={value} below minimum {min_val}")
            if max_val is not None and value > max_val:
                issues.append(f"{metric}={value} above maximum {max_val}")

        if issues:
            return (
                False,
                f"Performance metrics out of range: {'; '.join(issues)}. "
                f"Check data source for corruption.",
            )

        return True, "Performance metrics valid"


def validate_before_rendering(panel_name: str, data: dict[str, Any]) -> bool:
    """Validates panel data before rendering dashboard.

    Raises RuntimeError if critical data missing/invalid.
    Returns True if data is acceptable (may have optional fields missing).
    """
    if panel_name == "portfolio":
        is_valid, msg = PortfolioDataValidator.validate_portfolio_data(data.get("portfolio"))
        if not is_valid:
            logger.error(f"[PORTFOLIO_PANEL] {msg}")
            raise RuntimeError(f"Portfolio panel cannot render: {msg}")

        positions = data.get("positions", [])
        is_valid, msg = PortfolioDataValidator.validate_position_data(positions)
        if not is_valid:
            logger.error(f"[PORTFOLIO_PANEL] {msg}")
            raise RuntimeError(f"Portfolio panel cannot render: {msg}")

    elif panel_name == "performance":
        perf = data.get("performance", {})
        is_valid, msg = PortfolioDataValidator.validate_performance_metrics(perf)
        if not is_valid:
            logger.warning(f"[PERFORMANCE_PANEL] {msg}")
            # Performance issues are warnings, not errors (optional enrichment)

    return True
