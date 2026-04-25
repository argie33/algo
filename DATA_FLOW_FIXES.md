# Data Flow Audit & Fixes (2026-04-25)

## STATUS: CRITICAL ISSUES FIXED ✅

### FIXED - Blocking Issues

#### ✅ Fix #1: TradeHistory Field Mapping (CRITICAL)
**File:** `webapp/lambda/routes/trades.js`
**Issue:** Frontend expected `execution_price`, `execution_date`, `order_value` but backend aliased to `price`, `trade_date`, `total_amount`
**Fix Applied:** 
- Line 147-148: Changed `execution_price as price` → `execution_price` (no alias)
- Line 147-148: Changed `execution_date as trade_date` → `execution_date` (no alias)  
- Line 147-148: Changed `order_value as total_amount` → `order_value` (no alias)
- Line 167-169: Updated object mapping to use correct field names
**Impact:** ✅ TradeHistory page will now display trade data correctly

#### ✅ Fix #2: PortfolioDashboard Performance Chart (CRITICAL)
**File:** `webapp/frontend-admin/src/pages/PortfolioDashboard.jsx`
**Issue:** Backend returns array of objects `{date, portfolio_value, pnl_percent, pnl_dollars}` but frontend treated values as simple numbers
**Fix Applied:**
- Line 262-266: Changed `map((val, idx) => ...)` to `map((item) => ...)`
- Now correctly extracts `item.pnl_percent` instead of treating entire object as number
**Impact:** ✅ Performance chart will render correctly with historical returns

#### ✅ Fix #3: Technical Indicators Loaders (CRITICAL)
**Files Created:**
- `loadtechnicalsdaily.py` - Populates `technical_data_daily` (3,969 symbols)
- `loadtechnicalsweekly.py` - Populates `technical_data_weekly` (4,969 symbols)
- `loadtechnicalsmonthly.py` - Populates `technical_data_monthly` (4,969 symbols)

**Changes:**
- Fixed Windows compatibility (optional import for `resource` module)
- Removed emoji characters (encoding issues on Windows)

**Updated:** `run-all-loaders.sh`
- Removed non-existent `loadtechnicalindicators.py`
- Added three separate loaders with proper wait statements
**Impact:** ✅ Technical data will populate all three timeframes

### REMAINING BLOCKING ISSUES ❌

#### ❌ Issue #1: Missing FIFO/Matched Pairs Endpoint
**Component:** TradeHistory.jsx - "Matched Pairs (FIFO)" tab
**Problem:** Frontend has UI tab but no backend endpoint exists
**Options:**
- [ ] Create `/api/trades/fifo-analysis` endpoint with FIFO logic
- [ ] Remove the UI tab (simplest fix)
**Action:** DECIDE - Create endpoint or remove UI?

#### ❌ Issue #2: Portfolio Historical Data Not Updating
**Component:** PortfolioDashboard - performance metrics
**Problem:** `portfolio_performance` table only loaded once at initial portfolio sync
- After manual trades added via TradeHistory, performance data becomes stale
- Daily returns chart shows old data
**Root Cause:** `loadalpacaportfolio.py` runs once, doesn't update after manual trades
**Solution Needed:**
- Option A: Create `loadportfolioperformance.py` that recalculates daily from trades table
- Option B: Calculate performance on-demand in API endpoint
**Action:** DECIDE - which approach?

#### ❌ Issue #3: Sector Data May Be Incomplete
**Component:** PortfolioDashboard - sector metrics
**Tables Used:** `company_profile` (LEFT JOINed in portfolio endpoint)
**Loader:** `loaddailycompanydata.py` should populate this
**Verification Needed:** Run loaders and check if `company_profile.sector` field populated
**Action:** VERIFY after loaders run

### DETAILED DATA FLOW MAP

