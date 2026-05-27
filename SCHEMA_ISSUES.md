# Database Schema Issues - Fresh Setup

## Problem

When setting up a fresh database, columns are being added via ALTER TABLE statements instead of being included in the initial CREATE TABLE. This causes fresh installations to be incomplete.

## Fixed Issues

✅ **market_exposure_daily** (6 columns)
- Columns: exposure_pct, raw_score, regime, distribution_days, factors, halt_reasons  
- Fixed in commit 7fbb2ada0

## Remaining Issues (Priority Order)

### 1. **buy_sell_daily, buy_sell_weekly, buy_sell_monthly** (53, 52, 52 columns each)
**Impact**: HIGH - These tables have 50+ columns added via ALTER that should be in CREATE TABLE

ALTER columns being added:
- timeframe, signal_triggered_date, signal_type, signal_strength, entry_price
- buylevel, stoplevel, sell_level, inposition, initial_stop, trailing_stop
- exit_trigger_*_price (4 variants), pivot_price, buy_zone_start, buy_zone_end
- profit_target_8pct, profit_target_20pct, profit_target_25pct
- open, high, low, close, volume, avg_volume_50d
- rsi, adx, atr, sma_50, sma_200, ema_21, pct_from_ema21, pct_from_sma50
- mansfield_rs, sata_score, rs_rating, base_type, base_length_days
- breakout_quality, risk_reward_ratio, risk_pct, entry_quality_score
- position_size_recommendation, current_gain_pct, days_in_position
- stage_number, stage_confidence, substage, market_stage, macd, macd_signal

**Fix**: Move all 53 columns from ALTER TABLE statements into CREATE TABLE

### 2. **backtest_runs** (14 columns)
**Impact**: MEDIUM

ALTER columns: various backtest metrics

### 3. **data_loader_runs** (5 columns)  
**Impact**: LOW

ALTER columns: run_id, table_name, source_api, parameters, start_at

### 4. **stock_scores, algo_trades, algo_positions, algo_performance_daily** (2-3 columns each)
**Impact**: LOW

Minor columns added via ALTER

## Why This Matters

When setting up a **fresh database** from schema:
1. CREATE TABLE is executed first → table exists with basic columns only
2. ALTER TABLE statements run later → columns are added
3. If there's an error or interruption between these steps → incomplete schema
4. API queries expect all columns → UndefinedColumn errors → data display breaks

## Solution

Move all columns into the initial CREATE TABLE statement. This ensures fresh installations are complete from the start.

## Recommended Action

Priority 1: Fix buy_sell_daily and related tables (biggest impact)
- This is a large refactoring of 159 total columns across 3 tables
- Requires careful consolidation of ALTER statements into CREATE TABLE

Can be done in incremental PRs focused on one table family at a time.
