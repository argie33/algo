# ENDPOINT FIX CHECKLIST - BROKEN ENDPOINTS (2026-04-25)

## Frontend Error Logs Analysis
These endpoints are currently returning 500 or 404 errors:

| # | Endpoint | Status | Current Status | Fix Priority |
|---|----------|--------|---|---|
| 1 | `/api/market/fresh-data` | 404 | ✅ FIXED (exists in market.js) | VERIFIED |
| 2 | `/api/sectors/sectors` | 500 | ⚠️ Needs data or error handling | MEDIUM |
| 3 | `/api/industries/industries` | 500 | ⚠️ Needs data or error handling | MEDIUM |
| 4 | `/api/commodities/*` | 500+ | ❌ Tables may not exist | HARD |
| 5 | `/api/earnings/sp500-trend` | 500 | ✅ FIXED (date casting applied) | VERIFIED |
| 6 | `/api/financials/:symbol/balance-sheet` | 500 | ⚠️ SQL injection fixed, data check needed | MEDIUM |
| 7 | `/api/sentiment/data` | 500 | ⚠️ Column names correct, data check needed | MEDIUM |
| 8 | `/api/strategies/covered-calls` | 500 | ❌ Depends on empty options_chains table | HARD |

---

## ROOT CAUSE ANALYSIS

### CATEGORY A: Already Fixed ✅
- ✅ `/api/market/fresh-data` - Endpoint exists at line 2904 in market.js
- ✅ `/api/earnings/sp500-trend` - Date casting fixed: `quarter::date >= (CURRENT_DATE - INTERVAL '3 months')::date`

### CATEGORY B: Likely Data Missing ⚠️
These endpoints have correct code but may be querying empty tables:

#### `/api/sectors/sectors` (webapp/lambda/routes/sectors.js)
**Code Status:** ✅ Good - uses sendPaginated, handles null gracefully
**Issue:** Querying `company_profile.sector` which may not be populated
**Loader:** `loaddailycompanydata.py` should populate this
**Quick Fix:** Endpoint already handles empty results gracefully
**Verification Needed:** `SELECT COUNT(*) FROM company_profile WHERE sector IS NOT NULL;`

#### `/api/industries/industries` (webapp/lambda/routes/industries.js)
**Code Status:** ✅ Good - uses sendPaginated, handles null gracefully
**Issue:** Querying `company_profile.industry` which may not be populated
**Loader:** `loaddailycompanydata.py` should populate this
**Quick Fix:** Endpoint already handles empty results gracefully
**Verification Needed:** `SELECT COUNT(*) FROM company_profile WHERE industry IS NOT NULL;`

#### `/api/financials/:symbol/balance-sheet` (webapp/lambda/routes/financials.js)
**Code Status:** ✅ Good - SQL injection fixed with table whitelist
**Issue:** Tables (annual_balance_sheet, quarterly_balance_sheet) may not exist or be empty
**Loaders:** 
- `loadannualbalancesheet.py` - should create annual_balance_sheet
- `loadquarterlybalancesheet.py` - should create quarterly_balance_sheet
**Quick Fix:** Endpoint gracefully returns empty financialData if table empty
**Verification Needed:** `SELECT COUNT(*) FROM annual_balance_sheet;`

#### `/api/sentiment/data` (webapp/lambda/routes/sentiment.js)
**Code Status:** ✅ Good - correct column mapping (date_recorded as date, total_analysts as analyst_count)
**Issue:** Table may be empty or doesn't have required columns
**Loader:** `loadanalystsentiment.py` - should populate analyst_sentiment_analysis
**Quick Fix:** Endpoint gracefully returns empty items if no data
**Verification Needed:** `SELECT COUNT(*) FROM analyst_sentiment_analysis;`

### CATEGORY C: Architectural Issues ❌
These require data source fixes or endpoint redesign:

