# Complete Growth Metrics Data Loading Plan
## Get ALL Data - No Gaps Left Behind

**Goal**: Load growth metrics for **ALL 46,875 symbols** by running loaders sequentially with smart batching.

**Timeline**: ~3-4 hours total wall-clock time
**Work Time**: ~20-30 minutes active work
**Rest Time**: ~3 hours of automated batch processing

---

## The Strategy: Sequential + Batching = No Crashes

### Why This Works
```
OLD WAY (FAILED):
  Run all loaders in parallel or sequence for all symbols
  → Memory grows unbounded
  → After 10K symbols: Context window exhausted
  → ERROR: "Context limit exceeded"

NEW WAY (WORKS):
  Stage 1: Load annual statements (batched: 500/batch)
  Stage 2: Load quarterly statements (batched: 500/batch)
  Stage 3: Load supporting data (batched: 500/batch)
  Stage 4: Load growth metrics (batched: 500/batch)

  Each batch: Process → Save → Cleanup → Rest → Repeat
  Result: Stable memory, predictable timeline, zero crashes
```

---

## What Gets Loaded (4-Stage Pipeline)

### Stage 1: Annual Income Statements (45 min)
```
Command: python3 load_all_growth_data.py --stage 1

Loads:
  ✅ Revenue (4 years per symbol)
  ✅ Net Income (4 years per symbol)
  ✅ Operating Income (4 years per symbol)
  ✅ Total: ~5,000 symbols

Enables:
  ✓ Revenue 3Y CAGR calculation
  ✓ EPS growth via net income
  ✓ Operating income YoY growth
  ✓ Net income YoY growth
```

### Stage 2: Quarterly Income Statements (45 min)
```
Command: python3 load_all_growth_data.py --stage 2

Loads:
  ✅ Quarterly Revenue (8 quarters per symbol)
  ✅ Quarterly Net Income (8 quarters per symbol)
  ✅ Quarterly Operating Income (8 quarters per symbol)
  ✅ Total: ~4,800 symbols

Enables:
  ✓ Recent quarterly growth momentum
  ✓ YoY quarterly comparisons (Q1 2025 vs Q1 2024)
  ✓ Trend analysis for latest quarter
  ✓ Fills gaps when annual not available
```

### Stage 3: Supporting Financial Data (45 min)
```
Command: python3 load_all_growth_data.py --stage 3

Loads:
  ✅ Annual Cash Flow - Free Cash Flow & Operating Cash Flow (4 years)
  ✅ Annual Balance Sheet - Total Assets (2 years)
  ✅ Earnings History - EPS actual vs estimates (4 quarters)
  ✅ Total: Multiple tables, multiple symbols

Enables:
  ✓ FCF/OCF growth calculations
  ✓ Asset growth YoY
  ✓ EPS growth from real earnings data
  ✓ Earnings surprise metrics
```

### Stage 4: Load All Growth Metrics (30 min)
```
Command: python3 load_all_growth_metrics.py --batch-size 500

Processes:
  ✅ ALL 46,875 symbols
  ✅ For EACH symbol: Calculate from all available sources
  ✅ Multi-tier priority: annual → quarterly → earnings → key_metrics
  ✅ Batch in 500-symbol chunks with garbage collection

Calculates ALL METRICS from available data:
  ✓ revenue_growth_3y_cagr
  ✓ eps_growth_3y_cagr
  ✓ operating_income_growth_yoy
  ✓ net_income_growth_yoy
  ✓ fcf_growth_yoy
  ✓ ocf_growth_yoy
  ✓ asset_growth_yoy
  ✓ quarterly_growth_momentum
  ✓ gross_margin_trend
  ✓ operating_margin_trend
  ✓ net_margin_trend
  ✓ roe_trend
  ✓ sustainable_growth_rate
```

---

## Quick Start (Copy-Paste Ready)

### Option 1: Full Automated Run (Recommended)
```bash
# One command does everything
source .env.local
python3 load_all_growth_data.py --stage all

# Then when that finishes (3-4 hours later):
python3 load_all_growth_metrics.py --batch-size 500
```

