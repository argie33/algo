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
- Swing Trader Scoring (signal scoring weights and thresholds)

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
        return self.parent.set(key, value, value_type, description, changed_by)  # type: ignore[no-any-return]

    def get_stock_filter_config(self) -> dict[str, Any]:
        """Get all stock quality gates (liquidity, price, volume).

        Returns:
            {
                "min_stock_price": 5.0,
                "min_volume_ma_50d": 300000,
                "min_avg_daily_dollar_volume": 500000.0,
                "min_completeness_score": 70,
                "max_spread_pct": 0.5,
                "min_market_cap_millions": 300.0,
                "min_float_millions": 50.0,
                "max_short_interest_pct": 30.0,
                "min_daily_volume_shares": 500000,
                "min_price_history_days": 200,
            }
        """
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

    def get_signal_quality_config(self) -> dict[str, Any]:
        """Get signal quality gates (scoring and acceptance thresholds).

        Returns:
            {
                "min_signal_quality_score": 60,
                "signal_weak_threshold": 40.0,
                "signal_medium_threshold": 60.0,
                "signal_strong_threshold": 80.0,
                "max_signal_age_days": 3,
            }
        """
        return {
            "min_signal_quality_score": self.get("min_signal_quality_score"),
            "signal_weak_threshold": self.get("signal_weak_threshold"),
            "signal_medium_threshold": self.get("signal_medium_threshold"),
            "signal_strong_threshold": self.get("signal_strong_threshold"),
            "max_signal_age_days": self.get("max_signal_age_days"),
        }

    def get_entry_rules_config(self) -> dict[str, Any]:
        """Get Minervini entry technical requirements.

        Returns:
            {
                "require_sma50_above_sma200": True,
                "min_percent_from_52w_low": 0.0,
                "max_percent_from_52w_high": 25.0,
                "min_trend_template_score": 6,
                "require_stock_stage_2": True,
                "require_weekly_stage_2": False,
            }
        """
        return {
            "require_sma50_above_sma200": self.get("require_sma50_above_sma200"),
            "min_percent_from_52w_low": self.get("min_percent_from_52w_low"),
            "max_percent_from_52w_high": self.get("max_percent_from_52w_high"),
            "min_trend_template_score": self.get("min_trend_template_score"),
            "require_stock_stage_2": self.get("require_stock_stage_2"),
            "require_weekly_stage_2": self.get("require_weekly_stage_2"),
        }

    def get_entry_quality_gates_config(self) -> dict[str, Any]:
        """Get entry quality gates (volume, close quality, RS line, etc.).

        Returns:
            {
                "min_close_quality_pct": 40.0,
                "min_breakout_volume_ratio": 1.25,
                "min_rs_line_slope_days": 10,
                "max_rs_pct_from_60d_high": 15.0,
                "rs_slope_gate_enabled": False,
                "volume_decay_gate_enabled": False,
            }
        """
        return {
            "min_close_quality_pct": self.get("min_close_quality_pct"),
            "min_breakout_volume_ratio": self.get("min_breakout_volume_ratio"),
            "min_rs_line_slope_days": self.get("min_rs_line_slope_days"),
            "max_rs_pct_from_60d_high": self.get("max_rs_pct_from_60d_high"),
            "rs_slope_gate_enabled": self.get("rs_slope_gate_enabled"),
            "volume_decay_gate_enabled": self.get("volume_decay_gate_enabled"),
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

    def get_position_reentry_config(self) -> dict[str, Any]:
        """Get position monitoring and re-entry thresholds.

        Returns:
            {
                "position_halt_flag_count": 2,
                "max_reentries_per_name": 2,
                "min_days_before_reentry_same_symbol": 5,
            }
        """
        return {
            "position_halt_flag_count": self.get("position_halt_flag_count"),
            "max_reentries_per_name": self.get("max_reentries_per_name"),
            "min_days_before_reentry_same_symbol": self.get("min_days_before_reentry_same_symbol"),
        }

    def get_advanced_filters_config(self) -> dict[str, Any]:
        """Get advanced trading filters (sector, extensions, ADV).

        Returns:
            {
                "max_extension_above_50ma_pct": 15.0,
                "strong_sector_top_n": 5,
                "require_strong_sector": False,
                "min_adv_shares": 50000,
                "min_adv_dollars": 500000.0,
                "min_order_size_dollars": 100.0,
                "max_positions_per_sector": 10,
                "max_positions_per_industry": 8,
            }
        """
        return {
            "max_extension_above_50ma_pct": self.get("max_extension_above_50ma_pct"),
            "strong_sector_top_n": self.get("strong_sector_top_n"),
            "require_strong_sector": self.get("require_strong_sector"),
            "min_adv_shares": self.get("min_adv_shares"),
            "min_adv_dollars": self.get("min_adv_dollars"),
            "min_order_size_dollars": self.get("min_order_size_dollars"),
            "max_positions_per_sector": self.get("max_positions_per_sector"),
            "max_positions_per_industry": self.get("max_positions_per_industry"),
        }

    def get_swing_score_weights(self) -> dict[str, int]:
        """Get swing trader score component weights (must sum to 100).

        Returns:
            {
                "swing_weight_setup": 25,
                "swing_weight_trend": 20,
                "swing_weight_momentum": 20,
                "swing_weight_volume": 12,
                "swing_weight_fundamentals": 10,
                "swing_weight_sector": 8,
                "swing_weight_multi_timeframe": 5,
            }
        """
        return {
            "swing_weight_setup": self.get("swing_weight_setup"),
            "swing_weight_trend": self.get("swing_weight_trend"),
            "swing_weight_momentum": self.get("swing_weight_momentum"),
            "swing_weight_volume": self.get("swing_weight_volume"),
            "swing_weight_fundamentals": self.get("swing_weight_fundamentals"),
            "swing_weight_sector": self.get("swing_weight_sector"),
            "swing_weight_multi_timeframe": self.get("swing_weight_multi_timeframe"),
        }

    def get_swing_score_thresholds(self) -> dict[str, Any]:
        """Get swing trader score grading thresholds and gates.

        Returns:
            {
                "swing_min_trend_score": 5,
                "swing_min_industry_rank": 100,
                "swing_days_to_earnings_block": 5,
                "swing_grade_threshold_aplus": 85,
                "swing_grade_threshold_a": 75,
                "swing_grade_threshold_b": 65,
                "swing_grade_threshold_c": 55,
                "swing_grade_threshold_d": 45,
                "min_swing_score": 55.0,
                "min_swing_grade": "",
            }
        """
        return {
            "swing_min_trend_score": self.get("swing_min_trend_score"),
            "swing_min_industry_rank": self.get("swing_min_industry_rank"),
            "swing_days_to_earnings_block": self.get("swing_days_to_earnings_block"),
            "swing_grade_threshold_aplus": self.get("swing_grade_threshold_aplus"),
            "swing_grade_threshold_a": self.get("swing_grade_threshold_a"),
            "swing_grade_threshold_b": self.get("swing_grade_threshold_b"),
            "swing_grade_threshold_c": self.get("swing_grade_threshold_c"),
            "swing_grade_threshold_d": self.get("swing_grade_threshold_d"),
            "min_swing_score": self.get("min_swing_score"),
            "min_swing_grade": self.get("min_swing_grade"),
        }

    def get_advanced_filters_grades(self) -> dict[str, int]:
        """Get advanced filters signal grading thresholds.

        Returns:
            {
                "advanced_filters_grade_threshold_aplus": 90,
                "advanced_filters_grade_threshold_a": 80,
                "advanced_filters_grade_threshold_b": 70,
                "advanced_filters_grade_threshold_c": 60,
                "advanced_filters_grade_threshold_d": 50,
            }
        """
        return {
            "advanced_filters_grade_threshold_aplus": self.get("advanced_filters_grade_threshold_aplus"),
            "advanced_filters_grade_threshold_a": self.get("advanced_filters_grade_threshold_a"),
            "advanced_filters_grade_threshold_b": self.get("advanced_filters_grade_threshold_b"),
            "advanced_filters_grade_threshold_c": self.get("advanced_filters_grade_threshold_c"),
            "advanced_filters_grade_threshold_d": self.get("advanced_filters_grade_threshold_d"),
        }

    def get_earnings_blackout_config(self) -> dict[str, Any]:
        """Get earnings blackout and economic calendar settings.

        Returns:
            {
                "earnings_blackout_days_before": 7,
                "earnings_blackout_days_after": 3,
                "block_days_before_earnings": 5,
                "halt_entries_before_major_release_minutes": 60,
            }
        """
        return {
            "earnings_blackout_days_before": self.get("earnings_blackout_days_before"),
            "earnings_blackout_days_after": self.get("earnings_blackout_days_after"),
            "block_days_before_earnings": self.get("block_days_before_earnings"),
            "halt_entries_before_major_release_minutes": self.get("halt_entries_before_major_release_minutes"),
        }

    def get_imported_position_defaults(self) -> dict[str, float]:
        """Get default stop/target levels for imported positions (when ATR unavailable).

        Returns:
            {
                "imported_position_default_stop_loss_pct": 5.0,
                "imported_position_default_target_1_pct": 5.0,
                "imported_position_default_target_2_pct": 10.0,
                "imported_position_default_target_3_pct": 15.0,
            }
        """
        return {
            "imported_position_default_stop_loss_pct": self.get("imported_position_default_stop_loss_pct"),
            "imported_position_default_target_1_pct": self.get("imported_position_default_target_1_pct"),
            "imported_position_default_target_2_pct": self.get("imported_position_default_target_2_pct"),
            "imported_position_default_target_3_pct": self.get("imported_position_default_target_3_pct"),
        }
