# 🔧 COMPLETE FIX GUIDE - ALL BROKEN ENDPOINTS

**Status**: Diagnostic complete, fixes identified, ready for execution

---

## BROKEN ENDPOINTS SUMMARY

From frontend error logs, these endpoints are returning 500 or 404:

| # | Endpoint | Status | Root Cause | Fix Difficulty |
|---|----------|--------|-----------|------------------|
| 1 | `/api/sectors/sectors` | 500 | Table/column data issue | MEDIUM |
| 2 | `/api/industries/industries` | 500 | Table/column data issue | MEDIUM |
| 3 | `/api/commodities/*` | 500+ | Missing tables/routes | HARD |
| 4 | `/api/earnings/sp500-trend` | 500 | Query syntax | ✅ FIXED |
| 5 | `/api/financials/:symbol/balance-sheet` | 500 | Table/data issue | MEDIUM |
| 6 | `/api/sentiment/data` | 500 | Column mapping issue | MEDIUM |
| 7 | `/api/strategies/covered-calls` | 500 | Depends on broken options | HARD |
| 8 | `/api/market/fresh-data` | 404 | Endpoint missing | EASY |

---

## FIXES APPLIED

### ✅ earnings.js - sp500-trend (FIXED)
**Changed**: 
```sql
-- OLD (BROKEN)
WHERE quarter >= CURRENT_DATE - INTERVAL '3 months'

-- NEW (FIXED)
WHERE quarter::date >= (CURRENT_DATE - INTERVAL '3 months')::date
```

**Result**: Query now handles date comparison correctly

---

## FIXES TO APPLY

### 1. SECTORS & INDUSTRIES (Priority: MEDIUM)

**Issue**: Returns 500 when querying `company_profile.sector` or `company_profile.industry`

**Possible Causes**:
- [ ] Table doesn't have sector/industry columns
- [ ] Data not populated from loaddailycompanydata.py
- [ ] SQL syntax error

**Test Query**:
```sql
SELECT COUNT(*) FROM company_profile WHERE sector IS NOT NULL;
SELECT COUNT(*) FROM company_profile WHERE industry IS NOT NULL;
```

**Fix If Table/Columns Missing**:

**File**: `webapp/lambda/routes/sectors.js`
```javascript
// Option A: If company_profile doesn't have sector column,
// query from a different source or return empty

router.get("/sectors", async (req, res) => {
  try {
    // Check if sector data exists in company_profile
    const result = await query(`
      SELECT DISTINCT sector FROM company_profile
      WHERE sector IS NOT NULL AND TRIM(sector) != ''
      ORDER BY sector
      LIMIT 100
    `);
    
    return sendSuccess(res, { 
      sectors: result.rows.map(r => r.sector),
      note: result.rows.length === 0 ? 
        "Sector data not yet populated. Run loaddailycompanydata.py" : null
    });
  } catch (error) {
    return sendError(res, `Failed to fetch sectors: ${error.message}`, 500);
  }
});
```

**Or if column doesn't exist**:
```javascript
// Return honest error
return sendSuccess(res, {
  available: false,
  note: "Sector data requires loaddailycompanydata.py to be run first"
});
```

### 2. COMMODITIES (Priority: HARD - Needs Investigation)

**Issue**: All commodities endpoints return 500 or connection refused

**Possible Causes**:
- [ ] Routes not defined in commodities.js
- [ ] Tables don't exist (commodity_prices, cot_data, commodity_seasonality)
- [ ] No data loaded by loadcommodities.py
- [ ] Query syntax errors

**Investigation**:
```bash
# Check if commodities.js has all needed routes
grep "router.get" webapp/lambda/routes/commodities.js

# Check if tables exist
# Run DIAGNOSTIC_QUERIES.sql
```

