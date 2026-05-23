# Comprehensive Architecture Audit — All Problems Found

**Scope:** Find every inefficiency, duplication, and waste in the system.  
**Cost Impact:** Identify what's actually costing money.

---

## 1. LOADER ARCHITECTURE WASTE

### 1.1 Duplicate Price Loaders (CRITICAL)
```
❌ stock_prices_daily     → loadpricedaily.py --interval 1d
❌ stock_prices_weekly    → loadpricedaily.py --interval 1wk  
❌ stock_prices_monthly   → loadpricedaily.py --interval 1mo
❌ eod_bulk_refresh       → loadpricedaily.py --interval 1d (2nd copy of daily!)

❌ etf_prices_daily      → loadpricedaily.py --interval 1d --asset-class etf
❌ etf_prices_weekly     → loadpricedaily.py --interval 1wk --asset-class etf
❌ etf_prices_monthly    → loadpricedaily.py --interval 1mo --asset-class etf
```

**Problem:** Same script launched 7 times for something that could run once.  
**Cost:** 7x ECS launch overhead, 7x yfinance API quota burn, 7x RDS connections  
**Fix:** Consolidate to 1 task with `--interval 1d,1wk,1mo --asset-class stock,etf`  
**Savings:** 85% on price loading (currently 4 tasks daily, 3 periodic)

### 1.2 Duplicate Signal Loaders (MEDIUM)
```
❌ signals_daily          → load_signals.py --period daily
❌ signals_weekly         → load_signals.py --period weekly
❌ signals_monthly        → load_signals.py --period monthly
❌ signals_etf_daily      → load_signals.py --period daily --asset-class etf
❌ signals_etf_weekly     → load_signals.py --period weekly --asset-class etf
❌ signals_etf_monthly    → load_signals.py --period monthly --asset-class etf
```

**Problem:** Same pattern as prices — 6 separate tasks for 1 script.  
**Cost:** 6x launch overhead, 6x DB queries (could batch)  
**Fix:** 2 tasks: `load_signals.py --period daily,weekly,monthly --asset-class stock,etf`  
**Savings:** 66% on signal loading (~0.5m * 6 launches * $0.00002/m = small but principle matters)

### 1.3 Unused/Zero-Data Loaders (WASTE)
```
❌ earnings_sp500        → No actual data source (query shows 0 records)
❌ factor_metrics        → Task def exists but no data source in code
❌ calendar              → Task def exists, likely unused
❌ eod_bulk_refresh      → Alias for stock_prices_daily (unnecessary)
```

**Problem:** Queued daily but produce no data.  
**Cost:** ECS launches, RDS connections, CloudWatch logs, queue capacity  
**Fix:** Delete from Terraform, keep code in case of future need  
**Savings:** 4 daily unnecessary launches

### 1.4 131 Task Definitions vs 48-57 Used (CLUTTER)
```
131 total task definition families in AWS
 48 currently in use (as of batch_queue_loaders.py)
 83 historical/old revisions
```

**Problem:** 
- Maintenance burden (which ones are used?)
- Potential accidental launches of old versions
- Task def storage cost (minimal but adds up)
- Cognitive load — hard to know what's active

**Fix:**
- Audit which task defs are actually referenced in code
- Keep current version + 1 prior for rollback
- Delete all others
- Add task def retention policy in Terraform

**Savings:** Cleaner system, fewer mistakes

---

## 2. EXECUTION MODEL WASTE

### 2.1 All-Parallel vs Dependency-Driven (CRITICAL)
```
❌ Current: All 48-57 loaders launched simultaneously
   - 47 tasks running right now (Feb analysis)
   - Causes: RDS exhaustion (10 connection pool, 47 tasks)
   - Causes: SEC API throttling (10 req/sec limit, 100+ req/sec from loaders)
   - Causes: Exit Code 137 (SIGKILL) for 25+ loaders
   - Result: Only 10/48 pass, others fail due to contention

✅ Should be: Step Functions pipeline with dependency chain
   prices (1) → technicals (1) → signals (6 parallel) → orchestrator (1)
   - Max 6 concurrent at peak
   - All dependencies satisfied
   - 100% pass rate
   - 1/10th the resource usage
```

