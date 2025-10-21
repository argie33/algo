# Stock Scores N/A Values - Schema & Data Population Diagnosis

## Root Cause Analysis

You're seeing N/A values across pages (especially Score Dashboard factor breakdown) due to **missing data in the JSONB columns**, not a schema mismatch per se, but a **data population issue**.

## System Architecture

### Data Flow
```
Python Loaders (Run on schedule)
├── loadstockscores.py → Populates: composite_score, momentum_*, value_score, etc.
├── loadvaluemetrics.py → Populates: stock_scores.value_inputs (JSONB)
├── loadqualitymetrics.py → Populates: stock_scores.stability_inputs (JSONB)
└── Other loaders → Populate supporting tables (technical_data_daily, earnings, etc.)
                     ↓
PostgreSQL Database (stock_scores table)
├── Column: value_inputs (JSONB) - Contains 50+ financial metrics
├── Column: stability_inputs (JSONB) - Contains stability factors
└── Direct columns: composite_score, momentum_score, pe_ratio, etc.
                     ↓
API Routes (/api/scores)
├── Queries stock_scores table
├── Extracts data from value_inputs JSONB using: value_inputs->>'field_name'
└── Returns combined result set
                     ↓
Frontend (ScoresDashboard.jsx)
└── Receives data and displays factors (shows N/A if NULL/missing)
```

## What Gets Stored in JSONB

### `value_inputs` Contains:
```json
{
  "pb_ratio": 2.5,
  "ps_ratio": 1.8,
  "ev_ebitda": 12.3,
  "fcf_yield": 0.05,
  "dividend_yield": 0.03,
  "earnings_growth_pct": 15.2,
  "institutional_ownership": 65.4,
  "insider_ownership": 8.2,
  "short_percent_of_float": 3.1,
  "short_ratio": 1.5,
  "return_on_equity_pct": 18.5,
  "return_on_assets_pct": 8.2,
  "gross_margin_pct": 45.2,
  "operating_margin_pct": 22.3,
  "profit_margin_pct": 15.8,
  ... (45+ metrics total)
}
```

### `stability_inputs` Contains:
```json
{
  "volatility_factor": 0.8,
  "consistency_score": 75,
  "drawdown_resilience": 0.65,
  "recovery_speed": 0.75,
  "earnings_stability": 0.82,
  ... (stability factors)
}
```

## Diagnosis Steps

### 1. Check if Loaders Have Run
```bash
# Connect to database
psql -h localhost -U postgres -d stocks

# Check if stock_scores has any data
SELECT COUNT(*) as total_records, COUNT(value_inputs) as with_data FROM stock_scores;

# Expected: Both should be > 0
# If COUNT(*) > 0 but COUNT(value_inputs) = 0, loaders ran but didn't populate JSONB
```

### 2. Check Specific Symbol's Data
```bash
# For a symbol like AAPL
SELECT symbol, composite_score, value_inputs FROM stock_scores WHERE symbol = 'AAPL';

# Expected: value_inputs should be a JSON object, not NULL
# If NULL: Loaders haven't populated it yet
```

### 3. Check Loader Logs
```bash
# Look for loader execution logs (if available)
# Check if loadvaluemetrics.py ran successfully:
grep -r "UPDATE stock_scores" /var/log/  # or wherever logs are stored
```

### 4. Check Supporting Tables Exist
```bash
# These tables must exist and have data for loaders to work:
SELECT COUNT(*) FROM key_metrics;        # Financial metrics
SELECT COUNT(*) FROM technical_data_daily;  # Technical analysis
SELECT COUNT(*) FROM earnings;            # Earnings data
SELECT COUNT(*) FROM dividend;            # Dividend data
```

## Common Issues & Solutions

### Issue 1: Records Exist but `value_inputs` is NULL
**Symptom**: `COUNT(*)` > 0 but `COUNT(value_inputs)` = 0

**Causes**:
- `loadvaluemetrics.py` hasn't run yet
- `loadvaluemetrics.py` failed (check error logs)
- Supporting tables (key_metrics, technical_data_daily) are empty
- Database connection lost during loader execution

**Solutions**:
1. Manually run the loader: `python3 loadvaluemetrics.py`
2. Check loader dependencies exist: `psql -d stocks -c "SELECT COUNT(*) FROM key_metrics;"`
3. Check if database credentials are correct in loader
4. Enable loader logging and check for errors

### Issue 2: stock_scores Table is Empty
**Symptom**: `COUNT(*)` = 0

**Causes**:
- `loadstockscores.py` hasn't run
- Loader failed due to missing dependencies
- Table schema mismatch

**Solutions**:
1. Manually run: `python3 loadstockscores.py`
2. Check supporting tables exist
3. Verify database connectivity

### Issue 3: N/A Appearing in Frontend Despite Data in DB
**Symptom**: Database has data but frontend shows N/A

**Causes**:
- API query extracting from wrong JSONB column
- Frontend component not handling NULL/undefined properly
- Data type mismatch (expecting number, got string)

