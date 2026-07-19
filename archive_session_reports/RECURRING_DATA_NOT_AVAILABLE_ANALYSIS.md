# Root Cause Analysis: Recurring "Data Not Available" Issue

**Problem Statement:**  
Dashboard repeatedly shows "data not available" on all panels, with no clear error messages. This has happened multiple times (Sessions 131-136) with different root causes each time.

**Current Date:** 2026-07-14  
**Issue Status:** Data is 30+ hours stale; orchestrator not updating tables

---

## The Real Issue: Systemic Lack of Monitoring

The dashboard "data not available" is a SYMPTOM, not a cause. The real problem:

1. **No alert when data goes stale** - Data silently ages to 30+ hours before user notices on dashboard
2. **No alert when orchestrator fails** - Phases halt but no notification until dashboard breaks
3. **No graceful degradation** - Dashboard shows blank instead of stale data with warnings
4. **Recurring phase failures** - Phase 1 loaders incomplete after retries, Phase 6 exposure actions fail
5. **Silent failures** - Orchestrator completes with "success" but only 2/9 phases actually ran

---

## Failure Timeline (This Session)

```
2026-07-10 06:49 → Price data last updated
         ↓ (30 hours pass, NO ALERTS)
         ↓
2026-07-14 12:00 → User notices dashboard is blank
         ↓
2026-07-14 12:47 → dashboard_health_monitor.py diagnoses: prices 30h old
         ↓
2026-07-14 12:48 → Orchestrator runs but only completes 2/9 phases
         ↓
2026-07-14 12:48 → Prices still 30h old (Phase 1 failed, data never updated)
```

---

## What SHOULD Have Happened

```
2026-07-10 06:49 → Price data last updated, logged

2026-07-10 20:00 → Scheduled orchestrator run at 4:05 PM ET
         ↓ (Should update prices)
         ↓ [FAILURE] Phase 1 incomplete loaders
         ↓ → Alert: "Orchestrator Phase 1 halted, price loader retry pending"
         ↓
2026-07-10 21:00 → Cron job: `dashboard_health_monitor.py --watch 60`
         ↓
2026-07-10 21:15 → ALERT: "Orchestrator hasn't run in 4h, Phase 1 halted"
         ↓
2026-07-10 21:30 → Cron job runs: `python scripts/run_local_orchestrator.py --morning`
         ↓
2026-07-10 22:00 → Prices refreshed, all data fresh
         ↓
[PROBLEM PREVENTED]
```

---

## Root Causes by Layer

### Layer 1: Data Freshness (No Monitoring)
- **What:** No alert when data becomes stale (>24h old)
- **Impact:** User discovers via blank dashboard, 30h too late
- **Fix:** `dashboard_health_monitor.py --watch 60` as cron job

### Layer 2: Orchestrator Failures (No Visibility)
- **What:** Phases fail/halt but no logging accessible
- **Impact:** Dashboard shows "success" but only 2/9 phases ran
- **Root Cause:** Phase 1 loaders incomplete after retry; Phase 6 exposure policy fails
- **Evidence:**
  ```
  [EXECUTOR] Phase sequence halted at Phase 6
  2/9 phases succeeded
  ```
- **Fix:** Detailed phase logging + alerts when halt_required is triggered

### Layer 3: Dashboard Resilience (Hard Failure)
- **What:** Dashboard shows blank instead of stale data
- **Impact:** Operators blind during API outages
- **Fix:** Return stale data with `_stale_cache=True` flag (IMPLEMENTED in this session)

### Layer 4: Loader Retry Logic (Incomplete Retries)
- **What:** Phase 1 retries incomplete loaders but doesn't wait long enough
- **Impact:** Loaders still running asynchronously but next phase proceeds anyway
- **Evidence:** `RETRY_MONITOR_TIMEOUT_SECONDS = 45` (may be too short for 40+ min loader)
- **Fix:** Increase monitor timeout OR make Phase 2-9 skip if Phase 1 incomplete

---

## Known Recurring Issues (From Memory)

