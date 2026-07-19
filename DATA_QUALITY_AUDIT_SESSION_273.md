# Session 273: Data Quality & Loader Maintenance Audit

**Date:** 2026-07-19  
**Status:** CRITICAL ISSUES IDENTIFIED & PARTIALLY FIXED  
**Goal:** Review system for weird bypasses, cheats, and non-kosher workarounds

---

## Executive Summary

Found **11 PHANTOM STALE TABLES** caused by:
1. **Dead tracking entries** (6) - data_loader_status has entries for tables that don't exist or were renamed
2. **Orphaned loaders** (5) - tables exist but no active loader maintains them
3. **Loader failures** (1) - sector_performance runs but fails silently

Root cause: Migration from yfinance → SEC EDGAR + schema consolidations left orphaned tracking entries and dead data unresolved.

---

## Issues Fixed (Session 273)

### Fix #1: Removed 6 Dead Tracking Entries ✅

These tables don't exist, but were tracked in data_loader_status:

| Table | Threshold | Status | Action |
|-------|-----------|--------|--------|
| trend_criteria_data | 1d | DELETED | Renamed to trend_template_data, old entry orphaned |
| algo_reconciliation | 1d | DELETED | Never implemented, no such table |
| financial_statements | 30d | DELETED | Never implemented, no such table |
| market_constituents | 30d | DELETED | Never implemented, no such table |
| risk_metrics_daily | 1d | DELETED | Never implemented, no such table |
| sector_industry_daily | 7d | DELETED | Never implemented, no such table |

**Impact:** Eliminated 6 phantom "stale" warnings that confused staleness alerts.

### Fix #2: Archived earnings_history ✅

**Status:** No active loader (yfinance loaders removed in Session 271)  
**Replacement:** earnings_calendar_sec (SEC EDGAR)  
**Action:** Marked as "archived" in data_loader_status, removed from staleness threshold

**Why this matters:** earnings_history was showing as 9 days stale (7-day threshold) but no loader runs for it anymore. Confused alerts about actual staleness issues.

---

## Issues Identified (Still Broken)

### Issue #1: 5 Orphaned Tables - Loaders Deleted but Data Tracked

These tables have data but NO ACTIVE LOADERS. Last updated in May-June (1-2 months ago):

| Table | Age | Threshold | Last Update | Status |
|-------|-----|-----------|-------------|--------|
| buy_sell_weekly | 19d | 7d | 2026-05-22 | STALE - No loader |
| buy_sell_weekly_etf | 19d | 7d | 2026-05-22 | STALE - No loader |
| analyst_upgrade_downgrade | 19d | 7d | 2026-05-22 | STALE - No loader |
| naaim | 10d | 7d | 2026-06-28 | STALE - No loader |
| fear_greed_index | 3d | 7d | 2026-07-09 | STALE - No loader |

**Root Cause:** These were populated once (possibly manual upload or removed loaders) but no scheduled ECS tasks maintain them.

**Check:** No entries in `loader_execution_history` for these tables.

**Options:**
1. **DELETE** if they're truly not needed (clean up dead data)
2. **ARCHIVE** if they're historical reference data (update data_loader_status)
3. **RESTORE** if they should be actively loaded (reimplement loader + schedule)

### Issue #2: Loader Failures Not Surfaced

**sector_performance** runs but FAILS:
- Last attempt: 2026-07-19 06:01 (TODAY) → FAILED
- But data_loader_status shows `status=COMPLETED` (stale cached status!)
- System doesn't clear "COMPLETED" on failures, leading to misleading status

**Root Cause:** Phase 1 data freshness check doesn't validate that loaders actually SUCCEEDED, only that tables exist and have dates.

---

## Recommendations for Next Steps

### Immediate (Critical)

1. **Decide on orphaned tables:**
   - Do these provide value? (Dashboard enrichment, analytics, etc.)
   - If YES → Implement loader + schedule in Step Functions
   - If NO → Delete from data_loader_status and archive/drop data

2. **Fix sector_performance loader failure:**
   - Check CloudWatch logs for why it failed today
   - If transient (rate limit, network): schedule retry
   - If broken: fix code or disable

3. **Update Phase 1 to check loader status:**
   - Phase 1 should query loader_execution_history, not just data_loader_status
   - Validate last SUCCESSFUL run, not just existence of data
   - Example: `SELECT MAX(execution_start) FROM loader_execution_history WHERE loader_name='X' AND status='success'`

### Short Term

4. **Consolidate loader tracking:**
   - data_loader_status should match ONLY currently-deployed loaders
   - Remove entries for tables not in ECS task definitions (terraform/modules/loaders/main.tf)
   - Archive entries for historical/non-refreshed tables

5. **Add loader SLA monitoring:**
   - Each loader should have `frequency` (daily, weekly, monthly, once)
   - Each should have `expected_next_run` calculated from last_run + frequency
   - Alerts trigger if expected_next_run is missed

### Longer Term

6. **Deprecate data_loader_status staleness tracking:**
   - Move to orchestrator-driven validation (Phase 1)
   - orchestrator queries loader_execution_history to check "was loader successful in last 25 hours?"
   - More reliable than manual date tracking in data_loader_status

---

## Data Quality Status Now

**BEFORE Session 273:**
- 11 phantom "stale" tables (6 dead + 5 orphaned)
- 6 orphaned tracking entries creating noise

**AFTER Session 273 Fixes:**
- 5 truly orphaned tables (need decision: delete/archive/restore)
- 1 known loader failure (sector_performance)
- 0 phantom entries (all dead entries removed)

---

## Code Changes This Session

### Database Updates
```sql
-- Delete 6 dead tracking entries
DELETE FROM data_loader_status WHERE table_name IN (
  'trend_criteria_data', 'algo_reconciliation', 'financial_statements',
  'market_constituents', 'risk_metrics_daily', 'sector_industry_daily'
);

-- Mark earnings_history as archived
UPDATE data_loader_status
SET status='archived', stale_threshold_days=NULL,
    reason='Archived: Replaced by earnings_calendar_sec (SEC EDGAR). No longer actively loaded.'
WHERE table_name='earnings_history';
```

---

## Notes for Future Sessions

**Why this happened:**
1. **Schema consolidation** (trend_criteria_data → trend_template_data) left old tracking entries
2. **Loader removal** (yfinance elimination) didn't clean up data_loader_status
3. **Dead features** (analyst_upgrade, naaim, fear_greed) loaded once then abandoned
4. **Phase 1 trust issue** - checks if data EXISTS, not if it's ACTIVELY MAINTAINED

**How to prevent:**
- Before removing loaders, remove data_loader_status entries
- Before renaming tables, update data_loader_status
- Phase 1 should validate last SUCCESSFUL loader run, not just data existence
- data_loader_status should be source-of-truth for "what should be loaded", auto-sync with Terraform

