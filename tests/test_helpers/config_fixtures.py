#!/usr/bin/env python3
"""
Test Configuration Fixtures - Template configs for different market scenarios.

This module provides reusable mock configuration objects for unit and integration tests.
Each fixture represents a realistic market condition (bull, correction, crisis, etc.)
so tests can verify behavior across different trading regimes without mocking get_config().
"""

from copy import deepcopy
from typing import Any, Dict


# Base configuration with all required keys
BASE_CONFIG: dict[str, Any] = {
    # Risk Management
    "base_risk_pct": 0.75,
    "max_position_size_pct": 8.0,
    "max_positions": 12,
    "max_concentration_pct": 50.0,
    # Drawdown Defense
    "halt_drawdown_pct": 20.0,
    "risk_reduction_at_minus_5": 0.75,
    "risk_reduction_at_minus_10": 0.5,
    "risk_reduction_at_minus_15": 0.25,
    "risk_reduction_at_minus_20": 0.0,
    # Filter Thresholds
    "min_completeness_score": 70,
    "min_stock_price": 5.0,
    "min_signal_quality_score": 60,
    "min_volume_ma_50d": 300000,
    "min_avg_daily_dollar_volume": 500000,
    "require_stock_stage_2": True,
    "max_stop_distance_pct": 12.0,
    "max_positions_per_sector": 10,
    "max_positions_per_industry": 8,
    "min_swing_score": 55.0,
    "min_swing_grade": "",
    "max_total_invested_pct": 95.0,
    # Market Conditions
    "max_distribution_days": 4,
    "require_stage_2_market": False,
    "vix_max_threshold": 35.0,
    "vix_alert_threshold": 30.0,
    "vix_caution_threshold": 25.0,
    "vix_caution_risk_reduction": 0.75,
    # Market Exposure Engine (H12)
    "market_exposure_veto1_breadth_pct": 30,
    "market_exposure_veto1_cap_pct": 25.0,
    "market_exposure_veto2_vix_threshold": 40.0,
    "market_exposure_veto2_cap_pct": 30.0,
    "market_exposure_veto3_distribution_days_threshold": 6,
    "market_exposure_veto3_cap_pct": 35.0,
    "market_exposure_veto4_cap_pct": 40.0,
    "market_exposure_veto5_credit_spread_threshold": 8.5,
    "market_exposure_veto5_cap_pct": 30.0,
    # Economic Regime Stress Scores
    "econ_stress_curve_inverted_severe": 35.0,
    "econ_stress_curve_inverted_moderate": 20.0,
    "econ_stress_curve_flat": 8.0,
    "econ_stress_hy_spread_severe": 35.0,
    "econ_stress_hy_spread_elevated": 20.0,
    "econ_stress_hy_widening": 15.0,
    "econ_stress_claims_severe": 30.0,
    "econ_stress_claims_elevated": 15.0,
    "econ_stress_financial_severe": 25.0,
    "econ_stress_financial_elevated": 12.0,
    "econ_stress_moderate_threshold": 40,
    "econ_stress_severe_threshold": 60,
    "econ_stress_severe_cap_pct": 40.0,
    "put_call_bullish_threshold": 0.8,
    "put_call_fearful_threshold": 1.0,
    "upvol_good_threshold": 60.0,
    "upvol_caution_threshold": 50.0,
    "breadth_good_threshold": 50,
    "breadth_caution_threshold": 0,
    "yield_curve_good_threshold": 0.5,
    "beta_warning_threshold": 1.2,
    "beta_caution_threshold": 0.8,
    # Entry Rules (Minervini)
    "require_sma50_above_sma200": True,
    "min_percent_from_52w_low": 0.0,
    "max_percent_from_52w_high": 25.0,
    "min_trend_template_score": 6,
    # Entry Quality Gates
    "max_signal_age_days": 3,
    "min_close_quality_pct": 40.0,
    "min_breakout_volume_ratio": 1.25,
    "require_weekly_stage_2": False,
    "min_rs_line_slope_days": 10,
    "max_rs_pct_from_60d_high": 15.0,
    "rs_slope_gate_enabled": False,
    "volume_decay_gate_enabled": False,
    # Exit Rules
    "require_target_pullback": False,
    "t1_target_r_multiple": 1.5,
    "t2_target_r_multiple": 3.0,
    "t3_target_r_multiple": 4.0,
    # Imported Position Defaults
    "imported_position_default_stop_loss_pct": 5.0,
    "imported_position_default_target_1_pct": 5.0,
    "imported_position_default_target_2_pct": 10.0,
    "imported_position_default_target_3_pct": 15.0,
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
    # Drawdown Re-engagement
    "re_engage_recovery_pct": 8.0,
    "re_engage_min_days": 5,
    "require_ftd_to_re_engage": True,
    # Circuit Breaker Thresholds
    "max_daily_loss_pct": 2.0,
    "max_consecutive_losses": 3,
    "min_win_rate_pct": 40.0,
    "max_total_risk_pct": 4.0,
    "min_risk_pct_floor": 0.10,
    "max_weekly_loss_pct": 5.0,
    "max_data_staleness_days": 3,
    "daily_profit_cap_pct": 2.0,
    "sector_drawdown_halt_pct": -12.0,
    # Position Monitoring & Re-entry
    "position_halt_flag_count": 2,
    "max_reentries_per_name": 2,
    "min_days_before_reentry_same_symbol": 5,
    # Economic Calendar
    "halt_entries_before_major_release_minutes": 60,
    # Earnings Blackout
    "earnings_blackout_days_before": 7,
    "earnings_blackout_days_after": 3,
    # Other Thresholds
    "min_price_history_days": 200,
    "min_daily_volume_shares": 500000,
    "max_spread_pct": 0.5,
    "min_market_cap_millions": 300.0,
    "min_float_millions": 50.0,
    "max_short_interest_pct": 30.0,
    # Advanced Filters
    "block_days_before_earnings": 5,
    "max_extension_above_50ma_pct": 15.0,
    "strong_sector_top_n": 5,
    "require_strong_sector": False,
    "min_adv_shares": 50000,
    "min_adv_dollars": 500000,
    "min_order_size_dollars": 100.0,
    "phase1_min_coverage_pct": 75,
    "phase1_min_symbol_count": 8000,
    # Swing Trader Score Weights
    "swing_weight_setup": 25,
    "swing_weight_trend": 20,
    "swing_weight_momentum": 20,
    "swing_weight_volume": 12,
    "swing_weight_fundamentals": 10,
    "swing_weight_sector": 8,
    "swing_weight_multi_timeframe": 5,
    "swing_min_trend_score": 5,
    "swing_min_industry_rank": 100,
    "swing_days_to_earnings_block": 5,
    "swing_grade_threshold_aplus": 85,
    "swing_grade_threshold_a": 75,
    "swing_grade_threshold_b": 65,
    "swing_grade_threshold_c": 55,
    "swing_grade_threshold_d": 45,
    "advanced_filters_grade_threshold_aplus": 90,
    "advanced_filters_grade_threshold_a": 80,
    "advanced_filters_grade_threshold_b": 70,
    "advanced_filters_grade_threshold_c": 60,
    "advanced_filters_grade_threshold_d": 50,
    # Risk Metrics Calculation
    "var_percentile": 5,
    "cvar_percentile": 5,
    "stressed_var_percentile": 10,
    "dashboard_grade_threshold_a": 80,
    "dashboard_grade_threshold_b": 60,
    "dashboard_grade_threshold_c": 40,
    # Dashboard Configuration
    "dashboard_min_quality_threshold": 40.0,
    "dashboard_metrics_max_age_minutes": 120,
    # Execution Mode
    "execution_mode": "paper",
    "alpaca_paper_trading": False,
    "max_trades_per_day": 5,
    "default_portfolio_value": 100000.0,
    # Feature Flags
    "enable_algo": True,
    "enable_backtesting": False,
    "verbose_logging": True,
    # Network Configuration
    "api_request_timeout_seconds": 5,
    "db_connection_timeout_seconds": 15,
    # Failsafe Configuration
    "failsafe_ecs_timeout_sec": 180,
    "failsafe_grace_period_minutes": 240,
}