**Session 135:** Circuit-breaker data 32h stale, /api/algo/markets unavailable  
→ Root: Phase 1 price loading failed, EOD metrics never ran

**Session 134:** BACKFILL_DAYS default 365 caused full-year refetch  
→ Each loader run re-upserted 1.88M rows (performance disaster)

**Session 133:** AAII sentiment fabricated (not real data)  
→ Its deletion broke dashboard because caller didn't handle missing data

**Session 132:** Price-loader fail → orchestrator dead since Jul 9  
→ Cascaded to all panels blank

**Session 131:** Phase 1 halted every run (missing algo_config rows)  
→ Blocked all downstream phases

**Pattern:** Phase 1 → Phase 2+ dependency chain means ONE failure = everything fails

---

## Solution Stack

### Immediate (Session 136)
✅ **Done:** Added stale cache fallback to api_data_layer.py
- Dashboard shows `[STALE] data...` instead of blank
- Panels render stale data with explicit timestamp warnings

✅ **Done:** Created `scripts/dashboard_health_monitor.py`
- Detects data staleness, orchestrator failures, API errors
- Can be run as cron job with alert mode

### Short-Term
- [ ] Deploy health_monitor as hourly cron job with Slack alerts
- [ ] Add timestamp field to all dashboard data responses
- [ ] Dashboard panels show `[STALE NN h old]` warning when `_stale_cache=True`

### Medium-Term
- [ ] Fix Phase 1 loader retry logic (increase monitor timeout or check completeness)
- [ ] Add detailed Phase failure logs accessible to monitoring
- [ ] Create `/api/algo/orchestrator-status` endpoint with phase details
- [ ] Implement circuit-breaker auto-recovery logic

### Long-Term
- [ ] Migrate to event-driven architecture (trigger on data arrival, not schedule)
- [ ] Add real-time data freshness tracking (per symbol, per metric)
- [ ] Implement orchestrator state machine (can't proceed if Phase N incomplete)

---

## Implementation Guide

### For Operators: Immediate Recovery (Today)

```bash
# 1. Check data freshness
python scripts/dashboard_health_monitor.py

# 2. If data >24h old, run orchestrator manually
python3 scripts/run_local_orchestrator.py --morning

# 3. If phases still halt, check Phase 1 loader logs
# (Logs not yet accessible via API - need to add endpoint)

# 4. Dashboard should now show data with [STALE] warnings if >30m old
```

### For Developers: Prevent Recurrence

```bash
# 1. Add to crontab (production)
0 * * * * cd /path/to/algo && python scripts/dashboard_health_monitor.py --alert

# 2. Monitor orchestrator phases per the "Medium-Term" solutions
```

---

## Verification Checklist

- [ ] Dashboard shows `[STALE Xh old]` warning instead of blank when data >30m old
- [ ] Health monitor runs without errors: `python scripts/dashboard_health_monitor.py`
- [ ] Health monitor detects 30h stale data as CRITICAL
- [ ] Health monitor detects orchestrator not run in 24h as CRITICAL
- [ ] Orchestrator Phase 1 completes (check if prices/market_exposure updated)
- [ ] Next scheduled orchestrator run (4:05 PM ET) succeeds (verify in production)

---

## Why This Keeps Happening

1. **No feedback loop:** Data goes stale → Dashboard breaks → User notices → Operator manually fixes
2. **Phase dependencies:** 1 phase fails → everything downstream fails → ALL panels blank
3. **No graceful degradation:** "Data not available" instead of "Data is 30m old"
4. **Async retry mismatch:** Phase 1 fires async loader retries but doesn't wait for completion
5. **Missing observability:** Orchestrator "success" flag doesn't match phase-level reality

---

## References

- `DASHBOARD_STALENESS_FIX.md` - Detailed technical fix strategy
- `dashboard_health_monitor.py` - Monitoring script created this session
- `dashboard/api_data_layer.py` - Stale cache fallback implementation
- Memory files: session_135_alpaca_sip_verified.md, session_134_loading_architecture_overhaul.md
