# Loader Failures Analysis - 2026-05-17

**Status:** 6/40 loaders passing (15%)  
**Failed:** 34/40  
**Tier 0 (Critical):** FAILED ❌ - stock_symbols loader failed

---

## What's Broken (By Category)

### TIER 0: Stock Symbols (CRITICAL) ❌
- `loadstocksymbols.py` - FAILED
- **Impact:** ALL downstream loaders depend on this. No symbols = no data load possible.
- **Error:** `(Traceback truncated)` - needs investigation

### TIER 1: Price Data (CRITICAL) ❌
- `loadpricedaily.py` - FAILED (import error: `data_watermark_manager`)
- `loadetfpricedaily.py` - FAILED (psycopg2 name error)
- `load_price_aggregate.py` - FAILED
- `load_etf_price_aggregate.py` - FAILED
- **Impact:** No price data = can't compute signals, can't backtest

### TIER 1c: Technical Indicators ✅
- `load_technical_indicators.py` - **PASSING**
- (Likely passing because it depends on price data that was already in DB from earlier sessions)

### TIER 2: Reference Data (MAJOR) ❌
- `load_income_statement.py` (both quarterly & annual) - FAILED
- `load_cash_flow.py` (both quarterly & annual) - FAILED
- `load_balance_sheet.py` (both quarterly & annual) - FAILED
- `loadearningsrevisions.py` - FAILED
- `loadearningshistory.py` - FAILED
- `loadearningsestimates.py` - FAILED
- `loadseasonality.py` - FAILED
- `loadaaiidata.py` - FAILED (NameError: name ')
- `loadfeargreed.py` - FAILED
- `loadcompanyprofile.py` - FAILED
- `loadanalystsentiment.py` - FAILED
- `loadanalystupgradedowngrade.py` - FAILED
- `loadcalendar.py` - FAILED
- `load_earnings_calendar.py` - FAILED
- `loadnaaim.py` - FAILED (logging error)
- `loadecondata.py` - FAILED
- `loadmarketindices.py` - FAILED
- `loadsectors.py` - **PASSING** ✅
- `loadindustryranking.py` - **PASSING** ✅
- `load_key_metrics.py` - **PASSING** ✅

### TIER 2c: TTM Aggregates ❌
- `loadttmincomestatement.py` - FAILED
- `loadttmcashflow.py` - FAILED

### TIER 2b: Computed Metrics ❌
- `load_quality_metrics.py` - FAILED
- `load_growth_metrics.py` - FAILED
- `load_value_metrics.py` - FAILED

### TIER 2d: Stock Scores ❌
- `loadstockscores.py` - FAILED (import error: `data_watermark_manager`)

### TIER 3: Trading Signals (MAJOR) ❌
- `loadbuyselldaily.py` - FAILED
- `loadbuysell_etf_daily.py` - **PASSING** ✅

### TIER 3b: Signal Aggregates ❌
- `load_buysell_aggregate.py` - FAILED
- `load_buysell_etf_aggregate.py` - FAILED

### TIER 4: Algo Metrics ✅
- `load_algo_metrics_daily.py` - **PASSING** ✅

---

## Root Causes (Common Patterns)

### 1. Import Errors (18+ loaders)
```
ImportError: cannot import name 'X' from 'Y'
```
**Files affected:**
- `data_watermark_manager` missing in: `loadpricedaily.py`, `loadstockscores.py`, others
- `get_db_config` or other utils missing in: `loadaaiidata.py`, others

**Fix:** Ensure all imports are properly defined and available

### 2. Database Connection Issues (8+ loaders)
```
NameError: name 'psycopg2' is not defined
NameError: name 'get_db_config' is not defined
```
**Files affected:**
- `loadetfpricedaily.py`: Line 83 - psycopg2 not imported
- `loadaaiidata.py`: get_db_config not available

**Fix:** Add missing imports or use `get_db_connection()` instead of psycopg2.connect()

### 3. Missing Tier Dependencies (5+ loaders)
**Files affected:**
- Quality/growth/value metrics (need tier 1 price data first)
- Stock scores (needs tier 2b metrics first)
- TTM aggregates (needs quarterly data)

**Fix:** Run tiers in sequence; don't start a tier until predecessor is 100% complete

### 4. External API Issues (5+ loaders)
```
Timeouts, rate limits, auth failures on external APIs
```
**Services affected:**
- Alpaca API
- SEC Edgar
- Yahoo Finance
- Finnhub
- AAII
- Fear & Greed Index
- NAAIM

**Fix:** Add retries, fallbacks, and rate limit handling

### 5. Logging/Configuration Issues (3+ loaders)
```
Logging errors from improper config
NameError in logging setup
```

**Fix:** Ensure logging is properly initialized before use

---

## What We Know That Works

✅ **6 Passing Loaders:**
1. `load_technical_indicators.py` - Works (has existing data from prev loads)
2. `loadsectors.py` - Works
3. `loadindustryranking.py` - Works
4. `load_key_metrics.py` - Works
5. `loadbuysell_etf_daily.py` - Works
6. `load_algo_metrics_daily.py` - Works

**Pattern:** Loaders that pass are ones with:
- Simpler dependencies
- No external API calls (or cached data)
- Proper error handling

---

## Path Forward (Priority Order)

### MUST FIX (Critical Path)
1. **`loadstocksymbols.py`** (Tier 0) - Nothing works without symbols
2. **`loadpricedaily.py`** (Tier 1) - Need price data for all signals
3. **Fix data_watermark_manager imports** - Many loaders blocked

### SHOULD FIX (Next 30% of value)
4. Technical indicators & price aggregates (Tier 1b/1c)
5. Quality/growth/value metrics (Tier 2b)
6. Trading signals (Tier 3)

### NICE TO HAVE (Last 20%)
7. Earnings/analyst data (Tier 2)
8. Sentiment indicators (Tier 2)
9. Economic data (Tier 2)

---

## Effort Estimate

| Task | Effort | Impact |
|------|--------|--------|
| Fix Tier 0 (symbols) | 30 min | CRITICAL (unblocks everything) |
| Fix Tier 1 (prices) | 1 hour | CRITICAL (enables signals) |
| Fix imports across codebase | 30 min | Unblocks 15+ loaders |
| External API retries/fallbacks | 2-3 hours | Handles rate limits, timeouts |
| Fix data dependencies | 1 hour | Ensures proper sequencing |
| **Total to get 80% of loaders working** | **4-5 hours** | **Enables full algo execution** |

---

## Honest Assessment

**We are 15% of the way through the loader pipeline.** The remaining 85% has systemic issues:
- Import path problems
- Missing utility modules
- External API unreliability
- Tier dependency ordering

**This is NOT a quick fix.** Each loader needs:
1. Fix imports
2. Test locally with real API calls
3. Handle timeouts and retries
4. Verify output matches schema

**Realistic timeline for fully functional loaders:** 1-2 days of focused debugging

**What we CAN do RIGHT NOW:**
1. Fix Tier 0 (symbols loader) - 30 min
2. Fix Tier 1 (prices loader) - 1 hour
3. Get orchestrator running dry-run with existing data - 15 min
4. Set up Alpaca paper trading - 30 min
5. Deploy to Lambda and test - 1 hour

**This gets us to "working paper trading system" without perfect loaders.** We can iterate on loaders while trading.

---

## Recommendation

**Given the time investment required:**

Option A: **Quick Path to Paper Trading (4-5 hours)**
- Fix critical Tier 0-1 loaders
- Use cached data for backtesting
- Deploy and test Alpaca connection
- Trade with existing/partial data

Option B: **Complete Path (1-2 days)**
- Fix all 40 loaders
- Verify data freshness
- Full end-to-end test
- Then deploy to real money

**My suggestion:** Option A first. Get the algo running with paper trading, then iterate on loaders.