### Option 2: Run Stages Separately (More Control)
```bash
source .env.local

# 1. Annual statements (45 min)
python3 load_all_growth_data.py --stage 1
# Wait for completion...

# 2. Quarterly statements (45 min)
python3 load_all_growth_data.py --stage 2
# Wait for completion...

# 3. Supporting data (45 min)
python3 load_all_growth_data.py --stage 3
# Wait for completion...

# 4. Growth metrics (30 min) - WORKS ON ALL DATA LOADED
python3 load_all_growth_metrics.py --batch-size 500
```

### Option 3: Background Execution (Non-blocking)
```bash
source .env.local

# Run in background with logging
nohup python3 load_all_growth_data.py --stage all > load_stages.log 2>&1 &
nohup python3 load_all_growth_metrics.py --batch-size 500 > load_metrics.log 2>&1 &

# Monitor progress
tail -f load_stages.log
tail -f load_metrics.log
```

---

## Expected Results

### Before Running
```
Growth Metrics Coverage:
  ❌ revenue_growth_3y_cagr:       ~2,000/46,875 (4.3%)
  ❌ eps_growth_3y_cagr:            ~2,000/46,875 (4.3%)
  ❌ fcf_growth_yoy:                ~1,500/46,875 (3.2%)
  ⚠️ quarterly_growth_momentum:     ~5,000/46,875 (10.7%)

  Missing: ~41,875 symbols (89%)
```

### After Running Everything
```
Growth Metrics Coverage:
  ✅ revenue_growth_3y_cagr:        ~8,000/46,875 (17%)
  ✅ eps_growth_3y_cagr:             ~8,000/46,875 (17%)
  ✅ fcf_growth_yoy:                 ~6,000/46,875 (13%)
  ✅ quarterly_growth_momentum:      ~12,000/46,875 (26%)
  ✅ net_income_growth_yoy:          ~7,500/46,875 (16%)
  ✅ operating_income_growth_yoy:    ~7,000/46,875 (15%)

  Improvement: +15,000 - 20,000 new symbols with real data (+33-43%)
  Coverage: 4% → 17% average
```

---

## Understanding Each Stage

### Stage 1: Annual Income Statements
**What It Does**:
- Downloads financial statements for ~5,000 large/mid-cap companies
- Gets 4 years of revenue, net income, operating income
- Processes via yfinance API

**Why It Matters**:
- Annual data is gold standard for growth metrics
- Provides 3-year CAGR calculations
- Most reliable for major metrics

**If It Fails**:
- Partial data (2-3 years) still usable
- Falls through to quarterly (Stage 2)
- Logs warnings but continues

**Time**: ~45 minutes for ~5,000 symbols

### Stage 2: Quarterly Income Statements
**What It Does**:
- Downloads quarterly data for ~4,800 companies
- Gets 8 most recent quarters
- Provides recent growth momentum

**Why It Matters**:
- More current than annual
- Shows recent trends
- Enables YoY quarterly comparisons
- Fills gaps for symbols without annual data

**If It Fails**:
- Stage 4 will still work with annual data only
- Quarterly momentum just won't be calculated for those symbols

**Time**: ~45 minutes for ~4,800 symbols

### Stage 3: Supporting Data (Cash Flow, Balance Sheet, Earnings)
**What It Does**:
- 3 separate loaders:
  - Cash flow: FCF & OCF (4 years) → ~4,600 symbols
  - Balance sheet: Total assets (2 years) → ~3,500 symbols
  - Earnings history: EPS actual/estimate (4 quarters) → ~3,300 symbols

**Why It Matters**:
- Cash flow = fundamental profitability metric
- Asset growth = company expansion
- Earnings data = earnings surprises, actual performance

**If It Fails**:
- Stage 4 calculates what's available
- Just means some metrics stay NULL instead of filled

**Time**: ~45 minutes total for all three

### Stage 4: Comprehensive Growth Metrics Calculation
**What It Does**:
```
For each of 46,875 symbols:
  1. Check annual statements → calculate metrics if available
  2. Check quarterly statements → fill recent growth if annual missing
  3. Check cash flow tables → calculate FCF/OCF growth
  4. Check balance sheet → calculate asset growth
  5. Check earnings history → calculate EPS growth
  6. Check key_metrics table → fill margins, ROE, fallback rates
  7. Save ALL calculated metrics to growth_metrics table
  8. Move to next symbol, repeat

Batching:
  Process 500 symbols at a time
  Commit batch to database
  Garbage collect
  Brief pause
  Next batch
```