def bull_market_config() -> dict[str, Any]:
    """Configuration for aggressive bull market trading (high confidence, high risk).

    Conditions:
    - VIX low (<20)
    - SPY above 30-week MA
    - Strong breadth, rising participation
    - High risk tolerance for larger swings
    """
    config = deepcopy(BASE_CONFIG)
    config.update(
        {
            "base_risk_pct": 1.0,  # Increase risk in bull market
            "max_positions": 15,  # Increase position count
            "max_total_invested_pct": 98.0,  # Deploy more capital
            "vix_caution_threshold": 22.0,  # Raise caution threshold
            "vix_caution_risk_reduction": 0.9,  # Less reduction when VIX rises
            "require_stage_2_market": False,  # Less strict market requirement
            "min_swing_score": 50.0,  # Lower quality bar
            "max_distribution_days": 5,  # Tolerate more distribution
            "swing_weight_momentum": 25,  # Weight momentum more in bull
        }
    )
    return config


def correction_config() -> dict[str, Any]:
    """Configuration for correction/consolidation (cautious, balanced).

    Conditions:
    - VIX moderate (20-30)
    - SPY near/below 30-week MA
    - Mixed breadth
    - Balanced risk/reward
    """
    config = deepcopy(BASE_CONFIG)
    config.update(
        {
            "base_risk_pct": 0.50,  # Reduce risk
            "max_positions": 8,  # Fewer concurrent positions
            "max_total_invested_pct": 70.0,  # Deploy less capital
            "vix_caution_threshold": 25.0,  # Standard caution
            "require_stage_2_market": True,  # Stricter market requirement
            "min_swing_score": 65.0,  # Higher quality bar
            "max_distribution_days": 3,  # Low distribution tolerance
            "max_consecutive_losses": 2,  # Tighter loss limit
        }
    )
    return config


