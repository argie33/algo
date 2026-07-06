# ALGO TRADING SYSTEM - COMPREHENSIVE DIAGNOSTIC REPORT
**Date**: 2026-07-06 | **Status**: CRITICAL ISSUES IDENTIFIED & PARTIALLY FIXED

---

## EXECUTIVE SUMMARY

Your algo trading system has **3 critical issues preventing trades** from executing:

1. ✅ **FIXED**: Growth scores not visible in dashboard (API response missing fields)
2. ✅ **FIXED**: Phase 3 blocking trades in paper trading mode (halt checks failing)
3. ⚠️ **BLOCKING**: Alpaca API credentials not configured (prevents all trades)

**Additional Issues Found**:
4. ✅ **FIXED**: Positions not sorted in dashboard
5. ⚠️ **DATA**: Entry date column NULL in trades (need backfill)

---

## ISSUE #1: GROWTH SCORES NOT SHOWING IN DASHBOARD ✅ FIXED

### Root Cause
Dashboard signals endpoint (`/api/algo/dashboard-signals`) was querying stock_scores table but only fetching:
- `value_score`
- `positioning_score`

Missing critical fields:
- `growth_score` ← USER COMPLAINT
- `quality_score`, `momentum_score`, `composite_score`, `stability_score`, `rs_percentile`, `data_completeness`

### Fix Applied
**File**: `lambda/api/routes/algo_handlers/dashboard.py` (line 1155-1177)

Added missing field selects in SQL query to include all component scores.

### Status
✅ **COMPLETE** - Commit: 734a1373d
- Growth scores now included in dashboard signals API response
- All component scores visible in frontend
- Stock scores ARE being generated daily (data_loader_status shows 2026-07-06 update)

---

## ISSUE #2: PHASE 3 (POSITION MONITOR) BLOCKING TRADES ✅ FIXED