**Solutions**:
1. Test API directly: `curl http://localhost:5173/api/scores/AAPL`
2. Check API response for NULL values
3. Verify frontend parsing: `JSON.parse(data.value_inputs)`

## Loader Dependency Chain

```
loadstockscores.py
├── Requires: stock_prices, stock_symbols
├── Populates: composite_score, momentum_score, growth_score, etc.
├── Creates: stability_inputs column (empty, for quality metrics)
└── Creates: value_inputs column (empty, populated by loadvaluemetrics)

loadvaluemetrics.py
├── Requires: stock_scores (from loadstockscores) ✓
├── Requires: key_metrics table ← CRITICAL DEPENDENCY
├── Reads: PE ratio, PB ratio, dividend yield from key_metrics
└── Writes: value_inputs JSONB with 50+ financial metrics

loadqualitymetrics.py
├── Requires: stock_scores table ✓
├── Requires: technical_data_daily table
├── Calculates: stability, consistency, recovery factors
└── Writes: stability_inputs JSONB

Supporting Loaders (must run first):
├── Polygon/Alpaca API → price_daily, technical_data_daily
├── Financial APIs → key_metrics, earnings, dividend
└── These populate the data that score loaders depend on
```

## Verify No Duplicate Routes

### Routes are Distinct:
- **`/api/stocks`** - Stock list, quote, popular, movers, stats
- **`/api/scores`** - Stock scores and factor breakdowns ✓ CORRECT
- **`/api/screener`** - Stock screening/filtering

No duplicates. Each has unique responsibility.

## Quick Verification Script

```bash
#!/bin/bash
# save as verify_data_pipeline.sh

echo "=== Database Connection ==="
psql -h localhost -U postgres -d stocks -c "SELECT 1;" && echo "✓ Connected"

echo -e "\n=== Data Population Status ==="
psql -h localhost -U postgres -d stocks -c "
SELECT
  'stock_scores' as table_name,
  COUNT(*) as total_records,
  COUNT(value_inputs) as with_value_inputs,
  COUNT(stability_inputs) as with_stability_inputs,
  COUNT(composite_score) as with_scores
FROM stock_scores;
"

echo -e "\n=== Supporting Tables ==="
psql -h localhost -U postgres -d stocks -c "
SELECT table_name, COUNT(*) as records FROM (
  SELECT 'key_metrics' as table_name, COUNT(*) FROM key_metrics
  UNION ALL
  SELECT 'technical_data_daily', COUNT(*) FROM technical_data_daily
  UNION ALL
  SELECT 'earnings', COUNT(*) FROM earnings
  UNION ALL
  SELECT 'price_daily', COUNT(*) FROM price_daily
) AS t
GROUP BY table_name;
"

echo -e "\n=== Sample Stock Data ==="
psql -h localhost -U postgres -d stocks -c "
SELECT
  symbol,
  composite_score,
  momentum_score,
  CASE WHEN value_inputs IS NULL THEN 'NULL' ELSE 'HAS_DATA' END as value_inputs_status,
  CASE WHEN stability_inputs IS NULL THEN 'NULL' ELSE 'HAS_DATA' END as stability_inputs_status
FROM stock_scores
LIMIT 5;
"
```

## Frontend Expectations vs Database Reality

### Frontend Component Expects:
```javascript
{
  symbol: "AAPL",
  composite_score: 82.5,
  momentum_score: 78.3,
  pb_ratio: 25.4,  // ← FROM value_inputs JSONB
  pe_ratio: 28.1,
  institutional_ownership: 65.4,  // ← FROM value_inputs JSONB
  // ... 50+ fields
}
```

### Database Provides:
```sql
-- Direct columns (always available)
symbol, composite_score, momentum_score, pe_ratio

-- JSONB extracted values (only if JSONB populated)
value_inputs->>'pb_ratio' as pb_ratio
value_inputs->>'institutional_ownership' as institutional_ownership
```

### If JSONB is NULL:
```
value_inputs->>'pb_ratio' → NULL → Frontend displays "N/A"
```

## Action Items to Fix N/A Values

1. **Check Database**: Run `verify_data_pipeline.sh`
2. **If value_inputs is NULL**: Run `python3 loadvaluemetrics.py`
3. **If key_metrics is empty**: Run data loader that populates it (Polygon/Alpaca sync)
4. **If still NULL**: Check loader error logs and dependencies
5. **Verify API response**: `curl http://localhost:5173/api/scores/AAPL` and check for NULLs
6. **Frontend fallback**: Add defensive handling in ScoresDashboard.jsx for missing fields

## No Schema Mismatch - Just Missing Data

✓ Routes are clean (no duplicates)
✓ Schema is correct (value_inputs and stability_inputs are JSONB)
✓ Issue is: **Loaders haven't populated the JSONB yet** or failed silently

The data flows correctly from loaders → database → API → frontend, but the JSONB columns are empty/NULL, which the frontend renders as N/A.
