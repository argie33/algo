# Stock Symbol Database Analysis

## Current Filtering in Loaders

### Stock Scores Loader (loadstockscores.py)
**Filters Applied**:
```sql
WHERE s.exchange IN ('NASDAQ', 'New York Stock Exchange', 'American Stock Exchange', 'NYSE Arca', 'BATS Global Markets')
  AND (s.etf = 'N' OR s.etf IS NULL OR s.etf = '')
  AND (s.test_issue != 'Y' OR s.test_issue IS NULL)
  AND (s.financial_status != 'D' OR s.financial_status IS NULL)
```

**Filters**:
- ✅ Excludes ETFs (s.etf = 'N')
- ❌ Does NOT explicitly exclude ETNs, SPACs, or Funds
- ✅ Excludes test issues
- ✅ Excludes delisted companies

### Lambda Stock Scores API (webapp/lambda/routes/scores.js)
**Filters Applied** (Lines 494):
```sql
NOT EXISTS (SELECT 1 FROM stock_symbols WHERE symbol = ss.symbol 
  AND (security_name ILIKE '%SPAC%' 
  OR security_name ILIKE '%Special Purpose%' 
  OR security_name ILIKE '%Equity Partners%' 
  OR security_name ILIKE '%Blank Check%' 
  OR security_name ILIKE '%Acquisition Company%'))
```

**Filters**:
- ✅ Explicitly excludes SPACs from API results
- ❌ Does NOT exclude ETFs, ETNs, or Funds at API level

## Current Stock Database State

### Total Symbols
- **Total in stock_symbols**: ~5,010 symbols
- **In stock_scores**: 403 stocks (based on API results)

### Analysis

Based on API results, we're seeing:
- **Symbols with "ETN" in name**: DGP, ATMP (showing as "iPath Select MLP ETN")
- **Symbols with "ETF" in name**: DJP (showing as "iPath Bloomberg Commodity Index")
- **Symbols with fund characteristics**: Various holding companies

## Issues Found

1. **ETF Column May Not Be Properly Set**
   - The loader filters on `s.etf = 'N'`
   - But we're still seeing ETNs and ETFs in the data
   - This suggests the `etf` column in stock_symbols isn't properly populated

2. **ETNs Are Not Filtered**
   - ETNs (Exchange Traded Notes) are different from ETFs
   - They should probably be excluded like ETFs
   - Currently no filtering on security_name for ETNs in the loader

3. **SPACs Are Filtered in API But Not in Loader**
   - Stock scores loader doesn't filter SPACs
   - But SPAC query endpoint filters them out
   - This creates inconsistency between what's calculated and what's displayed

## Recommendations

### Option 1: Clean Up Database (RECOMMENDED)
```sql
-- Update stock_symbols to properly flag ETFs, ETNs, etc.
UPDATE stock_symbols 
SET etf = 'Y'
WHERE security_name ILIKE '%ETF%'
   OR security_name ILIKE '%ETN%'
   OR security_name ILIKE '%Index Fund%'
   OR security_name ILIKE '%Mutual Fund%';
```

### Option 2: Enhance Loader Filtering
```sql
-- Add filters for ETNs, Funds, etc.
AND (s.etf = 'N' OR s.etf IS NULL OR s.etf = '')
AND security_name NOT ILIKE '%ETN%'
AND security_name NOT ILIKE '%Fund%'
AND security_name NOT ILIKE '%Trust%'
```

### Option 3: Update API Filtering
Currently the API filters SPACs but not other types - should be consistent with what's calculated.

## Current Status

- ✅ SPACs are filtered from API results
- ✅ Test issues excluded
- ✅ Delisted companies excluded
- ❌ ETFs/ETNs/Funds still present in database
- ⚠️ Inconsistency between what's calculated and what's displayed

## Verification Needed

Need to check:
1. Are we actually calculating scores for ETFs/ETNs? (they have limited fundamentals)
2. Do we want to include them in stock_scores table?
3. Should they be excluded at the loader level or just not displayed?

