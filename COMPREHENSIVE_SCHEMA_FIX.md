# Comprehensive Schema & Data Flow Fix Guide
## April 25, 2026 - End-to-End Diagnostic

---

## THE REAL PROBLEM

Data is **not showing on the frontend** because of a **chain of schema/data mismatches** spanning:
1. **Loaders** (what gets written to database)
2. **Database schema** (what columns exist)
3. **API queries** (what gets selected from database)
4. **Frontend calls** (what endpoints are called)

---

## SYSTEMATIC FIX PROCESS

### PHASE 1: Identify All Broken Data Flows

#### Step 1: Test Database Directly
```bash
# Connect to PostgreSQL
psql -h localhost -U stocks -d stocks

# Check what's actually in key tables
SELECT COUNT(*) FROM earnings_history;
SELECT COUNT(*) FROM earnings_estimates;
SELECT COUNT(*) FROM options_chains;
SELECT COUNT(*) FROM analyst_sentiment_analysis;
SELECT COUNT(*) FROM stock_scores;

# Check for NULL values
SELECT COUNT(*) FROM earnings_estimates WHERE eps_estimate IS NOT NULL;
SELECT COUNT(*) FROM earnings_estimates WHERE eps_actual IS NOT NULL;
SELECT COUNT(*) FROM earnings_estimates WHERE revenue_estimate IS NOT NULL;

# Check actual columns in key tables
\d earnings_estimates
\d key_metrics
\d options_chains
\d stock_scores
```

#### Step 2: Test API Endpoints Directly
```bash
# Test each API endpoint with sample data
curl http://localhost:3001/api/earnings/info?symbol=AAPL
curl http://localhost:3001/api/scores/stockscores?limit=1
curl http://localhost:3001/api/technicals/AAPL
curl http://localhost:3001/api/signals/stocks?timeframe=daily&limit=1
curl http://localhost:3001/api/health

# Check for errors in response
```

#### Step 3: Test Frontend Calls
```bash
# Open browser console (F12) and check:
# 1. Are API calls being made?
# 2. What's the response status code?
# 3. What's in the response body?
# 4. Are there any CORS errors?
```

---

## KNOWN ISSUES & FIXES

### Issue 1: Earnings Estimates Table - All NULL Values

**Symptom**: Earnings pages show blank/empty data  
**Root Cause**: No loader populates `eps_estimate` and `revenue_estimate` columns

**Schema has these columns**:
```sql
earnings_estimates (
  id, symbol, quarter, fiscal_quarter, fiscal_year, earnings_date,
  estimated, eps_actual, revenue_actual,
  eps_estimate, revenue_estimate,  ← ALWAYS NULL
  eps_surprise_pct, revenue_surprise_pct, eps_difference, revenue_difference,
  beat_miss_flag, surprise_percent, estimate_revision_days,
  estimate_revision_count, fetched_at, created_at
)
```

**But loaders write**:
- `loaddailycompanydata.py` - DISABLED (was trying wrong columns)
- `loadearningshistory.py` - Only writes actual earnings to `earnings_history` table
- No loader fills forward `eps_estimate` or `revenue_estimate`

**Fix Options**:
1. **Accept reality**: Forward earnings estimates aren't available from yfinance
   - Update frontend to show only historical/actual earnings
   - Remove estimate fields from earnings pages

2. **Use alternative source**: Integrate paid API (FactSet, Refinitiv, S&P Capital IQ)
   - Costs money, may not be in scope

3. **Create mock data**: Populate estimates from analyst sentiment + historical growth
   - Complex but possible

**Recommended Fix Now**:
- Update frontend to NOT show earnings estimates section
- OR mark it as "Data not available"
- Keep historical earnings (actual EPS) which IS loading correctly

---

### Issue 2: Options Chains - 99.8% Empty (1 stock only)

**Symptom**: Options analysis pages completely empty  
**Root Cause**: loadoptionschains.py only loads 1 stock instead of all 515

**What's loading**:
- Only 1 record in options_chains table
- Only 1 record in options_greeks table
- Only 1 record in iv_history table

**Why**: Unknown - needs investigation

**Debug Steps**:
```bash
# 1. Run loader manually with debug output
python3 loadoptionschains.py --debug

# 2. Check if it's timing out on yfinance calls
# 3. Check if there's a break/exit early in the loop
# 4. Check if database inserts are failing silently
```

**Immediate Fix**: 
- Comment out options loader or mark feature as "Coming Soon"
- Prevents 99% empty data pages

**Better Fix**:
- Debug loader, likely yfinance timeout issues
- Add retry logic with exponential backoff
- Add timeout handling for slow symbols