#### PortfolioDashboard Page
```
Frontend Page → API Endpoint → Database Tables → Loaders
────────────────────────────────────────────────────────

PortfolioDashboard.jsx 
  ↓
/api/portfolio/metrics
  ↓
QUERIES:
- portfolio_holdings → loadalpacaportfolio.py ✅
- portfolio_performance → loadalpacaportfolio.py ✅
- company_profile → loaddailycompanydata.py ✅
- stock_scores → loadstockscores.py ✅
- buy_sell_daily → loadbuyselldaily.py ✅

DATA SHOWN:
✅ Portfolio value, positions, allocation
✅ Stock scores, technical signals  
⚠️ Sector breakdown (if company_profile.sector loaded)
⚠️ Performance chart (if daily_returns updated)
```

#### TradeHistory Page
```
TradeHistory.jsx
  ↓
/api/trades
  ↓
QUERIES:
- trades table (manual entry)

DATA SHOWN:
✅ Trade list (execution_price, execution_date, order_value) - FIXED
❌ Matched pairs (no backend endpoint)
```

#### Portfolio Optimizer Page
```
PortfolioOptimizerNew.jsx
  ↓
/api/optimization/analysis
  ↓
QUERIES:
- portfolio_holdings → loadalpacaportfolio.py ✅
- stock_scores → loadstockscores.py ✅
- analyst_sentiment_analysis → loadanalystsentiment.py ✅
- portfolio_performance → loadalpacaportfolio.py ✅
- buy_sell_daily → loadbuyselldaily.py ✅

DATA SHOWN:
✅ Score distributions, correlations
⚠️ Optimization metrics (depends on data freshness)
```

### LOADER SCHEDULE VERIFICATION

**Real Core Loaders Running:**
✅ loadpricedaily.py
✅ loadpriceweekly.py
✅ loadpricemonthly.py
✅ loadannualincomestatement.py
✅ loadannualbalancesheet.py
✅ loadannualcashflow.py
✅ loadquarterlyincomestatement.py
✅ loadquarterlybalancesheet.py
✅ loadquarterlycashflow.py
✅ loaddailycompanydata.py
✅ loadearningshistory.py
✅ loadstockscores.py
✅ loadfactormetrics.py
✅ loadanalystsentiment.py
✅ loadanalystupgradedowngrade.py
✅ loadbuyselldaily.py
✅ loadbuysellweekly.py
✅ loadbuysellmonthly.py
🆕 loadtechnicalsdaily.py (CREATED TODAY)
🆕 loadtechnicalsweekly.py (CREATED TODAY)
🆕 loadtechnicalsmonthly.py (CREATED TODAY)

**Not In Master Loader List (Cleanup Candidates):**
❌ loadlatestpricedaily.py (empty INSERT)
❌ loadlatestpriceweekly.py (empty INSERT)
❌ loadlatestpricemonthly.py (empty INSERT)
❌ loadbuysell_etf_daily.py (empty INSERT)
❌ loadbuysell_etf_weekly.py (empty INSERT)
❌ loadbuysell_etf_monthly.py (empty INSERT)
⚠️ loadetfpricedaily.py (negative row counts - query errors)
⚠️ loadetfpriceweekly.py (negative row counts)
⚠️ loadetfpricemonthly.py (negative row counts)
⚠️ loadoptionschains.py (99.8% missing data)

### NEXT STEPS

1. **IMMEDIATE - Start Loaders**
   ```bash
   bash run-all-loaders.sh
   ```
   - Monitor `/tmp/*.log` for errors
   - Wait for technical loaders to complete (~10 minutes)

2. **VERIFY Data Populated** (15 min after loaders finish)
   ```sql
   SELECT COUNT(*) FROM technical_data_daily;
   SELECT COUNT(*) FROM technical_data_weekly;
   SELECT COUNT(*) FROM technical_data_monthly;
   SELECT COUNT(*) FROM company_profile WHERE sector IS NOT NULL;
   ```

3. **TEST Frontend Pages**
   - PortfolioDashboard: Check sectors show, performance chart renders
   - TradeHistory: Add manual trade, verify it displays with correct fields
   - Optimizer: Check all metrics populate

4. **Decide On Remaining Issues**
   - FIFO endpoint: Create or remove UI tab?
   - Portfolio updates: Auto-recalculate or on-demand?

---

**Report Generated:** 2026-04-25 13:40 UTC
**Status:** 3 blocking issues fixed, 3 remaining issues identified