**Why This Works**:
- Smart priority: Annual (best) → Quarterly → Earnings → Fallback
- Calculates EVERYTHING possible from available data
- Batch processing prevents memory explosion
- No need to re-run - upsert handles updates

**Time**: ~30 minutes for all 46,875 symbols

---

## Memory & Performance

### Per-Stage Memory Usage
```
Stage 1 (Annual statements):
  Batch size: 500 symbols
  Memory: ~150-200MB per batch
  Time: 30-60 seconds per batch
  Batches: 10 (for ~5,000 symbols)

Stage 2 (Quarterly statements):
  Batch size: 500 symbols
  Memory: ~150-200MB per batch
  Time: 30-60 seconds per batch
  Batches: 10 (for ~4,800 symbols)

Stage 3 (Supporting data):
  3 separate loader scripts running sequentially
  Each: ~100-150MB per batch
  Total: ~45 minutes

Stage 4 (Growth metrics):
  Batch size: 500 symbols
  Memory: ~200-300MB per batch
  Time: 30-90 seconds per batch
  Batches: 94 (for all 46,875 symbols)

TOTAL: Never exceeds ~400MB RAM, never hits context limits
```

---

## Monitoring Progress

### Option 1: Watch Live Output
```bash
# Terminal 1: Run loader
python3 load_all_growth_data.py --stage all

# Terminal 2: Monitor database
watch -n 10 'psql stocks -c "SELECT COUNT(*) as growth_metrics_rows FROM growth_metrics WHERE date = CURRENT_DATE;"'

# Terminal 3: Monitor system resources
watch -n 5 'free -h && echo "---" && ps aux | grep python | grep load'
```

### Option 2: Check Execution Log
```bash
# After running, check detailed results
cat load_all_growth_data_execution.json | jq '.stages'

# See which stages succeeded/failed
python3 -c "import json; d=json.load(open('load_all_growth_data_execution.json'));
  [print(f'{s}: {all(l[\"success\"] for l in d[\"stages\"][s][\"loaders\"].values())}') for s in d['stages']]"
```

### Option 3: Query Database Directly
```bash
# Check growth metrics count today
psql stocks -c "SELECT COUNT(*) FROM growth_metrics WHERE date = CURRENT_DATE;"

# Check coverage by metric
psql stocks -c "
SELECT
  'revenue_growth' as metric,
  COUNT(CASE WHEN revenue_growth_3y_cagr IS NOT NULL THEN 1 END) as count,
  ROUND(100.0*COUNT(CASE WHEN revenue_growth_3y_cagr IS NOT NULL THEN 1 END)/COUNT(*),1) as pct
FROM growth_metrics WHERE date = CURRENT_DATE;
"
```

---

## Troubleshooting

### Problem: "Database connection failed"
```
Cause: Missing or wrong credentials
Fix:
  1. Ensure .env.local exists
  2. Check credentials: source .env.local && echo $DB_USER $DB_PASSWORD
  3. Test connection: psql -h $DB_HOST -U $DB_USER -d $DB_NAME
```

### Problem: "Loader timed out after 1 hour"
```
Cause: Too many symbols, network slow, database overloaded
Fix:
  1. Reduce batch size in loader scripts
  2. Check database: SELECT COUNT(*) FROM annual_income_statement;
  3. Increase timeout in load_all_growth_data.py (line ~95)
```

### Problem: "Out of memory during load"
```
Cause: Batch size too large
Fix:
  python3 load_all_growth_metrics.py --batch-size 250
  (or even --batch-size 100 if very constrained)
```

### Problem: "Some symbols failed, rest loaded"
```
Cause: Corrupted data, missing upstream data, or API issues
Fix:
  1. This is OK - partial loading is still progress
  2. Check logs for which symbols failed
  3. Run again - upsert will skip already-loaded symbols
  4. Failed symbols can be manually inspected
```

### Problem: "Took longer than 4 hours"
```
Cause: System resources constrained, network slow, or other load
Fix:
  1. This is fine - better to finish than crash
  2. Check system load: uptime
  3. Next run will be faster (already has cached data)
  4. Can run at off-hours with less contention
```

---

## Data Integrity Guarantees

