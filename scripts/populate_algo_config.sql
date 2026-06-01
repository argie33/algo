-- Populate algo_config table with default values
-- This script initializes all configuration parameters for the algo system
-- Run with: psql -h <host> -U <user> -d <dbname> -f populate_algo_config.sql

BEGIN;

-- Risk Management
INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES
  ('base_risk_pct', '0.75', 'float', 'Base portfolio risk per trade', 'init-script'),
  ('max_position_size_pct', '8.0', 'float', 'Maximum single position size', 'init-script'),
  ('max_positions', '12', 'int', 'Maximum concurrent positions', 'init-script'),
  ('max_concentration_pct', '50.0', 'float', 'Max concentration in top position', 'init-script')
ON CONFLICT (key) DO NOTHING;

-- Drawdown Defense (Circuit Breakers)
INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES
  ('halt_drawdown_pct', '20.0', 'float', 'Portfolio drawdown % to halt trading (CB1)', 'init-script'),
  ('risk_reduction_at_minus_5', '0.75', 'float', 'Risk % at -5% drawdown', 'init-script'),
  ('risk_reduction_at_minus_10', '0.5', 'float', 'Risk % at -10% drawdown', 'init-script'),
  ('risk_reduction_at_minus_15', '0.25', 'float', 'Risk % at -15% drawdown', 'init-script'),
  ('risk_reduction_at_minus_20', '0.0', 'float', 'Risk % at -20% drawdown (halt)', 'init-script')
ON CONFLICT (key) DO NOTHING;

-- Filter Thresholds (Critical for signal quality)
INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES
  ('min_completeness_score', '70', 'int', 'Minimum data completeness % (Minervini standard)', 'init-script'),
  ('min_stock_price', '5.0', 'float', 'Minimum stock price $', 'init-script'),
  ('min_signal_quality_score', '60', 'int', 'Minimum SQS 0-100 (signal quality gate)', 'init-script'),
  ('min_volume_ma_50d', '300000', 'int', 'Minimum 50-day avg volume', 'init-script'),
  ('min_avg_daily_dollar_volume', '500000', 'float', 'Minimum daily dollar volume for liquidity gate', 'init-script'),
  ('require_stock_stage_2', 'true', 'bool', 'Require Stage 2 trend template', 'init-script'),
  ('max_stop_distance_pct', '12.0', 'float', 'Max stop distance % from entry', 'init-script'),
  ('max_positions_per_sector', '5', 'int', 'Max concurrent positions in one sector', 'init-script'),
  ('max_positions_per_industry', '3', 'int', 'Max concurrent positions in one industry', 'init-script'),
  ('min_swing_score', '55.0', 'float', 'Min swing trader score to enter (regime manager may raise this)', 'init-script'),
  ('min_swing_grade', '', 'string', 'Min swing grade override (empty=use exposure tier default)', 'init-script'),
  ('max_total_invested_pct', '95.0', 'float', 'Max % of portfolio in open positions', 'init-script')
ON CONFLICT (key) DO NOTHING;

-- Market Conditions
INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES
  ('max_distribution_days', '4', 'int', 'Max market distribution days', 'init-script'),
  ('require_stage_2_market', 'false', 'bool', 'Require market Stage 2 at Tier 2', 'init-script'),
  ('vix_max_threshold', '35.0', 'float', 'VIX level to halt trading', 'init-script'),
  ('vix_caution_threshold', '25.0', 'float', 'VIX level to reduce positions', 'init-script'),
  ('vix_caution_risk_reduction', '0.75', 'float', 'Risk multiplier when VIX > caution threshold', 'init-script')
ON CONFLICT (key) DO NOTHING;

