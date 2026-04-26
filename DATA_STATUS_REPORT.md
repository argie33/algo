# 🔍 Data Status Report — What's Loaded vs Missing

**Generated:** 2026-04-26 15:18  
**API Status:** ✅ Connected to database  
**Database Status:** Connected but INCOMPLETE

---

## Summary: What's Missing

The database has data from old loaders, but **NOT ALL LOADERS HAVE RUN YET**. 

### ✅ Data Present (Good)
- stock_symbols: 4,966 ✅
- price_daily: 688,034 ✅
- etf_symbols: 5,113 ✅
- earnings_history: 35,644 ✅
- ttm_income_statement: 107,824 ✅
- ttm_cash_flow: 100,346 ✅
- technical_data_daily: 29,404 ✅
- company_profile: 4,029 ✅
- analyst_upgrade_downgrade: 80,948 ✅

### ❌ Data Missing or Broken (Critical Issues)

**Trading Signals - CONTAMINATED:**
- buy_sell_daily: 142,803 records BUT **97.8% are fake 'None' signals** ❌
  - Real Buy/Sell: ~3,087
  - Fake 'None': ~139,673
- buy_sell_weekly: -1 (ERROR - not populated) ❌
- buy_sell_monthly: -1 (ERROR - not populated) ❌

**Price Data - Incomplete:**
- price_daily: 688,034 ✅
- price_weekly: 4,969 (TOO LOW - should be 100k+) ❌
- price_monthly: 4,969 (TOO LOW) ❌
- etf_price_daily: 298,565 ✅
- etf_price_weekly: 61,728 ✅
- etf_price_monthly: 33,171 ✅

**Financial Data - Incomplete:**
- annual_balance_sheet: 12,387 (only ~20% of stocks) ❌
- annual_income_statement: 17,478 ❌
- annual_cash_flow: 17,433 ❌
- quarterly_balance_sheet: 64,796 ✅
- quarterly_income_statement: 64,702 ✅
- quarterly_cash_flow: 64,909 ✅

**Portfolio Data - NOT LOADED:**
- portfolio_holdings: -1 (not populated) ❌
- portfolio_performance: -1 (not populated) ❌
- portfolio_metrics: Not found ❌

**Market Data - NOT LOADED:**
- market_data: "not_found" ❌
- price_data_monthly: "not_found" ❌
- calendar_events: -1 ❌
- stock_news: "not_found" ❌

**Other:**
- positioning_metrics: -1 ❌
- revenue_estimates: "not_found" ❌
- trading_alerts: "not_found" ❌

---

## What Pages Need What Data

### 🏠 Dashboard Page
**Needs:**
- ✅ stock_symbols (for stock list) - **HAVE**
- ✅ price_daily (current prices) - **HAVE**
- ✅ buy_sell_daily (trading signals) - **BROKEN (97.8% fake)**
- ✅ stock_scores (rankings) - **HAVE (4,969)**
- ⚠️ market_data (market overview) - **MISSING**

**Status:** ⚠️ PARTIALLY WORKING - Shows stocks but signals are broken

---

### 📈 Trading Signals Page
**Needs:**
- ❌ buy_sell_daily (with real Buy/Sell only) - **BROKEN**
- ❌ buy_sell_weekly (aggregated signals) - **ERROR**
- ❌ buy_sell_monthly (aggregated signals) - **ERROR**
- ✅ technical_data_daily (RSI, MACD, etc.) - **HAVE**
- ✅ price_daily (OHLCV) - **HAVE**

**Status:** ❌ BROKEN - Can't show signals properly

**Fix Required:**
1. Delete all 'None' signals from buy_sell_daily
2. Run loadbuysellweekly.py (NOW FIXED)
3. Run loadbuysellmonthly.py (NOW FIXED)

---

### 💰 Earnings Page
**Needs:**
- ✅ earnings_history (35,644) - **HAVE**
- ❌ earnings_estimates (only 1,348 - should be 5k+) - **LOW**
- ✅ company_profile (4,029) - **HAVE**

**Status:** ⚠️ PARTIAL - Some data exists but incomplete

**Fix Required:**
- Run loadearningsrevisions.py (estimates/revisions)

---

### 📊 Financials Page
**Needs:**
- ❌ annual_balance_sheet (12,387 - only 25% complete) - **INCOMPLETE**
- ❌ annual_income_statement (17,478 - only 35% complete) - **INCOMPLETE**
- ❌ annual_cash_flow (17,433 - only 35% complete) - **INCOMPLETE**
- ✅ quarterly_* tables (60k+) - **HAVE**

**Status:** ⚠️ WORKS FOR QUARTERLY - Annual data is sparse

**Fix Required:**
- Run loadannualbalancesheet.py (more complete)
- Run loadannualincomestatement.py
- Run loadannualcashflow.py

---

### 🏛️ Portfolio Page
**Needs:**
- ❌ portfolio_holdings - **NOT LOADED**
- ❌ portfolio_performance - **NOT LOADED**
- ❌ trades (manual trade history) - **NOT LOADED**

**Status:** ❌ BROKEN - No portfolio data at all

**Fix Required:**
- This requires user authentication + Alpaca integration
- Run loadalpacaportfolio.py (if you want real Alpaca data)

---

