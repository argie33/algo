# API Schema Fixes - Complete List

**Status**: Finding and fixing all column name mismatches in API routes

---

## Fixed

### ✅ earnings.js
- Fixed line 60: `ORDER BY period DESC` → `ORDER BY quarter DESC`
- Fixed line 74: `ee.quarter = ee.period` → `ee.quarter = ee.quarter`
- Fixed line 91: Changed from `earnings_history` to `earnings_estimates` for surprise data

---

## To Fix

### API files using "period" (which doesn't exist in schema)

These files reference "period" column which should be "quarter":

#### 1. economic.js
Find and replace:
- `ORDER BY period` → `ORDER BY quarter`
- Search for any reference to "period" column and verify it exists

#### 2. financials.js
Find and replace:
- `period` column references → verify they exist in the actual financial tables
- Check `balance_sheet`, `income_statement`, `cash_flow` table schemas

#### 3. market.js
Find and replace:
- Any "period" references in time-series data

#### 4. portfolio.js
Find and replace:
- "period" column references → appropriate date/time columns

#### 5. sectors.js
Find and replace:
- Any "period" references in sector ranking/historical data

#### 6. sentiment.js
Check for:
- "period" column usage (likely should be "date")
- Verify all selected columns exist in `analyst_sentiment_analysis`

---

## General Guidelines for Fixing

### 1. Identify the Issue
```bash
# Find all files using "period"
grep -r "period" webapp/lambda/routes/*.js | grep -v "//" | head -20
```

### 2. Check Against Schema
For each query, cross-reference against `SCHEMA_DEFINITION.md`:
- Does the table exist?
- Do the columns exist?
- Are column names spelled correctly?
- Is the column type appropriate for the operation?

### 3. Fix Pattern

**Before**:
```sql
SELECT * FROM table_name 
WHERE created_at > $1
ORDER BY period DESC
```

**After**:
```sql
SELECT * FROM table_name 
WHERE created_at > $1
ORDER BY quarter DESC  -- or appropriate column name
```

### 4. Test the Fix
```bash
# Restart API
node webapp/lambda/index.js

# Test endpoint
curl http://localhost:3001/api/earnings/info?symbol=AAPL
```

Should return actual data, not empty arrays or NULL values.

---

## Known Problem Areas

### 1. Earnings Data
- **Tables**: earnings_estimates, earnings_history
- **Common error**: Using "period" instead of "quarter"
- **Fix**: Replace all `period` with `quarter`

### 2. Financial Statements
- **Tables**: annual_income_statement, annual_balance_sheet, annual_cash_flow
- **Common error**: May reference wrong column names
- **Action needed**: Verify all columns against actual schema

### 3. Sentiment Data
- **Tables**: analyst_sentiment_analysis
- **Common error**: Column names may not match
- **Action needed**: Check all selected columns exist

### 4. Time-Based Queries
- **Common error**: Using "period" for what should be "date" or "quarter"
- **Fix**: Review each query's intent and use correct column name

---

## Validation Checklist

Before committing API changes:

- [ ] Query runs without SQL errors
- [ ] All selected columns exist in table
- [ ] Column names match exactly (case-sensitive)
- [ ] Data types are appropriate for operations
- [ ] JOIN conditions use correct column names
- [ ] WHERE clauses reference valid columns
- [ ] ORDER BY uses valid columns
- [ ] GROUP BY uses valid columns
- [ ] API response includes actual data, not NULL

---

## Testing

### Unit Test Pattern

```javascript
// Test earnings endpoint
const response = await query("GET /api/earnings/info?symbol=AAPL");
assert(response.data.estimates.length > 0, "Should return estimates");
assert(response.data.estimates[0].eps_estimate !== null, "Should have eps_estimate data");
assert(response.success === true, "Should succeed");
```

### Manual Testing

```bash
# Test each fixed endpoint
curl http://localhost:3001/api/earnings/info?symbol=AAPL | jq '.data.estimates[0]'
curl http://localhost:3001/api/economic/data | jq '.data[0]'
curl http://localhost:3001/api/financials/AAPL/balance-sheet | jq '.data[0]'
```

All should return actual data with non-NULL values.

---

## Priority Order for Fixes

1. **CRITICAL**: earnings.js (Fixed ✅)
2. **HIGH**: sentiment.js, analysts.js
3. **MEDIUM**: financials.js, market.js
4. **LOW**: economic.js, portfolio.js, sectors.js

---

## Script to Find All Issues

```bash
#!/bin/bash
echo "Finding all SQL column references..."
echo ""

# Find potential period issues
echo "Files using 'period' column:"
grep -r "period" webapp/lambda/routes/*.js | grep -v "//" | wc -l

# Find all table references
echo "Tables referenced in APIs:"
grep -r "FROM\|JOIN" webapp/lambda/routes/*.js | \
  grep -o "FROM [a-z_]*\|JOIN [a-z_]*" | \
  sort | uniq | head -30

# Find SELECT * usage (bad practice)
echo "Files using SELECT * (should be specific columns):"
grep -r "SELECT \*" webapp/lambda/routes/*.js | \
  cut -d: -f1 | sort | uniq
```

---

## Summary

- **Total files with issues**: ~7 API route files
- **Main issue**: Using "period" column that doesn't exist
- **Status**: earnings.js FIXED, others need review
- **Impact**: Null/empty data in API responses
- **User symptom**: Blank sections on frontend (what was reported!)

The schema cleanup (loaders + init_database.py) fixes the DATA SIDE.  
The API fixes (this document) fixes the QUERY SIDE.  
Together they ensure data flows correctly end-to-end.