---

### Issue 3: Analyst Data - 30-60% Missing

**Analyst Sentiment**: 70% coverage (359/515)  
**Analyst Upgrades**: 37% coverage (193/515)

**Why**: yfinance API doesn't have complete data for all stocks

**Fix Options**:
1. **Accept limitation**: Not all stocks have analyst coverage
   - Update UI to show "No analyst data available" for missing stocks
   - Is this acceptable? Probably not - most S&P 500 stocks should have analysts

2. **Use alternative source**: Integrate external analyst data API
   - Seeking Alpha, Zacks, MarketWatch, Yahoo Finance News
   - Costs money or requires scraping

3. **Use what we have**: Show data for 70% of stocks
   - But 30% gaps make dashboard look broken

**Immediate Fix**:
- Update frontend to show "Data not yet loaded" instead of blank
- Run analyst loaders with retry logic

---

### Issue 4: Institutional Positioning - 59% Missing (209/515 loaded)

**Why**: yfinance Yahoo Finance API doesn't have complete institutional holdings data

**Fix Options**:
1. **Accept yfinance limitation** - Many stocks genuinely don't have public institutional data
2. **Use alternative source** - SEC EDGAR filings, Bloomberg, FactSet
3. **Supplement with estimates** - Calculate from other metrics

**Immediate Fix**:
- Accept current coverage
- Mark missing data in UI

---

## COMPLETE CHECKLIST - FIX EVERYTHING

### ✅ Part 1: Schema Integrity (DONE)

- [x] Fixed earnings_estimates INSERT mismatch in loaddailycompanydata.py
- [ ] Verify all table schemas match loader expectations
- [ ] Verify all API queries use correct column names

### [ ] Part 2: Data Verification

- [ ] Check each major table has data:
  ```bash
  SELECT COUNT(*) as records, COUNT(DISTINCT symbol) as stocks FROM earnings_history;
  SELECT COUNT(*) as records, COUNT(DISTINCT symbol) as stocks FROM stock_scores;
  SELECT COUNT(*) as records, COUNT(DISTINCT symbol) as stocks FROM technical_data_daily;
  SELECT COUNT(*) as records, COUNT(DISTINCT symbol) as stocks FROM buy_sell_daily;
  SELECT COUNT(*) as records, COUNT(DISTINCT symbol) as stocks FROM options_chains;
  SELECT COUNT(*) as records, COUNT(DISTINCT symbol) as stocks FROM analyst_sentiment_analysis;
  ```

- [ ] Check for NULL values in critical fields:
  ```bash
  SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NULL;
  SELECT COUNT(*) FROM key_metrics WHERE trailing_pe IS NULL;
  SELECT COUNT(*) FROM earnings_history WHERE eps_actual IS NULL;
  ```

### [ ] Part 3: API Query Verification

For each major API endpoint, verify:
1. SQL query is syntactically correct
2. Table names are spelled correctly
3. Column names exist in schema
4. JOINs use correct keys

**Endpoints to check**:
- /api/earnings/info → queries earnings_history, earnings_estimates
- /api/scores/stockscores → queries stock_scores
- /api/technicals/{symbol} → queries technical_data_daily
- /api/signals/stocks → queries buy_sell_daily, price_daily, technical_data_daily
- /api/analysts/sentiment → queries analyst_sentiment_analysis
- /api/options/chains → queries options_chains

### [ ] Part 4: Loader Execution

- [ ] Run each critical loader and capture output:
  ```bash
  python3 loaddailycompanydata.py 2>&1 | tee loader-output.log
  python3 loadoptionschains.py 2>&1 | tee loader-output.log
  python3 loadanalystsentiment.py 2>&1 | tee loader-output.log
  ```

- [ ] Check for errors in output:
  - SQL errors?
  - API connection errors?
  - Timeout errors?
  - Data validation errors?

### [ ] Part 5: Frontend Fix

- [ ] Update frontend pages to handle missing data:
  - Show "Data not yet loaded" instead of blank
  - Show error messages instead of silent failures
  - Add loading spinners while data loads

---

## SPECIFIC QUERY CHECKS

### Verify Earnings Data
```sql
-- Check what columns exist
\d earnings_estimates
\d earnings_history

-- Check data coverage
SELECT COUNT(*) as total, 
       COUNT(DISTINCT symbol) as symbols,
       COUNT(eps_actual) as has_eps_actual,
       COUNT(eps_estimate) as has_eps_estimate,
       COUNT(revenue_estimate) as has_revenue_estimate
FROM earnings_estimates;

-- Check earnings_history
SELECT COUNT(*) as total,
       COUNT(DISTINCT symbol) as symbols,
       COUNT(eps_actual) as has_eps_actual,
       COUNT(eps_estimate) as has_eps_estimate
FROM earnings_history;
```

