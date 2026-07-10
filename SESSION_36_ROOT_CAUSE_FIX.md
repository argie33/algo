# Session 36: Dashboard Data Availability - Root Cause & Fix

**Status:** IN PROGRESS - Root causes identified, critical fixes applied

**Issue:** Dashboard showing "data not available" across all panels

---

## Root Causes Identified

### 1. CRITICAL: Data Loaders Stuck & Not Running (PRIMARY BLOCKER)

**Impact:** Dashboard shows "data not available" because data isn't being loaded

**Details:**
- 75 total data loaders registered in `data_loader_status` table
- ALL showing status "ERR" (error state)  
- 12 loaders stuck with "Reset after being stuck > 4 hours" error
- Most data is 2-19 days stale
- Critical market data (fear_greed_index, market_sentiment, sentiment) missing or very stale

**Example Stale Data:**
```
fear_greed_index:      Latest 2026-05-23 (10 days old)
market_sentiment:      No data loaded  
market_health_daily:   No data loaded
sentiment:             19 days stale
stock_scores:          2026-07-08 (2 days old)
```

**Root Cause:** 
- Loaders are supposed to be scheduled via EventBridge (AWS), but scheduling isn't properly configured
- Individual loaders are getting stuck due to data dependencies or timeout issues
- No recovery mechanism to restart stuck loaders

---

### 2. Schema Bug: market_sentiment Loader Column Name Mismatch

**Impact:** Market sentiment loader crashes immediately when run

**Bug:**
- Loader tries to insert into `data_unavailable_reason` column
- Table actually has column named `reason` (not `data_unavailable_reason`)
- Causes: `UndefinedColumn` error, loader fails

**Error:**
```
column "data_unavailable_reason" of relation "market_sentiment" does not exist
```

**Files Affected:**
- `loaders/load_market_sentiment.py` - lines 41-66 and 77-101

---

### 3. Data Dependency Chain Broken

**Impact:** Market health and sentiment data can't be computed

**Chain:**
1. Breadth data (from `trend_template_data`) → used by market_health_daily
2. Market health (VIX + breadth) → used by market_sentiment  
3. Market sentiment → displayed in dashboard

**Problem:**
- `trend_template_data` hasn't been loaded in 19+ days
- Without breadth data, market_health_daily loader refuses to run (correct fail-fast behavior per GOVERNANCE.md)
- Without market health data, market_sentiment loader can't compute VIX-based fear/greed index
- Result: All dependent data unavailable

---

## Fixes Applied

### Fix #1: market_sentiment Loader Column Name ✓ COMPLETE

**File:** `loaders/load_market_sentiment.py`

**Change:** Replace column name in both INSERT statements:
- FROM: `data_unavailable_reason` 
- TO: `reason`

**Lines Fixed:**
- Line 45: INSERT column list
- Line 49: ON CONFLICT UPDATE clause
- Line 78: Second INSERT column list
- Line 84: Second ON CONFLICT UPDATE clause

**Commit:** `92ef52ee2` - "Fix: market_sentiment loader - use correct column name 'reason' instead of 'data_unavailable_reason'"

**Verification:**
```bash
python3 loaders/load_market_sentiment.py
# Output: Market sentiment marked data_unavailable for 2026-07-10: vix_data_missing
# Status: SUCCESS - Loader runs without errors (VIX missing is expected for today)
```

---

### Fix #2: Load Critical Data Script ✓ IN PROGRESS

**Script:** `scripts/load_critical_data.py`

**Purpose:** Load minimum data needed for dashboard to display

**Data Being Loaded:**
1. Price data (SPY, QQQ, etc.)
2. Market health indicators
3. Stock scores
4. Technical data
5. Market sentiment

**Status:** Running - will populate database with essential data for dashboard display

---

## System Architecture Issues (Not Yet Fixed)

### Issue #1: Loader Scheduling Not Working

**Problem:** Loaders should run via EventBridge (AWS Lambda scheduled tasks), but they're not being triggered

**Evidence:**
- Terraform has scheduler configuration in `terraform/modules/services/2x-daily-orchestrator.tf`
- But loaders aren't running on schedule
- Manual runs work, but no automation

**Required Fix:**
- Verify EventBridge rules are created in AWS
- Verify Lambda trigger permissions are correct
- Check CloudWatch logs for failed executions

### Issue #2: Loader Stuck Detection & Recovery

**Problem:** Stuck loaders aren't automatically recovered

**Evidence:**
- 12 loaders showing "Reset after being stuck > 4 hours"
- No automatic restart mechanism
- Manual intervention required

**Required Fix:**
- Implement timeout/watchdog for long-running loaders
- Add automatic retry logic with exponential backoff
- Alert ops when loaders get stuck

### Issue #3: GitHub Actions Deployment Not Triggering Loaders

**Problem:** GitHub Actions workflows (deploy-*.yml) don't trigger data loads after deployment

**Solution:** May need to add loader trigger step to post-deployment workflows

---

## Data Pipeline Dependencies

```
Orchestrator (runs 2x daily via EventBridge)
  └─ Phase 1-9: Trading logic, position management
      └─ Uses: portfolio snapshots, technical data, stock scores
  
Market Data (needs separate loaders):
  ├─ Price Data (load_prices.py) → price_daily table
  │   └─ Used by: orchestrator for position evaluation
  │
  ├─ Breadth Data (trend_template_data) → market_health_daily  
  │   └─ Critical for market exposure scoring
  │
  └─ Market Health (load_market_health_daily.py) → market_health_daily
      ├─ Provides: VIX, put/call ratio, breadth, distribution days
      └─ Used by: market_sentiment loader & dashboard

Sentiment Data (load_market_sentiment.py) → market_sentiment
  └─ Depends on: market_health_daily (VIX data)
  └─ Used by: Dashboard sentiment panel
```

---

## Immediate Actions Needed

1. **Let critical data loader finish** - `load_critical_data.py` currently loading prices/market/scores
2. **Verify dashboard shows data** - After loader completes, test React dashboard
3. **Schedule future loader runs** - Enable EventBridge or implement alternative scheduling
4. **Monitor loader health** - Add logging/alerts for stuck loaders
5. **Fix IaC deployment** - Ensure GitHub Actions can trigger loaders post-deploy

---

## Long-term Fixes Required

1. Implement loader orchestration (instead of relying on stuck EventBridge)
2. Add automated recovery for hung loaders
3. Better error handling for data dependency chains
4. Dashboard UX: Show which specific data sources are unavailable and why
5. Documentation: Publish loader dependency graph and troubleshooting guide

---

## Testing Checklist

- [ ] `load_critical_data.py` completes successfully
- [ ] Dashboard React app at :5173 displays data (no "data not available" messages)
- [ ] API endpoints return data: `/api/algo/markets`, `/api/market/sentiment`, etc.
- [ ] Orchestrator continues to run successfully (dry-run mode)
- [ ] Price data is current in database
- [ ] Market health data is current in database
- [ ] Market sentiment data is populated and current
- [ ] Loaders can be manually triggered and succeed

---

## Files Modified

1. `loaders/load_market_sentiment.py` - Fixed column names
2. `SESSION_36_ROOT_CAUSE_FIX.md` - This document

## Commits

- `92ef52ee2` - Fix: market_sentiment loader column name

---

## Next Session

Focus on:
1. Complete critical data load
2. Verify dashboard displays correctly
3. Fix EventBridge/loader scheduling
4. Full end-to-end test (orchestrator + dashboard + loaders all working together)
