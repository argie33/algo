# Symbol Filtering Fix for loadstockscores.py

## Summary
Fixed incomplete symbol filtering in `loadstockscores.py` to exclude non-common-stock securities from scoring calculations.

## What Was Fixed
**File:** `loadstockscores.py` (lines 496-516)

### Previous Filtering (Incomplete)
The loader only excluded:
- ETFs (via `s.etf = 'N'`)
- Test issues
- Delisted companies

### New Filtering (Comprehensive)
Now excludes ALL non-common-stock securities:

```sql
AND s.symbol NOT ILIKE '%$%'                          -- Preferred Shares
AND s.security_name NOT ILIKE '%SPAC%'               -- SPACs
AND s.security_name NOT ILIKE '%Special Purpose%'    -- SPACs
AND s.security_name NOT ILIKE '%Blank Check%'        -- SPAC Acquisition Companies
AND s.security_name NOT ILIKE '%Acquisition Company%' -- Acquisition Companies
AND s.security_name NOT ILIKE '%ETN%'                -- Exchange Traded Notes
AND s.security_name NOT ILIKE '%Fund%'               -- Mutual Funds
AND s.security_name NOT ILIKE '%Trust%'              -- Trusts
```

## Why This Matters

### Symbols Affected
- **Preferred Shares:** CADE$A, TFC$I, etc. (symbols with $ suffix)
- **SPACs:** Blank check companies and special purpose acquisition vehicles
- **ETNs:** Exchange Traded Notes (debt instruments, not equity)
- **Funds:** Mutual funds and similar investment vehicles
- **Trusts:** Investment trusts and holding companies

### Why They Should Be Excluded
1. **Different Characteristics**
   - Preferred shares have fixed dividends, lower volatility
   - SPACs are acquisition vehicles, not operating companies
   - ETNs are debt instruments backed by issuer creditworthiness
   - Funds are investment vehicles, not companies

2. **Limited Liquidity**
   - Preferred shares have lower trading volume
   - SPACs are speculative
   - Not suitable for standard retail analysis

3. **Incompatible Metrics**
   - Our scoring model designed for common stock fundamentals
   - These securities have different valuation metrics
   - Financial ratios not directly comparable

## Consistency Fix
The Lambda API (`webapp/lambda/routes/scores.js`) was already filtering SPACs at the API level but not other types. This fix aligns the loader with API filtering:

- **Before:** Loader calculated scores for all symbols, API filtered some
- **After:** Loader excludes properly, API filters consistently

## Verification
A verification script (`verify_filtering.py`) has been created to test the filtering:
```bash
python3 verify_filtering.py
```

This script shows:
- How many symbols are excluded by each filter
- Examples of excluded symbols
- Total filtered vs unfiltered symbol counts

## Commit
```
d791cb3ae - Fix: Comprehensive symbol filtering in loadstockscores.py
```

## Testing
The fix has been:
- ✅ Verified for Python syntax correctness
- ✅ Committed to GitHub
- ✅ Ready for AWS deployment
- ⏳ Pending database connection test (requires AWS credentials)

## Next Steps
When deployed to AWS:
1. The stock scores loader will skip non-common-stock securities
2. Scoring calculations will be more accurate and efficient
3. API results will be consistent with calculated data
4. Users will see only proper common stocks in results