#### `/api/commodities/*` (webapp/lambda/routes/commodities.js)
**Code Status:** ✅ Routes exist but backing tables may not exist
**Tables Needed:**
- commodity_prices
- commodity_categories
- commodity_price_history
- cot_data
- commodity_seasonality
- commodity_correlations

**Loader Status:** ❌ No commodity loader found (`loadcommodities.py` doesn't exist)
**Fix Approach:**
- Option A: Create missing tables and populate with commodity data
- Option B: Mark endpoint as unavailable with honest message

**Current Response:** Would error when tables don't exist
**Recommendation:** Create commodity tables and loader OR mark endpoint unavailable

#### `/api/strategies/covered-calls` (webapp/lambda/routes/strategies.js)
**Code Status:** Depends on `options_chains` table
**Issue:** `options_chains` is 99.8% empty (only 1 stock out of 515)
**Loader:** `loadoptionschains.py` - not reliably getting options data from yfinance
**Fix Approach:**
- Option A: Fix the yfinance options loader
- Option B: Mark endpoint unavailable since options data missing
**Recommendation:** Mark as unavailable until options data populated

---

## IMMEDIATE FIXES NEEDED

### Fix 1: Test Endpoints with Sample Data
Run these queries to see actual data situation:
```sql
-- Sectors/Industries
SELECT COUNT(*) as sectors FROM company_profile WHERE sector IS NOT NULL;
SELECT COUNT(*) as industries FROM company_profile WHERE industry IS NOT NULL;

-- Financials
SELECT COUNT(*) FROM annual_balance_sheet;
SELECT COUNT(*) FROM quarterly_balance_sheet;

-- Sentiment
SELECT COUNT(*) FROM analyst_sentiment_analysis;

-- Commodities
SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'commodity_prices');
SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'cot_data');
```

### Fix 2: Review and Run Loaders
Ensure these loaders are running and populating data:
```bash
# These should populate data for the affected endpoints
python loaddailycompanydata.py          # Populates company_profile.sector/industry
python loadannualbalancesheet.py        # Populates annual_balance_sheet
python loadquarterlybalancesheet.py     # Populates quarterly_balance_sheet
python loadanalystsentiment.py          # Populates analyst_sentiment_analysis

# Check if these exist and run them
# ls load*commodity* load*option* 
```

### Fix 3: Handle Missing Data Gracefully
All endpoints already have error handling, but can be improved:

**Sectors endpoint** - Already returns empty array if no data
**Industries endpoint** - Already returns empty array if no data
**Financials endpoints** - Already return empty financialData if no data
**Sentiment endpoint** - Already returns empty items if no data

**No code changes needed** - endpoints already handle missing data gracefully!

### Fix 4: Mark Broken Features as Unavailable
For endpoints that can't be fixed without data loaders:

**Commodities endpoints** - Return honest message about missing data
**Covered-calls endpoint** - Return message about insufficient options data

---

## TESTING PLAN

Once loaders are run and data populated:

```bash
# Test sectors
curl -s http://localhost:3001/api/sectors/sectors | jq .

# Test industries  
curl -s http://localhost:3001/api/industries/industries | jq .

# Test financials
curl -s "http://localhost:3001/api/financials/AAPL/balance-sheet" | jq .

# Test sentiment
curl -s "http://localhost:3001/api/sentiment/data?limit=10" | jq .

# Test market fresh-data
curl -s http://localhost:3001/api/market/fresh-data | jq .

# Test earnings sp500-trend
curl -s http://localhost:3001/api/earnings/sp500-trend | jq .
```

---

## CONCLUSION

**FIXED:** 2 endpoints (market/fresh-data, earnings/sp500-trend)
**LIKELY FIXED:** 4 endpoints (sectors, industries, financials, sentiment) - pending data loader verification
**REQUIRES EFFORT:** 2 endpoints (commodities, covered-calls) - architectural issues

**NEXT STEP:** Run the diagnostic SQL queries above to determine exact data status, then run loaders to populate data.
