# Data Quality Report - Financial Statements

## Critical Issues Found

### 1. Impossible Gross Profit Values
**Status:** CRITICAL ❌
- **Issue:** 3,466 records have gross_profit > revenue (impossible)
- **Impact:** Quality metrics calculated from this data are unreliable
- **Examples:**
  - CHTR (2021): Revenue $447K, Gross Profit $954M (213,222% margin!)
  - VRTS (2024): Revenue $894K, Gross Profit $1.7B (191,590% margin!)

### 2. Unit Mismatch
**Status:** LIKELY ⚠️
- The financial data appears to be in different units (thousands vs millions)
- Revenue shown as small numbers while gross profit shows billions

### 3. Root Cause
The financial statement loaders (loadannualincomestatement.py, loadannualbalancesheet.py) are either:
- Parsing data incorrectly from source API
- Mixing data with inconsistent units
- Loading from corrupted or malformed source data

## What Was Done

✅ Successfully calculated and populated 4,969 quality_metrics records with:
- gross_margin_pct, operating_margin_pct, profit_margin_pct
- debt_to_equity, current_ratio, return_on_equity_pct, return_on_assets_pct

❌ Problem: These values are unreliable because source data is corrupted
- Margins can exceed 100% (impossible)
- Ratios may be invalid
- Example: NVDA shows 741% gross margin

## Recommendation

**The financial data needs to be audited and reloaded.** 

Until that's done:
1. Quality metrics will display unreliable values
2. Should not be used for investment analysis
3. Needs validation constraint: gross_profit <= revenue

Would you like me to:
1. Investigate the financial statement loaders to find the data corruption source?
2. Implement data validation to catch these issues?
3. Reload financial data from a cleaner source?

