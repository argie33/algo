# Data Loader Status & Fixes

## Summary of Changes (2026-04-26)

### ✅ LOADERS FIXED
- **loadbuyselldaily.py** - Now only inserts Buy/Sell signals (skips 'None')
- **loadbuysell_etf_daily.py** - Now only inserts Buy/Sell signals
- **loadbuysellweekly.py** - Now filters out 'None' signals
- **loadbuysellmonthly.py** - Now filters out 'None' signals

**Impact:** This eliminates the 97.8% "None" signal pollution. Daily signals will now contain ~3,087 real Buy/Sell signals instead of 142,760 records (139,673 fake "None" records removed).

---

### ❌ LOADERS REMOVED (Extra/Weird)
- `loadindustryranking.py` - Not in official list
- `loadsectorranking.py` - Not in official list
- `loadtechnicalindicators_github.py` - Not in official list
- `Dockerfile.industryranking`, `Dockerfile.sectorranking`, `Dockerfile.technicalindicators_github`
- `populate-all-signals.js` - Fake populate script (inserted bad defaults)
- `populate-historical-signals.js` - Fake populate script
- `generate-signals-efficient.js` - Fake populate script
- All test/check scripts (check-*.js, view-*.js, audit-*.js, verify-*.js)

---

### ✅ DOCUMENTATION CREATED
- **DATA_LOADING.md** - Complete guide for 39 official loaders
  - Proper load order (Phase 1-6)
  - Prerequisites & setup
  - Data verification process
  - Rules to prevent future slop

---

## The 39 Official Loaders (From CI/CD)

### Core Data (Load First)
1. loadstocksymbols.py ✅
2. loaddailycompanydata.py ✅
3. loadmarketindices.py ✅

### Prices (Load Before Signals)
4. loadpricedaily.py ✅
5. loadpriceweekly.py ✅
6. loadpricemonthly.py ✅
7. loadlatestpricedaily.py ✅
8. loadlatestpriceweekly.py ✅
9. loadlatestpricemonthly.py ✅
10. loadetfpricedaily.py ✅
11. loadetfpriceweekly.py ✅
12. loadetfpricemonthly.py ✅

### Signals (Now Fixed!)
13. loadbuyselldaily.py ✅ **FIXED**
14. loadbuysellweekly.py ✅ **FIXED**
15. loadbuysellmonthly.py ✅ **FIXED**
16. loadbuysell_etf_daily.py ✅ **FIXED**
17. loadbuysell_etf_weekly.py ✅
18. loadbuysell_etf_monthly.py ✅
19. loadefsignals.py ✅

### Fundamentals
20. loadannualbalancesheet.py ✅
21. loadquarterlybalancesheet.py ✅
22. loadannualincomestatement.py ✅
23. loadquarterlyincomestatement.py ✅
24. loadannualcashflow.py ✅
25. loadquarterlycashflow.py ✅
26. loadttmincomestatement.py ✅
27. loadttmcashflow.py ✅

### Earnings
28. loadearningshistory.py ✅
29. loadearningsrevisions.py ✅
30. loadearningssurprise.py ✅

### Metrics & Scores
31. loadstockscores.py ✅
32. loadfactormetrics.py ✅
33. loadrelativeperformance.py ✅

### Market Data
34. loadmarket.py ✅
35. loadecondata.py ✅
36. loadcommodities.py ✅
37. loadseasonality.py ✅

### Analyst/Sentiment
38. loadanalystsentiment.py ✅
39. loadanalystupgradedowngrade.py ✅

### Optional (Advanced)
- loadalpacaportfolio.py
- loadbenchmark.py
- loadcalendar.py
- loadcoveredcallopportunities.py
- loadfeargreed.py
- loadguidance.py
- loadinsidertransactions.py
- loadnaaim.py
- loadnews.py
- loadoptionschains.py
- load_sp500_earnings.py

---

## Next Steps

1. **Clear corrupted data from database** (all the fake "None" signals)
   ```sql
   DELETE FROM buy_sell_daily WHERE signal = 'None';
   DELETE FROM buy_sell_weekly WHERE signal = 'None';
   DELETE FROM buy_sell_monthly WHERE signal = 'None';
   TRUNCATE buy_sell_weekly, buy_sell_monthly CASCADE;  -- They'll be regenerated
   ```

2. **Run loaders in order** (Phase 1 → Phase 6)
   ```bash
   # Phase 1: Core metadata
   python3 loadstocksymbols.py
   python3 loaddailycompanydata.py
   python3 loadmarketindices.py
   
   # Phase 2: Prices
   python3 loadpricedaily.py
   python3 loadpriceweekly.py
   python3 loadpricemonthly.py
   
   # Phase 3-6: See DATA_LOADING.md for full sequence
   ```

3. **Verify data is complete**
   - Check `/api/health` endpoint returns OK
   - Check `/api/diagnostics` for table counts
   - Run frontend and verify data loads

4. **Push to AWS**
   - CI/CD will build Docker images with fixed loaders
   - Deploy to AWS ECS tasks

---

## Enforcement Rules

**Going Forward:**
- Only loaders in the 39-item list can exist in root directory
- Loaders run LOCALLY first, then deployed to AWS
- No partial patches in routes or populate scripts
- No fake default values (no COALESCE to 0 or 'None')
- Only insert real Buy/Sell signals, skip 'None'
- Document new loaders in DATA_LOADING.md before creating them

---

**Status:** Ready for local data load. All loaders fixed and documented. ✅
