# Data Loading Process — Local First, Then AWS

## Overview
We load ALL data locally using Python loader scripts, verify completeness, then deploy to AWS. **No partial patches. No fake data. Full loads only.**

---

## The 39 Official Data Loaders

These are the ONLY loaders that should exist. Run them locally to populate the database:

### Core Data (Must Run First)
1. **loadstocksymbols.py** - Stock/ETF symbols and metadata
2. **loaddailycompanydata.py** - Company profile, sector, industry
3. **loadmarketindices.py** - Market indices and benchmarks

### Price Data (By Timeframe)
4. **loadpricedaily.py** - Daily OHLCV data
5. **loadpriceweekly.py** - Weekly aggregates
6. **loadpricemonthly.py** - Monthly aggregates
7. **loadlatestpricedaily.py** - Current day prices
8. **loadlatestpriceweekly.py** - Latest weekly
9. **loadlatestpricemonthly.py** - Latest monthly

### ETF Data
10. **loadetfpricedaily.py** - ETF daily prices
11. **loadetfpriceweekly.py** - ETF weekly prices
12. **loadetfpricemonthly.py** - ETF monthly prices
13. **loadefsignals.py** - ETF trading signals

### Trading Signals (Must Have Price Data First)
14. **loadbuyselldaily.py** - Daily Buy/Sell signals
15. **loadbuysellweekly.py** - Weekly Buy/Sell signals
16. **loadbuysellmonthly.py** - Monthly Buy/Sell signals
17. **loadbuysell_etf_daily.py** - ETF daily signals
18. **loadbuysell_etf_weekly.py** - ETF weekly signals
19. **loadbuysell_etf_monthly.py** - ETF monthly signals

### Fundamental Data
20. **loadannualbalancesheet.py** - Annual balance sheets
21. **loadquarterlybalancesheet.py** - Quarterly balance sheets
22. **loadannualincomestatement.py** - Annual income statements
23. **loadquarterlyincomestatement.py** - Quarterly income statements
24. **loadannualcashflow.py** - Annual cash flow
25. **loadquarterlycashflow.py** - Quarterly cash flow
26. **loadttmincomestatement.py** - TTM income statement
27. **loadttmcashflow.py** - TTM cash flow

### Earnings Data
28. **loadearningshistory.py** - Historical earnings & surprises
29. **loadearningsrevisions.py** - Earnings estimate revisions
30. **loadearningssurprise.py** - Earnings surprise metrics

### Stock Scores & Metrics
31. **loadstockscores.py** - Composite scores (growth, value, quality)
32. **loadfactormetrics.py** - Factor-based metrics
33. **loadrelativeperformance.py** - Performance rankings

### Market Data
34. **loadmarket.py** - Market summary & breadth
35. **loadecondata.py** - Economic indicators (FRED)
36. **loadcommodities.py** - Commodity prices
37. **loadseasonality.py** - Seasonal patterns

### Analyst/Sentiment
38. **loadanalystsentiment.py** - Analyst ratings & sentiment
39. **loadanalystupgradedowngrade.py** - Upgrade/downgrade activity

### Optional Loaders (Advanced/Real-time)
- loadalpacaportfolio.py - Real Alpaca account data
- loadbenchmark.py - Performance benchmarks
- loadcalendar.py - Economic calendar
- loadcoveredcallopportunities.py - Options analysis
- loadfeargreed.py - Fear & Greed index
- loadguidance.py - Company guidance
- loadinsidertransactions.py - Insider trading
- loadmarket.py - Market indicators
- loadnaaim.py - NAAIM data
- loadnews.py - News sentiment
- loadoptionschains.py - Options chains
- load_sp500_earnings.py - S&P 500 earnings

---

## Local Loading Process

