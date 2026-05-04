# Loader Diagnostic Report
**Date:** 2026-05-04  
**Status:** AUDIT & ANALYSIS

---

## Executive Summary

Loader inventory is **out of sync**:
- **39 official loaders** documented in DATA_LOADING.md
- **65 loaders** actually on disk
- **4 documented loaders missing** from disk
- **30 extra loaders** on disk not in official list

**Root Cause:** Documentation wasn't updated as loaders evolved (OptimalLoader migration, algo system added new loaders, base classes created).

---

## The 39 Official Loaders (Per DATA_LOADING.md)

### Status
- **35 present** on disk ✓
- **4 missing** - likely deprecated or renamed
  - loadearningssurprise.py (referenced but not in repo)
  - loadlatestpricedaily.py (referenced but not in repo)
  - loadlatestpriceweekly.py (referenced but not in repo)
  - loadlatestpricemonthly.py (referenced but not in repo)

These "latest price" loaders may have been replaced by `load_eod_bulk.py` (bulk loader for daily top-ups).

---

## The 30 Extra Loaders on Disk

### Category A: Algo-Required (Essential, documented in DATA_LOADING.md)
- `load_algo_metrics_daily.py` - orchestrates trend_template, market_health, SQS
- `load_market_health_daily.py` - IBD-style market state
- `load_trend_template_data.py` - Minervini 8-pt + Weinstein stage
- `loadalpacaportfolio.py` - Live Alpaca position sync
- `algo_data_patrol.py` - 10-check watchdog
- `algo_data_freshness.py` - 23-source staleness monitor
- `loadaaiidata.py` - AAII sentiment
- `loadnaaim.py` - NAAIM exposure
- `loadfeargreed.py` - CNN Fear & Greed
- `loadanalystsentiment.py` - Analyst sentiment composite

**Status:** DOCUMENTED but scattered, should consolidate in DATA_LOADING.md

### Category B: Newly Added Loaders (Not Yet Documented)
- `load_eod_bulk.py` - Bulk EOD loader (replaces per-symbol for daily)
- `loadswingscores.py` - Full-universe swing trader scores
- `loadsectorranking.py` - Sector performance ranking
- `loadindustryranking.py` - Industry ranking
- `algo_sector_rotation.py` - Sector rotation signals
- `algo_market_exposure.py` - Market exposure calculation
- `backfill_historical_scores.py` - Historical backfill
- `loadearningsestimates.py` - Earnings consensus
- `loadadrating.py` - A/D rating loader
- `loadmultisource_ohlcv.py` - Multi-source price reconciliation

**Status:** UNDOCUMENTED - need to add to DATA_LOADING.md

### Category C: Base Classes & Infrastructure (NOT Data Loaders)
- `loader_base_optimized.py` - Base class (imported by loaders)
- `loader_metrics.py` - Runtime metrics helper
- `loader_polars_base.py` - Polars optimization base class
- `loader_safety.py` - Safety wrappers for upserts
- `data_source_router.py` - Multi-source routing (Alpaca/yfinance/EDGAR)
- `sec_edgar_client.py` - SEC EDGAR API client
- `watermark_loader.py` - Incremental loading state tracking
- `optimal_loader.py` - Base class for all modern loaders
- `bloom_dedup.py` - Bloom filter deduplication

**Status:** INFRASTRUCTURE - should NOT be in main loader count

### Category D: Utility/Helper Scripts
- `backtest_*.py` - backtesting utilities
- `generate_*.py` - data generation (possibly for testing)
- Other utilities

---

## The Real Problem: GitHub Actions Workflow

The real issue blocking AWS deployment isn't the loaders - it's the **CloudFormation export lookup failure**.

**The Error Flow:**
```
1. GitHub Actions push trigger
2. detect-changes job identifies modified loaders
3. deploy-infrastructure job tries to run
4. Queries CloudFormation for exports (looking for 'StocksApp-ClusterArn', etc.)
5. FAILS - exports don't exist or have wrong names
6. Workaround added: && false to skip the job
7. execute-loaders job still tries to lookup the same exports
8. May or may not fail depending on error handling
```

**Why Exports Are Missing:**
- CloudFormation templates created but never deployed
- OR deployed with different names
- OR the exports were never defined in the templates

---

## What Needs to Happen (Right Way)

### 1. Fix Documentation (IMMEDIATE)
- [ ] Update DATA_LOADING.md to include all 20 supplementary loaders
- [ ] Mark 4 "latest price" loaders as deprecated/replaced
- [ ] Document `load_eod_bulk.py` as primary EOD loader
- [ ] Separate infrastructure classes (loader_*.py, optimal_loader.py, etc) into different section
- [ ] Add run schedule for all 59 canonical loaders

### 2. Verify Loader Quality (THIS WEEK)
- [ ] Test 39 official loaders locally (run_eod_loaders.sh)
- [ ] Verify OptimalLoader pattern applied (watermark + dedup + bulk copy)
- [ ] Check all loaders use .env.local credentials
- [ ] Verify data patrol passes all checks
- [ ] Confirm no duplicate/stale loaders

