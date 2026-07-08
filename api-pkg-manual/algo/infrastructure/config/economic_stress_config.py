#!/usr/bin/env python3
"""Economic stress configuration (regime scoring, yield curves, spreads).

Manages all economic regime and stress scoring parameters independently.
Risk team can tune stress thresholds without affecting trading execution.

Categories:
- Yield curve inversion stress (severe, moderate, flat)
- High-yield spread stress (severe, elevated, widening)
- Jobless claims stress (severe, elevated)
- Financial stress (severe, elevated)
- Regime penalties and exposure caps

Delegates all DB access to parent AlgoConfig._config dict.
Provides logical grouping methods for convenience.
"""

import logging
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig

logger = logging.getLogger(__name__)


class EconomicStressConfig:
    """Configuration for economic stress regime scoring."""

    def __init__(self, parent: "AlgoConfig") -> None:
        """Initialize EconomicStressConfig with parent AlgoConfig.

        Args:
            parent: Parent AlgoConfig instance (holds _config dict and DB connection)
        """
        self.parent = parent

    def get(self, key: str, default: Any = None) -> Any:
        """Get economic stress configuration value.

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
        """Set economic stress configuration value (writes to DB).

        Args:
            key: Configuration key
            value: New value
            value_type: Type ('int', 'float')
            description: Description (only used for new keys)
            changed_by: Actor making change (for audit trail)

        Returns:
            True if value was set as requested; False if rejected
        """
        return self.parent.set(key, value, value_type, description, changed_by)

    def get_yield_curve_stress(self) -> dict[str, int]:
        """Get yield curve inversion stress scores.

        Returns:
            {
                "severe": 40,      # Severe inversion
                "moderate": 25,    # Moderate inversion
                "flat": 15,        # Flat curve
            }

        Raises:
            ValueError if any critical config keys are missing (requires explicit configuration)
        """
        severe = self.get("econ_stress_curve_inverted_severe")
        moderate = self.get("econ_stress_curve_inverted_moderate")
        flat = self.get("econ_stress_curve_flat")

        missing = []
        if severe is None:
            missing.append("econ_stress_curve_inverted_severe")
        if moderate is None:
            missing.append("econ_stress_curve_inverted_moderate")
        if flat is None:
            missing.append("econ_stress_curve_flat")

        if missing:
            raise ValueError(
                f"Economic stress config missing critical risk thresholds: {missing}. "
                "Cannot proceed with incomplete risk configuration. "
                "Ensure all stress_level thresholds are explicitly configured in database."
            )

        return {
            "severe": cast(int, severe),
            "moderate": cast(int, moderate),
            "flat": cast(int, flat),
        }

    def get_hy_spread_stress(self) -> dict[str, int]:
        """Get high-yield spread stress scores.

        Returns:
            {
                "severe": 35,      # Severe widening (>600 bps)
                "elevated": 20,    # Elevated spread (400-600 bps)
                "widening": 10,    # Widening trend
            }

        Raises:
            ValueError if any critical config keys are missing
        """
        severe = self.get("econ_stress_hy_spread_severe")
        elevated = self.get("econ_stress_hy_spread_elevated")
        widening = self.get("econ_stress_hy_widening")

        missing = []
        if severe is None:
            missing.append("econ_stress_hy_spread_severe")
        if elevated is None:
            missing.append("econ_stress_hy_spread_elevated")
        if widening is None:
            missing.append("econ_stress_hy_widening")

        if missing:
            raise ValueError(
                f"High-yield spread stress config incomplete: {missing}. "
                "Cannot proceed without explicit risk thresholds configured."
            )

        return {
            "severe": cast(int, severe),
            "elevated": cast(int, elevated),
            "widening": cast(int, widening),
        }

    def get_claims_stress(self) -> dict[str, int]:
        """Get jobless claims stress scores.

        Returns:
            {
                "severe": 30,      # Severe spike (>400k initial claims)
                "elevated": 15,    # Elevated claims (350-400k)
            }

        Raises:
            ValueError if any critical config keys are missing
        """
        severe = self.get("econ_stress_claims_severe")
        elevated = self.get("econ_stress_claims_elevated")

        missing = []
        if severe is None:
            missing.append("econ_stress_claims_severe")
        if elevated is None:
            missing.append("econ_stress_claims_elevated")

        if missing:
            raise ValueError(
                f"Jobless claims stress config incomplete: {missing}. "
                "Cannot proceed without explicit risk thresholds configured."
            )

        return {
            "severe": cast(int, severe),
            "elevated": cast(int, elevated),
        }

    def get_financial_stress(self) -> dict[str, int]:
        """Get financial stress scores.

        Returns:
            {
                "severe": 40,      # Severe financial stress (>1.5 std dev)
                "elevated": 20,    # Elevated stress (>0.8 std dev)
            }

        Raises:
            ValueError if any critical config keys are missing
        """
        severe = self.get("econ_stress_financial_severe")
        elevated = self.get("econ_stress_financial_elevated")

        missing = []
        if severe is None:
            missing.append("econ_stress_financial_severe")
        if elevated is None:
            missing.append("econ_stress_financial_elevated")

        if missing:
            raise ValueError(
                f"Financial stress config incomplete: {missing}. "
                "Cannot proceed without explicit risk thresholds configured."
            )

        return {
            "severe": cast(int, severe),
            "elevated": cast(int, elevated),
        }

    def get_regime_thresholds(self) -> dict[str, int]:
        """Get economic regime severity thresholds.

        Returns:
            {
                "moderate_threshold": 30,   # Stress level for moderate penalty (4 pts)
                "severe_threshold": 60,    # Stress level for severe penalty (7 pts)
            }

        Raises:
            ValueError if any critical config keys are missing
        """
        moderate = self.get("econ_stress_moderate_threshold")
        severe = self.get("econ_stress_severe_threshold")

        missing = []
        if moderate is None:
            missing.append("econ_stress_moderate_threshold")
        if severe is None:
            missing.append("econ_stress_severe_threshold")

        if missing:
            raise ValueError(
                f"Economic regime threshold config incomplete: {missing}. "
                "Cannot proceed without explicit thresholds configured."
            )

        return {
            "moderate_threshold": cast(int, moderate),
            "severe_threshold": cast(int, severe),
        }

    def get_severe_exposure_cap_pct(self) -> float:
        """Get exposure cap percentage at severe economic stress.

        CRITICAL: Must be explicitly configured. Severe stress (score >= 60) caps portfolio exposure.

        Returns:
            Exposure cap as percentage (0-100)

        Raises:
            RuntimeError: If 'econ_stress_severe_cap_pct' config key is missing (fail-fast)
        """
        value = self.get("econ_stress_severe_cap_pct")
        if value is None:
            raise RuntimeError(
                "[ECON_STRESS_CONFIG] CRITICAL: econ_stress_severe_cap_pct config key missing. "
                "Severe stress exposure cap must be explicitly configured for risk management. "
                "Set 'econ_stress_severe_cap_pct' in algo_config table to proceed. "
                "Check database: SELECT * FROM algo_config WHERE key = 'econ_stress_severe_cap_pct';"
            )
        cap_pct = float(value)
        if not (0 <= cap_pct <= 100):
            raise RuntimeError(
                f"[ECON_STRESS_CONFIG] CRITICAL: econ_stress_severe_cap_pct must be 0-100% (got {cap_pct}). "
                f"Update algo_config: UPDATE algo_config SET value = '40.0' WHERE key = 'econ_stress_severe_cap_pct';"
            )
        return cap_pct

    def get_all_stress_scores(self) -> dict[str, Any]:
        """Get all economic stress configuration for debugging/logging.

        Returns:
            {
                "yield_curve": {...},
                "hy_spreads": {...},
                "claims": {...},
                "financial": {...},
                "regime_thresholds": {...},
                "severe_exposure_cap_pct": 40.0,
            }
        """
        return {
            "yield_curve": self.get_yield_curve_stress(),
            "hy_spreads": self.get_hy_spread_stress(),
            "claims": self.get_claims_stress(),
            "financial": self.get_financial_stress(),
            "regime_thresholds": self.get_regime_thresholds(),
            "severe_exposure_cap_pct": self.get_severe_exposure_cap_pct(),
        }

    def __repr__(self) -> str:
        return f"<EconomicStressConfig {len(self.get_all_stress_scores())} stress components>"
