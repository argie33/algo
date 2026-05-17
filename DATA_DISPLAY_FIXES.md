# Data Display Issues - Root Cause Analysis & Fixes

## Summary
Missing data in frontend pages (Markets Health, Trading Signals, etc.) was caused by:
1. **Database schema missing signal detail columns** - buy_sell_daily table only had basic columns (id, symbol, date, signal, strength, reason)
2. **API queries not selecting all available columns** - Queries were incomplete or referencing non-existent columns
3. **Market data endpoint returning wrong table** - /api/algo/markets was querying price_daily instead of market_exposure_daily

## Root Causes Identified

### 1. TradingSignals Page Issues
**Expected columns (not in database):**
- buylevel, stoplevel, risk_reward_ratio, volume_surge_pct
- base_type, base_length_days
- entry_quality_score, signal_quality_score
- buy_zone_start, buy_zone_end, pivot_price
- initial_stop, trailing_stop, position_size_recommendation
- profit_target_8pct/20pct/25pct
- exit_trigger_1_price, exit_trigger_2_price, sell_level
- rs_rating, avg_volume_50d
- signal_triggered_date (separate from date)

**Why:** No loader was writing this data; columns don't exist in buy_sell_daily schema

### 2. MarketsHealth Page Issues
**Expected data structure:**
- current market regime (exposure_pct, raw_score, regime, distribution_days, factors)
- 60-day exposure history
- active tier info

**Why:** /api/algo/markets endpoint was querying price_daily (OHLCV data) instead of market_exposure_daily

### 3. Technical Indicators
**Missing column:** ema_21 (table only had ema_12 and ema_26)

## Fixes Applied

### Commit: b7422ab (API Query Enhancements)

#### 1. Updated `/api/signals/stocks` Query (lambda_function.py:2066-2118)
- Added 24 new columns to SELECT statement with COALESCE defaults
- Maps missing columns from buy_sell_daily with NULL defaults:
  ```python
  COALESCE(bsd.buylevel, 0) as buylevel,
  COALESCE(bsd.base_type, NULL) as base_type,
  ... (all signal detail columns)
  ```
- Added technical indicators: ema_21, mansfield_rs
- Added signal_triggered_date field

**Result:** API now returns complete data structure. Missing columns show NULL/0 until database is populated.

#### 2. Fixed `/api/algo/markets` Endpoint (lambda_function.py:1592-1633)
- Changed query from price_daily → market_exposure_daily
- Now returns:
  - current: Latest market regime snapshot
  - history: 60-day exposure trend data
- Properly exposes exposure_pct, regime, distribution_days, etc.

**Result:** MarketsHealth page now receives proper market regime data.

#### 3. Added Missing Technical Indicator
- ema_21 selection added to technical data joins

## Still To Do

### 1. ✅ Database Schema Updates (Script Created)
**File:** utils/migrate_signal_columns.sql

Run this SQL to add missing columns:
```bash
psql $DATABASE_URL < utils/migrate_signal_columns.sql
```

Or via database init:
```bash
python3 init_database.py
```

### 2. ❌ Populate Signal Detail Columns
**Status:** Not implemented - no loader writes these columns

**Needed:** Create/update loader to populate:
- Chart pattern data (base_type, base_length_days)
- Entry/exit levels (buylevel, stoplevel, buy_zone_start, sell_level, etc.)
- Risk metrics (risk_reward_ratio, rs_rating)
- Volume metrics (volume_surge_pct, avg_volume_50d)
- Profit targets (profit_target_8pct/20pct/25pct)
- Score data (entry_quality_score, signal_quality_score)

**Options:**
- Option A: Create new loader that analyzes buy_sell_daily signals and computes these values
- Option B: Have Pine Script/signal generator provide this data directly

### 3. ❌ Populate EMA 21 Data
**Status:** Column added but not populated by loaders

**Fix:** Update technical indicator loader to calculate and store ema_21

### 4. ❌ Populate Market Exposure Data
**Status:** market_exposure_daily table exists but may be empty

**Fix:** Verify market exposure calculation is running and populating daily:
```bash
python3 scripts/market_exposure_calculator.py --mode daily
```

## Verification Steps

### 1. Apply Database Schema
```bash
python3 init_database.py
```
Or:
```bash
psql $DATABASE_URL < utils/migrate_signal_columns.sql
```

### 2. Verify API Response Structure
```bash
# Should now include all signal columns
curl http://localhost:3001/api/signals/stocks?limit=1 | jq '.items[0]'

# Should have current market data
curl http://localhost:3001/api/algo/markets | jq '.current'
```

### 3. Test Frontend Pages
- **TradingSignals**: Check if table displays all columns (they'll show 0/null until loaders populate)
- **MarketsHealth**: Check if exposure chart renders and shows regime data
- **Stock Detail**: Check if technical indicators display ema_21

## Testing Checklist
- [ ] Database schema applied (columns exist)
- [ ] /api/signals/stocks returns all expected columns
- [ ] /api/algo/markets returns market_exposure_daily data
- [ ] TradingSignals page renders without errors
- [ ] MarketsHealth page renders without errors
- [ ] Technical indicators display properly
- [ ] All null/0 values handle gracefully in UI

## Next Steps
1. Run database migration to add columns
2. Update loaders to populate signal detail columns (if available from Pine Script)
3. Verify market exposure pipeline is running
4. Test frontend pages and fix any remaining UI issues
5. Monitor for errors in browser console / server logs

## Files Modified
- `lambda/api/lambda_function.py` - API query fixes
- `utils/migrate_signal_columns.sql` - Schema migration (not committed)

## Files To Create/Update
- Loader for signal details (chart patterns, entry/exit levels)
- Technical indicator loader (ensure ema_21 is calculated)
- Market exposure calculator (ensure it's running daily)
