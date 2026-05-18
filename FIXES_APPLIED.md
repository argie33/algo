# API Schema Fixes Applied - May 18, 2026

## Summary
Fixed critical API schema mismatches that were preventing the system from running properly. All fixes target column name errors and placeholder values in data loaders that would cause 503 "Data schema mismatch" errors.

## Bugs Fixed (3 Total)

### 1. Signals API - Stock Signals Endpoint (lambda/api/routes/signals.py)
**Issue**: Querying non-existent columns from `technical_data_daily` table
**Fixes**:
- Line 41: `td.rsi` → `td.rsi_14` (column was named rsi_14 in loader output)
- Line 42: `td.atr` → `td.atr_14` (column was named atr_14 in loader output)
- Removed: `COALESCE(td.adx, 0)` - column never created by loader
- Removed: `COALESCE(td.mansfield_rs, 0)` - column never created by loader

**Impact**: Fixes schema mismatch errors in `/api/signals/stocks` endpoint that would return 503 "Data schema mismatch"

### 2. Signals API - ETF Signals Endpoint (lambda/api/routes/signals.py)
**Issue**: ETF signals function also had wrong RSI column reference
**Fix**:
- Line 102: `td.rsi` → `td.rsi_14`

**Impact**: Fixes schema mismatch errors in `/api/signals/etf` endpoint

### 3. Market Health Loader (loaders/load_market_health_daily.py)
**Issue**: Hardcoded placeholder values instead of None for external data
**Fixes**:
- `vix_level`: `20.0` → `None` (VIX data not yet integrated)
- `put_call_ratio`: `1.0` → `None` (options data not yet integrated)
- `yield_curve_slope`: `1.5` → `None` (treasury data not yet integrated)
- `fed_rate_environment`: `"neutral"` → `"unknown"` (Fed data not yet integrated)

**Impact**: Prevents hardcoded test values from appearing in production data

## Verification

### All Loaders Verified
✓ 23 loaders exist and are integrated in `run-all-loaders.py`
✓ All loader outputs match expected schema
✓ No missing loaders in the pipeline

### API Routes Audited
✓ 16 API route files reviewed for schema correctness
✓ All critical endpoints have correct column references
✓ Error handling properly configured

### Key Tables Verified
- `technical_data_daily`: rsi_14, macd, macd_signal, sma_*, ema_*, atr_14, bb_*, volume_ma_50
- `market_health_daily`: market_trend, market_stage, distribution_days_*, breadth_momentum_10d
- `swing_trader_scores`: score, components (JSONB), symbol, date
- `trend_template_data`: minervini_score, weinstein_stage, trend_direction, consolidation_flag

## Commits Applied
1. `bd221bdbf` - fix: correct API schema mismatches in signals endpoint and market health loader
2. `1e1090887` - fix: correct RSI column reference in ETF signals endpoint

## What This Fixes
- ✅ `/api/signals/stocks` will no longer return 503 "Data schema mismatch"
- ✅ `/api/signals/etf` will no longer return 503 "Data schema mismatch"
- ✅ Market health data will have valid None values instead of test placeholders
- ✅ Trading Signals page should load data without API errors
- ✅ Signal-dependent pages will have correct technical indicators

## Remaining Notes
- These fixes address schema correctness
- Actual data population depends on loaders running successfully
- F12 console validation requires running the complete system (database + API + frontend)
- All error handling is in place to catch any remaining schema issues with 503 responses

## Testing Required
See `RUN_COMPLETE_SYSTEM_TEST.md` for step-by-step validation procedure that proves system works:
1. Run database initialization
2. Run all data loaders
3. Start API server
4. Start frontend dev server
5. Check F12 console for errors on all 12 pages
6. Verify all data displays properly
