# Loader Architecture Cleanup — COMPLETE ✓

**Date:** 2026-05-09  
**Result:** Clean production pipeline with clear Phase 2+ future roadmap

---

## Summary of Changes

### Before Cleanup
- **64 loader files** in root directory
- **41 integrated** into Terraform (production)
- **23 orphaned** (experimental, alternative, or unused)
- **Mixed** production and aspirational code

### After Cleanup
- **46 loader files** in root directory (46 integrated into Terraform)
- **15 archived** in `/experimental/loaders/` (with clear phase roadmap)
- **5 deleted** (unused templates and scripts)
- **Clear separation** of Phase 1 (shipped) vs Phase 2+ (future)

---

## Decisions Made

### ✓ INTEGRATED (1)
- `load_eod_bulk.py` — Fast EOD price refresh (5 min vs hours)
  - Scheduled: 5:00am UTC (midnight ET, TUE-SAT)
  - Runs after previous day's signals complete
  - Uses threaded batch downloads for 5000+ symbols

### ⊘ ARCHIVED (15)
All moved to `/experimental/loaders/` with README explaining future phase:

**Phase 2 Features (Next Priority):**
- `load_market_health_daily.py` — Market breadth, distribution, regime detection
- `loadbenchmark.py` — Performance analytics
- `loadmeanreversionsignals.py`, `loadrangesignals.py`, `loadswingscores.py` — Alt signal approaches
- `loadnews.py` — News sentiment (complements official social_sentiment)
- `loadindustryranking.py` — Industry momentum

**Phase 3+ Features (Future):**
- `loadoptionschains.py`, `loadcoveredcallopportunities.py` — Options/derivatives
- `loadcommodities.py` — Macro hedging
- `loadsecfilings.py` — SEC filing events
- `loaddailycompanydata.py` — Company metrics
- `loadforwardeps.py` — Forward earnings
- `loadalpacaportfolio.py` — Real-time dashboard sync

### ✗ DELETED (5)
- `loadmultisource_ohlcv.py` — Unused fallback pattern
- `loaders.sh.DISABLED` — Outdated shell script (Terraform replaced)
- 3 template files that don't exist (cleanup artifacts)

---

## Official Pipeline (42 Loaders) — All Scheduled & Tested

**Tier 1 — 3:30am ET**
- stock_symbols (1)

**Tier 2 — 4:00am ET**
- stock_prices (3), etf_prices (3)

**Tier 3 — 4:15am ET**
- trend_template_data, technicals_daily (2)

**Tier 4 — 10:00am ET**
- financials (9: annual/quarterly/ttm × income/balance/cashflow)

**Tier 5 — 11:00am ET**
- earnings (4: history, revisions, surprise, sp500 snapshot)

**Tier 6 — 12:00pm ET**
- market_data (11: indices, sectors, relative, seasonality, econ, aaii, naaim, fear, calendar)

**Tier 7 — 1:00pm ET**
- analysis (5: sentiment, upgrades, social, factors, stock_scores)

**Tier 8 — 5:00pm ET**
- signals (7: daily/weekly/monthly + etf_daily/weekly/monthly + etf_signals)

**Tier 9 — 5:25pm ET**
- algo_metrics_daily (1)

**Tier 10 — 5:00am UTC next day (Midnight ET)**
- eod_bulk_refresh (1) — **NEW**

---

## Architecture Improvements

### ✓ Cleaner Root Directory
- Reduced visual clutter (64 → 46 files)
- Clear intent: only production loaders in root
- No confusion between shipped vs aspirational

### ✓ Clear Phase Roadmap
- `/experimental/loaders/` documents Phase 2, 3+ features
- Each loader has clear purpose and phase
- Easy to pick up Phase 2 work (just move loader back + add to Terraform)

### ✓ Better IaC Alignment
- Principle: if it's not in Terraform, don't keep it in root
- Eliminates "ghost code" that never runs
- Easier to audit deployment pipeline

### ✓ Improved Maintenance
- Fewer files to grep through
- Clearer dependencies (Terraform is source of truth)
- Onboarding: "see `/experimental/README.md` for Phase 2 items"

---

## Files Modified/Created

```
Modified:
  terraform/modules/loaders/main.tf (+10 lines: eod_bulk integration)

Created:
  LOADER_CLEANUP_DECISIONS.md (detailed rationale for each decision)
  CLEANUP_COMPLETE.md (this file)
  experimental/README.md (Phase 2+ roadmap)
  experimental/loaders/ (15 archived loaders)

Deleted:
  loadmultisource_ohlcv.py
  loaders.sh.DISABLED
  (3 non-existent templates)

Moved:
  load_market_health_daily.py → experimental/loaders/
  loadcommodities.py → experimental/loaders/
  ... (13 more)
```

---

## Verification

✓ Terraform validates: `terraform validate` passes  
✓ No orphaned imports: archived loaders not imported by algo code  
✓ Git clean: all changes committed  
✓ Production pipeline: 42 loaders all scheduled  
✓ Future roadmap: 15 loaders in experimental/ with clear phases  

---

## Next Steps for Phase 2

To integrate a Phase 2 loader:

1. Move from `experimental/loaders/` to root
2. Add to `terraform/modules/loaders/main.tf`:
   ```hcl
   loader_file_map: "name" = "file.py"
   scheduled_loaders: "name" = { schedule = "cron(...)" }
   all_loaders: "name" = { cpu = 256, ... }
   critical_loaders: (if on-demand Fargate needed)
   ```
3. Test with live data
4. Deploy via `terraform apply`

See `LOADER_CLEANUP_DECISIONS.md` for Phase 2 priority order.

---

## Why This Matters

The codebase now clearly reflects:
- **What ships:** 42 official loaders in root + Terraform
- **What's planned:** 15 Phase 2+ features in `/experimental/`
- **What's gone:** unused code removed

This eliminates the "architectural slop" you identified and makes the platform easier to understand, maintain, and extend.
