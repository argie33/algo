#!/usr/bin/env python3
"""
Algo Configuration System (Hot-Reload Enabled)

Centralized configuration from database. Changes take effect immediately without restart.
Supports: risk parameters, filter thresholds, execution modes, feature flags.
"""

import logging
import threading
import time
from typing import Any, cast

import psycopg2

from config.credential_validator import assert_credentials
from utils.db import DatabaseContext


logger = logging.getLogger(__name__)


def validate_environment():
    """Validate that all required environment variables are set at startup.

    Fails FAST with RuntimeError if any critical credential is missing.
    This prevents the app from starting and trading with incomplete credentials.
    """
    try:
        assert_credentials(on_failure="raise")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Credential validation failed: {e}")
        raise RuntimeError(f"Critical credential error: {e}") from e


# DEFERRED: Validate environment only when actually connecting to RDS/AWS,
# not at module import time. This allows loaders to run in dev environments
# without full production credentials configured locally.
# validate_environment() is called at connection time in db/connection.py


class AlgoConfig:
    """Configuration manager with hot-reload from database."""

    # Import validation schema from separate module (extracted for maintainability)
    from ..config_schema import VALIDATION_SCHEMA

    # Default configuration values
    # Format: (value, type, description, category) - category enables metadata-driven grouping
    DEFAULTS = {
        # Risk Management
        "base_risk_pct": ("0.75", "float", "Base portfolio risk per trade", "Risk Management"),
        "max_position_size_pct": ("6.3", "float", "Maximum single position size", "Risk Management"),
        "max_positions": ("15", "int", "Maximum concurrent positions", "Risk Management"),
        "max_concentration_pct": ("50.0", "float", "Max concentration in top position", "Risk Management"),
        # Drawdown Defense
        "halt_drawdown_pct": (
            "-20.0",
            "float",
            "Portfolio drawdown % to halt trading (CB1)",
            "Drawdown Defense",
        ),
        "risk_reduction_at_minus_5": ("0.75", "float", "Risk % at -5% drawdown"),
        "risk_reduction_at_minus_10": ("0.5", "float", "Risk % at -10% drawdown"),
        "risk_reduction_at_minus_15": ("0.25", "float", "Risk % at -15% drawdown"),
        "risk_reduction_at_minus_20": (
            "0.0",
            "float",
            "Risk % at -20% drawdown (halt)",
        ),
        # Filter Thresholds
        "min_completeness_score": (
            "70",
            "int",
            "Minimum data completeness % (Minervini standard)",
        ),
        "min_stock_price": ("5.0", "float", "Minimum stock price $"),
        "min_signal_quality_score": (
            "60",
            "int",
            "Minimum SQS 0-100 (signal quality gate)",
        ),
        "min_volume_ma_50d": ("300000", "int", "Minimum 50-day avg volume"),
        "min_avg_daily_dollar_volume": (
            "500000",
            "float",
            "Minimum daily dollar volume for liquidity gate",
        ),
        "require_stock_stage_2": ("true", "bool", "Require Stage 2 trend template"),
        "max_stop_distance_pct": ("12.0", "float", "Max stop distance % from entry"),
        "max_positions_per_sector": (
            "10",
            "int",
            "Max concurrent positions in one sector",
        ),
        "max_positions_per_industry": (
            "8",
            "int",
            "Max concurrent positions in one industry",
        ),
        "min_swing_score": (
            "55.0",
            "float",
            "Min swing trader score to enter (regime manager may raise this)",
        ),
        "min_swing_grade": (
            "",
            "string",
            "Min swing grade override (empty=use exposure tier default; set to F for testing to bypass grade gate)",
        ),
        "max_total_invested_pct": (
            "95.0",
            "float",
            "Max % of portfolio in open positions",
        ),
        # Market Conditions
        "max_distribution_days": ("4", "int", "Max market distribution days"),
        "require_stage_2_market": (
            "false",
            "bool",
            "Require market Stage 2 at Tier 2 (disabled: CB6 blocks Stage 4; per-stock weinstein_stage=2 check and exposure policy manage regime risk)",
        ),
        "vix_max_threshold": ("35.0", "float", "VIX level to halt trading"),
        "vix_alert_threshold": (
            "30.0",
            "float",
            "VIX level to trigger RED alert (dashboard display)",
        ),
        "vix_caution_threshold": ("25.0", "float", "VIX level to reduce positions"),
        "vix_caution_risk_reduction": (
            "0.75",
            "float",
            "Risk multiplier when VIX > caution threshold",
        ),
        # Market Exposure Engine  -” Veto Thresholds (H12)
        "market_exposure_veto1_breadth_pct": (
            "30",
            "int",
            "Breadth threshold for veto 1: SPY < 30wk MA AND breadth < N%",
        ),
        "market_exposure_veto1_cap_pct": (
            "25.0",
            "float",
            "Exposure cap % when veto 1 triggered (SPY < 30wk MA AND weak breadth)",
        ),
        "market_exposure_veto2_vix_threshold": (
            "40.0",
            "float",
            "VIX threshold for veto 2: VIX > N and rising",
        ),
        "market_exposure_veto2_cap_pct": (
            "30.0",
            "float",
            "Exposure cap % when veto 2 triggered (VIX > 40 rising)",
        ),
        "market_exposure_veto3_distribution_days_threshold": (
            "6",
            "int",
            "Distribution days threshold for veto 3 (6+ days)",
        ),
        "market_exposure_veto3_cap_pct": (
            "35.0",
            "float",
            "Exposure cap % when veto 3 triggered (6+ distribution days)",
        ),
        "market_exposure_veto4_cap_pct": (
            "40.0",
            "float",
            "Exposure cap % when veto 4 triggered (no FTD while SPY below 30wk MA)",
        ),
        "market_exposure_veto5_credit_spread_threshold": (
            "8.5",
            "float",
            "Credit spread threshold for veto 5 (systemic stress)",
        ),
        "market_exposure_veto5_cap_pct": (
            "30.0",
            "float",
            "Exposure cap % when veto 5 triggered (HY spread > 8.5%)",
        ),
        # Economic Regime Stress Scores (H12)
        "econ_stress_curve_inverted_severe": (
            "35.0",
            "float",
            "Stress score for severe yield curve inversion (<-0.5% for 8+ weeks)",
        ),
        "econ_stress_curve_inverted_moderate": (
            "20.0",
            "float",
            "Stress score for moderate yield curve inversion (<0%)",
        ),
        "econ_stress_curve_flat": (
            "8.0",
            "float",
            "Stress score for flat yield curve (<0.2%)",
        ),
        "econ_stress_hy_spread_severe": (
            "35.0",
            "float",
            "Stress score for severe HY credit spread (>6.5%)",
        ),
        "econ_stress_hy_spread_elevated": (
            "20.0",
            "float",
            "Stress score for elevated HY credit spread (>5.0%)",
        ),
        "econ_stress_hy_widening": (
            "15.0",
            "float",
            "Stress score for HY spread widening (>1.5pp in 60d)",
        ),
        "econ_stress_claims_severe": (
            "30.0",
            "float",
            "Stress score for severe jobless claims (>30% in 26w)",
        ),
        "econ_stress_claims_elevated": (
            "15.0",
            "float",
            "Stress score for elevated jobless claims (>20% in 26w)",
        ),
        "econ_stress_financial_severe": (
            "25.0",
            "float",
            "Stress score for severe financial stress (>1.5Ïƒ)",
        ),
        "econ_stress_financial_elevated": (
            "12.0",
            "float",
            "Stress score for elevated financial stress (>0.8Ïƒ)",
        ),
        "econ_stress_moderate_threshold": (
            "40",
            "int",
            "Stress level for moderate economic regime penalty (4 pts, no cap)",
        ),
        "econ_stress_severe_threshold": (
            "60",
            "int",
            "Stress level for severe economic regime penalty (7 pts, cap at 40%)",
        ),
        "econ_stress_severe_cap_pct": (
            "40.0",
            "float",
            "Exposure cap % at severe economic stress (stress >= 60)",
        ),
        "put_call_bullish_threshold": (
            "0.8",
            "float",
            "Put/Call ratio bullish threshold (<= for bullish)",
        ),
        "put_call_fearful_threshold": (
            "1.0",
            "float",
            "Put/Call ratio fearful threshold (>= for fearful)",
        ),
        "upvol_good_threshold": (
            "60.0",
            "float",
            "Up volume % threshold for good market (>= for GREEN)",
        ),
        "upvol_caution_threshold": (
            "50.0",
            "float",
            "Up volume % threshold for caution (>= for YELLOW)",
        ),
        "breadth_good_threshold": (
            "50",
            "int",
            "NH-NL difference threshold for good breadth (>= for GREEN)",
        ),
        "breadth_caution_threshold": (
            "0",
            "int",
            "NH-NL difference threshold for caution (>= for YELLOW)",
        ),
        "yield_curve_good_threshold": (
            "0.5",
            "float",
            "Yield curve slope for bullish signal (>= for GREEN)",
        ),
        "beta_warning_threshold": (
            "1.2",
            "float",
            "Portfolio beta threshold for caution (>= for WARNING)",
        ),
        "beta_caution_threshold": (
            "0.8",
            "float",
            "Portfolio beta threshold for bullish (>= for YELLOW)",
        ),
        # Entry Rules (Minervini)
        "require_sma50_above_sma200": ("true", "bool", "Price and MA alignment"),
        "min_percent_from_52w_low": (
            "0.0",
            "float",
            "Min % from 52w low (Minervini standard)",
        ),
        "max_percent_from_52w_high": ("25.0", "float", "Max % from 52w high"),
        "min_trend_template_score": (
            "6",
            "int",
            "Min Minervini score 0-8 (score 6 allows consolidating bases through; migration-006 lowered from 7)",
        ),
        # Entry Quality Gates (Sprint 2)
        "max_signal_age_days": ("3", "int", "Reject BUY signals older than N days"),
        "min_close_quality_pct": (
            "40.0",
            "float",
            "Close position threshold %: stock must close at/above this % of day range (0-100). E.g., 40 means close in upper 60% of range. Filters weak closes (near lows) indicating distribution, not accumulation.",
        ),
        "min_breakout_volume_ratio": (
            "1.25",
            "float",
            "Volume must be N x 50-day average",
        ),
        "require_weekly_stage_2": ("false", "bool", "Require weekly chart Stage 2"),
        "min_rs_line_slope_days": ("10", "int", "Days for RS line slope check"),
        "max_rs_pct_from_60d_high": (
            "15.0",
            "float",
            "Max % RS-line below 60d high (Minervini strict = 5%)",
        ),
        "rs_slope_gate_enabled": (
            "false",
            "bool",
            "Hard-gate T3 on RS line trending up (false=warn-only; consolidating bases show flat RS by design)",
        ),
        "volume_decay_gate_enabled": (
            "false",
            "bool",
            "Hard-gate T3 on volume decay into breakout (false=warn-only; accumulation naturally shows drying volume)",
        ),
        # Exit Rules
        "require_target_pullback": (
            "false",
            "bool",
            "Require 2%+ pullback before partial profit exits at T1/T2 (false = exit immediately at target)",
        ),
        "t1_target_r_multiple": ("1.5", "float", "Tier 1 profit target R-mult"),
        "t2_target_r_multiple": ("3.0", "float", "Tier 2 profit target R-mult"),
        "t3_target_r_multiple": ("4.0", "float", "Tier 3 profit target R-mult"),
        # Imported Position Defaults (when ATR calculation fails)
        "imported_position_default_stop_loss_pct": (
            "5.0",
            "float",
            "Default stop loss % for imported positions",
        ),
        "imported_position_default_target_1_pct": (
            "5.0",
            "float",
            "Default target 1 % for imported positions",
        ),
        "imported_position_default_target_2_pct": (
            "10.0",
            "float",
            "Default target 2 % for imported positions",
        ),
        "imported_position_default_target_3_pct": (
            "15.0",
            "float",
            "Default target 3 % for imported positions",
        ),
        "min_hold_days": ("1", "int", "Minimum days to hold"),
        "max_hold_days": ("20", "int", "Max days to hold position"),
        "exit_on_distribution_day": ("true", "bool", "Exit on market distribution"),
        "exit_on_rs_line_break_50dma": (
            "true",
            "bool",
            "Exit when RS line breaks 50-DMA",
        ),
        "exit_on_td_sequential": (
            "true",
            "bool",
            "Exit on TD Sequential 9/13 exhaustion",
        ),
        "use_chandelier_trail": ("true", "bool", "Use chandelier ATR trailing stop"),
        "switch_to_21ema_after_days": (
            "10",
            "int",
            "Days before switching chandelier to 21-EMA",
        ),
        "eight_week_rule_threshold_pct": (
            "20.0",
            "float",
            "ONeill 8-week hold threshold %",
        ),
        "eight_week_rule_window_days": ("21", "int", "Days to check for 20%+ gain"),
        "chandelier_atr_mult": ("3.0", "float", "ATR multiplier for chandelier stop"),
        "move_be_at_r": ("1.0", "float", "R-multiple to trigger breakeven stop raise"),
        # Drawdown Re-engagement (Sprint 3)
        "re_engage_recovery_pct": (
            "8.0",
            "float",
            "% recovery from peak to resume trading",
        ),
        "re_engage_min_days": ("5", "int", "Min days after halt before re-engagement"),
        "require_ftd_to_re_engage": (
            "true",
            "bool",
            "Require Follow-Through Day signal",
        ),
        # Circuit Breaker Thresholds (CB)
        "max_daily_loss_pct": ("2.0", "float", "Max daily loss % before halt"),
        "max_consecutive_losses": ("3", "int", "Max consecutive losing trades"),
        "min_win_rate_pct": ("40.0", "float", "Min win rate % to trade"),
        "max_total_risk_pct": ("4.0", "float", "Max total open risk %"),
        "min_risk_pct_floor": (
            "0.10",
            "float",
            "Minimum risk % floor when safety multipliers reduce position size",
        ),
        "max_weekly_loss_pct": ("5.0", "float", "Max weekly loss % before halt"),
        "max_data_staleness_days": ("3", "int", "Max data age in days"),
        "daily_profit_cap_pct": ("2.0", "float", "Daily profit cap %"),
        "sector_drawdown_halt_pct": (
            "-12.0",
            "float",
            "Sector drawdown % to halt trading",
        ),
        # Position Monitoring & Re-entry
        "position_halt_flag_count": ("2", "int", "Flags to propose early exit"),
        "max_reentries_per_name": ("2", "int", "Max times to re-enter same symbol"),
        "min_days_before_reentry_same_symbol": (
            "5",
            "int",
            "Days to wait before re-entering symbol",
        ),
        # Economic Calendar
        "halt_entries_before_major_release_minutes": (
            "60",
            "int",
            "Halt entries N minutes before major release",
        ),
        # Earnings Blackout
        "earnings_blackout_days_before": (
            "7",
            "int",
            "Days before earnings to block entries",
        ),
        "earnings_blackout_days_after": (
            "3",
            "int",
            "Days after earnings to block entries",
        ),
        "min_price_history_days": (
            "200",
            "int",
            "Min trading days of price history (IPO age gate  -” Minervini avoids stocks <1yr post-IPO)",
        ),
        "min_daily_volume_shares": ("500000", "int", "Minimum daily volume shares"),
        "max_spread_pct": ("0.5", "float", "Maximum bid-ask spread %"),
        "min_market_cap_millions": ("300.0", "float", "Minimum market cap $M"),
        "min_float_millions": ("50.0", "float", "Minimum float shares $M"),
        "max_short_interest_pct": ("30.0", "float", "Maximum short interest %"),
        # Advanced Filters
        "block_days_before_earnings": (
            "5",
            "int",
            "Block entries N days before earnings",
        ),
        "max_extension_above_50ma_pct": (
            "15.0",
            "float",
            "Max extension above 50-DMA %",
        ),
        "strong_sector_top_n": ("5", "int", "Top N sectors count as strong"),
        "require_strong_sector": (
            "false",
            "bool",
            "Require market sector to be strong before entering",
        ),
        "min_adv_shares": ("50000", "int", "Minimum average daily volume (shares)"),
        "min_adv_dollars": ("500000", "float", "Minimum average daily dollar volume"),
        "min_order_size_dollars": ("100.0", "float", "Minimum order size in dollars"),
        "phase1_min_coverage_pct": ("75", "int", "Phase 1: Minimum data coverage %"),
        "phase1_min_symbol_count": (
            "5000",
            "int",
            "Phase 1: Minimum symbol count for healthy coverage",
        ),
        # Swing Trader Score Weights (Minervini Research-Weighted Composite)
        "swing_weight_setup": ("25", "int", "Swing score: Setup quality weight %"),
        "swing_weight_trend": ("20", "int", "Swing score: Trend quality weight %"),
        "swing_weight_momentum": ("20", "int", "Swing score: Momentum/RS weight %"),
        "swing_weight_volume": ("12", "int", "Swing score: Volume weight %"),
        "swing_weight_fundamentals": (
            "10",
            "int",
            "Swing score: Fundamentals weight %",
        ),
        "swing_weight_sector": ("8", "int", "Swing score: Sector/industry weight %"),
        "swing_weight_multi_timeframe": (
            "5",
            "int",
            "Swing score: Multi-timeframe weight %",
        ),
        "swing_min_trend_score": (
            "5",
            "int",
            "Swing score: Minimum Minervini trend score 0-8",
        ),
        "swing_min_industry_rank": (
            "100",
            "int",
            "Swing score: Industry rank threshold (<=)",
        ),
        "swing_days_to_earnings_block": (
            "5",
            "int",
            "Swing score: Block entries N days to earnings",
        ),
        "swing_grade_threshold_aplus": (
            "85",
            "int",
            "Swing score: A+ grade threshold (score >= this value)",
        ),
        "swing_grade_threshold_a": (
            "75",
            "int",
            "Swing score: A grade threshold (score >= this value)",
        ),
        "swing_grade_threshold_b": (
            "65",
            "int",
            "Swing score: B grade threshold (score >= this value)",
        ),
        "swing_grade_threshold_c": (
            "55",
            "int",
            "Swing score: C grade threshold (score >= this value)",
        ),
        "swing_grade_threshold_d": (
            "45",
            "int",
            "Swing score: D grade threshold (score >= this value)",
        ),
        "advanced_filters_grade_threshold_aplus": (
            "90",
            "int",
            "Advanced filters: A+ grade threshold (score >= this value)",
        ),
        "advanced_filters_grade_threshold_a": (
            "80",
            "int",
            "Advanced filters: A grade threshold (score >= this value)",
        ),
        "advanced_filters_grade_threshold_b": (
            "70",
            "int",
            "Advanced filters: B grade threshold (score >= this value)",
        ),
        "advanced_filters_grade_threshold_c": (
            "60",
            "int",
            "Advanced filters: C grade threshold (score >= this value)",
        ),
        "advanced_filters_grade_threshold_d": (
            "50",
            "int",
            "Advanced filters: D grade threshold (score >= this value)",
        ),
        # Risk Metrics Calculation (M3 - Risk Thresholds)
        "var_percentile": (
            "5",
            "int",
            "Percentile for VaR calculation (5 = 95% confidence, measures 5th percentile loss)",
        ),
        "cvar_percentile": (
            "5",
            "int",
            "Percentile for CVaR calculation (5 = worst 5% of days)",
        ),
        "stressed_var_percentile": (
            "10",
            "int",
            "Percentile for stressed VaR (10 = worst 10% of days)",
        ),
        "dashboard_grade_threshold_a": (
            "80",
            "int",
            "Dashboard signals: A grade threshold (score >= this value)",
        ),
        "dashboard_grade_threshold_b": (
            "60",
            "int",
            "Dashboard signals: B grade threshold (score >= this value)",
        ),
        "dashboard_grade_threshold_c": (
            "40",
            "int",
            "Dashboard signals: C grade threshold (score >= this value)",
        ),
        # Dashboard Configuration (E8, E9 - Operator-tunable thresholds)
        "dashboard_min_quality_threshold": (
            "40.0",
            "float",
            "Minimum signal quality score to display (0-100; E8)",
        ),
        "dashboard_metrics_max_age_minutes": (
            "120",
            "int",
            "Maximum age of metrics in minutes before warning (E9)",
        ),
        # Execution Mode
        "execution_mode": ("auto", "string", "paper|dry|review|auto"),
        "alpaca_paper_trading": ("false", "bool", "Use Alpaca paper account"),
        "max_trades_per_day": ("5", "int", "Max new trades per day"),
        "default_portfolio_value": (
            "100000.0",
            "float",
            "Bootstrap portfolio value when Alpaca unreachable and no snapshot (Alpaca paper starts at $100k)",
        ),
        # Feature Flags
        "enable_algo": ("true", "bool", "Enable algo trading"),
        "enable_backtesting": ("false", "bool", "Enable backtest mode"),
        "verbose_logging": ("true", "bool", "Detailed logging"),
        # Network Configuration
        "api_request_timeout_seconds": (
            "5",
            "int",
            "HTTP request timeout (seconds) for Alpaca/FRED/market data APIs",
        ),
        "db_connection_timeout_seconds": (
            "15",
            "int",
            "Database connection timeout (seconds)  -” RDS Proxy adds latency",
        ),
        # Failsafe Configuration
        "failsafe_ecs_timeout_sec": (
            "180",
            "int",
            "Max seconds to wait for ECS task to reach RUNNING state (Fargate provisioning under load: 45-150s)",
        ),
        "failsafe_grace_period_minutes": (
            "240",
            "int",
            "Grace period before triggering second failsafe (min). Morning window 2-9:30AM=450min; expected load ~285min; allows 2:00+240m=6:00 expiry, second loader 6:00+285m~11:30am (acceptable). Must be <390 (450-60 Phase 2-7 buffer). Too long: no retry time. Too short: false positives if load is slow.",
        ),
        # Loader Rate Limiting Configuration
        "loader_rate_limit_circuit_break_threshold_morning": (
            "480",
            "int",
            "Circuit break threshold (seconds) during morning prep (8 min)",
        ),
        "loader_rate_limit_circuit_break_threshold_eod": (
            "180",
            "int",
            "Circuit break threshold (seconds) during EOD (3 min)",
        ),
        "loader_rate_limit_requests_per_min": (
            "120",
            "int",
            "Rate limit: maximum requests per minute",
        ),
        "loader_timeout_seconds": (
            "300",
            "int",
            "Loader operation timeout in seconds",
        ),
        "loader_emergency_mode_threshold_multiplier": (
            "0.5",
            "float",
            "Emergency mode triggered at N% of task timeout",
        ),
        # Data Staleness Thresholds
        "data_staleness_fresh_days": (
            "3",
            "int",
            "Data age (days) considered fresh",
        ),
        "data_staleness_stale_days_monday": (
            "10",
            "int",
            "Data age (days) on Monday to be considered stale",
        ),
        "data_staleness_stale_days_other": (
            "3",
            "int",
            "Data age (days) on non-Monday to be considered stale",
        ),
        # Signal Strength Thresholds
        "signal_weak_threshold": (
            "40.0",
            "float",
            "Signal score below this = weak signal",
        ),
        "signal_medium_threshold": (
            "60.0",
            "float",
            "Signal score 40-60 (by default) = medium strength",
        ),
        "signal_strong_threshold": (
            "80.0",
            "float",
            "Signal score 60-80 = strong, >=80 = very strong",
        ),
        # Dashboard Fetcher Failure Configuration
        "dashboard_fetcher_failure_threshold": (
            "0.5",
            "float",
            "Dashboard: if >N% of fetchers fail, enter degraded mode",
        ),
        # Portfolio Variance Threshold
        "portfolio_variance_threshold": (
            "0.15",
            "float",
            "Portfolio variance threshold to trigger CB circuit breaker",
        ),
    }

    # Configuration category mappings (pattern-based categorization)
    # Maps key patterns (substrings) to their category for UI grouping
    CONFIG_CATEGORY_PATTERNS = [
        ("drawdown", "Drawdown Defense"),
        ("halt", "Drawdown Defense"),
        ("risk_reduction", "Drawdown Defense"),
        ("circuit", "Circuit Breakers"),
        ("max_daily_loss", "Circuit Breakers"),
        ("max_consecutive", "Circuit Breakers"),
        ("min_win_rate", "Circuit Breakers"),
        ("max_total_risk", "Circuit Breakers"),
        ("max_weekly", "Circuit Breakers"),
        ("daily_profit_cap", "Circuit Breakers"),
        ("sector_drawdown", "Circuit Breakers"),
        ("swing", "Swing Trader Scoring"),
        ("vix", "Market Conditions"),
        ("put_call", "Market Conditions"),
        ("upvol", "Market Conditions"),
        ("breadth", "Market Conditions"),
        ("yield_curve", "Market Conditions"),
        ("beta", "Market Conditions"),
        ("max_distribution", "Market Conditions"),
        ("require_stage", "Market Conditions"),
        ("min_completeness", "Filter Thresholds"),
        ("min_stock_price", "Filter Thresholds"),
        ("min_signal", "Filter Thresholds"),
        ("min_volume", "Filter Thresholds"),
        ("min_avg_daily", "Filter Thresholds"),
        ("require_stock_stage", "Filter Thresholds"),
        ("max_stop_distance", "Filter Thresholds"),
        ("max_positions_per", "Filter Thresholds"),
        ("min_swing_score", "Filter Thresholds"),
        ("max_total_invested", "Filter Thresholds"),
        ("advanced_filters_grade", "Filter Thresholds"),
        ("require_sma50", "Entry Rules (Minervini)"),
        ("min_percent_from", "Entry Rules (Minervini)"),
        ("max_percent_from", "Entry Rules (Minervini)"),
        ("min_trend_template", "Entry Rules (Minervini)"),
        ("max_signal_age", "Entry Quality Gates"),
        ("min_close_quality", "Entry Quality Gates"),
        ("min_breakout_volume", "Entry Quality Gates"),
        ("require_weekly_stage", "Entry Quality Gates"),
        ("min_rs_line", "Entry Quality Gates"),
        ("max_rs_pct", "Entry Quality Gates"),
        ("rs_slope_gate", "Entry Quality Gates"),
        ("volume_decay_gate", "Entry Quality Gates"),
        ("require_target_pullback", "Exit Rules"),
        ("t1_target", "Exit Rules"),
        ("t2_target", "Exit Rules"),
        ("t3_target", "Exit Rules"),
        ("imported_position", "Exit Rules"),
        ("min_hold", "Exit Rules"),
        ("max_hold", "Exit Rules"),
        ("exit_on", "Exit Rules"),
        ("use_chandelier", "Exit Rules"),
        ("switch_to_21ema", "Exit Rules"),
        ("eight_week_rule", "Exit Rules"),
        ("chandelier_atr", "Exit Rules"),
        ("move_be", "Exit Rules"),
        ("re_engage", "Re-engagement"),
        ("position_halt_flag", "Position Monitoring"),
        ("max_reentries", "Position Monitoring"),
        ("min_days_before_reentry", "Position Monitoring"),
        ("earnings", "Economic & Earnings"),
        ("halt_entries_before", "Economic & Earnings"),
        ("block_days_before", "Economic & Earnings"),
        ("min_price_history", "Fundamental Filters"),
        ("min_daily_volume", "Fundamental Filters"),
        ("max_spread", "Fundamental Filters"),
        ("min_market_cap", "Fundamental Filters"),
        ("min_float", "Fundamental Filters"),
        ("max_short_interest", "Fundamental Filters"),
        ("max_extension", "Advanced Filters"),
        ("strong_sector", "Advanced Filters"),
        ("var_percentile", "Risk Metrics"),
        ("cvar_percentile", "Risk Metrics"),
        ("stressed_var", "Risk Metrics"),
        ("dashboard_grade", "Risk Metrics"),
        ("execution_mode", "Execution Mode"),
        ("alpaca_paper", "Execution Mode"),
        ("max_trades_per_day", "Execution Mode"),
        ("default_portfolio", "Execution Mode"),
        ("enable_", "Feature Flags"),
        ("verbose_", "Feature Flags"),
        ("api_request", "Network Configuration"),
        ("db_connection", "Network Configuration"),
        ("failsafe", "Failsafe Configuration"),
        ("base_risk", "Risk Management"),
        ("max_position_size", "Risk Management"),
        ("max_concentration", "Risk Management"),
    ]

    @classmethod
    def get_config_category(cls, key: str) -> str:
        """Get category for a config key based on pattern matching.

        Returns first matching category pattern, or 'Other' if no match.
        """
        for pattern, category in cls.CONFIG_CATEGORY_PATTERNS:
            if pattern in key:
                return category
        return "Other"

    def __init__(self):
        import time

        t0 = time.time()
        logger.info("[AlgoConfig] __init__ starting")
        self._config = {}
        self._sources = {}  # Track source of each config value: "default" or "database"
        self._validate_schema_consistency()
        self._load_defaults()
        t1 = time.time()
        logger.info(f"[AlgoConfig] defaults loaded in {t1 - t0:.2f}s")
        self._load_from_database()
        t2 = time.time()
        logger.info(f"[AlgoConfig] database loaded in {t2 - t1:.2f}s, total {t2 - t0:.2f}s")
        self._validate_critical_thresholds()
        t_crit = time.time()
        logger.info(f"[AlgoConfig] critical threshold validation completed in {t_crit - t2:.2f}s")
        self._validate_config_interdependencies()
        t3 = time.time()
        logger.info(f"[AlgoConfig] interdependency validation completed in {t3 - t_crit:.2f}s")
        self._audit_config_sources()

    @property
    def risk(self):
        """Get RiskConfig specialist (lazy-loaded on first access).

        Returns:
            RiskConfig instance (cached after first access)

        Usage:
            config = get_config()
            risk_sizing = config.risk.get_position_sizing_config()
        """
        if not hasattr(self, "_risk_config"):
            from .risk_config import RiskConfig

            self._risk_config = RiskConfig(self)
        return self._risk_config

    @property
    def circuit_breaker(self):
        """Get CircuitBreakerConfig specialist (lazy-loaded on first access).

        Returns:
            CircuitBreakerConfig instance (cached after first access)

        Usage:
            config = get_config()
            daily_limit = config.circuit_breaker.get("max_daily_loss_pct")
        """
        if not hasattr(self, "_circuit_breaker_config"):
            from .circuit_breaker_config import CircuitBreakerConfig

            self._circuit_breaker_config = CircuitBreakerConfig(self)
        return self._circuit_breaker_config

    @property
    def data_patrol(self):
        """Get DataPatrolConfig specialist (lazy-loaded on first access).

        Returns:
            DataPatrolConfig instance (cached after first access)

        Usage:
            config = get_config()
            staleness = config.data_patrol.get_staleness_windows()
        """
        if not hasattr(self, "_data_patrol_config"):
            from .data_patrol_config import DataPatrolConfig

            self._data_patrol_config = DataPatrolConfig(self)
        return self._data_patrol_config

    @property
    def timeout(self):
        """Get TimeoutConfig specialist (lazy-loaded on first access).

        Returns:
            TimeoutConfig instance (cached after first access)

        Usage:
            config = get_config()
            api_timeout = config.timeout.get_api_timeout()
            all_timeouts = config.timeout.get_all_timeouts()
        """
        if not hasattr(self, "_timeout_config"):
            from .timeout_config import TimeoutConfig

            self._timeout_config = TimeoutConfig(self)
        return self._timeout_config

    @property
    def execution(self):
        """Get ExecutionConfig specialist (lazy-loaded on first access).

        Returns:
            ExecutionConfig instance (cached after first access)

        Usage:
            config = get_config()
            mode = config.execution.get_execution_mode()
            all_exec = config.execution.get_execution_config()
        """
        if not hasattr(self, "_execution_config"):
            from .execution_config import ExecutionConfig

            self._execution_config = ExecutionConfig(self)
        return self._execution_config

    @property
    def economic_stress(self):
        """Get EconomicStressConfig specialist (lazy-loaded on first access).

        Returns:
            EconomicStressConfig instance (cached after first access)

        Usage:
            config = get_config()
            hy_spreads = config.economic_stress.get_hy_spread_stress()
            all_stress = config.economic_stress.get_all_stress_scores()
        """
        if not hasattr(self, "_economic_stress_config"):
            from .economic_stress_config import EconomicStressConfig

            self._economic_stress_config = EconomicStressConfig(self)
        return self._economic_stress_config

    def _validate_schema_consistency(self):
        """Verify that VALIDATION_SCHEMA and DEFAULTS are in sync.

        Every key in DEFAULTS must be in VALIDATION_SCHEMA (with type consistency).
        Every critical key in VALIDATION_SCHEMA must be in DEFAULTS.
        Raises RuntimeError if inconsistencies are found.
        """
        errors = []
        warnings = []

        # Check that all DEFAULTS keys have corresponding VALIDATION_SCHEMA entries
        for key, (_default_value, default_type, _) in self.DEFAULTS.items():
            if key not in self.VALIDATION_SCHEMA:
                errors.append(f"  {key}: in DEFAULTS but NOT in VALIDATION_SCHEMA (type: {default_type})")
            else:
                schema_type, _, _, _, _ = self.VALIDATION_SCHEMA[key]
                # Relaxed check: int/float can be interchanged in numeric contexts
                if default_type != schema_type:
                    if not ((default_type in ("int", "float")) and (schema_type in ("int", "float"))):
                        errors.append(
                            f"  {key}: type mismatch - DEFAULTS has {default_type} but SCHEMA has {schema_type}"
                        )

        # Check that all critical SCHEMA keys are in DEFAULTS
        for key, (_schema_type, _, _, is_critical, _) in self.VALIDATION_SCHEMA.items():
            if key not in self.DEFAULTS:
                if is_critical:
                    errors.append(f"  {key}: CRITICAL in SCHEMA but NOT in DEFAULTS (must have a safe default)")
                else:
                    warnings.append(f"  {key}: in SCHEMA but NOT in DEFAULTS (non-critical, will use schema default)")

        if errors:
            error_msg = (
                "FATAL: Configuration schema/defaults mismatch detected.\n"
                "This prevents proper validation of safety thresholds.\n\n"
                + "\n".join(errors)
                + "\n\nAction: Fix VALIDATION_SCHEMA and DEFAULTS to be consistent."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        if warnings:
            logger.warning("[AlgoConfig] Schema/defaults consistency warnings:\n" + "\n".join(warnings))

    def _load_defaults(self):
        """Load default configuration."""
        for key, (value, dtype, _desc) in self.DEFAULTS.items():
            self._config[key] = self._parse_value(value, dtype)
            self._sources[key] = "default"

    def _load_from_database(self):
        """Load configuration from database, overriding defaults.

        If a critical safety threshold is invalid, rejects the value and uses the
        fail-closed default instead, then logs an alert for the admin to fix it.
        """
        t0 = time.time()
        logger.info("[AlgoConfig] _load_from_database() starting")
        try:
            t_conn_start = time.time()
            with DatabaseContext("read", timeout=15) as cur:
                t_conn_done = time.time()
                logger.info(f"[AlgoConfig] database connection took {t_conn_done - t_conn_start:.2f}s")

                cur.execute("SELECT key, value, value_type FROM algo_config")
                rows = cur.fetchall()
                logger.info(f"[AlgoConfig] loaded {len(rows)} config rows from DB")

                invalid_critical_values = []
                for key, value, dtype in rows:
                    if value is not None:
                        try:
                            # Normalize PostgreSQL type names to schema type names
                            normalized_dtype = self._normalize_db_type(dtype)
                            self._validate_value(key, value, normalized_dtype)
                            self._config[key] = self._parse_value(value, normalized_dtype)
                            self._sources[key] = "database"
                        except ValueError as e:
                            # Check if this is a critical safety threshold
                            schema_info = self.VALIDATION_SCHEMA.get(key)
                            if schema_info and schema_info[3]:  # is_critical
                                _, _, _, _, fail_closed = schema_info
                                self._config[key] = fail_closed
                                self._sources[key] = "fail_closed_default"
                                invalid_critical_values.append(
                                    f"  {key}={value}: {e} -> using fail-closed default {fail_closed}"
                                )
                                logger.error(
                                    f"ALERT: Critical safety gate {key} has invalid value {value}. "
                                    f"Using fail-closed default {fail_closed}. "
                                    f"Admin must fix database value: {e}"
                                )
                            else:
                                logger.warning(f"Warning: Invalid config {key}={value}: {e}  -” using default")
                                self._sources[key] = "default_fallback"

                if invalid_critical_values:
                    logger.warning(
                        "[AlgoConfig] ALERT: Critical safety thresholds were invalid and reverted to fail-closed defaults:\n"
                        + "\n".join(invalid_critical_values)
                        + "\n\nAdmin must restore valid values in algo_config table before these thresholds take normal effect."
                    )

                self._validate_r_multiple_ordering()
                t_end = time.time()
                logger.info(f"[AlgoConfig] _load_from_database() completed in {t_end - t0:.2f}s")
        except ValueError as e:
            logger.error(f"Config validation error: {e}")
            raise
        except (psycopg2.DatabaseError, psycopg2.OperationalError, ConnectionError, Exception) as e:
            logger.error(f"CRITICAL: Failed to load config from database: {e}")
            raise RuntimeError(
                f"Config initialization failed: cannot load safety thresholds from database. "
                f"System will not trade with undefined safety configuration. Caused by: {e}"
            ) from e

    def _normalize_db_type(self, db_type: str) -> str:
        """Convert PostgreSQL type names to schema type names.

        Database stores PostgreSQL native types like 'integer', 'double precision', etc.
        Schema expects Python type names like 'int', 'float', 'bool', 'string'.
        """
        if db_type is None:
            return "string"

        db_type_lower = db_type.lower().strip()

        # Map PostgreSQL types to schema types
        type_mapping = {
            "integer": "int",
            "int": "int",
            "bigint": "int",
            "smallint": "int",
            "double precision": "float",
            "double": "float",
            "float": "float",
            "numeric": "float",
            "decimal": "float",
            "boolean": "bool",
            "bool": "bool",
            "text": "string",
            "varchar": "string",
            "string": "string",
            "character varying": "string",
        }

        return type_mapping.get(db_type_lower, "string")

    def _parse_value(self, value, dtype):
        """Parse configuration value to correct type."""
        if dtype == "int":
            return int(value)
        elif dtype == "float":
            return float(value)
        elif dtype == "bool":
            return value.lower() in ("true", "1", "yes")
        else:
            return str(value)

    def _validate_value(self, key, value, dtype):
        """Validate that a config value is within acceptable bounds using schema.

        If key is not in schema, performs backward-compatible basic validation.
        Raises ValueError if validation fails.
        """
        # Use validation schema if available; otherwise fall back to basic checks
        if key not in self.VALIDATION_SCHEMA:
            logger.warning(f"[CONFIG VALIDATE] Key {key!r} not in validation schema  -” using basic checks")
            return True

        schema_type, min_val, max_val, is_critical, fail_closed = self.VALIDATION_SCHEMA[key]

        # Type mismatch check
        if dtype != schema_type:
            # For backward compatibility, allow int/float interchangeably in numeric contexts
            if not ((dtype in ("int", "float")) and (schema_type in ("int", "float"))):
                raise ValueError(f"{key}: type mismatch. Expected {schema_type}, got {dtype}")

        # Parse value for range checking (skip bool/string which have no min/max)
        if schema_type in ("int", "float"):
            try:
                f_val = float(value)
            except (ValueError, TypeError) as e:
                raise ValueError(f"{key}: Cannot parse {value!r} as numeric") from e

            # Critical safety gates: for critical params, check near-zero FIRST (highest priority)
            if is_critical and abs(f_val) < 0.001:
                # Include "below minimum" context if this also violates min bound
                if min_val is not None and f_val < min_val:
                    raise ValueError(
                        f"{key}: below minimum|CRITICAL SAFETY GATE - cannot be zero or near-zero "
                        f"(would disable safety protection). Min allowed: {min_val}. "
                        f"Reverting to safe default {fail_closed}."
                    )
                raise ValueError(
                    f"{key}: CRITICAL SAFETY GATE - cannot be zero or near-zero "
                    f"(would disable safety protection). Reverting to safe default {fail_closed}."
                )

            # Validate range if bounds are defined (for non-critical or non-near-zero values)
            if min_val is not None and f_val < min_val:
                raise ValueError(f"{key}: {f_val} is below minimum {min_val}")
            if max_val is not None and f_val > max_val:
                raise ValueError(f"{key}: {f_val} is above maximum {max_val}")

        return True

    def _validate_r_multiple_ordering(self):
        """Verify t1 < t2 < t3 R-multiple targets (called after full config load)."""
        try:
            # Fail-fast: R-multiples are critical and must be explicitly configured
            t1_val = self._config.get("t1_target_r_multiple")
            t2_val = self._config.get("t2_target_r_multiple")
            t3_val = self._config.get("t3_target_r_multiple")

            if t1_val is None or t2_val is None or t3_val is None:
                raise ValueError(
                    f"CRITICAL: R-multiple config missing. Required: t1_target_r_multiple, t2_target_r_multiple, t3_target_r_multiple. "
                    f"Found: t1={t1_val}, t2={t2_val}, t3={t3_val}. "
                    f"Cannot apply silent defaults (1.5, 3.0, 4.0) — must be explicitly configured."
                )

            t1 = float(t1_val)
            t2 = float(t2_val)
            t3 = float(t3_val)
            if not (t1 < t2 < t3):
                raise ValueError(
                    f"R-multiple ordering broken: t1={t1} t2={t2} t3={t3}. Required: t1 < t2 < t3 for position sizing."
                )
        except (TypeError, ValueError) as e:
            logger.error(f"Config validation failed: {e}")
            raise

    def _validate_critical_thresholds(self):
        """Fail-fast validation: critical safety thresholds must be within safe ranges.

        Checks all keys marked as critical in VALIDATION_SCHEMA. Raises RuntimeError
        if any critical threshold is missing, zero, or out of valid range.
        """
        errors = []
        warnings = []

        for key, (
            _schema_type,
            min_val,
            max_val,
            is_critical,
            fail_closed,
        ) in self.VALIDATION_SCHEMA.items():
            if not is_critical:
                continue  # Skip non-critical params

            current_value = self._config.get(key)

            # Missing or None
            if current_value is None:
                errors.append(
                    f"  {key}: not configured (None). Safe default: {fail_closed}. Range: [{min_val}, {max_val}]"
                )
                continue

            # Convert to comparable type
            try:
                f_val = float(current_value)
            except (ValueError, TypeError):
                errors.append(f"  {key}: cannot parse value {current_value!r}. Safe default: {fail_closed}")
                continue

            # Zero/near-zero (disables safety gate)
            if abs(f_val) < 0.001:
                errors.append(
                    f"  {key} = {f_val}: ZERO or near-zero (disables safety gate). "
                    f"Safe default: {fail_closed}. Range: [{min_val}, {max_val}]"
                )
                continue

            # Out of range
            if min_val is not None and f_val < min_val:
                errors.append(f"  {key} = {f_val}: below minimum {min_val}. Safe default: {fail_closed}")
            if max_val is not None and f_val > max_val:
                errors.append(f"  {key} = {f_val}: above maximum {max_val}. Safe default: {fail_closed}")

        if errors:
            error_msg = (
                "SAFETY GATE FAILURE: Critical configuration thresholds are invalid.\n"
                "System will not trade with corrupt safety configuration.\n"
                "These thresholds prevent trading unsuitable stocks and during dangerous market conditions.\n\n"
                "Invalid thresholds:\n"
                + "\n".join(errors)
                + "\n\nAction: Restore valid thresholds in database before trading.\n"
                "Run: python migrations/runner.py up (migration-033) to restore safe defaults\n"
                "OR manually fix the database values per CLAUDE.md -> Trading Safety Configuration"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        if warnings:
            logger.warning("[AlgoConfig] Critical threshold warnings:\n" + "\n".join(warnings))

    def _validate_config_interdependencies(self):
        """Validate configuration interdependencies at startup.

        Checks for conflicting values that create impossible or dead-code scenarios.
        Raises ValueError for hard constraints; warns for soft conflicts.
        """
        try:
            # Validate all required config keys exist upfront
            required_keys = [
                "max_positions",
                "max_position_size_pct",
                "max_total_invested_pct",
                "vix_caution_threshold",
                "vix_max_threshold",
                "vix_alert_threshold",
                "halt_drawdown_pct",
                "risk_reduction_at_minus_5",
                "risk_reduction_at_minus_10",
                "risk_reduction_at_minus_15",
                "risk_reduction_at_minus_20",
                "earnings_blackout_days_before",
                "earnings_blackout_days_after",
                "max_stop_distance_pct",
                "base_risk_pct",
                "max_daily_loss_pct",
                "max_weekly_loss_pct",
                "min_completeness_score",
                "min_signal_quality_score",
                "min_swing_score",
                "min_stock_price",
            ]
            missing = [k for k in required_keys if k not in self._config or self._config[k] is None]
            if missing:
                raise ValueError(
                    f"Critical config keys missing (required for validation): {missing}. "
                    f"Ensure AlgoConfig defaults are loaded and database values override them correctly."
                )

            # Position geometry: max_positions * max_position_size_pct <= max_total_invested_pct
            max_pos = float(self._config["max_positions"])
            max_pos_size_pct = float(self._config["max_position_size_pct"])
            max_total_pct = float(self._config["max_total_invested_pct"])

            theoretical_max_from_position_size = (
                max_total_pct / max_pos_size_pct if max_pos_size_pct > 0 else float("inf")
            )
            if max_pos > theoretical_max_from_position_size:
                logger.warning(
                    f"Config conflict: max_positions={max_pos} * "
                    f"max_position_size_pct={max_pos_size_pct}% = "
                    f"{max_pos * max_pos_size_pct}% > max_total_invested_pct={max_total_pct}%. "
                    f"Geometric maximum is {theoretical_max_from_position_size:.1f} positions."
                )

            # VIX thresholds: caution < max (hard constraint)
            vix_caution = float(self._config["vix_caution_threshold"])
            vix_max = float(self._config["vix_max_threshold"])
            vix_alert = float(self._config["vix_alert_threshold"])

            if vix_caution >= vix_max:
                raise ValueError(
                    f"Config error: vix_caution_threshold ({vix_caution}) must be < vix_max_threshold ({vix_max})"
                )

            if vix_alert >= vix_max:
                logger.warning(
                    f"Config: vix_alert_threshold ({vix_alert}) >= vix_max_threshold ({vix_max}). "
                    "Alert will never trigger (max threshold reached first)."
                )

            if vix_caution >= vix_alert:
                logger.warning(
                    f"Config: vix_caution_threshold ({vix_caution}) >= "
                    f"vix_alert_threshold ({vix_alert}). Caution will trigger before alert."
                )

            # Drawdown thresholds: all should be negative and ordered
            halt_dd = float(self._config["halt_drawdown_pct"])
            r_at_minus_5 = float(self._config["risk_reduction_at_minus_5"])
            r_at_minus_10 = float(self._config["risk_reduction_at_minus_10"])
            r_at_minus_15 = float(self._config["risk_reduction_at_minus_15"])
            r_at_minus_20 = float(self._config["risk_reduction_at_minus_20"])

            if halt_dd >= 0:
                logger.warning(f"Config: halt_drawdown_pct ({halt_dd}) should be negative (represents downside loss)")

            if not (r_at_minus_20 <= r_at_minus_15 <= r_at_minus_10 <= r_at_minus_5):
                logger.warning(
                    f"Config: Risk reduction thresholds not ordered: "
                    f"-5%={r_at_minus_5}, -10%={r_at_minus_10}, "
                    f"-15%={r_at_minus_15}, -20%={r_at_minus_20}. "
                    f"Expected: -5% >= -10% >= -15% >= -20%"
                )

            # Earnings blackout: both should be non-negative
            eb_before = int(self._config["earnings_blackout_days_before"])
            eb_after = int(self._config["earnings_blackout_days_after"])

            if eb_before < 0 or eb_after < 0:
                logger.warning(
                    f"Config: Earnings blackout days should be non-negative (before={eb_before}, after={eb_after})"
                )

            # Stop loss: max_stop_distance_pct should be positive and reasonable
            max_stop = float(self._config["max_stop_distance_pct"])
            if max_stop <= 0:
                logger.warning(f"Config: max_stop_distance_pct ({max_stop}) should be positive")
            if max_stop > 50:
                logger.warning(f"Config: max_stop_distance_pct ({max_stop}) is very wide (typical range 5-20%)")

            # Risk percentages: should be positive
            base_risk = float(self._config["base_risk_pct"])
            if base_risk <= 0:
                logger.warning(f"Config: base_risk_pct ({base_risk}) should be positive")
            if base_risk > 5:
                logger.warning(f"Config: base_risk_pct ({base_risk}) is very high (typical: 0.5-2%)")

            # Daily/weekly loss caps should be positive
            daily_loss = float(self._config["max_daily_loss_pct"])
            weekly_loss = float(self._config["max_weekly_loss_pct"])

            if daily_loss <= 0 or weekly_loss <= 0:
                logger.warning(f"Config: Max loss caps should be positive (daily={daily_loss}, weekly={weekly_loss})")

            if daily_loss >= weekly_loss:
                logger.warning(
                    f"Config: max_daily_loss_pct ({daily_loss}) >= max_weekly_loss_pct ({weekly_loss}). "
                    "Daily limit will trigger before weekly limit."
                )

            # Minimum thresholds should be non-negative
            min_completeness = int(self._config["min_completeness_score"])
            min_signal_quality = int(self._config["min_signal_quality_score"])
            min_swing_score = float(self._config["min_swing_score"])
            min_stock_price = float(self._config["min_stock_price"])

            if min_completeness < 0 or min_signal_quality < 0 or min_swing_score < 0 or min_stock_price < 0:
                logger.warning(
                    f"Config: Score/price thresholds should be non-negative "
                    f"(completeness={min_completeness}, signal_quality={min_signal_quality}, "
                    f"swing_score={min_swing_score}, stock_price={min_stock_price})"
                )

            logger.info("[AlgoConfig] Interdependency validation passed")

        except ValueError as e:
            logger.error(f"[AlgoConfig] FATAL: {e}")
            raise
        except (ZeroDivisionError, TypeError) as e:
            logger.warning(f"[AlgoConfig] Interdependency validation error: {e}")

    def get_critical_thresholds_summary(self):
        """Return a dict of all critical safety thresholds and their current values.

        Useful for monitoring, dashboards, and admin verification.
        Format: {key: {"value": X, "min": Y, "max": Z, "source": "database"}}
        """
        summary = {}
        for key, (
            _schema_type,
            min_val,
            max_val,
            is_critical,
            fail_closed,
        ) in self.VALIDATION_SCHEMA.items():
            if is_critical:
                summary[key] = {
                    "value": self._config.get(key),
                    "min": min_val,
                    "max": max_val,
                    "safe_default": fail_closed,
                    "source": self._sources.get(key, "unknown"),
                }
        return summary

    def _audit_config_sources(self):
        """Log audit trail of config sources and critical threshold status.

        Helps detect silent fallbacks, schema inconsistencies, and unsafe thresholds.
        """
        num_db = sum(1 for s in self._sources.values() if s == "database")
        num_default = sum(1 for s in self._sources.values() if s == "default")
        num_fallback = sum(1 for s in self._sources.values() if s == "default_fallback")
        num_fail_closed = sum(1 for s in self._sources.values() if s == "fail_closed_default")

        logger.info(
            f"[AlgoConfig] SOURCES: {num_db} from database, {num_default} using defaults, "
            f"{num_fallback} fallback-to-default (invalid DB values), "
            f"{num_fail_closed} fail-closed-defaults (critical safety gates)"
        )

        # Log critical threshold status
        summary = self.get_critical_thresholds_summary()
        logger.info("[AlgoConfig] CRITICAL SAFETY THRESHOLDS (startup verification):")
        for key in sorted(summary.keys()):
            info = summary[key]
            logger.info(
                f"  {key:40s} = {info['value']:>15} "
                f"[{info['min']}, {info['max']}] "
                f"(source: {info['source']:15s} safe_default: {info['safe_default']})"
            )

        # Warn if any critical thresholds are using defaults or fail-closed
        problematic = [k for k, info in summary.items() if info["source"] in ("default", "fail_closed_default")]
        if problematic:
            logger.warning(
                f"[AlgoConfig] ALERT: {len(problematic)} critical thresholds NOT loaded from database "
                f"(using defaults/fail-closed): {sorted(problematic)}. "
                f"Verify algo_config table is properly populated."
            )

    def get(self, key, default=None):
        """Get configuration value with type validation.

        FIXED Issue #8: Validates that the retrieved value matches the expected type.
        If value is missing, returns default. If value exists but has wrong type,
        logs error and returns fail-closed default from VALIDATION_SCHEMA (if critical)
        or the default parameter (if non-critical).

        WARNING: Providing a hardcoded default parameter can hide config load failures.
        Ensures the default matches DEFAULTS to detect misalignment in code.
        """
        if default is not None and key in self.DEFAULTS:
            default_value, _, _ = self.DEFAULTS[key]
            parsed_default = self._parse_value(default_value, self.DEFAULTS[key][1])
            if parsed_default != default:
                logger.warning(
                    f"[CONFIG] Default mismatch for {key!r}: code has {default!r} but DEFAULTS has {parsed_default!r}"
                )

        value = self._config.get(key)
        if value is None:
            # Check if this is a critical parameter using fallback
            if key in self.VALIDATION_SCHEMA:
                is_critical = self.VALIDATION_SCHEMA[key][3]
                if is_critical:
                    logger.warning(
                        f"[CONFIG FALLBACK] Critical parameter {key!r} not in database. "
                        f"Using default: {default!r}. Set via config.set() to override."
                    )
            return default

        # FIXED Issue #8: Validate type safety at retrieval time
        # FIXED Cluster 6: Detect runtime safety gate corruption (zero critical values)
        if key in self.VALIDATION_SCHEMA:
            expected_type = self.VALIDATION_SCHEMA[key][0]
            is_critical = self.VALIDATION_SCHEMA[key][3]
            fail_closed_value = self.VALIDATION_SCHEMA[key][4] if len(self.VALIDATION_SCHEMA[key]) > 4 else None

            # Check if value has correct type
            type_ok = self._check_type(value, expected_type)
            if not type_ok:
                error_msg = (
                    f"[CONFIG TYPE ERROR] {key!r} has type {type(value).__name__}, "
                    f"expected {expected_type}. Value: {value!r}"
                )
                logger.error(error_msg)

                # Return fail-closed value for critical thresholds
                if is_critical and fail_closed_value is not None:
                    logger.warning(
                        f"[CONFIG TYPE ERROR] {key!r} is critical  -” returning fail-closed value {fail_closed_value!r}"
                    )
                    return fail_closed_value
                else:
                    # Return provided default for non-critical values
                    return default

            # Detect safety gate corruption at runtime (critical value set to zero after startup)
            if is_critical and expected_type in ("int", "float"):
                try:
                    f_val = float(value)
                    if abs(f_val) < 0.001:
                        logger.error(
                            f"[CONFIG SAFETY GATE CORRUPTION] Critical parameter {key!r} = {f_val} (zero/near-zero). "
                            f"This disables a safety protection. Returning fail-closed value {fail_closed_value}. "
                            f"Action: Restore valid value in database or run migration-033 to reset to safe defaults."
                        )
                        if fail_closed_value is not None:
                            return fail_closed_value
                except (ValueError, TypeError):
                    pass  # Type validation already caught this above

        return value

    def __getitem__(self, key: str) -> Any:
        """Enable dict-like access: config[key]."""
        value = self._config.get(key)
        if value is None:
            raise KeyError(f"Configuration key {key!r} not found")
        return value

    def __contains__(self, key: str) -> bool:
        """Enable membership testing: key in config."""
        return key in self._config

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value has the expected type without coercion."""
        if expected_type == "int":
            return isinstance(value, int) and not isinstance(value, bool)
        elif expected_type == "float":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        elif expected_type == "bool":
            return isinstance(value, bool)
        elif expected_type == "string":
            return isinstance(value, str)
        return True  # Unknown types pass through

    def override(self, key: str, value: Any) -> None:
        """Apply an in-memory-only override (env var wins over DB). No DB write, no audit.

        Used for command-line args and event-level test overrides that should not persist.
        """
        if key not in self.DEFAULTS:
            logger.warning(f"[CONFIG OVERRIDE] Unknown key {key!r}  -” ignored")
            return
        _, dtype, _ = self.DEFAULTS[key]
        try:
            self._validate_value(key, str(value), dtype)
            self._config[key] = self._parse_value(str(value), dtype)
            self._sources[key] = "override"
            logger.info(f"[CONFIG OVERRIDE] {key} = {value} ({dtype})")
        except ValueError as e:
            logger.error(f"[CONFIG OVERRIDE] Invalid value for {key}: {e}  -” ignored")

    def set(self, key, value, value_type, description="", changed_by="system"):
        """Set configuration value in database, memory, and audit log.

        For critical safety thresholds: if the value is invalid, rejects it and instead
        writes the fail-closed safe default. Returns False to signal that the requested
        value was rejected.

        Args:
            key: Configuration key
            value: New value
            value_type: Type ('int', 'float', 'bool', 'string')
            description: Description (only used for new keys)
            changed_by: Actor making the change (for audit trail)

        Returns: bool (success if value was set as requested; False if rejected/fail-closed)
        """
        try:
            # Validate the requested value
            self._validate_value(key, str(value), value_type)
            final_value = value
            was_fail_closed = False

        except ValueError as e:
            # Value is invalid. For critical thresholds, apply fail-closed default.
            schema_info = self.VALIDATION_SCHEMA.get(key)
            if schema_info and schema_info[3]:  # is_critical
                _, _, _, _, fail_closed = schema_info
                logger.error(
                    f"ALERT: Admin attempted to set critical safety gate {key} = {value}. "
                    f"REJECTED (invalid): {e}. "
                    f"Applying fail-closed default {fail_closed} instead. "
                    f"Actor: {changed_by}"
                )
                final_value = fail_closed
                was_fail_closed = True
            else:
                # Non-critical: just reject and return False
                logger.error(f"Error: Invalid config value for {key}: {e}")
                return False

        try:
            with DatabaseContext("write") as cur:
                # Capture old value for audit trail
                cur.execute("SELECT value FROM algo_config WHERE key = %s", (key,))
                row = cur.fetchone()
                old_value = row[0] if row else None

                # Upsert config value (use final_value which may be fail-closed default)
                cur.execute(
                    """
                    INSERT INTO algo_config (key, value, value_type, description, updated_at, updated_by)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, %s)
                    ON CONFLICT (key) DO UPDATE SET
                        value = EXCLUDED.value,
                        value_type = EXCLUDED.value_type,
                        description = EXCLUDED.description,
                        updated_at = CURRENT_TIMESTAMP,
                        updated_by = EXCLUDED.updated_by
                """,
                    (key, str(final_value), value_type, description, changed_by),
                )

                # Write audit trail (note: include original requested value if fail-closed)
                audit_note = " (FAIL-CLOSED from invalid request)" if was_fail_closed else ""
                cur.execute(
                    """
                    INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                    (key, old_value, str(final_value) + audit_note, changed_by),
                )

            self._config[key] = self._parse_value(str(final_value), value_type)
            self._sources[key] = "database" if not was_fail_closed else "fail_closed_default"
            if was_fail_closed:
                logger.warning(
                    f"[CONFIG SET - FAIL-CLOSED] {key}: requested {value}, set to safe default {final_value}, "
                    f"actor={changed_by}"
                )
                return False
            else:
                logger.info(f"[CONFIG SET] {key} = {final_value} (was {old_value}), actor={changed_by}")
                return True

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def to_dict(self) -> dict:
        """Convert config to dictionary for compatibility with code expecting dict."""
        return dict(self._config)

    def initialize_defaults(self):
        """Initialize all default configs in database."""
        try:
            with DatabaseContext("write") as cur:
                for key, (value, dtype, desc) in self.DEFAULTS.items():
                    cur.execute(
                        """
                        INSERT INTO algo_config (key, value, value_type, description, updated_at, updated_by)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, 'system')
                        ON CONFLICT (key) DO NOTHING
                    """,
                        (key, value, dtype, desc),
                    )
            logger.info(f"[OK] Initialized {len(self.DEFAULTS)} config defaults")
            return True
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    def reload(self):
        """Reload configuration from database with full validation.

        Ensures hot-reloaded values pass the same critical safety checks as startup.
        Invalidates cached specialist configs (RiskConfig, CircuitBreakerConfig, DataPatrolConfig)
        so they re-read updated values on next access.
        """
        self._config.clear()
        self._sources.clear()
        # Invalidate specialist config caches so they refresh on next access
        if hasattr(self, "_risk_config"):
            delattr(self, "_risk_config")
        if hasattr(self, "_circuit_breaker_config"):
            delattr(self, "_circuit_breaker_config")
        if hasattr(self, "_data_patrol_config"):
            delattr(self, "_data_patrol_config")
        if hasattr(self, "_timeout_config"):
            delattr(self, "_timeout_config")
        self._load_defaults()
        self._load_from_database()
        self._validate_critical_thresholds()
        self._validate_config_interdependencies()
        self._audit_config_sources()
        logger.info("[AlgoConfig] Reload completed with validation")

    def get_staleness_windows(self) -> dict[str, int]:
        """Deprecated: Use config.data_patrol.get_staleness_windows() instead.

        Get data patrol staleness thresholds (days) for all data types.
        """
        logger.warning("get_staleness_windows() is deprecated. Use config.data_patrol.get_staleness_windows() instead.")
        return cast(dict[str, int], self.data_patrol.get_staleness_windows())

    def get_coverage_thresholds(self) -> dict[str, int]:
        """Deprecated: Use config.data_patrol.get_coverage_thresholds() instead."""
        logger.warning(
            "get_coverage_thresholds() is deprecated. Use config.data_patrol.get_coverage_thresholds() instead."
        )
        return cast(dict[str, int], self.data_patrol.get_coverage_thresholds())

    def get_price_sanity_config(self) -> dict[str, Any]:
        """Deprecated: Use config.data_patrol.get_price_sanity_config() instead."""
        logger.warning(
            "get_price_sanity_config() is deprecated. Use config.data_patrol.get_price_sanity_config() instead."
        )
        return cast(dict[str, Any], self.data_patrol.get_price_sanity_config())

    def get_volume_config(self) -> dict[str, Any]:
        """Deprecated: Use config.data_patrol.get_volume_config() instead."""
        logger.warning("get_volume_config() is deprecated. Use config.data_patrol.get_volume_config() instead.")
        return cast(dict[str, Any], self.data_patrol.get_volume_config())

    def get_quality_config(self) -> dict[str, Any]:
        """Deprecated: Use config.data_patrol.get_quality_config() instead."""
        logger.warning("get_quality_config() is deprecated. Use config.data_patrol.get_quality_config() instead.")
        return cast(dict[str, Any], self.data_patrol.get_quality_config())

    def get_cross_validation_config(self) -> dict[str, Any]:
        """Deprecated: Use config.data_patrol.get_cross_validation_config() instead."""
        logger.warning(
            "get_cross_validation_config() is deprecated. Use config.data_patrol.get_cross_validation_config() instead."
        )
        return cast(dict[str, Any], self.data_patrol.get_cross_validation_config())

    def get_corporate_actions_config(self) -> dict[str, Any]:
        """Deprecated: Use config.data_patrol.get_corporate_actions_config() instead."""
        logger.warning(
            "get_corporate_actions_config() is deprecated. "
            "Use config.data_patrol.get_corporate_actions_config() instead."
        )
        return cast(dict[str, Any], self.data_patrol.get_corporate_actions_config())

    def get_loader_contracts(self) -> dict[str, dict[str, Any]]:
        """Deprecated: Use config.data_patrol.get_loader_contracts() instead."""
        logger.warning("get_loader_contracts() is deprecated. Use config.data_patrol.get_loader_contracts() instead.")
        return cast(dict[str, dict[str, Any]], self.data_patrol.get_loader_contracts())

    def __repr__(self):
        return f"<AlgoConfig {len(self._config)} keys>"


