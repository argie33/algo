# Dashboard Staleness Handling & Recovery Strategy

**Problem:** Dashboard shows "data not available" on ALL panels when data is stale (>30h old), instead of showing stale data with warnings.

**Root Causes:**
1. `api_data_layer.py` throws on stale cache (>30 min old)
2. Dashboard fetchers don't have fallback to show stale data
3. No monitoring alerts before data goes stale
4. Orchestrator phase failures prevent data updates but aren't noticed until dashboard breaks

**Solution (3-part):**

## Part 1: Make Fetchers Show Stale Data (NOT "data not available")

**Current flow:**
```
API call → stale cache (>30 min) → RuntimeError → fetcher returns `{"_error": "..."}`
→ Dashboard shows blank panel
```

**New flow:**
```
API call → stale cache (>30 min) → Return data with `_stale_cache=True` warning
→ Dashboard shows [STALE] data instead of blank
```

**Files to change:**
- `dashboard/api_data_layer.py` - `get_cached_response()` should return stale data with flag instead of raising
- `dashboard/fetchers_*.py` - Already handle `_stale_cache` flag (just needs API layer change)
- `dashboard/panels/*.py` - Already render `[STALE]` warning (no changes needed)

## Part 2: Add Alerts Before Data Goes Stale

**Script:** `scripts/dashboard_health_monitor.py` (already created)

**Integration:**
- Run as cron job every hour: `python scripts/dashboard_health_monitor.py --alert`
- Exit code 1 if unhealthy → triggers Slack/email alert
- Catches:
  - Data >24h old (critical)
  - Orchestrator hasn't run in >4 hours (warning)
  - API endpoints returning 500+ errors (warning)

**Setup:**
```bash
# Add to crontab (runs every hour)
0 * * * * cd /path/to/algo && python scripts/dashboard_health_monitor.py --alert && echo "dashboard-healthy" || echo "DASHBOARD UNHEALTHY" | slack-notify
```

## Part 3: Fix Orchestrator Failures (Phase 1 halts)

**Current issue:** Phase 1 frequently halts due to incomplete loaders.

**Diagnosis script needed:**
```bash
python scripts/diagnose_orchestrator_failures.py --recent
```

Would show:
- Which phases are halting
- Why (loader incomplete, price fetch failed, etc.)
- Which loader retry attempts failed
- How to recover

## Implementation Priority

**IMMEDIATE (fixes "data not available" showing on dashboard):**
1. Change `get_cached_response()` to return data with stale flag instead of raising
2. Test: stale data should show as "[STALE] data..." instead of blank

**SHORT-TERM (prevents data staleness from breaking dashboard):**
1. Deploy `dashboard_health_monitor.py` as hourly cron job
2. Set up Slack alerts on unhealthy status

**MEDIUM-TERM (fixes root cause):**
1. Debug why Phase 1 loaders fail
2. Add automatic Phase 1 recovery (retry on 503, handle partial completeness better)
3. Add kill-switch to let orchestrator halt gracefully if Phase 1 can't recover

---

## Technical Details: Stale Cache Handling

**Why stale data is better than "data not available":**
- Stale positions/portfolio data = position sizing is 30 min delayed (acceptable with warning)
- No data = trading halted, no position visibility, dashboard blank (unacceptable)

**Finance app requirements:**
- ✅ Show stale data with [STALE] warning
- ✅ Allow user to see position/risk status even if 30min old
- ✅ Timestamp shows when data was last updated
- ❌ DO NOT trade on stale data without explicit manual confirmation
- ❌ DO NOT silently use stale data in risk calculations

**Dashboard panels that can show stale data:**
- Portfolio (positions, PnL, exposure): Can show 30min stale
- Market data (prices, vol): Can show 30min stale with warning
- Signals (technical, sentiment): Can show 30min stale
- Risk/Exposure: Can show 30min stale
- Algo health/metrics: Can show 30min stale

**Panels that CANNOT show stale data (must blank):**
- Circuit breaker status (safety-critical, must be real-time)
- Position sync status (if stale, can't trust if positions are synced)
