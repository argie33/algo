#!/usr/bin/env python3
"""Configuration validation schema for AlgoConfig.

Defines all configuration parameters with their validation rules:
- Type: float, int, bool, string
- Min/max bounds for numeric types
- Critical flag: True if field must not be zero/None
- Fail-closed value: default if invalid value provided by admin

This schema is the single source of truth for configuration validation across the system.
"""

# Format: key -> (type, min_value, max_value, is_critical, fail_closed_value)
# is_critical: if True, zero/None values are not allowed (safety gates)
# fail_closed_value: value to use if admin tries to set an invalid value (prevents trading)
VALIDATION_SCHEMA = {
    # Risk Management (all must remain positive)
    "base_risk_pct": ("float", 0.01, 5.0, True, 0.5),  # Fail-closed to 0.5%
    "max_position_size_pct": ("float", 0.1, 15.0, True, 5.0),
    "max_positions": ("int", 1, 100, False, 15),
    "max_concentration_pct": ("float", 0.0, 100.0, False, 50.0),
    # Drawdown Defense (halt_drawdown_pct must be negative)
    "halt_drawdown_pct": (
        "float",
        -100.0,
        -5.0,
        True,
        -20.0,
    ),  # MUST be negative; fail-closed to -20%
    "risk_reduction_at_minus_5": ("float", 0.0, 1.0, False, 0.75),
    "risk_reduction_at_minus_10": ("float", 0.0, 1.0, False, 0.5),
    "risk_reduction_at_minus_15": ("float", 0.0, 1.0, False, 0.25),
    "risk_reduction_at_minus_20": ("float", 0.0, 1.0, False, 0.0),
    # Filter Thresholds (all critical hard-gates; must not be zero)
    "min_completeness_score": ("int", 1, 100, True, 70),  # Fail-closed to 70%
    "min_stock_price": ("float", 0.1, 1000.0, False, 5.0),
    "min_signal_quality_score": ("int", 1, 100, True, 60),  # Fail-closed to 60
    "min_volume_ma_50d": ("int", 1, 10000000, True, 300000),
    "min_avg_daily_dollar_volume": ("float", 1.0, 100000000.0, True, 500000.0),
    "require_stock_stage_2": ("bool", None, None, False, None),
    "max_stop_distance_pct": ("float", 0.1, 50.0, False, 12.0),
    "max_positions_per_sector": ("int", 1, 100, False, 10),
    "max_positions_per_industry": ("int", 1, 100, False, 8),
    "max_total_invested_pct": ("float", 50.0, 100.0, False, 95.0),
    # Market Conditions
    "max_distribution_days": ("int", 0, 30, False, 4),
    "require_stage_2_market": ("bool", None, None, False, None),
    "vix_max_threshold": ("float", 20.0, 100.0, True, 35.0),  # Critical halt threshold
    "vix_alert_threshold": ("float", 20.0, 100.0, False, 30.0),
    "vix_caution_threshold": ("float", 20.0, 100.0, False, 25.0),
    "vix_caution_risk_reduction": ("float", 0.0, 1.0, False, 0.75),
    # Market Exposure Engine — Veto Thresholds
    "market_exposure_veto1_breadth_pct": ("int", 0, 100, False, 30),
    "market_exposure_veto1_cap_pct": ("float", 0.0, 100.0, False, 25.0),
    "market_exposure_veto2_vix_threshold": ("float", 20.0, 100.0, False, 40.0),
    "market_exposure_veto2_cap_pct": ("float", 0.0, 100.0, False, 30.0),
    "market_exposure_veto3_distribution_days_threshold": ("int", 1, 30, False, 6),
    "market_exposure_veto3_cap_pct": ("float", 0.0, 100.0, False, 35.0),
    "market_exposure_veto4_cap_pct": ("float", 0.0, 100.0, False, 40.0),
    "market_exposure_veto5_credit_spread_threshold": ("float", 0.0, 20.0, False, 8.5),
    "market_exposure_veto5_cap_pct": ("float", 0.0, 100.0, False, 30.0),
    # Economic Regime Stress Scores
    "econ_stress_curve_inverted_severe": ("float", 0.0, 100.0, False, 35.0),
    "econ_stress_curve_inverted_moderate": ("float", 0.0, 100.0, False, 20.0),
    "econ_stress_curve_flat": ("float", 0.0, 100.0, False, 8.0),
    "econ_stress_hy_spread_severe": ("float", 0.0, 100.0, False, 35.0),
    "econ_stress_hy_spread_elevated": ("float", 0.0, 100.0, False, 20.0),
    "econ_stress_hy_widening": ("float", 0.0, 100.0, False, 15.0),
    "econ_stress_claims_severe": ("float", 0.0, 100.0, False, 30.0),
    "econ_stress_claims_elevated": ("float", 0.0, 100.0, False, 15.0),
    "econ_stress_financial_severe": ("float", 0.0, 100.0, False, 25.0),
    "econ_stress_financial_elevated": ("float", 0.0, 100.0, False, 12.0),
    "econ_stress_moderate_threshold": ("int", 0, 100, False, 40),
    "econ_stress_severe_threshold": ("int", 0, 100, False, 60),
    "econ_stress_severe_cap_pct": ("float", 0.0, 100.0, False, 40.0),
    "put_call_bullish_threshold": ("float", 0.0, 5.0, False, 0.8),
    "put_call_fearful_threshold": ("float", 0.0, 5.0, False, 1.0),
    "upvol_good_threshold": ("float", 0.0, 100.0, False, 60.0),
    "upvol_caution_threshold": ("float", 0.0, 100.0, False, 50.0),
    "breadth_good_threshold": ("int", -10000, 10000, False, 50),
    "breadth_caution_threshold": ("int", -10000, 10000, False, 0),
    "yield_curve_good_threshold": ("float", -5.0, 5.0, False, 0.5),
    "beta_warning_threshold": ("float", 0.1, 10.0, False, 1.2),
    "beta_caution_threshold": ("float", 0.1, 10.0, False, 0.8),
    # Entry Rules
    "require_sma50_above_sma200": ("bool", None, None, False, None),
    "min_percent_from_52w_low": ("float", 0.0, 100.0, False, 0.0),
    "max_percent_from_52w_high": ("float", 0.0, 100.0, False, 25.0),
    "min_trend_template_score": ("int", 0, 8, False, 6),
    # Entry Quality Gates
    "max_signal_age_days": ("int", 0, 30, False, 3),
    "min_close_quality_pct": ("float", 0.0, 100.0, False, 40.0),
    "min_breakout_volume_ratio": ("float", 0.5, 10.0, False, 1.25),
    "require_weekly_stage_2": ("bool", None, None, False, None),
    "min_rs_line_slope_days": ("int", 1, 100, False, 10),
    "max_rs_pct_from_60d_high": ("float", 0.0, 100.0, False, 15.0),
    "rs_slope_gate_enabled": ("bool", None, None, False, None),
    "volume_decay_gate_enabled": ("bool", None, None, False, None),
    # Exit Rules
    "require_target_pullback": ("bool", None, None, False, None),
    "t1_target_r_multiple": ("float", 0.5, 10.0, False, 1.5),
    "t2_target_r_multiple": ("float", 0.5, 10.0, False, 3.0),
    "t3_target_r_multiple": ("float", 0.5, 10.0, False, 4.0),
    # Imported Position Defaults
    "imported_position_default_stop_loss_pct": ("float", 0.1, 50.0, False, 5.0),
    "imported_position_default_target_1_pct": ("float", 0.1, 50.0, False, 5.0),
    "imported_position_default_target_2_pct": ("float", 0.1, 50.0, False, 10.0),
    "imported_position_default_target_3_pct": ("float", 0.1, 50.0, False, 15.0),
    "min_hold_days": ("int", 0, 365, False, 1),
    "max_hold_days": ("int", 1, 365, False, 20),
    "exit_on_distribution_day": ("bool", None, None, False, None),
    "exit_on_rs_line_break_50dma": ("bool", None, None, False, None),
    "exit_on_td_sequential": ("bool", None, None, False, None),
    "use_chandelier_trail": ("bool", None, None, False, None),
    "switch_to_21ema_after_days": ("int", 0, 100, False, 10),
    "eight_week_rule_threshold_pct": ("float", 0.0, 100.0, False, 20.0),
    "eight_week_rule_window_days": ("int", 1, 100, False, 21),
    "chandelier_atr_mult": ("float", 0.5, 10.0, False, 3.0),
    "move_be_at_r": ("float", 0.5, 10.0, False, 1.0),
    # Drawdown Re-engagement
    "re_engage_recovery_pct": ("float", 0.0, 100.0, False, 8.0),
    "re_engage_min_days": ("int", 0, 100, False, 5),
    "require_ftd_to_re_engage": ("bool", None, None, False, None),
    # Circuit Breaker Thresholds
    "max_daily_loss_pct": ("float", 0.1, 50.0, True, 2.0),  # Critical halt
    "max_consecutive_losses": ("int", 1, 100, False, 3),
    "min_win_rate_pct": ("float", 0.0, 100.0, False, 40.0),
    "max_total_risk_pct": ("float", 0.1, 100.0, False, 4.0),
    "min_risk_pct_floor": ("float", 0.01, 10.0, False, 0.10),
    "max_weekly_loss_pct": ("float", 0.1, 100.0, False, 5.0),
    "max_data_staleness_days": ("int", 0, 30, False, 3),
    "daily_profit_cap_pct": ("float", 0.0, 100.0, False, 2.0),
    "sector_drawdown_halt_pct": (
        "float",
        -100.0,
        -1.0,
        True,
        -12.0,
    ),  # Must be negative
    # Position Monitoring & Re-entry
    "position_halt_flag_count": ("int", 1, 100, False, 2),
    "max_reentries_per_name": ("int", 0, 100, False, 2),
    "min_days_before_reentry_same_symbol": ("int", 0, 100, False, 5),
    # Economic Calendar
    "halt_entries_before_major_release_minutes": ("int", 0, 1440, False, 60),
    # Earnings Blackout (critical hard-gates; must not be zero)
    "earnings_blackout_days_before": ("int", 1, 30, True, 7),  # Fail-closed to 7 days
    "earnings_blackout_days_after": ("int", 1, 30, True, 3),  # Fail-closed to 3 days
    "min_price_history_days": ("int", 1, 1000, False, 200),
    "min_daily_volume_shares": ("int", 1, 10000000, False, 500000),
    "max_spread_pct": ("float", 0.0, 10.0, False, 0.5),
    "min_market_cap_millions": ("float", 0.0, 1000000.0, False, 300.0),
    "min_float_millions": ("float", 0.0, 1000000.0, False, 50.0),
    "max_short_interest_pct": ("float", 0.0, 100.0, False, 30.0),
    # Advanced Filters
    "block_days_before_earnings": ("int", 0, 100, False, 5),
    "max_extension_above_50ma_pct": ("float", 0.0, 100.0, False, 15.0),
    "strong_sector_top_n": ("int", 1, 100, False, 5),
    "require_strong_sector": ("bool", None, None, False, None),
    "min_adv_shares": ("int", 1, 10000000, False, 50000),
    "min_adv_dollars": ("float", 1.0, 100000000.0, False, 500000.0),
    "min_order_size_dollars": ("float", 0.1, 100000.0, False, 100.0),
    "phase1_min_coverage_pct": ("int", 0, 100, False, 75),
    "phase1_min_symbol_count": ("int", 100, 100000, False, 5000),
    "phase7_min_composite_score": ("int", 0, 100, False, 50),
    "advanced_filters_grade_threshold_aplus": ("int", 0, 100, False, 90),
    "advanced_filters_grade_threshold_a": ("int", 0, 100, False, 80),
    "advanced_filters_grade_threshold_b": ("int", 0, 100, False, 70),
    "advanced_filters_grade_threshold_c": ("int", 0, 100, False, 60),
    "advanced_filters_grade_threshold_d": ("int", 0, 100, False, 50),
    # Risk Metrics Calculation
    "var_percentile": ("int", 1, 50, False, 5),
    "cvar_percentile": ("int", 1, 50, False, 5),
    "stressed_var_percentile": ("int", 1, 50, False, 10),
    "dashboard_grade_threshold_a": ("int", 0, 100, False, 80),
    "dashboard_grade_threshold_b": ("int", 0, 100, False, 60),
    "dashboard_grade_threshold_c": ("int", 0, 100, False, 40),
    # Dashboard Configuration
    "dashboard_min_quality_threshold": ("float", 0.0, 100.0, False, 40.0),
    "dashboard_metrics_max_age_minutes": ("int", 1, 1000, False, 120),
    # Execution Mode
    "execution_mode": ("string", None, None, False, None),
    "alpaca_paper_trading": ("bool", None, None, False, None),
    "max_trades_per_day": ("int", 1, 100, False, 5),
    "default_portfolio_value": ("float", 1000.0, 10000000.0, False, 100000.0),
    # Feature Flags
    "enable_algo": ("bool", None, None, False, None),
    "enable_backtesting": ("bool", None, None, False, None),
    "verbose_logging": ("bool", None, None, False, None),
    # Network Configuration
    "api_request_timeout_seconds": ("int", 1, 300, False, 5),
    "db_connection_timeout_seconds": ("int", 1, 300, False, 15),
    # Failsafe Configuration
    "failsafe_ecs_timeout_sec": ("int", 30, 600, False, 180),
    "failsafe_grace_period_minutes": ("int", 60, 500, False, 240),
    # Data Patrol Configuration (monitoring system for data quality)
    "patrol_staleness_price": ("int", 0, 1000, False, None),
    "patrol_staleness_technical_data": ("int", 0, 1000, False, None),
    "patrol_staleness_fundamentals": ("int", 0, 1000, False, None),
    "patrol_staleness_stock_scores": ("int", 0, 1000, False, None),
    "patrol_staleness_aaii_sentiment": ("int", 0, 1000, False, None),
    "patrol_staleness_growth_metrics": ("int", 0, 1000, False, None),
    "patrol_staleness_earnings_history": ("int", 0, 1000, False, None),
    "patrol_min_universe_pct": ("float", 0.0, 100.0, False, None),
    "patrol_min_coverage_ratio": ("float", 0.0, 100.0, False, None),
    "patrol_max_daily_move_pct": ("float", 0.0, 1000.0, False, None),
    "patrol_max_daily_move_count": ("int", 0, 100000, False, None),
    "patrol_low_volume_threshold": ("int", 0, 10000000, False, None),
    "patrol_high_volume_threshold": ("int", 0, 10000000, False, None),
    "patrol_new_low_volume_alert": ("int", 0, 10000000, False, None),
    "patrol_price_daily_14d_min": ("int", 0, 10000, False, None),
    "patrol_buy_sell_daily_14d_min": ("int", 0, 10000, False, None),
    "patrol_coverage_ratio_min": ("float", 0.0, 1.0, False, None),
    "patrol_max_null_pct_threshold": ("float", 0.0, 100.0, False, None),
    # Signal and Loader Configuration
    "signal_max_data_age_days": ("int", 0, 100, False, None),
    "stale_loader_threshold_minutes": ("int", 0, 1000, False, None),
    # Swing Score Configuration
    # Loader Rate Limiting Configuration
    # Morning: 1-15 min window (conservative for 450-min budget); EOD: 1-10 min window (aggressive for 85-min budget)
    "loader_rate_limit_circuit_break_threshold_morning": ("int", 60, 900, False, 480),
    "loader_rate_limit_circuit_break_threshold_eod": ("int", 60, 600, False, 180),
    "loader_rate_limit_requests_per_min": ("int", 0, 10000, False, 120),
    "loader_timeout_seconds": ("int", 0, 36000, False, 300),
    "loader_emergency_mode_threshold_multiplier": ("float", 0.01, 100.0, False, 0.5),
    # Data Staleness Thresholds
    "data_staleness_fresh_days": ("int", 1, 100, False, 3),
    # CRITICAL: Data staleness thresholds for trading decisions
    # Swing/day traders MUST use fresh data - gap risk is too high with 3-10 day old prices
    # Default values intentionally CONSERVATIVE: reject stale data by default
    "data_staleness_stale_days_monday": (
        "int",
        1,
        2,  # Max 2 days old (prevent weekend lag accepting stale Friday close as fresh Monday)
        False,
        1,  # Fail-closed to 1 day: reject if data older than 1 day
    ),
    "data_staleness_stale_days_other": (
        "int",
        0,
        1,  # Max 1 day old - prices older than today unacceptable for intraday trading
        False,
        0,  # Fail-closed to 0 days: only today's data acceptable (reject any older)
    ),
    # Signal Strength Thresholds
    "signal_weak_threshold": ("float", 0.0, 100.0, False, 40.0),
    "signal_medium_threshold": ("float", 0.0, 100.0, False, 60.0),
    "signal_strong_threshold": ("float", 0.0, 100.0, False, 80.0),
    # Dashboard Fetcher Failure Configuration
    "dashboard_fetcher_failure_threshold": ("float", 0.0, 1.0, False, 0.5),
    # Portfolio Variance Threshold
    "portfolio_variance_threshold": ("float", 0.0, 1.0, False, 0.15),
    # Advanced Filters
    "enable_advanced_filters": ("bool", None, None, False, None),
    # Pyramid Trading Configuration
    "pyramid_enabled": ("bool", None, None, False, None),
    "pyramid_split_pct": ("float", 0.0, 100.0, False, None),
    "pyramid_add_1_gain_pct": ("float", 0.0, 100.0, False, None),
    "pyramid_add_2_gain_pct": ("float", 0.0, 100.0, False, None),
    # Data Patrol Staleness Thresholds (per-table granularity)
    "patrol_staleness_price_daily": ("int", 0, 365, False, None),
    "patrol_staleness_technical_daily": ("int", 0, 365, False, None),
    "patrol_staleness_buy_sell_daily": ("int", 0, 365, False, None),
    "patrol_staleness_trend_data": ("int", 0, 365, False, None),
    "patrol_staleness_signal_quality_scores": ("int", 0, 365, False, None),
    "patrol_staleness_market_health": ("int", 0, 365, False, None),
    "patrol_staleness_sector_ranking": ("int", 0, 365, False, None),
    "patrol_staleness_industry_ranking": ("int", 0, 365, False, None),
    "patrol_staleness_insider_transactions": ("int", 0, 365, False, None),
    "patrol_staleness_analyst_upgrades": ("int", 0, 365, False, None),
    # Stale Order Management
    "stale_order_alert_minutes": ("int", 0, 1440, False, None),
    "stale_order_auto_cancel_minutes": ("int", 0, 1440, False, None),
    # Data Patrol Coverage Error Threshold
    "patrol_coverage_error_threshold_pct": ("float", 0.0, 100.0, False, None),
}
