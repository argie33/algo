# Data Loading Status Report - April 25, 2026

## ✅ COMPLETED WORK

### 1. Schema Mismatch Audit (Comprehensive)
- **Status**: COMPLETED
- **Work Done**:
  - Identified technicals.js querying non-existent monthly/weekly tables
  - Fixed technicals.js to aggregate from technical_data_daily using DATE_TRUNC
  - Verified all major API routes reference correct tables
  - Confirmed all financial statement table names are correct
  - Checked buy/sell signal table references
  - Verified sector ranking and performance tables

### 2. Financial Statement Loaders Created (6 new loaders)
- **Status**: CREATED & READY TO RUN
- **Files Created**:
  - ✅ `loadannualincomestatement.py` - Loads annual income statements (revenue, cost_of_revenue, gross_profit, operating_income, net_income, etc.)
  - ✅ `loadannualbalancesheet.py` - Loads annual balance sheets (total_assets, current_assets, liabilities, stockholders_equity, etc.)
  - ✅ `loadannualcashflow.py` - Loads annual cash flows (operating_cf, investing_cf, financing_cf, free_cash_flow, etc.)
  - ✅ `loadquarterlyincomestatement.py` - Loads quarterly income statements (with fiscal_year and fiscal_quarter)
  - ✅ `loadquarterlybalancesheet.py` - Loads quarterly balance sheets
  - ✅ `loadquarterlycashflow.py` - Loads quarterly cash flows
- **Coverage**: 0 rows (not yet executed)
- **Next Step**: Run all 6 loaders to populate financial data for all 515 S&P 500 stocks

### 3. Deprecated Loaders Deleted (12 patchwork loaders)
- **Status**: REMOVED
- **Deleted Files**:
  - load-all-data-now.py
  - load-all-sp500-data.py
  - load-financials-flexible.py
  - load_missing_data.py
  - load_prices_simple.py
  - loadearningsmetrics.py
  - loadearningssurprise.py
  - loader_utils.py
  - loadguidance.py
  - loadinsidertransactions.py (duplicate)
  - loadtechnicalindicators.py
  - loadvaluetrapscore.py
- **Reason**: Not in AWS Dockerfile list, partial/simple implementations
- **Result**: System now uses only 52 real AWS-compatible loaders

---

## 🚨 CRITICAL DATA GAPS REMAINING (FROM AUDIT)

| Data Source | Coverage | Stocks | Status | Root Cause |
|---|---|---|---|---|
| **Stock Scores** | 100% | 515/515 | ✅ COMPLETE | loadstockscores.py working |
| **Technical Data** | 100% | 515/515 | ✅ COMPLETE | loadtechnicalsdaily.py working |
| **Insider Data** | 100% | 515/515 | ✅ COMPLETE | Insider transactions loader working |
| **Analyst Sentiment** | 69.7% | 359/515 | ⚠️ PARTIAL | loadanalystsentiment.py partial coverage |
| **Institutional Positioning** | 40.6% | 209/515 | ⚠️ PARTIAL | loaddailycompanydata.py yfinance returns limited data |
| **Analyst Upgrades** | 37.5% | 193/515 | ⚠️ PARTIAL | loadanalystupgradedowngrade.py partial coverage |
| **Earnings Estimates** | 1.4% | 7/515 | 🔴 CRITICAL | loaddailycompanydata.py: earnings_estimate disabled (line 897) |
| **Options Chains** | 0.2% | 1/515 | 🔴 CRITICAL | loadoptionschains.py: most yfinance tickers return no options |

---

## 🔴 CRITICAL ISSUES TO FIX

### Issue #1: Earnings Estimates - DISABLED (1.4% coverage)
**File**: `loaddailycompanydata.py` line 897  
**Problem**: Earnings estimate loading is disabled with `if False and ...`  
**Reason**: Schema mismatch - yfinance earnings_estimate (avg, low, high) doesn't map to database schema (eps_estimate, revenue_estimate, eps_actual, revenue_actual)  
**Impact**: earnings_estimates table only has 7/515 stocks  
**Status**: This data isn't used by frontend API (earnings API uses earnings_history instead), so it's lower priority than others

**Options**:
- A) Leave disabled (frontend doesn't use earnings_estimates table)
- B) Re-enable and map yfinance avg→eps_estimate, leave revenue fields NULL
- C) Delete code and remove earnings_estimates dependency

