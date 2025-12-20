# Growth Metrics Data Gap Remediation Guide

## Problem Statement
- **Issue**: Growth metrics table has many NULL/missing values
- **Root Cause**: 89% of symbols lack detailed financial statement data
- **Previous Approach**: Running all loaders at once → context window errors
- **New Approach**: Selective, batch-based loading with targeted data sources

---

## Architecture Overview

### Data Sources for Growth Metrics (Priority Order)

| Tier | Source | Symbols Covered | Metrics Provided |
|------|--------|-----------------|------------------|
| 1 | Annual Income Statements | ~5,000 symbols | Revenue/EPS CAGR, operating income YoY |
| 2 | Quarterly Income Statements | ~4,800 symbols | Quarterly growth, recent trends |
| 3 | Annual Cash Flow | ~4,600 symbols | FCF/OCF growth |
| 4 | Annual Balance Sheet | ~3,500 symbols | Asset growth |
| 5 | Earnings History | ~3,300 symbols | EPS actual vs estimate |
| 6 | Key Metrics Provider | ~5,200 symbols | Fallback margins, growth %s |

**Critical Gap**: 41,648 symbols (89%) have **no detailed financials** - only key_metrics fallback

---

## Tools Created

### 1. `analyze_growth_gaps.py`
**Purpose**: Identify which symbols are missing growth metrics and why

```bash
# Check your environment (set these from .env.local)
export DB_HOST="localhost"
export DB_PORT="5432"
export DB_USER="stocks"
export DB_PASSWORD="<from .env.local>"
export DB_NAME="stocks"

# Run analysis
python3 analyze_growth_gaps.py

# Output shows:
# - Growth metrics coverage by metric (%)
# - Upstream data source coverage (%)
# - Gap categories (has_annual, has_quarterly, has_key_metrics_only, no_data)
# - Remediation recommendations
```

**What It Does**:
- Queries growth_metrics table for completeness
- Checks each upstream data source for coverage
- Categorizes symbols by available data
- Recommends which loaders to run

---

### 2. `selective_growth_loader.py`
**Purpose**: Load growth metrics ONLY for symbols with missing data, in batches

```bash
# Check what would be loaded (don't actually load)
python3 selective_growth_loader.py --check-only

# Load with default batch size (500 symbols)
python3 selective_growth_loader.py

# Load specific symbols
python3 selective_growth_loader.py --symbols AAPL,MSFT,TSLA

# Load with custom batch size (smaller = lower memory)
python3 selective_growth_loader.py --batch-size 250
```

**Key Features**:
- ✅ Only processes symbols with missing growth metrics
- ✅ Batch processing (default 500/batch) to avoid memory issues
- ✅ Automatic garbage collection between batches
- ✅ Upsert logic (insert new, update existing)
- ✅ Detailed logging of progress

---

## Recommended Workflow

### Step 1: Analyze the Gap
```bash
# See what's missing
python3 analyze_growth_gaps.py

# Expected output shows:
# ✅ Growth metric coverage (which metrics have data, which don't)
# ✅ Upstream data sources (which tables have data for how many symbols)
# ✅ Gap categories (annual vs quarterly vs metrics-only vs nothing)
# ✅ Remediation plan (which loaders to run, in order)
```

### Step 2: Load Missing Upstream Data (Selective)
**Only run loaders for symbols missing data** - don't re-load everything!

**Option A: Targeted Symbols**
```bash
# If analysis shows "has_quarterly_statements" gap, run ONLY quarterly loader
# This is FASTER and uses LESS memory than running annual+quarterly+etc.

# Load annual statements (if needed)
# Load quarterly statements (if needed)
# Load cash flow (if needed)
# etc - run only what the analysis recommends
```

**Option B: Let the Analysis Guide You**
- The `analyze_growth_gaps.py` output tells you EXACTLY which loaders are needed
- Run only those, skipping ones that have high coverage already