### Verify Stock Scores
```sql
-- Check columns
\d stock_scores

-- Check data
SELECT COUNT(*) as total,
       COUNT(DISTINCT symbol) as symbols,
       COUNT(composite_score) as has_composite,
       COUNT(growth_score) as has_growth,
       COUNT(quality_score) as has_quality
FROM stock_scores;
```

### Verify Options Data
```sql
-- Check what exists
SELECT COUNT(*) as total,
       COUNT(DISTINCT symbol) as symbols
FROM options_chains;

SELECT COUNT(*) as total,
       COUNT(DISTINCT symbol) as symbols
FROM options_greeks;
```

---

## IF DATA EXISTS BUT APIS DONT WORK

### 1. SQL Syntax Errors

Check API route files for:
- Typos in table names
- Typos in column names
- Invalid SQL syntax
- Missing column qualifiers in joins

Example bad query:
```sql
SELECT id, name, price FROM stocks WHERE id = $1
-- But 'stocks' table doesn't exist, should be 'stock_symbols'
```

### 2. Missing JOINs

APIs might be trying to SELECT columns that don't exist in the main table.

Example:
```sql
SELECT symbol, rsi, macd FROM buy_sell_daily
-- buy_sell_daily doesn't have rsi/macd, need JOIN to technical_data_daily
```

Fix: Ensure all JOINs are present and using correct ON clauses

### 3. Column Name Mismatches

Loader writes to `column_name_1`, API tries to SELECT `column_name_2`

Fix: Grep for all column names in both loader and API, ensure they match:
```bash
# Find all column names loaders write
grep -o "INSERT INTO [a-z_]* ([^)]*)" load*.py | grep -o "[a-z_][a-z0-9_]*"

# Find all column names APIs select
grep -o "SELECT [^F]*FROM" webapp/lambda/routes/*.js | grep -o "[a-z_][a-z0-9_]*"

# Compare and find mismatches
```

---

## TESTING PROCESS

### 1. Test Database
```bash
# Can we connect?
psql -h localhost -U stocks -d stocks -c "SELECT 1"

# Does data exist?
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM stock_scores"

# Are key columns populated?
psql -h localhost -U stocks -d stocks -c "SELECT COUNT(composite_score) FROM stock_scores"
```

### 2. Test API Directly
```bash
# Start the API server
node webapp/lambda/index.js

# In another terminal:
curl -s http://localhost:3001/api/health | jq
curl -s http://localhost:3001/api/stocks?limit=1 | jq
curl -s http://localhost:3001/api/scores/stockscores?limit=1 | jq
```

### 3. Test Frontend
```bash
# Start frontend
cd webapp/frontend-admin && npm run dev

# Open http://localhost:5174 in browser
# F12 → Network tab
# Try clicking on a page
# Check network requests and responses
```

---

## ROOT CAUSE ANALYSIS TEMPLATE

For each missing data issue:

1. **Where is data supposed to come from?**
   - Loader file: ___________
   - Data source: ___________

2. **What table should it be in?**
   - Table: ___________
   - Columns: ___________

3. **Is the loader running?**
   - Yes / No / Unknown
   - If no: Why not?

4. **Is data in the table?**
   - Yes / No / Partial
   - If no/partial: Why not?

5. **Is the API querying the right table?**
   - Yes / No
   - If no: What's the bug?

6. **Is the API returning data?**
   - Yes / No / Errors
   - If no: What's the error?

7. **Is the frontend displaying data?**
   - Yes / No / Errors
   - If no: What's the error?

---

## NEXT ACTIONS

1. **Run this diagnostic** on your database:
   - Connect to PostgreSQL
   - Run all the COUNT queries above
   - See which tables have 0 data

2. **For each empty table**:
   - Find the loader that should populate it
   - Run the loader manually with debug output
   - Check for errors

3. **For each loader with errors**:
   - Fix the error (schema mismatch, API failure, etc.)
   - Re-run loader
   - Verify data now exists

4. **For each API endpoint returning empty**:
   - Test directly with curl
   - Check if database has data
   - If yes, fix API query
   - If no, fix loader

5. **Update frontend**:
   - Show loading states
   - Show error messages  
   - Show "data not available" instead of blanks

---

**This is your complete fix roadmap. Start with the database diagnostics.**
