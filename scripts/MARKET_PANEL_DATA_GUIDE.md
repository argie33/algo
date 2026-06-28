# Markets Panel - Real Data Loading Guide

## Problem
The markets panel shows blank values for some factors because critical market data is not fully populated in the database:
- **VIX Level**: Only in 80/1283 rows (93% missing for historical dates)
- **Put/Call Ratio**: 0 rows (completely missing)

When these data sources are unavailable, the market factors return `None` scores and are skipped from the dashboard display.

## Solution
Ensure all required market data is loaded into the database before running the algo orchestrator.

## Critical Data Sources

### 1. VIX (^VIX) Price Data
**Location**: `price_daily` table, symbol = '^VIX'  
**Requirement**: Required for market factor calculation (VIX regime, circuit breaker halt logic)  
**Current Status**: ✓ 85 prices available, but market_health_daily only has VIX level in 80 rows

**To load/refresh**:
```bash
python loaders/load_prices.py --symbols "^VIX"
```

### 2. SPY Price Data
**Location**: `price_daily` and `price_weekly` tables  
**Requirement**: Required for trend and momentum factors  
**Current Status**: ✓ 1283 daily + 266 weekly prices

### 3. Market Health Daily
**Location**: `market_health_daily` table  
**Requirement**: Required for VIX level, put/call ratio, breadth (new highs/lows)  
**Current Status**: ✓ 1283 rows but incomplete:
- VIX level: 80/1283 rows (7%)
- Put/call ratio: 0/1283 rows (0%)
- New highs/lows: 1205/1283 rows (94%)

**To load/refresh**:
```bash
python loaders/load_market_health_daily.py
```

This loader:
1. Computes market health metrics from SPY prices
2. Merges VIX data from price_daily
3. Fetches put/call ratio from yfinance
4. Enriches with breadth data (new highs/lows, advance/decline)
5. Adds yield curve slope data
6. Stores result in market_health_daily

### 4. Technical Data (Breadth Calculations)
**Location**: `technical_data_daily` table  
**Requirement**: Required for breadth factors (% > 50-DMA, % > 200-DMA)  
**Current Status**: ✓ 207672 rows across 10517 symbols with SMA calculations

### 5. Optional Enrichment Data
These are optional - if missing, factors gracefully degrade:

- **AAII Sentiment**: ✓ 2028 rows
- **NAAIM Exposure**: ✓ 1044 rows
- **A/D Line Direction**: ✗ Missing table
- **Credit Spreads (HY OAS)**: ✗ Missing table

## Why VIX Level is Incomplete

The `load_market_health_daily.py` loader performs a CRITICAL check on VIX data:
- It fetches VIX from `price_daily` where symbol = '^VIX'
- If ANY trading date is missing VIX, the loader FAILS with an error (line 222-225)
- This fail-fast behavior prevents data corruption

**Why only 80 rows have VIX**:
1. The loader was likely interrupted or errored out
2. It only partially populated the market_health_daily table
3. The 80 VIX values correspond to dates where the VIX fetch succeeded

**Fix**:
1. Ensure `price_daily` has complete VIX (^VIX) data for all trading dates
2. Re-run the market_health_daily loader with the complete VIX dataset
3. The loader will validate that all dates have VIX and populate the table fully

## Why Put/Call Ratio is Missing

The loader only fetches put/call ratio for the current date (`end`), not historical dates:
- Line 252 in load_market_health_daily.py: `today_pc = self._put_call_fetcher.fetch(end)`
- Line 270-272: Only matches current date: `if m["date"] == end_str:`
- Historical dates keep their existing put_call_ratio values (if any)

**Why there are 0 rows**:
1. Put/call data was never successfully fetched for any date
2. The fetcher likely failed and raised an error
3. The loader stopped without completing

**Fix**:
1. Ensure yfinance can fetch put/call ratio data (check internet connectivity)
2. Re-run the market_health_daily loader
3. The current date's put/call will be populated, and future runs will update it

## Full Data Loading Workflow