### Step 3: Load Growth Metrics from Available Data
```bash
# Once upstream data is ready, load growth metrics
python3 selective_growth_loader.py

# Monitor progress:
# Batch 1/10: Processing 500 symbols...
# Batch 2/10: Processing 500 symbols...
# etc.

# Final output:
# ✅ Total inserted: 5200
# ✅ Total updated: 1500
```

---

## Understanding the Gap Categories

### `has_annual_statements` (~5,000 symbols)
- **What**: Full annual P&L, cash flow, balance sheet data available
- **Metrics Available**:
  - Revenue growth 3Y CAGR ✅
  - EPS growth 3Y CAGR ✅
  - Operating income YoY ✅
  - Net income YoY ✅
  - FCF/OCF growth ✅
  - Asset growth ✅
- **Action**: `selective_growth_loader.py` will fill all metrics

### `has_quarterly_statements` (~4,800 symbols)
- **What**: Quarterly P&L data but no annual statements
- **Metrics Available**:
  - Quarterly growth (QoQ/QoY) ✅
  - Recent revenue/earnings momentum ✅
  - Margin trends ✅
- **Metrics Missing**:
  - 3Y CAGR (not available from quarterly data)
  - Historical YoY comparisons (only recent quarters)
- **Action**: `selective_growth_loader.py` will get what's available

### `has_key_metrics_only` (~5,200 symbols)
- **What**: Only key_metrics provider data (no statements from SEC)
- **Metrics Available**:
  - Earnings growth % (from provider) ✅
  - Revenue growth % (from provider) ✅
  - ROE, margin trends ✅
- **Metrics Missing**:
  - FCF/OCF growth (requires cash flow statements)
  - Precise CAGR calculations (requires 4+ years)
- **Action**: `selective_growth_loader.py` will get fallback values

### `no_data` (~41,600 symbols)
- **What**: No financial data available anywhere
- **Metrics Available**: NONE - all NULL
- **Why**: Micro-cap, delisted, private, or data provider doesn't cover
- **Action**: Cannot load growth metrics - fundamental data doesn't exist

---

## Execution Details

### Why Batch Processing?

**Problem**: Running all 46,875 symbols at once

```python
# Naive approach (BAD - crashes with context window error)
for symbol in all_46875_symbols:
    load_growth_metrics(symbol)  # ← Context grows unbounded
    # After ~10,000 symbols: context window exhausted → ERROR
```

**Solution**: Batch with garbage collection

```python
# Smart approach (GOOD - stable memory usage)
batch_size = 500
for batch in chunks(all_46875_symbols, batch_size):
    for symbol in batch:
        load_growth_metrics(symbol)  # ← Isolated context per batch
    gc.collect()  # ← Force cleanup between batches
    time.sleep(1)  # ← Brief pause for recovery
```

**Result**:
- Memory stays ~200-400MB (not exponential growth)
- No context window errors
- Processing time: ~2-3 hours for full universe
- Can be interrupted and resumed

---

## Expected Results

### Before Remediation
```
Growth Metrics Coverage:
  ❌ revenue_growth_3y_cagr:    2,100/46,875 (4.5%)
  ❌ eps_growth_3y_cagr:         2,050/46,875 (4.4%)
  ❌ fcf_growth_yoy:             1,800/46,875 (3.8%)
  ⚠️ quarterly_growth_momentum:  5,200/46,875 (11.1%)
```

### After Running Remediation
```
Growth Metrics Coverage:
  ✅ revenue_growth_3y_cagr:    7,200/46,875 (15.4%)  [+5,100]
  ✅ eps_growth_3y_cagr:         7,100/46,875 (15.2%)  [+5,050]
  ✅ fcf_growth_yoy:             5,600/46,875 (12.0%)  [+3,800]
  ✅ quarterly_growth_momentum: 10,000/46,875 (21.3%)  [+4,800]
```

---

## Troubleshooting

### Problem: "Database connection failed"
**Solution**: Ensure `.env.local` is present and has correct credentials
```bash
source .env.local
python3 analyze_growth_gaps.py
```

