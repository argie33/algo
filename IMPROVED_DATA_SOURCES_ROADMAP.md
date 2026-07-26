# Data Loading Improvements Roadmap

**Status**: INITIATED - Foundation built, type-safety fixes in progress

**Goal**: Get all things working right by pursuing better official data sources. We currently have 25 working loaders pulling from SEC, FINRA, FRED, AAII, NAAIM, and Alpaca. This roadmap identifies additional official sources to improve trading signals.

---

## New Data Sources Created (Foundations Laid)

### 1. Form 8-K Current Reports (Material Events)
**Files Created**:
- Migration: `migrations/versions/1154_add_current_reports_8k_table.sql`
- Loader: `loaders/load_current_reports_8k.py`
- Registered in: `scripts/local_loader_scheduler.py` (metrics pipeline, 3:30 PM)

**Status**: Type-safety fixes needed (18 mypy errors to resolve)

**What it does**:
- Tracks SEC Form 8-K filings (material events)
- Classifies event types (acquisitions, bankruptcies, leadership changes, etc.)
- Feeds catalyst detection in trading signals
- Scheduled: Run daily with metrics pipeline

**Impact**:
- Improves catalyst-based trading signals
- Identifies material events that move stocks
- Official SEC source (authoritative)

**Next Steps**:
1. Fix type annotations to pass mypy strict
2. Test against live SEC API
3. Verify 8-K parsing logic
4. Wire into terraform pipeline

---

### 2. Dividend Data (Position Management)
**Files Created**:
- Migration: `migrations/versions/1155_add_dividend_data_table.sql`
- Loader: `loaders/load_dividend_data.py`
- Registered in: `scripts/local_loader_scheduler.py` (metrics pipeline, 3:30 PM)

**Status**: Type-safety fixes needed (8 mypy errors)

**What it does**:
- Tracks dividend ex-dates, payment dates, yields
- Extracts from SEC XBRL financial statements and 8-K filings
- Critical for dividend-capture strategies
- Prevents being caught short before ex-dividend date

**Impact**:
- Supports dividend capture strategies
- Improves position management
- Better portfolio yield calculation
- Helps avoid unexpected ex-date exposure

**Next Steps**:
1. Fix type annotations
2. Test dividend extraction from SEC XBRL
3. Verify ex-date estimation logic
4. Wire into terraform

---

### 3. Insider Transaction Velocity (Confidence Signals)
**Files Created**:
- Migration: `migrations/versions/1156_add_insider_transaction_velocity_table.sql`
- Loader: `loaders/load_insider_transaction_velocity.py`
- Registered in: `scripts/local_loader_scheduler.py` (signals pipeline, 4:05 PM)

**Status**: Type-safety fixes needed (7 mypy errors)

**What it does**:
- Analyzes insider buying/selling patterns over time
- Computes from existing insider_holdings_sec Form 4/5 data
- Generates insider confidence score (0-100)
- Tracks 30-day and 90-day transaction velocities

**Impact**:
- High insider buying velocity = confidence signal (often precedes price increases)
- High selling velocity = concern signal
- Proprietary insider knowledge source
- Useful for risk scoring

**Next Steps**:
1. Fix type annotations
2. Test velocity calculations
3. Verify confidence score formula
4. Wire into terraform

---

## Outstanding Type-Safety Issues to Fix

All three loaders have mypy strict-mode errors that need resolution:

### Form 8-K Loader (18 errors)
- Method signature mismatch with base class
- Missing `_unavailable_record` and `run_date_et` attributes
- Incorrect `get_filing_text()` method name (should be `get_filing_plaintext()` or `get_filing_xml()`)
- Incorrect `run_loader()` call signature
- Incorrect `handle_exception()` call signature

### Dividend Data Loader (8 errors)
- Similar base class mismatches
- Missing required method implementations
- Type annotation issues

### Insider Transaction Velocity Loader (7 errors)
- CustomLoader doesn't inherit from OptimalLoader
- Missing proper base class integration
- Database query type issues

---

## Migration Scripts Created

All three migrations are ready to run:
```bash
# Apply migrations to create tables
psql -d stocks -f migrations/versions/1154_add_current_reports_8k_table.sql
psql -d stocks -f migrations/versions/1155_add_dividend_data_table.sql
psql -d stocks -f migrations/versions/1156_add_insider_transaction_velocity_table.sql
```

---

## Integration Points

### Local Development (`scripts/local_loader_scheduler.py`)
- Form 8-K: Added to metrics pipeline ✓
- Dividend Data: Added to metrics pipeline ✓
- Insider Velocity: Added to signals pipeline ✓

