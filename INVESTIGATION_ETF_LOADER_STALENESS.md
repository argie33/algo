# ETF Loader Staleness Investigation - Root Cause Analysis

**Current Date:** 2026-07-09  
**Issue:** ETF price loaders (daily/weekly/monthly) are 79.5 hours stale (last run: 2026-07-06 09:14-09:17)

## Key Findings

### 1. **THE PROBLEM: ETF Loaders Run SEPARATELY from Stock Loaders**

| Loader | Last Updated | Staleness | Data Age |
|--------|--------------|-----------|----------|
| `price_daily` (stock) | 2026-07-09 11:02 | **5.7h ago** | 2026-07-09 |
| `price_weekly` (stock) | 2026-07-09 11:08 | **5.6h ago** | 2026-07-09 |
| `etf_price_daily` | 2026-07-06 09:14 | **79.5h ago** | 2026-07-06 |
| `etf_price_weekly` | 2026-07-06 09:15 | **79.5h ago** | 2026-07-06 |
| `etf_price_monthly` | 2026-07-06 09:17 | **79.5h ago** | 2026-07-01 |

**CRITICAL INSIGHT:** Stock prices were just updated 5.7 hours ago, but ETF prices haven't been touched since Sunday 2026-07-06.

### 2. **ROOT CAUSE: Unified Loader Not Processing ETF Assets**

The Terraform configuration (terraform/modules/loaders/main.tf line 687-695) sets up a UNIFIED price loader:

```terraform
each.key == "stock_prices_daily" ? [
  {
    name  = "LOADER_INTERVALS"
    value = "1d,1wk,1mo"
  },
  {
    name  = "LOADER_ASSET_CLASSES"
    value = "stock,etf"    # ← BOTH asset classes should load
  }
] : [],
```

The loader configuration is CORRECT. However:

1. **The loader IS running** (evidenced by recent stock price updates)
2. **But only for stocks** - ETF prices are NOT being updated
3. **The LOADER_ASSET_CLASSES="stock,etf" environment variable is set correctly**

### 3. **Why ETF Prices Aren't Updating**

There are four possible causes:

**A. Loader Silently Skips ETF Processing**
- The unified loader starts with `asset_class="stock"` 
- May crash/fail when trying to load ETF symbols
- Silent failure → no error logged → looks like "completed successfully"
- **Evidence:** ETF status is marked `COMPLETED` with 100%, but data hasn't changed

**B. Loader Runs Multiple Times with Different Asset Classes**
- Loader runs once for stocks (updates daily/weekly)
- Loader should run again for ETFs (should update etf_price_*)
- Second invocation never happens or fails silently
- **Need to verify:** Does EventBridge trigger separate tasks for each asset class?

**C. Environment Variable Not Reaching the Task**
- LOADER_ASSET_CLASSES set in Terraform but not passed to ECS container
- Container defaults to `asset_class="stock"` only
- **Need to verify:** CloudWatch logs for the actual task execution

**D. Loader Code Doesn't Support Multiple Asset Classes**
- The code loads OHLCV data but doesn't create separate table entries for ETF vs stock
- Both use the same `price_daily` table (no `asset_class` column to differentiate)
- **Unlikely** - the schema clearly has `etf_price_daily`, `etf_price_weekly`, etc.

### 4. **Critical Questions Requiring Investigation**

1. **How is the unified loader invoked?**
   - Is it a single ECS task that loops through asset classes internally?
   - Or separate EventBridge triggers for each asset class?

2. **What does load_prices.py actually do?**
   - Line 62: `def __init__(self, interval: str = "1d", asset_class: str = "stock", ...)`
   - The loader takes a single `asset_class` parameter
   - **How does one task load BOTH stocks AND ETFs if each instance only handles one?**

3. **Is there a missing wrapper script?**
   - The Terraform sets `LOADER_ASSET_CLASSES="stock,etf"` (plural, comma-separated)
   - But the Python loader expects single `asset_class="stock"` (singular)
   - **There should be a script that parses the environment and spawns multiple loader instances**

## Immediate Next Steps

1. **Check CloudWatch logs** for stock_prices_daily task (2026-07-09 11:02 run)
   - Search for "asset_class" or "etf" 
   - Look for any errors or "skipped" messages

2. **Check runner.py** (loaders/runner.py)
   - How does it parse LOADER_ASSET_CLASSES?
   - Does it spawn separate loader instances per asset class?

3. **Check load_prices.py main() entry point**
   - Does it read LOADER_ASSET_CLASSES and loop?
   - Or does it only load the single asset_class specified?

4. **Verify ECS task history**
   - How many stock_prices_daily tasks have run since 2026-07-06?
   - Are they all taking the same time (suggests same workload)?
   - Or do some take longer (suggests processing both stocks + ETFs)?

## Hypothesis

**Most Likely:** The unified loader is being invoked as a single ECS task but is not parsing `LOADER_ASSET_CLASSES` correctly. The runner.py or load_prices.py entry point should:

1. Read `LOADER_ASSET_CLASSES` environment variable
2. Parse comma-separated values ("stock,etf")
3. Create separate `PriceLoader` instances for each asset class
4. Run them sequentially or in parallel

Currently, it's probably:
- Reading the environment variable but ignoring it
- Only loading `asset_class="stock"`
- Completing "successfully" without ever touching the ETF tables
- No error raised because stock loading succeeded

This is a classic SILENT FAILURE pattern that violates GOVERNANCE.md.