### Problem: "Too many rows, query taking too long"
**Solution**: Reduce batch size
```bash
python3 selective_growth_loader.py --batch-size 250
```

### Problem: "Memory usage growing"
**Solution**: Check for database locks or slow queries
```bash
# Monitor in separate terminal:
watch -n 5 'free -h'
```

### Problem: "Partial load - some symbols loaded, then stopped"
**Solution**: Resume from where it left off
```bash
# Check which symbols are missing
python3 analyze_growth_gaps.py

# Run again - upsert logic handles duplicates safely
python3 selective_growth_loader.py --check-only | grep "to process"
python3 selective_growth_loader.py
```

---

## Data Integrity Rules

### What Gets Loaded
- ✅ Real financial statement data (annual/quarterly)
- ✅ Real earnings history data
- ✅ Real key_metrics provider values
- ✅ Calculated metrics (CAGR, YoY, etc.) from real data

### What Does NOT Get Loaded
- ❌ Fake defaults (never "50%" for missing data)
- ❌ Synthetic calculations (never calculated proxies)
- ❌ Hardcoded fallback values
- ✅ NULL/None for unavailable metrics (correct!)

**Why**: Prevents data corruption in scoring algorithms. A metric with real data (0.5%) is better than a metric with fake data (50%).

---

## Integration with Rest of System

### Consuming Applications
- `webapp/lambda/routes/scores.js` - Stock scoring engine
- `webapp/lambda/routes/financials.js` - Financial data endpoint
- Growth category (25% weight) in composite scores

### Update Frequency
- Daily updates recommended (as new market data comes in)
- Can be run manually anytime to refresh
- Safe to run multiple times (upsert = idempotent)

---

## Advanced: Custom Symbol Selection

### Load Only Large Caps
```bash
# Modify selective_growth_loader.py to add WHERE clause
WHERE symbol IN (
    SELECT symbol FROM key_metrics
    WHERE market_cap > 10000000000  -- $10B+
)
```

### Load Only Symbols with Annual Statements
```bash
WHERE symbol IN (
    SELECT DISTINCT symbol FROM annual_income_statement
)
```

### Load Symbols Updated Recently
```bash
WHERE symbol IN (
    SELECT symbol FROM growth_metrics
    WHERE created_at < NOW() - INTERVAL '7 days'  -- Older than 1 week
)
```

---

## Performance Expectations

| Operation | Time | Memory | Notes |
|-----------|------|--------|-------|
| Analyze gaps | 10-30s | 100MB | Quick database scan |
| Load 500 symbols | 30-90s | 200MB | Per batch |
| Load full universe | 2-3 hrs | 300MB | All batches |
| Database upsert | <5s | 50MB | Per batch commit |

---

## Summary

### 🎯 The Right Way (NEW)
1. Run `analyze_growth_gaps.py` → see what's missing
2. Run upstream loaders ONLY for missing data
3. Run `selective_growth_loader.py` with batching
4. Monitor progress with logging
5. ✅ Complete in 2-3 hours without crashes

### ❌ The Wrong Way (OLD)
1. Run all loaders at once
2. No selective processing
3. No batching
4. Context window error after 10K symbols
5. Restart, retry, repeat...

---

## Next Steps

1. **Immediate** (15 min):
   ```bash
   python3 analyze_growth_gaps.py
   # Review the recommendations
   ```

2. **Short term** (1-2 hours):
   ```bash
   python3 selective_growth_loader.py --batch-size 500
   # Monitor progress, review logs
   ```

3. **Verification** (15 min):
   ```bash
   python3 analyze_growth_gaps.py
   # Confirm improvement in coverage %
   ```

---

## Questions?

- **Script not running?** Check `DB_*` environment variables in `.env.local`
- **Still getting errors?** Check PostgreSQL is running: `ps aux | grep postgres`
- **Slow performance?** Reduce batch size: `--batch-size 250`
- **Want to inspect data?** Use `selective_growth_loader.py --check-only` first