### Terraform (Production Pipeline)
- **NOT YET DONE**: Need to add Step Functions tasks for each loader in `terraform/modules/pipeline/main.tf`
- Should follow same pattern as other SEC loaders
- Metrics pipeline: Add before or after InsiderHoldingsSec
- Signals pipeline: Add at end after all scoring

### Testing
- Unit tests needed for each loader
- Integration tests needed to verify SEC API connectivity
- Mock SEC responses for CI testing

---

## Opportunities Still Available

### Medium Priority (2-4 hours each, real impact)
1. ✅ **Form 8-K** - INITIATED (needs type fixes)
2. ✅ **Dividend Data** - INITIATED (needs type fixes)
3. ✅ **Insider Velocity** - INITIATED (needs type fixes)

### Low Priority (architectural, lower ROI)
1. **Earnings Surprises** - Compare actual to consensus (need external source for estimates)
2. **Regulatory Actions** - SEC enforcement (probably not trading-relevant)
3. **Segment Metrics** - XBRL segment reporting (complex, not used by trading logic)

---

## Reference: Existing Data Sources (All Working)

| Source | Loader | Table | Update Freq |
|--------|--------|-------|-------------|
| Alpaca | load_prices.py | price_daily | Daily (2 AM + 4 PM) |
| SEC EDGAR | load_financial_statements.py | income/balance/cashflow statements | Quarterly |
| SEC EDGAR | load_earnings_calendar_sec.py | earnings_calendar_sec | Daily |
| SEC EDGAR | load_sec_valuations.py | sec_valuations | Daily |
| SEC EDGAR | load_insider_holdings_sec.py | insider_holdings_sec | Daily |
| FINRA | load_short_interest_finra.py | short_interest_finra | Bi-weekly |
| FRED | load_economic_data.py | economic_data | Daily |
| AAII | load_aaii_sentiment.py | aaii_sentiment | Weekly |
| NAAIM | load_naaim.py | naaim_sentiment | Weekly |

**New Additions** (foundations in progress):
- SEC Form 8-K → current_reports_8k
- SEC XBRL → dividend_data  
- Insider Form 4/5 analytics → insider_transaction_velocity

---

## Why These Improvements Matter

### Current State
- 25 loaders working, all critical data fresh
- 3 architectural gaps gracefully degraded (analyst data, 13F, segments)
- Trading signals generated from: technicals + fundamental scores + market regime

### After Improvements
- 28 loaders (3 new sources added)
- Enhanced catalyst detection (8-K material events)
- Better position management (dividend tracking)
- Improved risk scoring (insider confidence)
- All from official SEC/FINRA sources (authoritative)

---

## Quick Start: Completing the Integration

### Step 1: Fix Type Safety
```bash
# Run mypy to see remaining errors
python -m mypy loaders/load_current_reports_8k.py --strict

# Common fixes needed:
# - Change base class from SecLoaderBase to OptimalLoader where needed
# - Fix method signatures to match parent class
# - Use correct SEC API method names
# - Fix run_loader() call (remove script_name parameter)
```

### Step 2: Test Loaders
```bash
# Test 8-K loader with a few symbols
python loaders/load_current_reports_8k.py --symbols AAPL,MSFT --parallelism 1

# Test dividend loader
python loaders/load_dividend_data.py --symbols AAPL,MSFT --parallelism 1

# Test insider velocity (no external API, DB-only)
python loaders/load_insider_transaction_velocity.py
```

### Step 3: Wire into Production
1. Update `terraform/modules/pipeline/main.tf` with new Step Functions tasks
2. Register loaders in terraform variables
3. Set appropriate parallelism and timeouts
4. Test with terraform plan/apply

### Step 4: Verify Data Quality
```bash
# Check data loaded successfully
psql -d stocks -c "SELECT COUNT(*) FROM current_reports_8k WHERE filing_date = CURRENT_DATE"
psql -d stocks -c "SELECT COUNT(*) FROM dividend_data WHERE ex_dividend_date >= CURRENT_DATE"
psql -d stocks -c "SELECT COUNT(*) FROM insider_transaction_velocity WHERE measurement_date = CURRENT_DATE"
```

---

## Success Criteria

✓ All 3 loaders pass mypy strict mode  
✓ All 3 loaders run without errors  
✓ Data populates in correct tables  
✓ Wired into production terraform pipeline  
✓ Trading signals improved with new data sources  
✓ No performance degradation  

---

## Notes

- **Date**: Initiated 2026-07-26
- **Motivation**: User goal: "get all things working right...we not trying hard enough to get the data we need"
- **Approach**: Use official sources (SEC, FINRA) we already access
- **Architecture**: Follow existing loader patterns (OptimalLoader base class)
- **Philosophy**: Explicit data_unavailable markers, no silent fallbacks