# Global config instance (thread-safe)
_instance = None
_instance_lock = threading.Lock()


def get_config():
    """Get or create global config instance (thread-safe).

    Uses double-checked locking to prevent race conditions during initialization.
    """
    global _instance
    if _instance is None:
        with _instance_lock:
            # Double-check pattern to avoid race conditions
            if _instance is None:
                _instance = AlgoConfig()
    return _instance


def reset_config() -> None:
    """Reset singleton  -” call at Lambda invocation start so config is fresh each run.

    This ensures warm Lambda invocations reload config from the DB, picking up
    any changes made between invocations (e.g., lowering a risk threshold).
    Thread-safe reset using lock.
    """
    global _instance
    with _instance_lock:
        _instance = None
    logger.info("[AlgoConfig] Singleton reset  -” will reload from DB on next get_config() call")


def get_api_timeout() -> int:
    """Get API request timeout in seconds.

    Delegates to TimeoutConfig.
    """
    return cast(int, get_config().timeout.get_api_timeout())


def get_db_timeout() -> int:
    """Get database connection timeout in seconds.

    Delegates to TimeoutConfig.
    """
    return cast(int, get_config().timeout.get_db_timeout())


def get_market_data_timeout() -> int:
    """Get market data API timeout in seconds.

    Delegates to TimeoutConfig.
    """
    return cast(int, get_config().timeout.get_market_data_timeout())


def get_alpaca_timeout() -> int:
    """Get Alpaca API timeout in seconds.

    Delegates to TimeoutConfig.
    """
    return cast(int, get_config().timeout.get_alpaca_timeout())


def get_webhook_timeout() -> int:
    """Get webhook timeout in seconds.

    Delegates to TimeoutConfig.
    """
    return cast(int, get_config().timeout.get_webhook_timeout())


def get_subprocess_timeout() -> int:
    """Get subprocess timeout in seconds.

    Delegates to TimeoutConfig.
    """
    return cast(int, get_config().timeout.get_subprocess_timeout())


def get_alpaca_base_url() -> str:
    """Get Alpaca API base URL from unified config.

    Delegates to config/api_endpoints.py (single source of truth for all external APIs).
    """
    from config.api_endpoints import get_alpaca_base_url as get_unified_url

    return get_unified_url()


if __name__ == "__main__":
    config = get_config()
    config.initialize_defaults()
    logger.info("\nConfiguration Summary:")
    logger.info("=" * 60)
    for key, val in sorted(config.to_dict().items()):
        logger.info(f"  {key:.<40} {val}")
    logger.info("=" * 60)