def crisis_config() -> dict[str, Any]:
    """Configuration for crisis/bear market (very cautious, capital preservation).

    Conditions:
    - VIX high (>35)
    - SPY below 30-week MA with downtrend
    - Falling breadth
    - Risk-off mode
    """
    config = deepcopy(BASE_CONFIG)
    config.update(
        {
            "base_risk_pct": 0.25,  # Minimal risk
            "max_positions": 3,  # Very few positions
            "max_total_invested_pct": 30.0,  # Minimal deployment
            "vix_max_threshold": 45.0,  # Higher halt threshold (allow some activity)
            "vix_caution_threshold": 30.0,  # Low caution threshold
            "require_stage_2_market": True,  # Strict market requirement
            "min_swing_score": 75.0,  # Very high quality bar
            "max_distribution_days": 2,  # Very low distribution tolerance
            "halt_drawdown_pct": 10.0,  # Aggressive halt level
            "max_daily_loss_pct": 1.0,  # Tight daily loss limit
            "max_weekly_loss_pct": 2.0,  # Tight weekly loss limit
            "econ_stress_severe_cap_pct": 20.0,  # Low exposure cap in stress
        }
    )
    return config


def minimal_config() -> dict[str, Any]:
    """Minimal configuration with only essential keys for unit tests."""
    return {
        "base_risk_pct": 0.75,
        "max_position_size_pct": 8.0,
        "max_positions": 12,
        "vix_max_threshold": 35.0,
        "vix_alert_threshold": 30.0,
        "execution_mode": "paper",
        "enable_algo": True,
    }


def strict_risk_config() -> dict[str, Any]:
    """Configuration with very tight risk limits for testing circuit breakers."""
    config = deepcopy(BASE_CONFIG)
    config.update(
        {
            "max_daily_loss_pct": 1.0,
            "max_weekly_loss_pct": 2.0,
            "max_total_risk_pct": 2.0,
            "halt_drawdown_pct": 10.0,
            "max_consecutive_losses": 2,
            "min_win_rate_pct": 50.0,
            "daily_profit_cap_pct": 1.0,
        }
    )
    return config


def relaxed_risk_config() -> dict[str, Any]:
    """Configuration with relaxed risk limits for testing edge cases."""
    config = deepcopy(BASE_CONFIG)
    config.update(
        {
            "max_daily_loss_pct": 5.0,
            "max_weekly_loss_pct": 10.0,
            "max_total_risk_pct": 10.0,
            "halt_drawdown_pct": 30.0,
            "max_consecutive_losses": 5,
            "min_win_rate_pct": 30.0,
            "daily_profit_cap_pct": 5.0,
        }
    )
    return config


def sandbox_config() -> dict[str, Any]:
    """Configuration for sandbox/testing with no actual trading."""
    config = deepcopy(BASE_CONFIG)
    config.update(
        {
            "execution_mode": "review",  # No actual orders
            "alpaca_paper_trading": True,  # Use paper account if we do connect
            "enable_algo": True,
            "verbose_logging": True,
        }
    )
    return config


def merge_configs(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge configuration overrides into a base config.

    Args:
        base: Base configuration dictionary
        overrides: Dictionary of keys to override

    Returns:
        New configuration dict with overrides applied
    """
    config = deepcopy(base)
    config.update(overrides)
    return config


def validate_config(config: dict[str, Any], required_keys: list | None = None) -> bool:
    """Validate that config has all required keys.

    Args:
        config: Configuration dictionary to validate
        required_keys: List of required keys (defaults to BASE_CONFIG keys)

    Returns:
        True if valid, raises ValueError otherwise
    """
    if required_keys is None:
        required_keys = list(BASE_CONFIG.keys())

    missing_keys = [key for key in required_keys if key not in config]
    if missing_keys:
        raise ValueError(f"Configuration missing required keys: {missing_keys}")

    return True
