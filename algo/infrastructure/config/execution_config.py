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
from typing import TYPE_CHECKING, Any

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

        CRITICAL: Must be explicitly configured. Execution mode determines trading behavior.

        Returns:
            Execution mode string

        Raises:
            RuntimeError: If 'execution_mode' config key is missing (fail-fast)
        """
        mode = self.get("execution_mode")
        if mode is None:
            raise RuntimeError(
                "[EXECUTION_CONFIG] CRITICAL: execution_mode config key missing. "
                "Execution mode must be explicitly configured (paper|dry|review|auto). "
                "Set 'execution_mode' in algo_config table to proceed. "
                "Check database: SELECT * FROM algo_config WHERE key = 'execution_mode';"
            )
        mode_str = str(mode).lower()
        valid_modes = {"paper", "dry", "review", "auto"}
        if mode_str not in valid_modes:
            raise RuntimeError(
                f"[EXECUTION_CONFIG] CRITICAL: Invalid execution_mode '{mode}'. "
                f"Valid modes are: {', '.join(sorted(valid_modes))}. "
                f"Update algo_config: UPDATE algo_config SET value = 'auto' WHERE key = 'execution_mode';"
            )
        return mode_str

    def is_paper_trading(self) -> bool:
        """Check if using Alpaca paper trading account.

        CRITICAL: Must be explicitly configured to ensure trading account type is intentional.

        Returns:
            True if paper trading enabled, False for live

        Raises:
            RuntimeError: If 'alpaca_paper_trading' config key is missing (fail-fast)
        """
        value = self.get("alpaca_paper_trading")
        if value is None:
            raise RuntimeError(
                "[EXECUTION_CONFIG] CRITICAL: alpaca_paper_trading config key missing. "
                "Trading account type must be explicitly configured (paper vs live). "
                "Set 'alpaca_paper_trading' in algo_config table to proceed. "
                "Check database: SELECT * FROM algo_config WHERE key = 'alpaca_paper_trading';"
            )
        return bool(value)

    def get_max_trades_per_day(self) -> int:
        """Get maximum number of new trades allowed per day.

        CRITICAL: Must be explicitly configured to enforce risk limits on daily trading volume.

        Returns:
            Max trades per day (positive integer)

        Raises:
            RuntimeError: If 'max_trades_per_day' config key is missing or invalid (fail-fast)
        """
        value = self.get("max_trades_per_day")
        if value is None:
            raise RuntimeError(
                "[EXECUTION_CONFIG] CRITICAL: max_trades_per_day config key missing. "
                "Maximum daily trades must be explicitly configured for risk management. "
                "Set 'max_trades_per_day' in algo_config table to proceed. "
                "Check database: SELECT * FROM algo_config WHERE key = 'max_trades_per_day';"
            )
        max_trades = int(value)
        if max_trades <= 0:
            raise RuntimeError(
                f"[EXECUTION_CONFIG] CRITICAL: max_trades_per_day must be positive (got {max_trades}). "
                f"Update algo_config: UPDATE algo_config SET value = '5' WHERE key = 'max_trades_per_day';"
            )
        return max_trades

    def get_default_portfolio_value(self) -> float:
        """Get default portfolio value.

        CRITICAL: Must be explicitly configured. No hardcoded fallback to $100k.
        Portfolio value is a critical parameter for position sizing and risk management.

        Returns:
            Portfolio value in dollars

        Raises:
            RuntimeError: If 'default_portfolio_value' config key is missing (fail-fast)
        """
        value = self.get("default_portfolio_value")
        if value is None:
            raise RuntimeError(
                "[EXECUTION_CONFIG] CRITICAL: default_portfolio_value config key missing. "
                "Portfolio value must be explicitly configured — no fallback to $100k. "
                "Set 'default_portfolio_value' in algo_config table to proceed. "
                "Check database: SELECT * FROM algo_config WHERE key = 'default_portfolio_value';"
            )
        return float(value)

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
