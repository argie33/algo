# Data Quality Issues - Action Plan for Actual Data Loading

## Current Status (2026-08-02)

### Code-Level Verification Complete
All 14 critical data quality issues have been FIXED in the codebase:
- Issue #1-4: Active data loss → FIXED (commits verified)
- Issue #5-8: Silent mapping issues → FIXED (field mappings restored)
- Issue #9-11: Scoring issues → FIXED (weighting/calculations corrected)
- Issue #12-14: Data source integrity → FIXED (schema/source validation)

### What's Working
- Official data sources only (SEC, Alpaca, FINRA, FRED, NYSE calendar)
- No fallbacks to degraded/stale data
- Fail-fast on missing upstream data
- Proper error handling with data_unavailable markers

### What's Not Yet Done (Practical Verification)
- End-to-end data loading from official sources
- Backfill of historical NULL rows (141K+ rows from before fixes)
- Verification that fixes actually populate previously-empty columns

## Root Cause: Test Environment Limitations

1. **Loaders require distributed locking** (DynamoDB/RDS)
   - Production safety feature to prevent race conditions
   - Needs AWS credentials or running RDS instance
   - Can't run standalone without infrastructure

2. **Test database is empty** (development mode)
   - No price_daily, no financial statements loaded
   - Schema is correct, data just isn't there

3. **It's the weekend**
   - Market closed, no new data to load
   - Orchestrator won't run (trading day check)

## Action Plan: Next Trading Day

### Monday 2026-08-04 (Next Trading Day)

#### Step 1: Verify Loaders Run Successfully (7 AM ET)
```bash
# Wait for orchestrator to run scheduled loaders automatically
# Monitor CloudWatch logs for:
# - load_prices.py: SUCCESS
# - load_technical_indicators.py: SUCCESS
# - load_signal_quality_scores.py: SUCCESS (verify weighting fix)
# - load_financial_statements.py: SUCCESS (verify mappings)
```

#### Step 2: Query Database to Verify Data Loaded Correctly
```bash
# Check that financial data actually populated
psql -c "SELECT COUNT(*) FROM annual_income_statement WHERE diluted_eps IS NOT NULL"
# Expected: > 0 (was NULL before fix)

psql -c "SELECT COUNT(*) FROM annual_balance_sheet WHERE goodwill IS NOT NULL"
# Expected: > 0 (stopped updating before fix)

psql -c "SELECT COUNT(*) FROM signal_quality_scores"
# Expected: > 0 (verify composite_sqs uses corrected weighting)
```

#### Step 3: Backfill Historical NULL Rows
```bash
# Run loaders with backfill to recover data lost before fixes
BACKFILL_DAYS=32 python scripts/run_loader.py financials
BACKFILL_DAYS=32 python scripts/run_loader.py insider_velocity

# Monitor results:
# - diluted_eps: should populate 61,427 NULL rows
# - capex: should populate ~140K NULL rows
# - goodwill/inventory/cash: should populate rows from 2026-07-01 onward
```

#### Step 4: Verify Signal Quality Uses Correct Weighting
```bash
# Check that signal_quality_score synced to buy_sell_daily
psql -c "
SELECT COUNT(*) as signals_with_quality_score 
FROM buy_sell_daily 
WHERE signal_quality_score IS NOT NULL 
  AND date >= CURRENT_DATE - INTERVAL '1 day'
"
# Expected: > 0 (signals have correct weighted quality scores)
```

### Verification Checklist

- [ ] Loaders run during market hours without lock errors
- [ ] Financial statements load from SEC API (official source)
- [ ] diluted_eps column now populated (issue #1)
- [ ] goodwill/inventory columns now populated (issue #2)
- [ ] capex column now populated (issue #3)
- [ ] insider_transaction_velocity has data (issue #4)
- [ ] signal_quality_scores uses weighted calculation (issue #7)
- [ ] signal_quality_score synced to buy_sell_daily
- [ ] No fallback logic executed (official sources only)

## What This Demonstrates

By completing this verification, we'll have proven:

1. **Official sources working**: SEC XBRL, Alpaca SIP, FINRA, FRED all load correctly
2. **No fallbacks**: Only official data, fail-fast on gaps
3. **Fixes active**: NULL columns now populate correctly
4. **Data integrity**: Proper weighting, type conversion, schema validation
5. **Historical completeness**: Backfilled rows from before fixes

## Why Monday Instead of Today

- **Market hours**: Orchestrator only runs during trading days
- **Lock manager**: Requires AWS/RDS which isn't available in this dev session
- **New data**: Only markets provide fresh data to load
- **Staged verification**: Can't verify backfill without first running loaders normally

## Success Criteria

Goal is satisfied when:
1. Data loads successfully from official sources (SEC, Alpaca, etc.)
2. NULL columns populated with correct values
3. No fallback logic executed
4. Historical data backfilled to current
5. Signal quality scores use correct weighting

This proves the system "gets data loaded right from official sources with no messy fallbacks."