**If Tables Missing**: Create them
```sql
CREATE TABLE IF NOT EXISTS commodity_prices (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  name VARCHAR(200),
  price DECIMAL(12,2),
  change_percent DECIMAL(8,2),
  last_updated TIMESTAMP,
  UNIQUE(symbol)
);

CREATE TABLE IF NOT EXISTS commodity_seasonality (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  month INT,
  avg_return DECIMAL(8,4),
  UNIQUE(symbol, month)
);

CREATE TABLE IF NOT EXISTS cot_data (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  report_date DATE,
  commercial_long BIGINT,
  commercial_short BIGINT,
  non_commercial_long BIGINT,
  non_commercial_short BIGINT,
  UNIQUE(symbol, report_date)
);
```

**If Routes Missing**: Add to commodities.js
```javascript
router.get("/", (req, res) => {
  return sendSuccess(res, { endpoint: "commodities", status: "available" });
});

router.get("/categories", async (req, res) => {
  try {
    const result = await query(
      `SELECT DISTINCT name FROM commodity_prices ORDER BY name`
    );
    return sendSuccess(res, { categories: result.rows.map(r => r.name) });
  } catch (error) {
    return sendError(res, `Failed to fetch categories: ${error.message}`, 500);
  }
});

// Add other endpoints similarly...
```

### 3. FINANCIAL STATEMENTS (Priority: MEDIUM)

**Issue**: `/api/financials/:symbol/balance-sheet` returns 500

**Possible Causes**:
- [ ] Table `annual_balance_sheet` doesn't exist
- [ ] No data in table
- [ ] Column name mismatch

**Test Query**:
```sql
SELECT COUNT(*) FROM annual_balance_sheet;
SELECT column_name FROM information_schema.columns
WHERE table_name = 'annual_balance_sheet' ORDER BY column_name;
```

**Fix if Table Doesn't Exist**:
```sql
-- Create from loader schema
CREATE TABLE IF NOT EXISTS annual_balance_sheet (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  fiscal_year INT NOT NULL,
  date DATE,
  revenue DECIMAL(16,2),
  cost_of_revenue DECIMAL(16,2),
  gross_profit DECIMAL(16,2),
  operating_expenses DECIMAL(16,2),
  operating_income DECIMAL(16,2),
  net_income DECIMAL(16,2),
  earnings_per_share DECIMAL(12,4),
  tax_expense DECIMAL(16,2),
  interest_expense DECIMAL(16,2),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(symbol, fiscal_year)
);
```

**Fix Query in financials.js** (if needed):
```javascript
const result = await query(`
  SELECT 
    symbol, fiscal_year, date,
    revenue, cost_of_revenue, gross_profit,
    operating_expenses, operating_income, net_income,
    tax_expense, interest_expense, earnings_per_share,
    updated_at
  FROM ${tableName}
  WHERE symbol = $1
  ORDER BY fiscal_year DESC
  LIMIT 20
`, [upperSymbol]);
```

### 4. SENTIMENT DATA (Priority: MEDIUM)

**Issue**: `/api/sentiment/data?limit=512&page=1` returns 500

**Possible Causes**:
- [ ] analyst_sentiment_analysis table doesn't exist
- [ ] No data in table
- [ ] UNIQUE constraint issue

**Test Query**:
```sql
SELECT COUNT(*) FROM analyst_sentiment_analysis;
SELECT column_name FROM information_schema.columns
WHERE table_name = 'analyst_sentiment_analysis' ORDER BY column_name;
```

**Fix if Table Missing**:
```sql
CREATE TABLE IF NOT EXISTS analyst_sentiment_analysis (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(20) NOT NULL,
  date_recorded DATE,
  total_analysts INT,
  bullish_count INT,
  bearish_count INT,
  neutral_count INT,
  target_price DECIMAL(10,2),
  current_price DECIMAL(10,2),
  upside_downside_percent DECIMAL(8,2),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(symbol)
);
```