### Step 1: Verify Price Data
```bash
python scripts/diagnose_market_data.py
```
This shows what data is available. Look for:
- SPY prices: Daily + Weekly ✓
- VIX prices (^VIX): Should be same count as SPY ✓
- Technical data: Should have SMA_50 and SMA_200 ✓

### Step 2: Load Missing Prices
If VIX or SPY prices are missing:
```bash
# Load SPY prices
python loaders/load_prices.py --symbols "SPY"

# Load VIX prices
python loaders/load_prices.py --symbols "^VIX"
```

### Step 3: Load Market Health Data
Once prices are complete:
```bash
python loaders/load_market_health_daily.py
```

This populates:
- `market_health_daily.vix_level` (from price_daily)
- `market_health_daily.put_call_ratio` (from yfinance)
- `market_health_daily.new_highs_count` / `new_lows_count` (from breadth)
- `market_health_daily.yield_curve_slope` (from Fred API)

### Step 4: Verify Data is Loaded
```bash
python scripts/diagnose_market_data.py
```
All critical sources should show ✓ OK

### Step 5: Run Orchestrator
```bash
python algo/algo_orchestrator.py
```

This will:
1. Load market exposure from market_exposure_daily
2. Compute the 12 market factors using the complete data
3. Calculate market regime and exposure %
4. Display on the markets panel with real values (not None scores)

## Frontend Display Logic

The MarketsHealth.jsx component displays market factors as bars:
```javascript
if (!f || f.max == null || f.pts == null) {
  return null;  // Skip factors with missing data
}
```

**What this means**:
- If a factor has `score: None` (data missing), `pts: 0.0` results
- The factor is KEPT and displayed with 0% bar (correct behavior)
- If a factor has `score: 50`, `pts: 5.0` displays as 50% bar
- Sub-values (like "val 18.5" for VIX) only show if `f.value != null`

**So when you see blank/missing values**:
- The factor bar shows 0% (correct - no data available)
- The value column doesn't show a number (correct - no real value to display)

## Verifying the Fix

After loading data and running the orchestrator:

1. Navigate to **Markets Health** page in the dashboard
2. Scroll to the **12-Factor Exposure Composite** section
3. Check that factors show:
   - **Bar filled to some %** (not empty 0%)
   - **Value number** in parentheses (e.g., "val 18.5" for VIX)
   - Factor name clearly visible

If any factor still shows blank/0%, check:
1. Is the data in the database? Run: `python scripts/diagnose_market_data.py`
2. Is the orchestrator computing factors? Check logs for Phase 3b/Phase 4
3. Is the API returning the data? Check: `GET /api/algo/markets` response

## Key Principle

The system is designed to **FAIL FAST when data is missing**, not silently show zeros:
- VIX fetcher raises error if ANY date is missing (circuit breaker safety)
- Put/call fetcher raises error if current date is missing (exposure scoring)
- All factors return `{"score": None}` gracefully if data unavailable
- Dashboard shows 0% bars for missing factors (visible, not hidden)

This ensures **no silent data corruption** - if markets panel shows blank/0%, you know data is missing and can diagnose it.

## Troubleshooting

### VIX level shows in only 80 rows
1. Check price_daily for ^VIX: `SELECT COUNT(*) FROM price_daily WHERE symbol = '^VIX'`
2. If count is low, load VIX prices: `python loaders/load_prices.py --symbols "^VIX"`
3. Re-run market_health_daily loader

### Put/call ratio shows 0 rows
1. Test yfinance connectivity: `python -c "import yfinance; print(yfinance.download('^VIX', period='1d'))"`
2. If fails, check internet connectivity and yfinance access
3. Re-run market_health_daily loader: `python loaders/load_market_health_daily.py`

### Markets panel shows 0% for all factors
1. Run diagnostic: `python scripts/diagnose_market_data.py`
2. Check which data sources are missing
3. Follow the Full Data Loading Workflow steps
4. Wait for orchestrator to complete Phase 3b-4 (market exposure computation)

### Orchestrator fails during Phase 4
1. Check if market_health_daily has recent data: `SELECT MAX(date) FROM market_health_daily`
2. If data is stale, re-run market_health_daily loader
3. Check logs for specific factor that failed (VIX, put/call, breadth)
4. Address the missing data source and retry