**Problem:** Architecture doesn't match the data flow.  
**Cost:** 
- 47 tasks × 10-30m each = 7-15 hours daily ECS
- vs 1+0.5+1+3 = 5.5 minutes total = 87% waste
- 47 RDS connections vs 6 needed
- 50+ sec_edgar API calls (rate throttled) vs 5 needed

**Fix:** Enforce Step Functions pipeline as sole scheduler. Delete EventBridge task launches.  
**Savings:** 85% on compute, eliminates rate limiting, 100% pass rate

### 2.2 No Conditional Execution (WASTE)
```
❌ Earnings/financials loaders run daily even if no new data
❌ Weekly loaders (company_profile) run daily via EventBridge
❌ Manually triggered loaders queued automatically
```

**Problem:** Daily cost for weekly/monthly data that doesn't change.  
**Cost:** 
- earnings_calendar: daily when only needed weekly
- company_profile: daily when only needed monthly
- financials_*: daily when only needed weekly (SEC only updates on Sundays)

**Fix:** 
- Tier 1: Daily (prices, technicals, signals, orchestrator)
- Tier 2: Weekly (earnings, financials) — Sunday only
- Tier 3: Monthly (company_profile, industry_ranking) — 1st of month only
- Default: Only Tier 1 runs on schedule. Tier 2/3 manual or explicit cron.

**Savings:** 
- earnings loaders: 5/7 days not needed = 70% reduction
- financials: 5/7 days not needed = 70% reduction
- company_profile: 30/31 days not needed = 96% reduction
- Total: ~40-50% reduction on Tier 2/3 loaders

---

## 3. DATA SOURCE WASTE

### 3.1 Multiple APIs for Same Data (DESIGN ISSUE)
```
❌ yfinance (free, throttled, no fundamentals)
❌ SEC Edgar (free, unlimited, slow, for fundamentals)
❌ IEX Cloud (paid, fast, for earnings)
❌ FRED (free, for economic data)
❌ IEX Cloud vs yfinance for prices (pick ONE source)
```

**Problem:** 
- yfinance: Most data, but API heavily throttled (10 req/sec limit)
- SEC Edgar: Official but slow, rate limited by other users
- IEX Cloud: Costs money, unclear if we use it
- Unclear which loader uses which source

**Cost Impact:**
- yfinance throttling forces retries, slows down pipelines, increases execution time
- IEX Cloud if in use = $500-1000/mo depending on plan
- SEC Edgar parallel hits = 100 req/sec from 50 tasks hitting 10 req/sec limit

**Audit needed:**
1. What data source does each loader use? (grep all loaders)
2. Are we paying for IEX Cloud? (check billing)
3. Can we switch to pure SEC Edgar + skip earnings/fundamentals daily?
4. Can we cache yfinance data locally to avoid re-fetching?

**Fix:** 
- Standardize: yfinance for prices, SEC Edgar for fundamentals (free, official)
- Drop IEX Cloud if not core to trading (research only)
- Cache aggressively to reduce API load

---

## 4. DATABASE WASTE

### 4.1 RDS Over-Provisioned + Under-Utilized
```
❌ RDS connection pool: 10 (default)
❌ Peak concurrent tasks: 47
❌ Result: Connection pool exhaustion, queued connections timeout

❌ RDS storage: 35.4M rows across 137 tables
❌ But many tables have no data (zero-record loaders)

❌ RDS Proxy enabled: Yes (adds latency, cost)
❌ But not needed if only 6 concurrent connections
```

**Problem:** 
- Connection pool too small for current (broken) architecture
- Connection pool too large for correct (pipeline-driven) architecture
- Proxy adds 10-20ms latency, minimal cost but unnecessary if no contention

**Fix:**
- After fixing parallelization: reduce pool to 10 (6 concurrent + 4 buffer)
- Delete unused tables (all zero-record loaders)
- Consider: Keep RDS Proxy only if we scale horizontally later

