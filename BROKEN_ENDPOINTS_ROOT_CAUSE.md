# 🔴 BROKEN ENDPOINTS - ROOT CAUSE ANALYSIS

**Based on Frontend Error Logs**

---

## CRITICAL FAILURES (IMMEDIATE FIXES NEEDED)

### 1. ❌ `/api/sectors/sectors?limit=20` - 500 ERROR

**Symptom**: SectorAnalysis.jsx getting 500 Internal Server Error

**Root Cause**: 
- Querying `company_profile.sector` field
- `company_profile` table may not have sector data populated
- Or column doesn't exist in schema

**Location**: `webapp/lambda/routes/sectors.js:15-34`

**Fix Required**:
```sql
-- Check if sector data exists
SELECT COUNT(*) FROM company_profile WHERE sector IS NOT NULL;
-- If 0, then data not loaded

-- Check if column exists
\d company_profile | grep sector;
```

**Solution**:
- [ ] Verify loaddailycompanydata.py is populating company_profile.sector
- [ ] If not, add sector population to that loader
- [ ] Or populate from yfinance directly

---

### 2. ❌ `/api/industries/industries` - 500 ERROR

**Symptom**: SectorAnalysis.jsx getting 500 Internal Server Error

**Root Cause**: 
- Querying `company_profile.industry` field
- Same issue as sectors - data not populated

**Location**: `webapp/lambda/routes/industries.js:17-58`

**Fix Required**: Same as above - verify industry data in company_profile

---

### 3. ❌ `/api/commodities/*` - MULTIPLE 500s + CONNECTION REFUSED

**Symptoms**:
- `/api/commodities/categories` - 500
- `/api/commodities/prices?limit=100` - 500
- `/api/commodities/market-summary` - 500
- `/api/commodities/correlations?minCorrelation=0.5` - 500
- `/api/commodities/cot/GC=F` - 500
- `/api/commodities/seasonality/GC=F` - 500

**Root Cause**: 
- Commodities routes not fully implemented
- Missing routes OR broken queries
- commodities.js exists but endpoints failing

**Location**: `webapp/lambda/routes/commodities.js`

**Investigation Needed**:
- [ ] Check if commodities.js has all these routes
- [ ] Check if commodity tables exist and have data
- [ ] Verify loadcommodities.py is working

---

### 4. ❌ `/api/earnings/sp500-trend?years=10` - 500 ERROR

**Symptom**: EarningsCalendar.jsx getting 500

**Root Cause**: 
- We fixed this endpoint earlier but query might still be broken
- Check line 159-172 in earnings.js

**Location**: `webapp/lambda/routes/earnings.js:159-172`

**Issue**: 
```javascript
const result = await query(
  `SELECT COUNT(DISTINCT symbol) as stock_count FROM earnings_history
   WHERE quarter >= DATE_TRUNC('quarter', CURRENT_DATE - INTERVAL '1 quarter')`
);
```

**Problem**: Missing CAST or wrong date logic

**Fix**:
```javascript
const result = await query(
  `SELECT COUNT(DISTINCT symbol) as stock_count FROM earnings_history
   WHERE quarter >= DATE_TRUNC('quarter', CURRENT_DATE) - INTERVAL '1 quarter'`
);
```

---

### 5. ❌ `/api/financials/AAPL/balance-sheet?period=annual` - 500 ERROR

**Symptom**: FinancialData.jsx getting 500

**Root Cause**: 
- Query error in financials.js
- Table name or column name mismatch

**Location**: `webapp/lambda/routes/financials.js:27-62`

**Investigation**:
- [ ] Check if `annual_balance_sheet` table exists
- [ ] Check if query in financials.js matches table structure
- [ ] Verify loadannualbalancesheet.py populated the table

---

### 6. ❌ `/api/sentiment/data?limit=512&page=1` - 500 ERROR

**Symptom**: Sentiment.jsx getting 500 repeatedly

**Root Cause**: 
- We modified sentiment.js but there's still an issue
- Check if `analyst_sentiment_analysis` table has the right columns

**Location**: `webapp/lambda/routes/sentiment.js:18-83`

**Possible Issues**:
- Column name mismatch (analyst_count vs total_analysts)
- Date column not called "date"

---

### 7. ❌ `/api/strategies/covered-calls?...` - 500 ERROR

**Symptom**: CoveredCallOpportunities.jsx getting 500

