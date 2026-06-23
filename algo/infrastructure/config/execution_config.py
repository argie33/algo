#!/usr/bin/env python3
"""Execution configuration (mode, trading flags, rate limits).

Manages execution behavior independently from risk and market data config.
Trading team can tune execution settings without coordinating with risk team.

Categories:
- Execution mode (paper, dry-run, review, auto)
- Trading limits (max trades/day, max position size)
- Account configuration (paper vs live, default portfolio)

Delegates all DB access to parent AlgoConfig._config dict.
Provides logical grouping methods for convenience.
"""

import logging
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig

logger = logging.getLogger(__name__)


class ExecutionConfig:
    """Configuration for trade execution mode and limits."""

    def __init__(self, parent: "AlgoConfig") -> None:
        """Initialize ExecutionConfig with parent AlgoConfig.

        Args:
            parent: Parent AlgoConfig instance (holds _config dict and DB connection)
        """
        self.parent = parent

    def get(self, key: str, default: Any = None) -> Any:
        """Get execution configuration value.

        Delegates to parent AlgoConfig.get(), which handles:
        - Database lookup
        - Type validation via VALIDATION_SCHEMA
        - Fallback to defaults

        Args:
            key: Configuration key
            default: Default value if key missing

        Returns:
            Configuration value or default
        """
        return self.parent.get(key, default)

    def set(
        self,
        key: str,
        value: Any,
        value_type: str,
        description: str = "",
        changed_by: str = "system",
    ) -> bool:
        """Set execution configuration value (writes to DB).

        Args:
            key: Configuration key
            value: New value
            value_type: Type ('string', 'bool', 'int')
            description: Description (only used for new keys)
            changed_by: Actor making change (for audit trail)

        Returns:
            True if value was set as requested; False if rejected
        """
        return self.parent.set(key, value, value_type, description, changed_by)
    def get_execution_mode(self) -> str:
        """Get execution mode (paper|dry|review|auto).

        Returns:
            Execution mode string
        """
        mode = self.get("execution_mode", "auto")
        valid_modes = {"paper", "dry", "review", "auto"}
        if str(mode).lower() not in valid_modes:
            logger.warning(f"Invalid execution_mode '{mode}', defaulting to 'auto'")
            return "auto"
        return str(mode).lower()

    def is_paper_trading(self) -> bool:
        """Check if using Alpaca paper trading account.

        Returns:
            True if paper trading enabled, False for live
        """
        return bool(self.get("alpaca_paper_trading", False))

    def get_max_trades_per_day(self) -> int:
        """Get maximum number of new trades allowed per day.

        Returns:
            Max trades per day (positive integer)
        """
        return cast(int, self.get("max_trades_per_day", 5))

    def get_default_portfolio_value(self) -> float:
        """Get default portfolio value for dry-run mode.

        Returns:
            Portfolio value in dollars
        """
        return float(self.get("default_portfolio_value", 100000.0))

    def get_execution_config(self) -> dict[str, Any]:
        """Get all execution configuration as a dictionary.

        Returns:
            {
                "mode": "auto",
                "paper_trading": False,
                "max_trades_per_day": 5,
                "default_portfolio_value": 100000.0,
            }
        """
        return {
            "mode": self.get_execution_mode(),
            "paper_trading": self.is_paper_trading(),
            "max_trades_per_day": self.get_max_trades_per_day(),
            "default_portfolio_value": self.get_default_portfolio_value(),
        }

    def __repr__(self) -> str:
        return f"<ExecutionConfig mode={self.get_execution_mode()} paper={self.is_paper_trading()}>"
