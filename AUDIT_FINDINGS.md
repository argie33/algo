# System Audit Findings (2026-05-16)

## CRITICAL ISSUE: Missing Terraform Loaders

**Status:** RESOLVED ROOT CAUSE - DECISION NEEDED

### The Problem
7 Python loader files are referenced in Terraform but don't exist:
- `loadanalystsentiment.py`
- `loadanalystupgradedowngrade.py`
- `loadearningsestimates.py`
- `loadtechnicalsdaily.py`
- `load_trend_template_data.py`
- `load_market_data_batch.py`
- `algo_continuous_monitor.py`

### Root Cause
These loaders were **intentionally deleted** in commit 933927ff2 because they "weren't integrated into run-all-loaders.py." However:
1. Database schema still defines tables for them (init_database.py)
2. Terraform still references them in loader_file_map
3. Algorithm logic queries these tables (57 refs to technical_data, 72 refs to trend_template)
4. Data patrol monitors their freshness

**Current state:** BROKEN REFERENCE LOOP - tables exist but are never populated; algo code tries to use NULL values.

### Solution Options

**OPTION A: Clean Up (Recommended for Immediate Stability)**
Remove all references - Terraform, schema, algorithm logic. System becomes honest about what's implemented. ~200 lines across 10 files.
- **Timeline:** 1-2 hours
- **Benefit:** Clean, honest system
- **Cost:** Lose advanced technical features
- **Decision:** Best if features aren't critical to trading

**OPTION B: Restore & Integrate (Full-Featured)**
Restore loaders from git history, fix them, add to data pipeline. System becomes fully featured as originally designed. ~500 lines, needs real API access.
- **Timeline:** 4-6 hours + testing
- **Benefit:** Full feature set
- **Cost:** More complex, API dependencies
- **Decision:** Better if features add real trading value

---

## Action Plan (Recommended PHASE 1)

### Immediate (1-2 hours) - Option A: Clean Up
1. Remove missing loaders from `terraform/modules/loaders/main.tf` (loader_file_map, scheduled_loaders, all_loaders)
2. Remove tables from `init_database.py`
3. Update algo logic:
   - `algo_advanced_filters.py` - remove analyst_upgrade_downgrade query
   - `algo_exit_engine.py` - remove technical_data_daily JOINs (or make optional)
   - `algo_filter_pipeline.py` - make trend_template optional
4. Update `algo_data_patrol.py` - don't check for missing tables
5. Test: Run `python3 algo_orchestrator.py --mode paper --dry-run` - should complete without errors

### Next (2-3 hours) - Verify Core Calculations
1. Swing score formula (peak detection, trend scoring)
2. Signal generation (BUY/SELL criteria correctness)
3. Exit logic (stop placement, target calculation, Minervini breaks)
4. Trade executor (position sizing, validation)
5. Market exposure (sector/industry calculations)

### Follow-up (2-4 hours) - Performance & Security
1. Profile slow API queries
2. Verify parallelization in loaders
3. Check rate limiting
4. Verify no secrets in code
5. Test paper trading limits

---

## Data Pipeline Architecture

**Working (23 loaders):**
- Tier 0: Stock symbols (loadstocksymbols.py)
- Tier 1: Prices daily/weekly/monthly (load_price_aggregate.py, loadpricedaily.py, etc.)
- Tier 2: Reference data (earnings, sectors, profiles, financials, key metrics, etc.)
- Tier 2b: Computed metrics (growth, quality, value)
- Tier 3: Trading signals (buy/sell daily, buy/sell aggregates)
- Tier 4: Algo metrics (load_algo_metrics_daily.py)

**Missing (7 loaders - need decision):**
- Technical indicators (RSI, MACD, SMA, EMA, ATR, ADX, ROC, etc.)
- Trend template scoring
- Analyst sentiment
- Analyst upgrades/downgrades
- Earnings surprises
- Market data batch (consolidation)
- Continuous monitor (every 15 min)

---

## Key Findings

✅ **Working Well:**
- Core orchestrator (7 phases)
- Trading signals generation
- Position management
- Exit execution logic
- 23 existing loaders

⚠️ **Needs Attention:**
- Broken Terraform references (7 files)
- Incomplete schema (tables without loaders)
- Missing technical/sentiment data (optional features)
- Performance not yet profiled

❌ **Not Yet Audited:**
- Calculation accuracy (swing score, signals, exposure)
- Security (API keys, rate limiting, secrets)
- Data freshness (SLA compliance)
- End-to-end orchestrator test

---

## Recommendation

**Approach:** Fix Option A first (1-2 hours), verify system works, then decide if Option B needed.

**Why:** 
- Creates a clean, honest system immediately
- Unblocks testing of core trading logic
- Allows verification of calculation accuracy
- Can always restore missing loaders later if needed (they're in git)

**Next:** 
- Get user approval on Option A vs B
- Implement chosen option
- Test orchestrator end-to-end