### 3. Fix AWS Deployment (THIS WEEK)
Option A: Deploy CloudFormation Properly
- [ ] Create actual CloudFormation stacks (not just templates)
- [ ] Define correct export names
- [ ] Update GitHub Actions to reference real exports
- [ ] Enable deploy-infrastructure job once exports exist

Option B: Use Local-First Strategy (Shorter Term)
- [ ] Keep && false workaround
- [ ] Focus on local + scheduled execution (Windows Task Scheduler)
- [ ] Move to AWS later once infrastructure is stable

### 4. Improve Loaders (ONGOING)
- [ ] Ensure all 59 use OptimalLoader pattern
- [ ] Apply S3 staging for high-volume loaders (prices, technicals)
- [ ] Set up parallel execution (max 5 concurrent)
- [ ] Add comprehensive error logging
- [ ] Create health check per loader

---

## Current State of Individual Loaders

### Core Price Loaders (OptimalLoader Status)
- `loadpricedaily.py` - ✓ Migrated to OptimalLoader
- `loadpriceweekly.py` - ✓ Migrated
- `loadpricemonthly.py` - ✓ Migrated
- `load_eod_bulk.py` - ✓ Uses batched yfinance (new pattern)

### Signal Loaders (OptimalLoader Status)
- `loadbuyselldaily.py` - ✓ Migrated
- `loadbuysellweekly.py` - ✓ Migrated
- `loadbuysellmonthly.py` - ✓ Migrated
- `loadbuysell_etf_*` - ✓ Migrated

### Fundamental Loaders (OptimalLoader Status)
- `loadannualbalancesheet.py` - ✓ Migrated (uses SEC EDGAR client)
- `loadquarterlybalancesheet.py` - ✓ Migrated
- All income statement + cash flow loaders - ✓ Migrated

### Newer Loaders (OptimalLoader Status)
- `loadswingscores.py` - ✓ Full-universe, uses OptimalLoader
- `loadsectorranking.py` - ? Need to verify
- `loadindustryranking.py` - ? Need to verify
- `loadaaiidata.py` - ? Need to verify

---

## The && false Situation

**Why it's there:**
```bash
if: ${{ needs.detect-changes.outputs.infrastructure-changed == 'true' && false }}
```

This means: "Deploy infrastructure IF changed AND if false (never)". It's a workaround.

**Why it was added:**
Commit 59ce7487f (May 2, 2026):
- "GitHub Actions was failing on CloudFormation export lookup"
- "Infrastructure is already in place - skip it and run loaders immediately"

**What this means:**
1. Someone deployed infrastructure manually to AWS (before GitHub Actions)
2. But didn't define CloudFormation exports
3. GitHub Actions tried to look them up, failed
4. Added `&& false` to skip the failing job

**Current Impact:**
- Infrastructure job always skipped
- Loader jobs try to look up same exports (may fail silently or not)
- Data loading might work despite the workaround

---

## Recommendation: Fix Root Cause, Not Workaround

**Option 1: Go Back to AWS Console (30 min)**
1. Check if CloudFormation stacks exist
2. Add exports if they exist but exports are missing
3. Update GitHub Actions to reference correct export names
4. Re-enable deploy-infrastructure job
5. Test end-to-end

**Option 2: Start Fresh with Infrastructure (2 hours)**
1. Delete existing CloudFormation stacks (if any)
2. Verify GitHub secrets are configured (AWS creds, API keys)
3. Remove `&& false` from workflow
4. Push code to trigger fresh deployment
5. Monitor CloudFormation stack creation

**Option 3: Local-First Strategy (1 hour)**
1. Keep `&& false` for now (infrastructure is manual for now)
2. Focus on validating loaders work locally
3. Set up Windows Task Scheduler for daily EOD runs
4. Come back to AWS once local pipeline is bulletproof

---

## Next Steps (Your Decision)

**If you want to fix AWS deployment properly:**
1. Tell me to check AWS console for CloudFormation stacks
2. Or tell me to start fresh deployment
3. We'll fix the export issue and re-enable infrastructure job

**If you want to focus on loader quality first:**
1. We update DATA_LOADING.md (consolidate documentation)
2. Test all 59 loaders locally via run_eod_loaders.sh
3. Verify OptimalLoader pattern across the board
4. Make sure local pipeline is rock-solid
5. THEN tackle AWS deployment with confidence

**My recommendation:** Go with Option 3 (local-first) because:
- Infrastructure deployment is currently broken (exports missing)
- Fixing it requires AWS console access or starting from scratch
- Local pipeline is proven to work (data is current through 5/1)
- Better to have reliable local → AWS later than broken AWS → rollback

---

## Action Items

Pick one:

A) **"Diagnose AWS infrastructure" →** Tell me to check CloudFormation stacks, find missing exports, fix workflow

B) **"Focus on loader quality first" →** We update docs, test loaders locally, ensure all 59 are production-ready

C) **"Just get data loading working best way possible right now" →** Set up Windows Task Scheduler for local EOD runs (5:30pm daily), data goes in database, frontend reads it

Which path?
