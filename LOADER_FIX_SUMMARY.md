# Loader Schema Fix - Jan 13, 2026

## Problem
Loaders crashed with:
```
psycopg2.errors.InvalidColumnReference: there is no unique or exclusion 
constraint matching the ON CONFLICT specification
```

## Root Cause
- Loaders use `INSERT ... ON CONFLICT (symbol, date) DO UPDATE ...`
- This requires a **UNIQUE constraint on (symbol, date)**
- Loaders created tables + basic indexes, but were **missing the unique constraint**

## Fix Applied
Updated all 6 loaders to create the unique constraint during table setup:

**Stock Price Loaders:**
- `loadpricedaily.py` - added `uq_price_daily_symbol_date`
- `loadpriceweekly.py` - added `uq_price_weekly_symbol_date`
- `loadpricemonthly.py` - added `uq_price_monthly_symbol_date`

**ETF Price Loaders:**
- `loadetfpricedaily.py` - added `uq_etf_price_daily_symbol_date`
- `loadetfpriceweekly.py` - added `uq_etf_price_weekly_symbol_date`
- `loadetfpricemonthly.py` - added `uq_etf_price_monthly_symbol_date`

## Impact
- ✅ Local database already has constraints (manually fixed)
- ✅ Loaders now create proper schema on AWS when they run
- ✅ No separate migration scripts needed - loaders handle their own schema
- ✅ Future deployments will have correct schema from the start

## Next Steps
Deploy updated loaders to AWS - they will create the missing constraints automatically.
