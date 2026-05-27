# Database Schema Issues - Consolidated (2026-05-27)

## Summary

**156 redundant ALTER TABLE statements consolidated into CREATE TABLE definitions** across both `terraform/modules/database/init.sql` and `lambda/db-init/schema.sql`.

This ensures fresh database installations have complete schemas from the start, without requiring ALTER statements that could fail if interrupted between CREATE TABLE and ALTER execution.

## Schema Consolidation Completed

### ✅ buy_sell_daily, buy_sell_weekly, buy_sell_monthly (159 columns total)

**Before**: 
- buy_sell_daily: 7 columns in CREATE TABLE + 52 via ALTER TABLE
- buy_sell_weekly: 7 columns in CREATE TABLE + 52 via ALTER TABLE  
- buy_sell_monthly: 7 columns in CREATE TABLE + 52 via ALTER TABLE

**After**:
- All 59 columns now in single CREATE TABLE statement
- 156 redundant ALTER TABLE statements removed

**Impact**: HIGH - These core signal tables now have complete schema from fresh install

**Consolidated Columns Include**:
- Signal metadata: timeframe, signal, signal_triggered_date, signal_type, signal_strength
- Price levels: entry_price, buylevel, stoplevel, sell_level, pivot_price, buy_zone_start/end
- Stop/target management: initial_stop, trailing_stop, exit_trigger_*_price, profit_target_*
- Price/volume: open, high, low, close, volume, avg_volume_50d
- Technicals: rsi, adx, atr, sma_50, sma_200, ema_21, pct_from_ema21, pct_from_sma50, mansfield_rs
- Quality scores: sata_score, rs_rating, entry_quality_score, signal_quality_score, risk_reward_ratio
- Position tracking: inposition, position_size_recommendation, current_gain_pct, days_in_position
- Market context: base_type, base_length_days, stage_number, stage_confidence, substage, market_stage

### ✅ Redundant ALTER Statements Removed

**stock_scores**:
- data_completeness and rs_percentile already in CREATE TABLE
- Removed 2 redundant ALTERs

**data_loader_runs**:
- run_id, table_name, source_api, parameters, start_at already in CREATE TABLE
- Removed 5 redundant ALTERs

**backtest_runs**:
- All columns (strategy_name, start_date, end_date, financial metrics, trade counts, created_at) already in CREATE TABLE
- Removed 14 redundant ALTERs

**backtest_trades**:
- quantity and profit_loss_percent already in CREATE TABLE
- Removed 2 redundant ALTERs

**technical_data_daily/weekly/monthly**:
- close and ema_21 columns already in CREATE TABLE
- Removed 6 redundant ALTERs

**algo_trades**:
- mfe_pct and mae_pct already in CREATE TABLE
- Removed 2 redundant ALTERs

## Remaining ALTER Statements (24 total - all legitimate)

These 24 ALTERs are for:
1. **Backward compatibility** - Adding columns to existing production tables
2. **Schema fixes** - Columns referenced by code but missing from original schema
3. **Financial data tables** - annual_balance_sheet, quarterly_balance_sheet, quarterly_cash_flow
4. **Performance tracking** - algo_performance_daily, algo_positions, sector_ranking
5. **Sentiment/economic** - analyst_sentiment_analysis, economic_calendar

These ALTERs are correctly placed and NOT part of fresh-install issues.

## Files Modified

- ✅ `terraform/modules/database/init.sql` - Core production schema
- ✅ `lambda/db-init/schema.sql` - Lambda deployment schema (now in sync)

## Fresh Install Guarantee

After these changes, fresh database setup ensures:
1. ✅ buy_sell_* tables created with all 59 columns (no follow-up ALTERs needed)
2. ✅ technical_data_* tables have close and ema_21 columns
3. ✅ All core signal/trading tables complete from CREATE TABLE
4. ✅ No UndefinedColumn errors on API queries or orchestrator phases
5. ✅ Data loaders can run without schema errors

## Related Issues Fixed

- Resolves: Fresh database setup missing critical columns
- Prevents: UndefinedColumn errors for buy_sell_* and technical_data_* tables
- Supports: Orchestrator phases 2-7 without column reference errors
- Enables: Clean deployments to new RDS instances

## How This Helps

**Before**: Fresh RDS → CREATE tables with 7 cols → Interrupt or race condition → Tables incomplete → Loaders fail with "column does not exist"

**After**: Fresh RDS → CREATE tables with all 59+ cols → Complete from the start → Loaders run successfully

Schema consolidation eliminates the "gap" where ALTERs could fail, ensuring schema integrity from first instance.
