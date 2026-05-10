# Architecture Cleanup Session — 2026-05-09

## Overview
Comprehensive audit of loader architecture to identify and document "architectural slop" — files that clutter the codebase without clear purpose or integration.

## Key Findings

**Loader Inventory:**
- 64 loader Python files in git repository
- 41 loaders integrated into Terraform pipeline + scheduled
- 23 orphaned loaders (not in Terraform)

**Root Cause:** Early development accumulated experimental, extended, and alternative loaders without deciding which are:
- Production (schedule in Terraform) 
- Future (archive to `/experimental/`)
- Unused (delete)

---

## Work Completed This Session

### 1. Fixed Missing ETF Signal Loader Schedules
**Issue:** `loadbuysell_etf_weekly.py` and `loadbuysell_etf_monthly.py` existed but weren't in Terraform at all.

**Fix:** Added to `terraform/modules/loaders/main.tf`:
- Added to `loader_file_map` (lines 161-162)
- Added to `scheduled_loaders` (lines 343-349), scheduled at 10pm UTC (5pm ET) same as stock signals
- Added to `all_loaders` with cpu/memory/timeout (lines 418-419)
- Added to `critical_loaders` set (line 431)

**Result:** ETF signal loaders now scheduled and will run as part of official pipeline.

### 2. Created Architectural Decision Matrix
**Document:** `LOADER_CLEANUP_RECOMMENDATIONS.md`

Categorized all 23 orphaned loaders:

| Category | Count | Examples | Recommendation |
|----------|-------|----------|-----------------|
| Bulk/Alternative Implementations | 2 | `load_eod_bulk.py`, `loadmultisource_ohlcv.py` | Decide: Keep as fallback or integrate? |
| Market/Economic Extensions | 2 | `load_market_health_daily.py`, `loadcommodities.py` | Is market health used by algo? |
| News/Sentiment | 2 | `loadnews.py`, `loadsecfilings.py` | Delete (not in signal logic) |
| Technical/Options | 3 | `loadoptionschains.py`, `loadcoveredcallopportunities.py` | Archive (future phase?) |
| Rankings/Comparisons | 3 | `loadsectorranking.py`, `loadbenchmark.py` | Consolidate or delete? |
| Alternative Signals | 3 | `loadmeanreversionsignals.py`, `loadrangesignals.py` | Archive (not in official tiers) |
| Account Integration | 1 | `loadalpacaportfolio.py` | Decide: Live import needed? |
| Utility Infrastructure | 3 | `loader_safety.py`, `loader_metrics.py`, `loader_sla_tracker.py` | Keep in root (core) |

### 3. Verified Terraform Structure
- Validated Terraform syntax: ✓ Success (with pre-existing deprecation warnings)
- All 41 official loaders properly mapped to Python files
- All scheduled loaders have ECS task definitions
- Proper dependency ordering maintained (e.g., trend_template_data before signals)

---

## Remaining Architecture Decisions Required

The audit has identified which loaders exist and which are integrated, but **USER DECISION REQUIRED** on each orphaned loader:

1. **For each orphaned loader, decide:**
   - `INTEGRATE` — Add to Terraform with schedule (rare, only if critical)
   - `ARCHIVE` — Move to `/experimental/` or `docs/archived/` (likely most)
   - `DELETE` — Remove from repo entirely (for genuinely unused)

2. **Files needing decision:**
   - Is `load_eod_bulk.py` faster/better than `loadpricedaily.py`? (Replace or keep as fallback?)
   - Is `load_market_health_daily.py` used by circuit breakers? (Integrate or archive?)
   - Is `loadalpacaportfolio.py` needed for position import? (Integrate or delete?)
   - Are `loadnews.py`, `loadsecfilings.py`, `loadoptionschains.py` Phase 2+ features? (Archive or delete?)

---

## Files Modified This Session

```
terraform/modules/loaders/main.tf
  +10 lines (added ETF signal loaders to file_map, schedules, cpu/memory, critical_loaders)
```

## Files Created This Session

```
LOADER_CLEANUP_RECOMMENDATIONS.md (decision matrix for all 23 orphaned loaders)
ARCHITECTURE_CLEANUP_SESSION.md (this file)
```

---

## Current Official Pipeline (41 Loaders, All Scheduled)

**Tier 1 — 3:30am ET**
- stock_symbols

**Tier 2 — 4:00am ET**
- stock_prices_daily/weekly/monthly, etf_prices_daily/weekly/monthly

**Tier 3 — 4:15am ET**
- trend_template_data, technicals_daily

**Tier 4 — 10:00am ET**
- financials (annual/quarterly/ttm × income/balance/cashflow)

**Tier 5 — 11:00am ET**
- earnings_history, earnings_revisions, earnings_surprise

**Tier 6 — 12:00pm ET**
- market_overview, market_indices, sectors, relative_performance, seasonality, econ_data, aaiidata, naaim_data, feargreed, calendar

**Tier 7 — 1:00pm ET**
- analyst_sentiment, analyst_upgrades, social_sentiment, factor_metrics, stock_scores

**Tier 8 — 5:00pm ET**
- signals_daily/weekly/monthly, signals_etf_daily/weekly/monthly, etf_signals

**Tier 9 — 5:25pm ET**
- algo_metrics_daily

---

## Next Steps

1. **Review Decision Matrix** (`LOADER_CLEANUP_RECOMMENDATIONS.md`)
2. **Provide decisions** on each orphaned loader (INTEGRATE/ARCHIVE/DELETE)
3. **Execute cleanup:**
   - Move archived loaders to `/experimental/` with README explaining purpose
   - Delete unused loaders (verify no imports via grep first)
   - Integrate any new loaders into Terraform
4. **Verify:** Run `grep -r` to ensure deleted loaders have no references
5. **Document:** Update loader README with final inventory and architecture decisions

---

## Rationale

**Why this matters:**
- 23 orphaned loader files create confusion about what's production
- No clear signal whether extended features (news, options, etc.) are future or unused
- Mix of official + experimental code in root makes it hard to understand the platform
- IaC principle violated: if it's not in Terraform, it shouldn't be in the code

**Outcome:**
- Clear separation: official pipeline (41) vs experimental (TBD)
- Reduced context load: new developers see only integrated loaders
- Easier maintenance: decision record for each loader
- Proper IaC: everything deployed is in Terraform, everything in Terraform is deployed