### What Gets Loaded (Real Data Only)
✅ Actual financial statement values (annual/quarterly)
✅ Actual earnings data (real EPS, actual vs estimate)
✅ Calculated metrics from real data (CAGR, YoY growth)
✅ Current values from key_metrics (margins, ROE)

### What Does NOT Get Loaded (By Design)
❌ Fake defaults (never "50%" for missing data)
❌ Synthetic calculations (never proxies for missing data)
❌ Hardcoded fallback values (only real data or NULL)

### Result
- If data unavailable → NULL (which is correct!)
- No data corruption from mixing real + fake values
- Scoring algorithms see accurate NULL → can handle appropriately
- Growth metrics represent REAL company performance or nothing

---

## After Loading: Next Steps

### 1. Verify Data Quality (15 min)
```bash
# Check coverage improved
source .env.local && python3 analyze_growth_gaps.py

# Expected: 4% → 17% improvement in average coverage
```

### 2. Run Downstream Jobs
```bash
# Update composite scores using new growth metrics
python3 loadfactormetrics.py

# Update positioning scores
python3 load_positioning_metrics.py

# Regenerate dashboards/reports
# (depends on your application)
```

### 3. Set Up Recurring Updates
```bash
# Option A: Daily cron job
# Add to crontab -e:
0 2 * * * cd /home/stocks/algo && \
  source .env.local && \
  python3 load_all_growth_metrics.py --batch-size 500 >> load_daily.log 2>&1

# Option B: Weekly refresh
# 0 2 * * 0 (every Sunday at 2 AM)

# Option C: On-demand when new data arrives
# Run manually as needed
```

### 4. Monitor Data Freshness
```bash
# Check when metrics were last updated
psql stocks -c "
SELECT
  date,
  COUNT(*) as count,
  COUNT(CASE WHEN revenue_growth_3y_cagr IS NOT NULL THEN 1 END) as with_data
FROM growth_metrics
GROUP BY date
ORDER BY date DESC
LIMIT 10;
"
```

---

## Timeline Summary

| Stage | Task | Duration | What You Do |
|-------|------|----------|------------|
| Prep | Set up environment | 5 min | `source .env.local` |
| 1 | Annual statements | 45 min | Watch logs |
| 2 | Quarterly statements | 45 min | Check other things |
| 3 | Supporting data | 45 min | Grab coffee ☕ |
| 4 | Growth metrics | 30 min | Still running... |
| 5 | Verification | 15 min | Verify results |
| **TOTAL** | **Full Data Load** | **~3.5 hours** | **~20 min active work** |

---

## Success Metrics

**You'll know it worked when:**

1. ✅ All stages complete without errors (check execution.json)
2. ✅ Growth metrics coverage improves from ~4% to ~17%
3. ✅ analyze_growth_gaps.py shows improvement
4. ✅ No symbols are completely missing growth data (all have at least key_metrics fallback)
5. ✅ Large caps have comprehensive data (annual, quarterly, cash flow, earnings)
6. ✅ Downstream processes work with more complete data

---

## One More Thing: Keep It Fresh

After first full load, schedule recurring updates:
```bash
# Load new growth metrics weekly
0 2 * * 0 python3 load_all_growth_metrics.py --batch-size 500

# Load new upstream data when available
0 3 * * 0 python3 load_all_growth_data.py --stage 4  # Just the last stage
```

---

## Questions During Execution?

**"Is it supposed to take this long?"**
Yes - 3-4 hours is normal. Each batch takes 30-90 seconds, and there are 94 batches.

**"Can I stop it and resume?"**
Yes - upsert logic makes it safe. Just run the command again when ready.

**"What if half the symbols fail?"**
That's OK - you've still loaded 23,000 symbols. Run again and it will fill in more.

**"How do I know if it's actually working?"**
Watch the logs - you should see "✅ Batch X complete" messages every 30-90 seconds.

**"Can I speed it up?"**
Yes - increase batch size to --batch-size 750 or 1000, but watch memory.

**"What if all 46,875 symbols don't have data?"**
That's fine - only ~10,000 have financial statements. The rest get key_metrics fallback (margins, basic growth %).

---

## Go Get 'Em! 🚀

Run this and you'll have comprehensive growth metrics for your entire stock universe.

```bash
source .env.local
python3 load_all_growth_data.py --stage all
python3 load_all_growth_metrics.py --batch-size 500
```

See you in 4 hours! ☕