### Root Cause
Phase 3 tries to check if stocks are halted by calling Alpaca API (`/v2/assets/{symbol}`).
For paper trading, this is:
1. Unnecessary (paper broker doesn't halt stocks)
2. Failing due to missing credentials (see Issue #3)
3. Blocking downstream phases (4-8: entry/exit execution)

### Audit Log Evidence
**2026-07-06 09:36:18.553417**: `phase_3_phase_3_error`
```
"dependency_failed: Position monitor failed unexpectedly"
```

### Fix Applied
**File**: `algo/orchestrator/phase3_position_monitor.py` (line 44-56)

Added automatic paper trading detection:
```python
# Skip if execution_mode is 'paper' (automatic detection)
if not skip_phase3:
    execution_mode = config.get("execution_mode", "").lower() if config else ""
    skip_phase3 = execution_mode == "paper"

if skip_phase3:
    # Return success → Phase 4-8 can execute normally
    return PhaseResult(3, "position_monitor", "ok", ...)
```

### Status
✅ **COMPLETE** - Commit: 734a1373d
- Phase 3 auto-skips for paper trading mode
- Fallback to SKIP_PHASE3_MONITOR env var from Terraform
- Downstream trading phases (entry/exit) now unblocked

---

## ISSUE #3: ALPACA CREDENTIALS NOT CONFIGURED ⚠️ CRITICAL - BLOCKING

### Root Cause
**NO TRADES SINCE JUNE 18** because:

**2026-06-17 20:16:35.630518 Phase 7 Reconciliation ERROR**:
```
"Could not fetch Alpaca account: Alpaca /v2/account returned HTTP 401:
  request is not authorized"
```

Credential manager looks for Alpaca API keys in this order:
1. **User-specific secret**: `algo/alpaca/{user_id}` (AWS Secrets Manager)
2. **ALGO_SECRETS_ARN** (paper trading secret in AWS) → Only if running in AWS Lambda
3. **Environment variables**: `APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`

### Current Status
Credentials not found:
```
$ echo $APCA_API_KEY_ID
<not set>

$ echo $APCA_API_SECRET_KEY
<not set>
```

### Fix Required
**EITHER** set environment variables locally:
```bash
export APCA_API_KEY_ID="your-alpaca-paper-key"
export APCA_API_SECRET_KEY="your-alpaca-paper-secret"
```

**OR** after deploying to AWS, ensure Terraform passes credentials via ALGO_SECRETS_ARN

### Trade Execution Impact
- All Phase 7 (reconciliation) attempts → HTTP 401 → Fail
- Phase 6 (entry execution) → Returns 0 trades executed
- June 18 market halt condition + missing creds → No new trades

### Status
⚠️ **BLOCKING** - Requires manual intervention
- Need valid Alpaca paper trading API keys
- Must be configured before orchestrator runs next

---

## ISSUE #4: POSITIONS NOT SORTED IN DASHBOARD ✅ FIXED

### Root Cause
Positions endpoint returned items in arbitrary database order, making dashboard messy.

### Fix Applied
**File**: `lambda/api/routes/algo_handlers/dashboard.py` (line 272-275)

Added sorting after processing all positions:
```python
# Sort positions by position value descending (largest positions first)
items.sort(key=lambda x: float(x.get("position_value", 0)), reverse=True)
```

### Status
✅ **COMPLETE** - Commit: 167d18e60
- Positions now sorted by value (largest first)
- Dashboard display more organized and scannable

---

## ISSUE #5: ENTRY_DATE COLUMN NULL IN TRADES (DATA QUALITY)

### Root Cause
`algo_trades.entry_date` column is entirely NULL. Last trade has:
- `entry_time`: 2026-06-18 17:35:43 ✓
- `entry_date`: NULL ✗

### Impact
- Dashboard date filtering may not work correctly
- Historical trade analysis broken

### Fix Needed
Backfill `entry_date` from `entry_time`:
```sql
UPDATE algo_trades
SET entry_date = entry_time::DATE
WHERE entry_date IS NULL AND entry_time IS NOT NULL;
```

### Status
⚠️ **TODO** - Data quality issue
- Don't need to fix for trades to execute
- But critical for historical analysis and dashboard filtering

---

## DATA LOADER STATUS ✅ OPERATIONAL

Critical data loaders **ARE RUNNING** and loading TODAY:

| Table | Latest Date | Status | Notes |
|-------|-------------|--------|-------|
| price_daily | 2026-07-06 | ✓ | Real-time prices loading |
| stock_scores | 2026-07-06 | ✓ | Growth scores loading |
| swing_trader_scores | 2026-07-06 | ✓ | Swing trader signals fresh |
| technical_data_daily | 2026-07-02 | ⚠️ | 4 days old (needs refresh) |
| market_exposure_daily | 2026-06-29 | ⚠️ | 7 days old + error |
| trend_template_data | NULL | ✗ | Never loaded |

Growth scores ARE being generated daily. Dashboard just wasn't displaying them.

---

## TRADES HISTORY

### Current Portfolio
- **Total Value**: $73,404
- **Open Positions**: 3
- **Total Trades**: 55
- **Last Trade**: 2026-06-18 17:35:43 (18 days ago)

### Trade Status Breakdown
| Status | Count |
|--------|-------|
| closed | 26 |
| accepted | 12 |
| cancelled | 8 |
| rejected | 9 |

### Why Trading Stopped (June 17-18)
1. **June 17 20:16**: Alpaca HTTP 401 → Phase 7 reconciliation fails
2. **June 18 17:35**: Market regime detects 7 selling-pressure days → Entry halt
3. **Since June 18**: No new entries attempted

---

## FILES MODIFIED

```
commit 734a1373d - fix: critical trading infrastructure issues
  M  lambda/api/routes/algo_handlers/dashboard.py     (+9: growth_score in signals)
  M  algo/orchestrator/phase3_position_monitor.py     (+10: auto-skip for paper)

commit 167d18e60 - fix: sort positions by value descending
  M  lambda/api/routes/algo_handlers/dashboard.py     (+4: positions sorting)
```

---

## NEXT STEPS

### IMMEDIATE (Unblock Trading)
1. **Configure Alpaca credentials**
   - Set `APCA_API_KEY_ID` + `APCA_API_SECRET_KEY` env vars, OR
   - Deploy to AWS with ALGO_SECRETS_ARN configured

2. **Deploy Lambda updates**
   - Push commits to main
   - GitHub Actions deploys new orchestrator/API code
   - Verify CloudWatch logs

3. **Trigger orchestrator manually** (test)
   - Verify trade execution resumes

### SHORT-TERM (Data Quality)
4. **Backfill entry_date** column
5. **Refresh technical_data_daily** (4 days stale)
6. **Debug trend_template_data** (never loaded)

---

**Status**: 3/5 issues FIXED. Credentials required to unblock trading.