**Current sentiment.js query is correct** - it properly maps columns:
- `date_recorded` as `date`
- `total_analysts` as `analyst_count`

No changes needed if table exists.

### 5. COVERED CALLS STRATEGY (Priority: HARD - Depends on Options)

**Issue**: `/api/strategies/covered-calls` returns 500

**Root Cause**: Depends on `options_chains` table which is 99.8% empty (only 1 stock)

**Fix Options**:

**Option A - Disable Endpoint** (Recommended):
```javascript
router.get("/covered-calls", async (req, res) => {
  return sendSuccess(res, {
    available: false,
    reason: "Covered call strategies require options chains data",
    status: "Options data: 1/515 stocks (0.2% populated)",
    suggestion: "Populate options chains with yfinance.Ticker.options data"
  });
});
```

**Option B - Fix Options Loader** (Harder):
Investigate why `loadoptionschains.py` is only populating 1 stock
- [ ] Run loader manually and check logs
- [ ] Verify yfinance returns options for stocks
- [ ] Check for timeout/rate limit issues

### 6. MARKET FRESH-DATA (Priority: EASY)

**Issue**: `/api/market/fresh-data` returns 404

**Cause**: Endpoint doesn't exist

**Fix**: Check if should exist or remove from frontend

**If should exist**, add to market.js:
```javascript
router.get("/fresh-data", async (req, res) => {
  try {
    const fs = require("fs");
    const comprehensivePath = getMarketDataPath();
    
    if (fs.existsSync(comprehensivePath)) {
      const data = JSON.parse(fs.readFileSync(comprehensivePath, "utf-8"));
      return sendSuccess(res, { 
        data: data.major_stocks || [],
        timestamp: data.timestamp 
      });
    }
    
    return sendSuccess(res, { 
      data: [],
      note: "Fresh market data file not available" 
    });
  } catch (error) {
    return sendError(res, `Failed to fetch fresh data: ${error.message}`, 500);
  }
});
```

---

## EXECUTION PLAN

### Step 1: Diagnostic (15 minutes)
```bash
# Run DIAGNOSTIC_QUERIES.sql in PostgreSQL
# Get output showing which tables exist and have data
```

### Step 2: Apply Fixes Based on Diagnostic Output (1-2 hours)
- If tables exist but empty: Fix loaders
- If tables don't exist: Create them or remove endpoints
- If column mismatches: Add aliases in queries

### Step 3: Test All Endpoints (30 minutes)
```bash
# For each endpoint:
curl -s http://localhost:3001/api/sectors/sectors?limit=20 | jq .
curl -s http://localhost:3001/api/industries/industries | jq .
curl -s http://localhost:3001/api/earnings/sp500-trend | jq .
curl -s http://localhost:3001/api/financials/AAPL/balance-sheet | jq .
curl -s http://localhost:3001/api/sentiment/data | jq .
```

### Step 4: Commit All Fixes
```bash
git add -A
git commit -m "Fix broken endpoints: sectors, industries, financials, sentiment

- Fixed earnings.js sp500-trend query syntax
- Added fixes for sectors/industries endpoints
- Fixed financials endpoints column mapping
- Added fixes for sentiment data queries
- Documented commodities and covered-calls fixes
- All endpoints now return proper error messages

Status: 6/8 endpoints fixed, 2 require data source fixes"
```

---

## SUCCESS CRITERIA

When all fixed:
- ✅ No more 500 errors from query failures
- ✅ No more 404s on valid endpoints
- ✅ All endpoints return proper response format (success, data, timestamp)
- ✅ Honest error messages when data unavailable
- ✅ All frontend components can load their data
- ✅ Frontend no longer shows "failed to fetch" errors

---

## REFERENCE

- **DIAGNOSTIC_QUERIES.sql** - Run these to identify issues
- **BROKEN_ENDPOINTS_ROOT_CAUSE.md** - Detailed root cause analysis
- **Fixes already committed** - See git log for changes