-- Entry Rules (Minervini Standard)
INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES
  ('require_sma50_above_sma200', 'true', 'bool', 'Price and MA alignment', 'init-script'),
  ('min_percent_from_52w_low', '30.0', 'float', 'Min % from 52w low (Minervini standard)', 'init-script'),
  ('max_percent_from_52w_high', '25.0', 'float', 'Max % from 52w high', 'init-script'),
  ('min_trend_template_score', '6', 'int', 'Min Minervini score 0-8 (6+ balanced, 7+ strict)', 'init-script')
ON CONFLICT (key) DO NOTHING;

-- Entry Quality Gates (Tier 3 Critical)
INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES
  ('max_signal_age_days', '3', 'int', 'Reject BUY signals older than N days', 'init-script'),
  ('min_close_quality_pct', '60.0', 'float', 'Close must be in upper N% of range', 'init-script'),
  ('min_breakout_volume_ratio', '1.25', 'float', 'Volume must be N x 50-day average', 'init-script'),
  ('require_weekly_stage_2', 'true', 'bool', 'Require weekly chart Stage 2', 'init-script'),
  ('min_rs_line_slope_days', '10', 'int', 'Days for RS line slope check', 'init-script'),
  ('max_rs_pct_from_60d_high', '15.0', 'float', 'Max % RS-line below 60d high (Minervini strict = 5%)', 'init-script')
ON CONFLICT (key) DO NOTHING;

-- Exit Rules
INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES
  ('require_target_pullback', 'false', 'bool', 'Require 2%+ pullback before partial profit exits', 'init-script'),
  ('t1_target_r_multiple', '1.5', 'float', 'Tier 1 profit target R-mult', 'init-script'),
  ('t2_target_r_multiple', '3.0', 'float', 'Tier 2 profit target R-mult', 'init-script'),
  ('t3_target_r_multiple', '4.0', 'float', 'Tier 3 profit target R-mult', 'init-script'),
  ('min_hold_days', '1', 'int', 'Minimum days to hold', 'init-script'),
  ('max_hold_days', '20', 'int', 'Max days to hold position', 'init-script'),
  ('exit_on_distribution_day', 'true', 'bool', 'Exit on market distribution', 'init-script'),
  ('exit_on_rs_line_break_50dma', 'true', 'bool', 'Exit when RS line breaks 50-DMA', 'init-script'),
  ('exit_on_td_sequential', 'true', 'bool', 'Exit on TD Sequential 9/13 exhaustion', 'init-script'),
  ('use_chandelier_trail', 'true', 'bool', 'Use chandelier ATR trailing stop', 'init-script'),
  ('switch_to_21ema_after_days', '10', 'int', 'Days before switching chandelier to 21-EMA', 'init-script'),
  ('chandelier_atr_mult', '3.0', 'float', 'ATR multiplier for chandelier stop', 'init-script'),
  ('move_be_at_r', '1.0', 'float', 'R-multiple to trigger breakeven stop raise', 'init-script')
ON CONFLICT (key) DO NOTHING;

-- Advanced Filters (Feature 7)
INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES
  ('enable_advanced_filters', 'true', 'bool', 'Enable advanced quality filters (momentum, quality, catalyst, risk)', 'init-script'),
  ('require_strong_sector', 'false', 'bool', 'Require position in top 5 sectors (false = all sectors OK)', 'init-script'),
  ('strong_sector_top_n', '5', 'int', 'Number of top sectors to use for sector strength filter', 'init-script'),
  ('block_days_before_earnings', '5', 'int', 'Block entry N days before earnings', 'init-script'),
  ('max_extension_above_50ma_pct', '15.0', 'float', 'Max extension above 50-DMA %', 'init-script')
ON CONFLICT (key) DO NOTHING;

-- Feature Flags
INSERT INTO algo_config (key, value, value_type, description, updated_by)
VALUES
  ('bypass_stage_2_filter', 'false', 'bool', 'Force-test: bypass Stage 2 requirement (never for production)', 'init-script')
ON CONFLICT (key) DO NOTHING;

COMMIT;

SELECT COUNT(*) as config_count FROM algo_config;