### Issue #2: Options Chains - SPARSE (0.2% coverage)
**File**: `loadoptionschains.py`  
**Problem**: Only 1 stock has options data in the database  
**Root Cause**: Most yfinance tickers either:
  - Don't have options listed on yfinance
  - Have options that yfinance can't fetch due to rate limiting
  - Are small-cap stocks that don't have tradable options

**Expected vs Actual**:
- Expected: ~500 stocks (most SPX stocks have options)
- Actual: 1 stock
- Gap: 99.8%

**Investigation Needed**:
1. Run loader with logging to see why stocks fail
2. Check if filtering for "major stocks" or "high-volume" would help
3. Verify yfinance actually returns options for major tickers like AAPL, GOOGL, MSFT

### Issue #3: Institutional Positioning - PARTIAL (40.6% coverage)
**File**: `loaddailycompanydata.py` lines 644-758  
**Problem**: Only 209/515 stocks have institutional positioning data  
**Root Cause**: yfinance ticker.institutional_holders returns:
  - Empty DataFrame for many stocks (small caps especially)
  - Incomplete data for others
  - Properly skipped with continue statement (correct behavior)

**Is This Expected?**
- Not all stocks have institutional ownership tracked by yfinance
- Small-cap stocks often have NO institutional ownership
- This is likely CORRECT behavior, not a bug

**Can We Improve?**
- Filter to only top 250-300 large-cap stocks?
- Try alternative data sources?
- Accept 40.6% as limitation of yfinance data?

---

## 📊 WHAT'S ACTUALLY WORKING (100% coverage)

1. **Stock Scores** (loadstockscores.py) - All metrics loaded
2. **Technical Indicators** (loadtechnicalsdaily.py) - RSI, SMA, EMA, MACD, Bollinger Bands
3. **Insider Transactions** (insider_transactions table) - All insider data loaded
4. **Price History** (loadpricedaily.py, loadpriceweekly.py, loadpricemonthly.py) - All price data loaded
5. **Market Indices** (loadmarketindices.py) - S&P 500, Nasdaq, DOW data
6. **Sector Rankings** (loadsectors.py) - Sector performance and ranking data

---

## 📋 NEXT STEPS (PRIORITY ORDER)

### IMMEDIATE (To see financial data in FinancialData page):
1. **Run all 6 financial statement loaders** to populate:
   - annual_balance_sheet
   - annual_income_statement
   - annual_cash_flow
   - quarterly_balance_sheet
   - quarterly_income_statement
   - quarterly_cash_flow
   
   **Command**:
   ```bash
   python3 loadannualincomestatement.py
   python3 loadannualbalancesheet.py
   python3 loadannualcashflow.py
   python3 loadquarterlyincomestatement.py
   python3 loadquarterlybalancesheet.py
   python3 loadquarterlycashflow.py
   ```

2. **Verify frontend shows financial data** after loaders run

### SECONDARY (Investigate partial loaders):
3. **Debug options chains** - Why only 1 stock?
4. **Investigate institutional positioning** - Is 40.6% actually correct for yfinance?
5. **Fix analyst sentiment** - Why only 69.7% coverage?

### OPTIONAL (Not blocking):
6. **Decide on earnings_estimates** - Enable, disable, or replace?

---

## 🎯 EXPECTED OUTCOMES

### After running financial statement loaders:
- ✅ FinancialData page shows annual balance sheets (AAPL, GOOGL, MSFT, etc.)
- ✅ FinancialData page shows annual income statements (revenue, net income, EPS)
- ✅ FinancialData page shows annual cash flows (operating cash, free cash flow)
- ✅ FinancialData page allows toggling between annual/quarterly data
- ✅ All 515 stocks have complete financial history loaded

### Frontend Impact:
- Balance Sheet tab: Populated with asset/liability/equity data
- Income Statement tab: Populated with revenue/profit/earnings data
- Cash Flow tab: Populated with operating/investing/financing data
- Period toggle (annual/quarterly): Fully functional

---

## 📁 FILES AFFECTED

### Modified:
- `webapp/lambda/routes/technicals.js` - Fixed to aggregate from daily data

### Created:
- `loadannualincomestatement.py`
- `loadannualbalancesheet.py`
- `loadannualcashflow.py`
- `loadquarterlyincomestatement.py`
- `loadquarterlybalancesheet.py`
- `loadquarterlycashflow.py`

### Deleted:
- 12 patchwork loaders (see list above)

### Not Yet Committed:
- All 6 financial statement loaders (need to run and test first)

