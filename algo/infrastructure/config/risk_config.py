#!/usr/bin/env python3
"""Risk configuration (position sizing, drawdown defense, re-engagement).

Manages all risk-related parameters independently from CircuitBreakerConfig.
Risk team can tune position sizing without coordinating with CB team.

Categories:
- Base risk & position sizing (base_risk_pct, max_position_size_pct, etc.)
- Drawdown defense (halt_drawdown_pct, risk_reduction_at_*, re_engage_*)
- Position monitoring (position_halt_flag_count, max_reentries_per_name)
- Risk metrics thresholds (var_percentile, cvar_percentile, etc.)

Delegates all DB access to parent AlgoConfig._config dict.
Provides logical grouping methods for convenience.
"""

import logging
from typing import TYPE_CHECKING, Any, cast


if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig

logger = logging.getLogger(__name__)


class RiskConfig:
    """Configuration for risk management (position sizing, drawdown defense)."""

    def __init__(self, parent: "AlgoConfig") -> None:
        """Initialize RiskConfig with parent AlgoConfig.

        Args:
            parent: Parent AlgoConfig instance (holds _config dict and DB connection)
        """
        self.parent = parent

    def get(self, key: str, default: Any = None) -> Any:
        """Get risk configuration value.

        Delegates to parent AlgoConfig.get(), which handles:
        - Type validation via VALIDATION_SCHEMA
        - Fallback to defaults
        - Fail-closed values for critical thresholds

        Args:
            key: Configuration key (e.g., "base_risk_pct")
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
        """Set risk configuration value (writes to DB).

        For critical safety thresholds (e.g., halt_drawdown_pct):
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
        return cast(bool, self.parent.set(key, value, value_type, description, changed_by))

    def get_base_risk(self) -> float:
        """Get base risk % per trade."""
        return cast(float, self.get("base_risk_pct", 0.75))

    def get_position_sizing_config(self) -> dict[str, Any]:
        """Get all position sizing thresholds (for risk team).

        Returns:
            {
                "base_risk_pct": 0.75,          # Base risk per trade
                "max_position_size_pct": 6.3,   # Max single position size
                "max_positions": 15,             # Max concurrent positions
                "max_concentration_pct": 50.0,   # Max concentration in top position
            }
        """
        return {
            "base_risk_pct": self.get("base_risk_pct"),
            "max_position_size_pct": self.get("max_position_size_pct"),
            "max_positions": self.get("max_positions"),
            "max_concentration_pct": self.get("max_concentration_pct"),
        }

    def get_drawdown_defense_config(self) -> dict[str, Any]:
        """Get all drawdown defense thresholds and recovery rules.

        Returns:
            {
                "halt_drawdown_pct": -20.0,              # Halt at -20% DD
                "risk_reduction_at_minus_5": 0.75,      # 75% risk at -5% DD
                "risk_reduction_at_minus_10": 0.5,      # 50% risk at -10% DD
                "risk_reduction_at_minus_15": 0.25,     # 25% risk at -15% DD
                "risk_reduction_at_minus_20": 0.0,      # 0% (halt) at -20% DD
                "re_engage_recovery_pct": 8.0,          # Resume at +8% recovery
                "re_engage_min_days": 5,                 # Min 5 days after halt
                "require_ftd_to_re_engage": True,        # Require Follow-Through Day
            }
        """
        return {
            "halt_drawdown_pct": self.get("halt_drawdown_pct"),
            "risk_reduction_at_minus_5": self.get("risk_reduction_at_minus_5"),
            "risk_reduction_at_minus_10": self.get("risk_reduction_at_minus_10"),
            "risk_reduction_at_minus_15": self.get("risk_reduction_at_minus_15"),
            "risk_reduction_at_minus_20": self.get("risk_reduction_at_minus_20"),
            "re_engage_recovery_pct": self.get("re_engage_recovery_pct"),
            "re_engage_min_days": self.get("re_engage_min_days"),
            "require_ftd_to_re_engage": self.get("require_ftd_to_re_engage"),
        }

    def get_position_monitoring_config(self) -> dict[str, Any]:
        """Get position monitoring & re-entry rules.

        Returns:
            {
                "position_halt_flag_count": 2,                   # Flags to exit
                "max_reentries_per_name": 2,                     # Max re-entries
                "min_days_before_reentry_same_symbol": 5,        # Days between entries
            }
        """
        return {
            "position_halt_flag_count": self.get("position_halt_flag_count"),
            "max_reentries_per_name": self.get("max_reentries_per_name"),
            "min_days_before_reentry_same_symbol": self.get("min_days_before_reentry_same_symbol"),
        }

    def get_risk_metrics_config(self) -> dict[str, Any]:
        """Get risk metrics thresholds (VaR, CVaR, etc.).

        Returns:
            {
                "var_percentile": 5,            # 95% confidence
                "cvar_percentile": 5,           # Worst 5% of days
                "stressed_var_percentile": 10,  # Worst 10% of days
            }
        """
        return {
            "var_percentile": self.get("var_percentile"),
            "cvar_percentile": self.get("cvar_percentile"),
            "stressed_var_percentile": self.get("stressed_var_percentile"),
        }

    def __repr__(self) -> str:
        return f"<RiskConfig {len(self.get_position_sizing_config())} keys>"
