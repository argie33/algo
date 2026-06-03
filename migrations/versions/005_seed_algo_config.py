#!/usr/bin/env python3
"""
Migration 005: Seed algo_config table with all default values.

AlgoConfig falls back to Python DEFAULTS when the DB table is empty, so trading
is not blocked by an empty table. However, the table being empty means hot-reload
configuration changes via the database have no effect (overwrites require existing
rows). This migration populates all DEFAULTS as the initial DB state using
ON CONFLICT DO NOTHING so it is safe to run on an already-populated table.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.database_context import DatabaseContext

DESCRIPTION = "Seed algo_config table with all default configuration values"

# Mirrors AlgoConfig.DEFAULTS exactly. ON CONFLICT DO NOTHING keeps existing values.
_DEFAULTS = [
    # Risk Management
    ('base_risk_pct', '0.75', 'float', 'Base portfolio risk per trade'),
    ('max_position_size_pct', '8.0', 'float', 'Maximum single position size'),
    ('max_positions', '12', 'int', 'Maximum concurrent positions'),
    ('max_concentration_pct', '50.0', 'float', 'Max concentration in top position'),
    # Drawdown Defense
    ('halt_drawdown_pct', '20.0', 'float', 'Portfolio drawdown % to halt trading (CB1)'),
    ('risk_reduction_at_minus_5', '0.75', 'float', 'Risk % at -5% drawdown'),
    ('risk_reduction_at_minus_10', '0.5', 'float', 'Risk % at -10% drawdown'),
    ('risk_reduction_at_minus_15', '0.25', 'float', 'Risk % at -15% drawdown'),
    ('risk_reduction_at_minus_20', '0.0', 'float', 'Risk % at -20% drawdown (halt)'),
    # Filter Thresholds
    ('min_completeness_score', '70', 'int', 'Minimum data completeness %'),
    ('min_stock_price', '5.0', 'float', 'Minimum stock price $'),
    ('min_signal_quality_score', '60', 'int', 'Minimum SQS 0-100'),
    ('min_volume_ma_50d', '300000', 'int', 'Minimum 50-day avg volume'),
    ('min_avg_daily_dollar_volume', '500000', 'float', 'Minimum daily dollar volume'),
    ('require_stock_stage_2', 'true', 'bool', 'Require Stage 2 trend template'),
    ('max_stop_distance_pct', '12.0', 'float', 'Max stop distance % from entry'),
    ('max_positions_per_sector', '5', 'int', 'Max concurrent positions in one sector'),
    ('max_positions_per_industry', '3', 'int', 'Max concurrent positions in one industry'),
    ('min_swing_score', '55.0', 'float', 'Min swing trader score to enter'),
    ('min_swing_grade', '', 'string', 'Min swing grade override (empty=use exposure tier default)'),
    ('max_total_invested_pct', '95.0', 'float', 'Max % of portfolio in open positions'),
    # Market Conditions
    ('max_distribution_days', '4', 'int', 'Max market distribution days'),
    ('require_stage_2_market', 'false', 'bool', 'Require market Stage 2 at Tier 2'),
    ('vix_max_threshold', '35.0', 'float', 'VIX level to halt trading'),
    ('vix_caution_threshold', '25.0', 'float', 'VIX level to reduce positions'),
    ('vix_caution_risk_reduction', '0.75', 'float', 'Risk multiplier when VIX > caution threshold'),
    # Entry Rules (Minervini)
    ('require_sma50_above_sma200', 'true', 'bool', 'Price and MA alignment'),
    ('min_percent_from_52w_low', '0.0', 'float', 'Min % from 52w low (Minervini allows 52w lows with RS strength)'),
    ('max_percent_from_52w_high', '25.0', 'float', 'Max % from 52w high'),
    ('min_trend_template_score', '7', 'int', 'Min Minervini score 0-8'),
    # Entry Quality Gates
    ('max_signal_age_days', '3', 'int', 'Reject BUY signals older than N days'),
    ('min_close_quality_pct', '60.0', 'float', 'Close must be in upper N% of range'),
    ('min_breakout_volume_ratio', '1.25', 'float', 'Volume must be N x 50-day average'),
    ('require_weekly_stage_2', 'true', 'bool', 'Require weekly chart Stage 2'),
    ('min_rs_line_slope_days', '10', 'int', 'Days for RS line slope check'),
    ('max_rs_pct_from_60d_high', '15.0', 'float', 'Max % RS-line below 60d high'),
    ('rs_slope_gate_enabled', 'true', 'bool', 'Hard-gate T3 on RS line trending up (set false during strong SPY runs)'),
    ('volume_decay_gate_enabled', 'true', 'bool', 'Hard-gate T3 on volume decay into breakout (set false to soften)'),
    # Exit Rules
    ('require_target_pullback', 'false', 'bool', 'Require 2%+ pullback before partial profit exits'),
    ('t1_target_r_multiple', '1.5', 'float', 'Tier 1 profit target R-mult'),
    ('t2_target_r_multiple', '3.0', 'float', 'Tier 2 profit target R-mult'),
    ('t3_target_r_multiple', '4.0', 'float', 'Tier 3 profit target R-mult'),
    ('imported_position_default_stop_loss_pct', '5.0', 'float', 'Default stop loss % for imported positions'),
    ('imported_position_default_target_1_pct', '5.0', 'float', 'Default target 1 % for imported positions'),
    ('imported_position_default_target_2_pct', '10.0', 'float', 'Default target 2 % for imported positions'),
    ('imported_position_default_target_3_pct', '15.0', 'float', 'Default target 3 % for imported positions'),
    ('min_hold_days', '1', 'int', 'Minimum days to hold'),
    ('max_hold_days', '20', 'int', 'Max days to hold position'),
    ('exit_on_distribution_day', 'true', 'bool', 'Exit on market distribution'),
    ('exit_on_rs_line_break_50dma', 'true', 'bool', 'Exit when RS line breaks 50-DMA'),
    ('exit_on_td_sequential', 'true', 'bool', 'Exit on TD Sequential 9/13 exhaustion'),
    ('use_chandelier_trail', 'true', 'bool', 'Use chandelier ATR trailing stop'),
    ('switch_to_21ema_after_days', '10', 'int', 'Days before switching chandelier to 21-EMA'),
    ('eight_week_rule_threshold_pct', '20.0', 'float', 'ONeill 8-week hold threshold %'),
    ('eight_week_rule_window_days', '21', 'int', 'Days to check for 20%+ gain'),
    ('chandelier_atr_mult', '3.0', 'float', 'ATR multiplier for chandelier stop'),
    ('move_be_at_r', '1.0', 'float', 'R-multiple to trigger breakeven stop raise'),
    # Pyramid Entry
    ('pyramid_enabled', 'true', 'bool', 'Enable multi-entry pyramiding'),
    ('pyramid_split_pct', '50,33,17', 'string', 'Entry size split %'),
    ('pyramid_add_1_gain_pct', '2.0', 'float', 'Gain % to trigger Add #1'),
    ('pyramid_add_2_gain_pct', '3.0', 'float', 'Additional gain % to trigger Add #2'),
    # Drawdown Re-engagement
    ('re_engage_recovery_pct', '8.0', 'float', '% recovery from peak to resume trading'),
    ('re_engage_min_days', '5', 'int', 'Min days after halt before re-engagement'),
    ('require_ftd_to_re_engage', 'true', 'bool', 'Require Follow-Through Day signal'),
    # Circuit Breaker Thresholds
    ('max_daily_loss_pct', '2.0', 'float', 'Max daily loss % before halt'),
    ('max_consecutive_losses', '3', 'int', 'Max consecutive losing trades'),
    ('min_win_rate_pct', '40.0', 'float', 'Min win rate % to trade'),
    ('max_total_risk_pct', '4.0', 'float', 'Max total open risk %'),
    ('max_weekly_loss_pct', '5.0', 'float', 'Max weekly loss % before halt'),
    ('max_data_staleness_days', '3', 'int', 'Max data age in days'),
    ('daily_profit_cap_pct', '2.0', 'float', 'Daily profit cap %'),
    ('sector_drawdown_halt_pct', '-12.0', 'float', 'Sector drawdown % to halt trading'),
    # Position Monitoring & Re-entry
    ('position_halt_flag_count', '2', 'int', 'Flags to propose early exit'),
    ('max_reentries_per_name', '2', 'int', 'Max times to re-enter same symbol'),
    ('min_days_before_reentry_same_symbol', '5', 'int', 'Days to wait before re-entering symbol'),
    # Economic Calendar & Earnings
    ('halt_entries_before_major_release_minutes', '60', 'int', 'Halt entries N minutes before major release'),
    ('earnings_blackout_days_before', '7', 'int', 'Days before earnings to block entries'),
    ('earnings_blackout_days_after', '3', 'int', 'Days after earnings to block entries'),
    # Liquidity & Quality Gates
    ('min_price_history_days', '200', 'int', 'Min trading days of price history (IPO age gate)'),
    ('min_daily_volume_shares', '500000', 'int', 'Minimum daily volume shares'),
    ('max_spread_pct', '0.5', 'float', 'Maximum bid-ask spread %'),
    ('min_market_cap_millions', '300.0', 'float', 'Minimum market cap $M'),
    ('min_float_millions', '50.0', 'float', 'Minimum float shares $M'),
    ('max_short_interest_pct', '30.0', 'float', 'Maximum short interest %'),
    # Advanced Filters
    ('block_days_before_earnings', '5', 'int', 'Block entries N days before earnings'),
    ('max_extension_above_50ma_pct', '15.0', 'float', 'Max extension above 50-DMA %'),
    ('strong_sector_top_n', '5', 'int', 'Top N sectors count as strong'),
    # Swing Trader Score Weights
    ('swing_weight_setup', '25', 'int', 'Swing score: Setup quality weight %'),
    ('swing_weight_trend', '20', 'int', 'Swing score: Trend quality weight %'),
    ('swing_weight_momentum', '20', 'int', 'Swing score: Momentum/RS weight %'),
    ('swing_weight_volume', '12', 'int', 'Swing score: Volume weight %'),
    ('swing_weight_fundamentals', '10', 'int', 'Swing score: Fundamentals weight %'),
    ('swing_weight_sector', '8', 'int', 'Swing score: Sector/industry weight %'),
    ('swing_weight_multi_timeframe', '5', 'int', 'Swing score: Multi-timeframe weight %'),
    ('swing_min_trend_score', '5', 'int', 'Swing score: Minimum Minervini trend score 0-8'),
    ('swing_min_industry_rank', '100', 'int', 'Swing score: Industry rank threshold (<=)'),
    ('swing_days_to_earnings_block', '5', 'int', 'Swing score: Block entries N days to earnings'),
    # Execution
    ('execution_mode', 'auto', 'string', 'paper|dry|review|auto'),
    ('alpaca_paper_trading', 'false', 'bool', 'Use Alpaca paper account'),
    ('max_trades_per_day', '5', 'int', 'Max new trades per day'),
    ('default_portfolio_value', '100000.0', 'float', 'Bootstrap portfolio value when Alpaca unreachable'),
    # Feature Flags
    ('enable_algo', 'true', 'bool', 'Enable algo trading'),
    ('enable_backtesting', 'false', 'bool', 'Enable backtest mode'),
    ('verbose_logging', 'true', 'bool', 'Detailed logging'),
    # Network
    ('api_request_timeout_seconds', '5', 'int', 'HTTP request timeout (seconds)'),
    ('db_connection_timeout_seconds', '15', 'int', 'Database connection timeout (seconds)'),
]


def up():
    with DatabaseContext('write') as cur:
        for key, value, value_type, description in _DEFAULTS:
            cur.execute(
                """
                INSERT INTO algo_config (key, value, value_type, description, updated_by)
                VALUES (%s, %s, %s, %s, 'migration-005')
                ON CONFLICT (key) DO NOTHING
                """,
                (key, value, value_type, description),
            )


def down():
    with DatabaseContext('write') as cur:
        cur.execute(
            "DELETE FROM algo_config WHERE updated_by = 'migration-005'"
        )