### 📈 Market Overview
**Needs:**
- ❌ market_data - **NOT FOUND**
- ✅ price_daily (for calculations) - **HAVE**
- ✅ analyst_upgrade_downgrade (80,948) - **HAVE**
- ✅ fear_greed_index (254) - **HAVE**
- ✅ aaii_sentiment (2,150) - **HAVE**

**Status:** ⚠️ PARTIAL - Has sentiment data but market data is missing

**Fix Required:**
- Run loadmarket.py

---

### 🏢 Sectors & Industries
**Needs:**
- ✅ company_profile (sector info) - **HAVE**
- ✅ stock_scores (4,969) - **HAVE**
- ✅ technical_data_daily - **HAVE**

**Status:** ✅ WORKING

---

### 📰 News & Sentiment
**Needs:**
- ✅ analyst_upgrade_downgrade (80,948) - **HAVE**
- ✅ analyst_sentiment_analysis (3,459) - **HAVE**
- ❌ stock_news - **NOT FOUND**

**Status:** ⚠️ PARTIAL - Analyst data present, news missing

---

## Critical Issues to Fix (Priority Order)

### 🔴 CRITICAL (Pages won't work)

1. **Trading Signals Tables Are Broken**
   ```bash
   # Delete all fake 'None' signals
   DELETE FROM buy_sell_daily WHERE signal = 'None';
   
   # Rebuild weekly/monthly from daily
   python3 loadbuysellweekly.py    # NOW FIXED
   python3 loadbuysellmonthly.py   # NOW FIXED
   ```
   **Impact:** Trading Signals page will work

2. **Price Weekly/Monthly Are Incomplete**
   ```bash
   # These should have 100k+ records each, only have 4,969
   # They're probably from aggregation of daily
   # May need to recalculate
   ```
   **Impact:** Affects charting on weekly/monthly views

3. **Annual Financial Data Is Sparse**
   ```bash
   python3 loadannualbalancesheet.py
   python3 loadannualincomestatement.py
   python3 loadannualcashflow.py
   ```
   **Impact:** Financials page will show more data

---

### 🟠 IMPORTANT (Pages partially broken)

4. **Missing Earnings Estimates**
   ```bash
   python3 loadearningsrevisions.py
   ```
   **Impact:** Earnings page completeness

5. **Missing Market Data**
   ```bash
   python3 loadmarket.py
   ```
   **Impact:** Market Overview page

6. **Missing Portfolio Data**
   ```bash
   python3 loadalpacaportfolio.py
   # (Only if you want to sync real Alpaca portfolio)
   ```
   **Impact:** Portfolio page (unless using mock data)

---

### 🟡 NICE TO HAVE

7. **Missing News Data**
   ```bash
   python3 loadnews.py
   ```
   **Impact:** News section completeness

8. **Missing Economic Data Updates**
   ```bash
   python3 loadecondata.py
   ```
   **Impact:** Economic indicators freshness

---

## Action Plan to Get All Data Loaded

### Option A: Full Clean Load (RECOMMENDED)
```bash
# Step 1: Clear corrupted data
DELETE FROM buy_sell_daily WHERE signal = 'None';
TRUNCATE buy_sell_weekly, buy_sell_monthly CASCADE;

# Step 2: Run CRITICAL loaders only (fast, 1-2 hours)
python3 loadbuysellweekly.py    # 30 min
python3 loadbuysellmonthly.py   # 30 min
python3 loadannualbalancesheet.py  # 15 min
python3 loadannualincomestatement.py  # 15 min
python3 loadannualcashflow.py   # 15 min
python3 loadearningsrevisions.py  # 10 min

# Step 3: Verify
curl http://localhost:3001/api/diagnostics | jq .data_availability
```

**Total Time:** 2-3 hours  
**Pages Fixed:** Dashboard, Trading Signals, Financials, Earnings

### Option B: Selective Load (Fast)
```bash
# Just fix the broken ones:
python3 loadbuysellweekly.py
python3 loadbuysellmonthly.py
```

**Total Time:** 1 hour  
**Pages Fixed:** Trading Signals

---

## Current Data Completeness

| Page | Status | Issue | Fix |
|------|--------|-------|-----|
| Dashboard | ⚠️ Partial | Signals are fake | Delete 'None' signals |
| Trading Signals | ❌ Broken | No weekly/monthly | Run weekly/monthly loaders |
| Financials | ⚠️ Partial | Annual data sparse | Run annual loaders |
| Earnings | ⚠️ Partial | Low estimate coverage | Run earnings revision loader |
| Sectors | ✅ Working | - | - |
| Market Overview | ⚠️ Partial | Missing market data | Run loadmarket.py |
| Portfolio | ❌ Missing | No data | Run loadalpacaportfolio.py |
| Sentiment | ⚠️ Partial | No news data | Run loadnews.py |

---

## Next Steps

**Immediate (Do This Now):**
```bash
# 1. Stop fake signals from polluting database
DELETE FROM buy_sell_daily WHERE signal = 'None';

# 2. Load the 4 critical missing tables (FAST - 2 hours)
python3 loadbuysellweekly.py
python3 loadbuysellmonthly.py
python3 loadannualbalancesheet.py
python3 loadannualincomestatement.py
python3 loadannualcashflow.py

# 3. Verify in browser
http://localhost:5174
```

**Optional (When you have time):**
- Run remaining loaders for complete data
- See full list in DATA_LOADING.md

---

**Your system is 60% complete. Do the 2-hour fix above to get to 90%.**