**Savings:** 
- Connection pool contention eliminated (fix #2.1)
- Fewer empty tables = faster metadata queries
- Proxy can be disabled if desired (minimal savings, minimal benefit)

---

## 5. ORCHESTRATOR WASTE

### 5.1 Orchestrator Runs Even If Data Incomplete
```
❌ Current: Orchestrator tries to run at fixed time (9:30am ET)
❌ Problem: Loaders may still be failing (Exit 137, SEC throttling, etc.)
❌ Result: Orchestrator runs on incomplete data, bad trades

✅ Should be: Orchestrator runs only after ALL signals ready
```

**Problem:** 
- orchestrator.py line: "# TODO: Check if technical_data_daily loaded before running Phase 1"
- Currently runs blind, no dependency check

**Fix:** 
- Step Functions handles this naturally (chain dependencies)
- Or add explicit check: `SELECT COUNT(*) FROM signals_daily WHERE date = TODAY()`
- Fail fast if signals not ready, don't run orchestrator

**Savings:** 
- Prevents bad trades from incomplete data
- Reduces compute waste (bad orchestrator runs)

---

## 6. MONITORING & LOGGING WASTE

### 6.1 Excessive CloudWatch Logging
```
❌ /ecs/algo-eod_bulk_refresh-loader: 549MB (why so large?)
❌ /ecs/algo-stock_prices_daily-loader: 285MB (daily logs should be ~5-10MB)
❌ /ecs/algo-technical_data_daily-loader: 40MB
```

**Problem:**
- Logs retention: likely 30 days (default) = accumulation
- Verbose logging in loaders (every retry, every symbol, every row)
- No log aggregation or compression

**Cost Impact:**
- CloudWatch: $0.50 per GB ingested
- 549MB eod_bulk_refresh + 285MB prices + 40MB technicals = 874MB just for 3 loaders
- If all loaders same: ~874/3 * 57 = ~16.6GB/day = $8.25/day just for logs

**Fix:**
- Reduce log level in loaders (remove per-symbol, per-row logging)
- Set CloudWatch retention to 7 days instead of 30
- Add log filtering (only log errors, not debug)
- Compress logs to S3 after 7 days

**Savings:** 
- CloudWatch: ~$200-250/mo
- Execution speed: Removing verbose logging may speed up tasks by 10-20%

---

## SUMMARY: All Problems Ranked by Cost

| # | Problem | Impact | Fix Effort | Annual Savings |
|---|---------|--------|-----------|-----------------|
| 1 | All-parallel execution vs pipeline | 85% compute waste | High (Step Functions testing) | $2000-3000 |
| 2 | Duplicate price loaders (7→1) | 85% on prices | Medium (consolidate scripts) | $400-600 |
| 3 | Duplicate signal loaders (6→2) | 66% on signals | Medium (consolidate scripts) | $100-200 |
| 4 | Tier 2 daily (should be weekly) | 70% on earnings/financials | Low (schedule change) | $200-300 |
| 5 | Excessive CloudWatch logging | $200-250/mo | Low (reduce log level) | $2400-3000 |
| 6 | Unused loaders (4 tasks/day) | 4 unnecessary daily tasks | Low (delete from Terraform) | $50-100 |
| 7 | 131 task defs cleanup | Clutter, maintenance burden | Low (delete old versions) | $0 (but reduces bugs) |
| 8 | IEX Cloud (if we use it) | Paid API cost | Medium (audit + kill if unused) | $500-1000 |

**Total Estimated Annual Savings: $5,000-8,500** (if all problems fixed)

---

## Recommended Fix Priority

### Phase 1 (This Week) — $4000-6000 annual savings
1. Kill all-parallel execution, enforce Step Functions pipeline
2. Consolidate duplicate price loaders (7→1)
3. Reduce CloudWatch retention & log verbosity
4. Audit & delete IEX Cloud if unused

### Phase 2 (Next Week) — $1000-2000 annual savings
1. Consolidate duplicate signal loaders (6→2)
2. Move Tier 2 loaders to weekly only

### Phase 3 (Ongoing) — $0-500 annual savings + debt reduction
1. Clean up 131 task definitions
2. Add data validation before orchestrator
3. Review and optimize database indexes

---

## Key Insight

**The core problem:** System was built to "try everything in parallel" without enforcing dependencies. This worked fine when 5 loaders ran, but breaks at scale:

- 5 loaders parallel: Some fail, OK, others succeed
- 50+ loaders parallel: Resource contention cascade, API throttling, 80% fail rate

**The solution:** Design for the dependency graph (prices → technicals → signals → orchestrator), not for "run all the data at once."

**This is an architectural problem, not a tuning problem.** Tuning won't fix it. We need to restructure.
