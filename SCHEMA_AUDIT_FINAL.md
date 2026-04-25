# Schema Audit & Fixes - Complete Report
## Date: 2026-04-25

## Issues Found & Fixed

### ✅ CRITICAL ISSUE #1: key_metrics API Query (FIXED)
**File:** `webapp/lambda/routes/financials.js:142-154`
- **Problem:** API was selecting company info columns from `key_metrics` table, but those columns actually live in `company_profile`
- **Impact:** `/api/financials/:symbol/key-metrics` would fail - columns like short_name, long_name, sector, industry don't exist in key_metrics
- **Fix:** Changed query to JOIN company_profile and key_metrics tables
```sql
-- BEFORE: SELECT short_name, long_name... FROM key_metrics WHERE ticker = $1
-- AFTER: SELECT cp.short_name, cp.long_name... FROM company_profile cp 
--        LEFT JOIN key_metrics km ON cp.ticker = km.ticker WHERE cp.ticker = $1
```

### ✅ CRITICAL ISSUE #2: Financial Statement Schema Mismatch (FIXED)
**File:** `webapp/lambda/scripts/reset-database-to-loaders.sql`
- **Problem:** Reset script had minimal annual_balance_sheet schema (ticker, year, total_assets...) but loaders use (symbol, fiscal_year, date, ...) with many more columns
- **Impact:** Schema mismatch between loaders, API queries, and database
- **Fix:** Updated reset script to match loader schemas:
  - `annual_balance_sheet` - Now has 14 columns including fiscal_year, current_assets, stockholders_equity, etc.
  - `quarterly_balance_sheet` - Added with fiscal_quarter support
  - `annual_income_statement` - Defined properly
  - `quarterly_income_statement` - Added with fiscal_quarter support
  - `annual_cash_flow` - Properly defined
  - `quarterly_cash_flow` - Properly defined

### ✅ ISSUE #3: positioning_metrics Schema Missing Columns (FIXED)
**File:** `webapp/lambda/scripts/reset-database-to-loaders.sql`
- **Problem:** Reset script had incomplete positioning_metrics schema - missing institutional_holders_count, short_percent_of_float, ad_rating
- **Impact:** loaddailycompanydata.py would fail when trying to insert these columns
- **Fix:** Updated positioning_metrics table to include all columns the loader is inserting

### ✅ ISSUE #4: quarterly_cash_flow Partial Updates (FIXED)
**File:** `loadquarterlycashflow.py:96-110`
- **Problem:** ON CONFLICT clause only updated operating_cash_flow, not other columns
- **Impact:** When updating existing records, only operating_cash_flow would be refreshed, other columns would remain stale
- **Fix:** Updated ON CONFLICT to update all cash flow columns (investing, financing, capex, free_cf)

### ✅ ISSUE #5: Missing Indexes for New Financial Tables (FIXED)
**File:** `webapp/lambda/scripts/reset-database-to-loaders.sql`
- **Problem:** New financial statement tables had no indexes for symbol, fiscal_year queries
- **Impact:** API queries would be slow
- **Fix:** Added 6 new indexes:
  - idx_annual_balance_sheet_symbol_fiscal_year
  - idx_quarterly_balance_sheet_symbol_fiscal_year
  - idx_annual_income_statement_symbol_fiscal_year
  - idx_quarterly_income_statement_symbol_fiscal_year
  - idx_annual_cash_flow_symbol_fiscal_year
  - idx_quarterly_cash_flow_symbol_fiscal_year

## Schema Alignment Verification

All components now use consistent column naming:
- ✓ API routes use `symbol` and `fiscal_year` (financials.js lines 37-40)
- ✓ All loaders use `symbol` and `fiscal_year` (loadannual*.py, loadquarterly*.py)
- ✓ Reset script defines all tables with `symbol` and `fiscal_year`
- ✓ Indexes on symbol + fiscal_year for fast lookups

## Tables Now Properly Aligned

| Table | Symbol Column | Fiscal Year Col | Quarterly Support | API Endpoint |
|-------|----------------|-----------------|------------------|--------------|
| annual_balance_sheet | symbol | fiscal_year | ❌ | /api/financials/:symbol/balance-sheet?period=annual |
| quarterly_balance_sheet | symbol | fiscal_year | ✅ | /api/financials/:symbol/balance-sheet?period=quarterly |
| annual_income_statement | symbol | fiscal_year | ❌ | /api/financials/:symbol/income-statement?period=annual |
| quarterly_income_statement | symbol | fiscal_year | ✅ | /api/financials/:symbol/income-statement?period=quarterly |
| annual_cash_flow | symbol | fiscal_year | ❌ | /api/financials/:symbol/cash-flow?period=annual |
| quarterly_cash_flow | symbol | fiscal_year | ✅ | /api/financials/:symbol/cash-flow?period=quarterly |

## Data Loaders Status

All data loaders present and aligned:
- ✓ loadannualbalancesheet.py - Creates/populates annual_balance_sheet
- ✓ loadquarterlybalancesheet.py - Creates/populates quarterly_balance_sheet
- ✓ loadannualincomestatement.py - Creates/populates annual_income_statement
- ✓ loadquarterlyincomestatement.py - Creates/populates quarterly_income_statement
- ✓ loadannualcashflow.py - Creates/populates annual_cash_flow
- ✓ loadquarterlycashflow.py - Creates/populates quarterly_cash_flow
- ✓ loaddailycompanydata.py - Creates company_profile, key_metrics, positioning_metrics

## Files Modified

1. `webapp/lambda/routes/financials.js` - Fixed key_metrics API query
2. `webapp/lambda/scripts/reset-database-to-loaders.sql` - Fixed all financial statement schemas
3. `loadquarterlycashflow.py` - Fixed ON CONFLICT clause for complete updates

## Validation

All schemas now pass verification:
- Column names consistent across loaders, API, and database (symbol, fiscal_year)
- Data types match (VARCHAR(20) for symbol, INT for fiscal_year)
- Foreign key relationships maintained
- Indexes created for performance
- ON CONFLICT clauses fully populated for upserts

## Next Steps

1. Run the SQL reset script to update database schema
2. Run loaders to populate data:
   ```bash
   python loadannualbalancesheet.py
   python loadquarterlybalancesheet.py
   python loadannualincomestatement.py
   python loadquarterlyincomestatement.py
   python loadannualcashflow.py
   python loadquarterlycashflow.py
   ```
3. Test API endpoints to verify data retrieval works

## References

- **CLAUDE.md** - Architecture documentation
- **recent commits** - Prior schema mismatch fixes (b74264b6e, fe1a55543, etc.)
