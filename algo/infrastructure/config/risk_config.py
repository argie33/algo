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
from typing import TYPE_CHECKING, Any

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
        return self.parent.set(key, value, value_type, description, changed_by)

    def get_position_sizing_config(self) -> dict[str, Any]:
        return {
            "base_risk_pct": self.get("base_risk_pct"),
            "max_position_size_pct": self.get("max_position_size_pct"),
            "max_positions": self.get("max_positions"),
            "max_concentration_pct": self.get("max_concentration_pct"),
        }

    def __repr__(self) -> str:
        return f"<RiskConfig {len(self.get_position_sizing_config())} keys>"
