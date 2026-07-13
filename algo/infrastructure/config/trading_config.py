#!/usr/bin/env python3
"""Trading configuration (entry/exit rules, stock filters, signal quality).

Manages all trading-related parameters independently from risk and execution.
Trading team can tune signal gates and stock filters without coordinating with risk.

Categories:
- Filter Thresholds (stock quality gates, liquidity, price ranges)
- Entry Rules (technical requirements: Minervini, MA alignment, etc.)
- Entry Quality Gates (signal age, volume, RS line, etc.)
- Exit Rules (profit targets, stop loss, hold time)
- Position Monitoring & Re-entry
- Advanced Filters (sector/industry concentration, extensions)

Delegates all DB access to parent AlgoConfig._config dict.
Provides logical grouping methods for trading team convenience.
"""

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from algo.infrastructure.config import AlgoConfig

logger = logging.getLogger(__name__)


class TradingConfig:
    """Configuration for trading rules, filters, and entry/exit logic."""

    def __init__(self, parent: "AlgoConfig") -> None:
        """Initialize TradingConfig with parent AlgoConfig.

        Args:
            parent: Parent AlgoConfig instance (holds _config dict and DB connection)
        """
        self.parent = parent

    def get(self, key: str, default: Any = None) -> Any:
        """Get trading configuration value.

        Delegates to parent AlgoConfig.get(), which handles:
        - Type validation via VALIDATION_SCHEMA
        - Fallback to defaults
        - Fail-closed values for critical thresholds

        Args:
            key: Configuration key (e.g., "min_signal_quality_score")
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
        """Set trading configuration value (writes to DB).

        For critical safety thresholds (e.g., min_signal_quality_score):
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

    def get_stock_filter_config(self) -> dict[str, Any]:
        return {
            "min_stock_price": self.get("min_stock_price"),
            "min_volume_ma_50d": self.get("min_volume_ma_50d"),
            "min_avg_daily_dollar_volume": self.get("min_avg_daily_dollar_volume"),
            "min_completeness_score": self.get("min_completeness_score"),
            "max_spread_pct": self.get("max_spread_pct"),
            "min_market_cap_millions": self.get("min_market_cap_millions"),
            "min_float_millions": self.get("min_float_millions"),
            "max_short_interest_pct": self.get("max_short_interest_pct"),
            "min_daily_volume_shares": self.get("min_daily_volume_shares"),
            "min_price_history_days": self.get("min_price_history_days"),
        }

    def get_entry_rules_config(self) -> dict[str, Any]:
        return {
            "require_sma50_above_sma200": self.get("require_sma50_above_sma200"),
            "min_percent_from_52w_low": self.get("min_percent_from_52w_low"),
            "max_percent_from_52w_high": self.get("max_percent_from_52w_high"),
            "min_trend_template_score": self.get("min_trend_template_score"),
            "require_stock_stage_2": self.get("require_stock_stage_2"),
            "require_weekly_stage_2": self.get("require_weekly_stage_2"),
        }

    def get_exit_rules_config(self) -> dict[str, Any]:
        """Get exit rules (profit targets, stop loss, hold time, chandelier).

        Returns:
            {
                "require_target_pullback": False,
                "t1_target_r_multiple": 1.5,
                "t2_target_r_multiple": 3.0,
                "t3_target_r_multiple": 4.0,
                "min_hold_days": 1,
                "max_hold_days": 20,
                "exit_on_distribution_day": True,
                "exit_on_rs_line_break_50dma": True,
                "exit_on_td_sequential": True,
                "use_chandelier_trail": True,
                "switch_to_21ema_after_days": 10,
                "eight_week_rule_threshold_pct": 20.0,
                "eight_week_rule_window_days": 21,
                "chandelier_atr_mult": 3.0,
                "move_be_at_r": 1.0,
                "max_stop_distance_pct": 12.0,
            }
        """
        return {
            "require_target_pullback": self.get("require_target_pullback"),
            "t1_target_r_multiple": self.get("t1_target_r_multiple"),
            "t2_target_r_multiple": self.get("t2_target_r_multiple"),
            "t3_target_r_multiple": self.get("t3_target_r_multiple"),
            "min_hold_days": self.get("min_hold_days"),
            "max_hold_days": self.get("max_hold_days"),
            "exit_on_distribution_day": self.get("exit_on_distribution_day"),
            "exit_on_rs_line_break_50dma": self.get("exit_on_rs_line_break_50dma"),
            "exit_on_td_sequential": self.get("exit_on_td_sequential"),
            "use_chandelier_trail": self.get("use_chandelier_trail"),
            "switch_to_21ema_after_days": self.get("switch_to_21ema_after_days"),
            "eight_week_rule_threshold_pct": self.get("eight_week_rule_threshold_pct"),
            "eight_week_rule_window_days": self.get("eight_week_rule_window_days"),
            "chandelier_atr_mult": self.get("chandelier_atr_mult"),
            "move_be_at_r": self.get("move_be_at_r"),
            "max_stop_distance_pct": self.get("max_stop_distance_pct"),
        }
