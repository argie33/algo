#!/usr/bin/env python3
"""Circuit breaker configuration (halt switches, failsafe).

Manages all circuit breaker kill-switch parameters independently from RiskConfig.
CB team can tune halt thresholds without coordinating with Risk team.

Categories:
- Daily/weekly loss limits (max_daily_loss_pct, max_weekly_loss_pct)
- Consecutive loss limits (max_consecutive_losses)
- Win rate floor (min_win_rate_pct)
- Total open risk limit (max_total_risk_pct)
- Daily profit cap (daily_profit_cap_pct)
- Sector concentration halt (sector_drawdown_halt_pct)
- Data staleness check (max_data_staleness_days)
- Failsafe configuration (ecs_timeout, grace_period)

Delegates all DB access to parent AlgoConfig._config dict.
Provides logical grouping methods for convenience.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig

logger = logging.getLogger(__name__)


class CircuitBreakerConfig:
    """Configuration for circuit breaker kill-switches."""

    def __init__(self, parent: "AlgoConfig") -> None:
        """Initialize CircuitBreakerConfig with parent AlgoConfig.

        Args:
            parent: Parent AlgoConfig instance (holds _config dict and DB connection)
        """
        self.parent = parent

    def get(self, key: str, default: Any = None) -> Any:
        """Get circuit breaker configuration value.

        Delegates to parent AlgoConfig.get(), which handles:
        - Type validation via VALIDATION_SCHEMA
        - Fallback to defaults
        - Fail-closed values for critical thresholds

        Args:
            key: Configuration key (e.g., "max_daily_loss_pct")
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
        """Set circuit breaker configuration value (writes to DB).

        For critical safety thresholds (e.g., max_daily_loss_pct):
        - If value invalid, applies fail-closed default instead
        - Returns False to signal rejection

        Args:
            key: Configuration key
            value: New value
            value_type: Type ('int', 'float', 'bool', 'string')
            description: Description (only used for new keys)
            changed_by: Actor making change (for audit trail)

        Returns:
            True if value was set as requested; False if rejected/fail-closed
        """
        return self.parent.set(key, value, value_type, description, changed_by)

    def get_loss_limits_config(self) -> dict[str, Any]:
        """Get daily/weekly loss limit thresholds.

        Returns:
            {
                "max_daily_loss_pct": 2.0,     # Halt at -2% daily loss
                "max_weekly_loss_pct": 5.0,    # Halt at -5% weekly loss
                "daily_profit_cap_pct": 2.0,   # Cap at +2% daily profit
            }
        """
        return {
            "max_daily_loss_pct": self.get("max_daily_loss_pct"),
            "max_weekly_loss_pct": self.get("max_weekly_loss_pct"),
            "daily_profit_cap_pct": self.get("daily_profit_cap_pct"),
        }

    def get_trade_quality_limits_config(self) -> dict[str, Any]:
        """Get consecutive loss & win rate floor limits.

        Returns:
            {
                "max_consecutive_losses": 3,   # Halt after 3 losing trades
                "min_win_rate_pct": 40.0,      # Halt if win rate <40%
            }
        """
        return {
            "max_consecutive_losses": self.get("max_consecutive_losses"),
            "min_win_rate_pct": self.get("min_win_rate_pct"),
        }

    def get_risk_limits_config(self) -> dict[str, Any]:
        """Get total open risk & sector concentration limits.

        Returns:
            {
                "max_total_risk_pct": 4.0,           # Halt if total open risk >4%
                "sector_drawdown_halt_pct": -12.0,   # Halt if sector DD <-12%
            }
        """
        return {
            "max_total_risk_pct": self.get("max_total_risk_pct"),
            "sector_drawdown_halt_pct": self.get("sector_drawdown_halt_pct"),
        }

    def get_data_freshness_config(self) -> dict[str, Any]:
        """Get data staleness threshold.

        Returns:
            {
                "max_data_staleness_days": 3,  # Halt if data >3 days old
            }
        """
        return {
            "max_data_staleness_days": self.get("max_data_staleness_days"),
        }

    def get_failsafe_config(self) -> dict[str, Any]:
        """Get failsafe ECS & grace period configuration.

        Returns:
            {
                "failsafe_ecs_timeout_sec": 180,     # Max 180s to start ECS task
                "failsafe_grace_period_minutes": 240, # Grace period before retry
            }
        """
        return {
            "failsafe_ecs_timeout_sec": self.get("failsafe_ecs_timeout_sec"),
            "failsafe_grace_period_minutes": self.get("failsafe_grace_period_minutes"),
        }

    def __repr__(self) -> str:
        return f"<CircuitBreakerConfig {sum(len(d) for d in [self.get_loss_limits_config(), self.get_trade_quality_limits_config()])} keys>"