**Root Cause**: 
- Depends on options_chains table (which is 99.8% empty)
- Endpoint trying to query data that doesn't exist

**Location**: `webapp/lambda/routes/strategies.js` (if exists)

**Real Issue**: 
- Options chains are broken (only 1/515 stocks)
- Covered call calculations impossible without options data

---

### 8. ❌ `/api/market/fresh-data` - 404 NOT FOUND

**Symptom**: Missing endpoint entirely

**Root Cause**: 
- Frontend calling endpoint that doesn't exist
- Probably removed or never created

**Investigation**:
- [ ] Search for `fresh-data` in routes
- [ ] Check if endpoint was meant to exist
- [ ] Check if should be in market.js or earnings.js

---

## ARCHITECTURAL PATTERNS FOUND

### Pattern 1: Querying Empty Tables
**Problem**: Endpoints query tables that have no data
**Examples**: 
- sectors/industries querying company_profile without sector/industry data
- commodities querying commodity tables with no data
- covered-calls querying options_chains (1 record)

**Solution**: Verify data loaders are actually populating these tables

### Pattern 2: Column Name Mismatches  
**Problem**: Loaders create columns with one name, endpoints query different name
**Examples**:
- sentiment endpoint expects "analyst_count" but loader creates "total_analysts"
- balance-sheet query might not match actual column names

**Solution**: Standardize column names between loaders and endpoints

### Pattern 3: Missing Data Sources
**Problem**: Tables created but loaders don't populate them
**Examples**:
- earnings_estimates (0% populated)
- options_chains (0.2% populated)
- ETF price tables (errors)

**Solution**: Either populate with data or remove the endpoints

### Pattern 4: Abandoned Endpoints
**Problem**: Endpoints exist but tables or data missing
**Examples**:
- covered-calls (depends on missing options data)
- commodities sub-endpoints (possibly missing tables)

**Solution**: Either fix data source or mark as unavailable

---

## IMMEDIATE ACTION PLAN

### Phase 1: Verify Data (30 minutes)
```sql
-- Check company_profile completeness
SELECT COUNT(*) FROM company_profile;
SELECT COUNT(*) FROM company_profile WHERE sector IS NOT NULL;
SELECT COUNT(*) FROM company_profile WHERE industry IS NOT NULL;

-- Check financial statements
SELECT COUNT(*) FROM annual_balance_sheet;
SELECT COUNT(*) FROM annual_income_statement;

-- Check analyst sentiment
SELECT COUNT(*) FROM analyst_sentiment_analysis;

-- Check commodities
SELECT COUNT(*) FROM commodity_prices;
SELECT table_name FROM information_schema.tables 
WHERE table_name LIKE '%commodity%' OR table_name LIKE '%commodit%';
```

### Phase 2: Fix Column Name Mismatches (15 minutes)

**sentiment.js** - Check actual column names in analyst_sentiment_analysis:
- Is it `analyst_count` or `total_analysts`?
- Is date column called `date` or something else?

**financials.js** - Check actual columns in balance sheet tables

### Phase 3: Fix Broken Endpoints (1 hour)

1. **sectors.js & industries.js**
   - If company_profile.sector/industry exist: leave as-is
   - If not: query from different table or mark unavailable

2. **commodities.js**
   - Check which endpoints have backing data
   - Remove endpoints without data
   - Fix those that have data

3. **earnings.js**
   - Fix sp500-trend query syntax
   - Test other earnings endpoints

4. **financials.js**
   - Verify table names match (annual_balance_sheet vs balance_sheet, etc.)
   - Fix column references

5. **strategies.js**
   - If covered-calls depends on options_chains: mark unavailable
   - Remove broken endpoint or add note about missing data

### Phase 4: Add Proper Error Messages (15 minutes)

For endpoints querying missing data, return honest response:
```javascript
// Instead of 500 error
return sendSuccess(res, {
  note: "This feature requires data that hasn't been populated yet",
  suggestion: "Check if [loader] has been run"
});
```

---

## SUCCESS CRITERIA

When all fixed:
- ✅ No more 500 errors from data queries
- ✅ No 404s on valid endpoints
- ✅ All endpoints return proper response format
- ✅ Honest messages when data unavailable
- ✅ All frontend components can load their data

---

## NEXT STEPS

1. Run the SQL diagnostic queries above
2. Get output of what tables exist and what's populated
3. Fix column mismatches found
4. Fix broken queries
5. Test each endpoint with curl
6. Deploy fixes