### 1. Prerequisites
```bash
# Install dependencies
pip install -r requirements.txt

# Set .env.local with database credentials
DB_HOST=localhost
DB_PORT=5432
DB_USER=stocks
DB_PASSWORD=<password>
DB_NAME=stocks

# API Keys (optional but recommended)
FRED_API_KEY=<key>
ALPACA_API_KEY=<key>
ALPACA_API_SECRET=<secret>
```

### 2. Load Data in Order

**Phase 1: Metadata (MUST run first)**
```bash
python3 loadstocksymbols.py
python3 loaddailycompanydata.py
python3 loadmarketindices.py
```

**Phase 2: Price Data (MUST run before signals)**
```bash
python3 loadpricedaily.py
python3 loadpriceweekly.py
python3 loadpricemonthly.py
python3 loadlatestpricedaily.py
python3 loadlatestpriceweekly.py
python3 loadlatestpricemonthly.py
python3 loadetfpricedaily.py
python3 loadetfpriceweekly.py
python3 loadetfpricemonthly.py
```

**Phase 3: Signals (Depends on Phase 1 & 2)**
```bash
python3 loadbuyselldaily.py
python3 loadbuysellweekly.py
python3 loadbuysellmonthly.py
python3 loadbuysell_etf_daily.py
python3 loadbuysell_etf_weekly.py
python3 loadbuysell_etf_monthly.py
```

**Phase 4: Fundamentals**
```bash
python3 loadannualbalancesheet.py
python3 loadquarterlybalancesheet.py
python3 loadannualincomestatement.py
python3 loadquarterlyincomestatement.py
python3 loadannualcashflow.py
python3 loadquarterlycashflow.py
python3 loadttmincomestatement.py
python3 loadttmcashflow.py
```

**Phase 5: Earnings & Scores**
```bash
python3 loadearningshistory.py
python3 loadearningsrevisions.py
python3 loadearningssurprise.py
python3 loadstockscores.py
python3 loadfactormetrics.py
python3 loadrelativeperformance.py
```

**Phase 6: Market Data**
```bash
python3 loadmarket.py
python3 loadecondata.py
python3 loadcommodities.py
python3 loadseasonality.py
python3 loadanalystsentiment.py
python3 loadanalystupgradedowngrade.py
```

### 3. Verify Data Loaded
```bash
node /path/to/verify-data-complete.js
```

### 4. Deploy to AWS
Once verified locally, commit changes and push:
```bash
git add .
git commit -m "Load all data with proper loaders - [date]"
git push origin main
# CI/CD will handle AWS deployment
```

---

## Rules to Prevent Sloppy Loading

### ✅ DO
- Use the 39 official loaders only
- Load ALL data locally first before pushing to AWS
- Verify data completeness with checks
- Document what data each loader provides
- Run loaders in dependency order (Phase 1 → Phase 6)

### ❌ DON'T
- Create new loaders without adding them to this list
- Create fake populate scripts (populate-*.js, generate-*.js)
- Insert hardcoded default values (COALESCE to 0, 'None')
- Insert records with missing critical data
- Patch data in routes instead of using loaders
- Add test/debug scripts in root directory

### No More Weird Patches
If data is missing, **FIX THE LOADER**, don't patch with:
- Fake populate-all-signals.js scripts ❌
- Default values in routes ❌
- Test queries in root directory ❌
- Ad-hoc SQL inserts ❌

---

## Current Status

**Last Updated:** 2026-04-26

| Loader | Status | Last Run | Notes |
|--------|--------|----------|-------|
| loadstocksymbols | ✅ | ? | Core data |
| loadpricedaily | ✅ | ? | Needed by signals |
| loadbuyselldaily | ⚠️ | ? | Inserting 97.8% "None" signals - NEEDS FIX |
| loadstockscores | ⚠️ | ? | Check coverage |
| loadecondata | ⚠️ | ? | FRED integration |

---

## Next Steps

1. Check which loaders are failing/incomplete
2. Fix loaders to ensure complete data (no "None" defaults)
3. Run all loaders locally
4. Verify all data in frontend
5. Deploy to AWS
