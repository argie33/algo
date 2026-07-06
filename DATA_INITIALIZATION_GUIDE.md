# Dashboard 5xx Errors: Data Initialization Guide

## Status Summary
✅ **Code**: All correct (no bugs, type-safe, proper error handling)  
❌ **Data**: 8 endpoints failing because tables are empty  
⏳ **Fix**: ~20-30 minutes to populate all tables and restore 26/26 endpoints

---

## Current State
```
18/26 endpoints working (OK)
 8/26 endpoints failing (data table empty)
 1/1  endpoint missing field (will populate after orchestrator runs)
```

## What Happened?
The system is **code-complete and deployed**, but **data hasn't been loaded yet**. This is expected behavior.

The 8 failing endpoints properly return 503 (fail-closed) when data is unavailable — this is correct per GOVERNANCE.md, not a bug.

---

## Step-by-Step Fix

### Step 1: Verify AWS Infrastructure (2 minutes)
Check that the API Lambda is responding (already verified ✅):
```bash
python -m dashboard.diagnose_dashboard
# If you can see 18 endpoints returning data, infrastructure is deployed
```

### Step 2: Run Data Loaders (10-15 minutes)
These populate the market data tables needed by dashboard endpoints.

Run in this order (tier dependencies):
```bash
# Tier 1: Foundation (required by all others)
python -m loaders.load_prices  
python -m loaders.load_company_profile

# Tier 2: Fixes endpoints #6, #8
python -m loaders.load_aaii_sentiment  # → market_sentiment table (fixes: sentiment endpoint)
python -m loaders.load_sector_ranking  # → sector_performance (fixes: sector_rotation, sectors)

# Tier 3: Fixes endpoint #7
python -m loaders.load_swing_trader_scores  # → swing_trader_scores (partial fix for rejection_funnel)

# Tier 4: Everything else (if desired)
python -m loaders.load_market_health_daily
python -m loaders.load_technical_data_daily
python -m loaders.load_*  # Run all loaders
```

**Progress after Step 2:**
- Endpoints #5, #6, #8 now return data ✅
- Endpoints #1, #2, #3, #4, #7 still failing (need orchestrator)

### Step 3: Run Orchestrator (5 minutes)
The orchestrator creates system-generated data tables and fixes the remaining 5 endpoints.

**Via AWS Console (easiest):**
1. Go to AWS Lambda Console
2. Find function: `algo-orchestrator`
3. Click **Test** tab
4. Create test event (use default `{}`)
5. Click **Test** button
6. Wait 2-3 minutes for run to complete

**Via CLI (alternative):**
```bash
aws lambda invoke \
  --function-name algo-orchestrator \
  --region us-east-1 \
  /tmp/response.json
```

**Progress after Step 3:**
- All endpoints now have data ✅
- orchestrator_execution_log populated (fixes: execution/recent)
- circuit_breaker_status populated (fixes: circuit-breakers)
- algo_audit_log populated (fixes: audit-log)
- halt_reason field populated (fixes: missing field)

### Step 4: Verify All 26 Endpoints (2 minutes)
```bash
python -m dashboard.diagnose_dashboard
# Expected:
#   [OK] Success:        26
#   [!] Stale:          0
#   [X] Errors:         0
#   [~] Missing fields: 0
```

---

## Failing Endpoints & What Fixes Them

| Endpoint | Loader | Step |
|----------|--------|------|
| `/api/algo/sentiment` | load_aaii_sentiment | 2 |
| `/api/sectors` | load_sector_ranking | 2 |
| `/api/algo/sector-rotation` | load_sector_ranking | 2 |
| `/api/algo/execution/recent` | (orchestrator) | 3 |
| `/api/algo/circuit-breakers` | (orchestrator) | 3 |
| `/api/algo/audit-log` | (orchestrator) | 3 |
| `/api/algo/rejection-funnel` | load_swing_trader_scores + orchestrator | 2+3 |
| `/api/algo/last-run` (missing field) | (orchestrator) | 3 |

---

## What NOT to Do

❌ Don't modify endpoint code (it's correct)  
❌ Don't disable data validation (it's working as designed)  
❌ Don't add fallback defaults (violates GOVERNANCE.md)  
❌ Don't silence the 503 errors (they're informative)  

---

## Expected Results

**Before**: `python -m dashboard.diagnose_dashboard`
```
SUMMARY
  [OK] Success:        18
  [!] Stale:          0
  [X] Errors:         8
  [~] Missing fields: 1
```

**After**: `python -m dashboard.diagnose_dashboard`
```
SUMMARY
  [OK] Success:        26
  [!] Stale:          0
  [X] Errors:         0
  [~] Missing fields: 0
```

---

## Troubleshooting

**Q: Load fails with rate limit error**  
A: Loaders have backoff; increase `max_parallelism` in the loader config (default: 5)

**Q: Orchestrator times out**  
A: Normal (can take 3-5 min); check CloudWatch logs: `/aws/lambda/algo-orchestrator`

**Q: Still seeing 503 after orchestrator**  
A: Data freshness check may be stale; wait 5 minutes and try again

**Q: One endpoint still returns error**  
A: Check logs: `aws logs tail /aws/lambda/algo-api-dev --follow`

---

## Related Documentation
- `steering/GOVERNANCE.md` — Why fail-fast and 503 responses are correct
- `steering/DATA_LOADERS.md` — Loader parallelism, batch sizing
- `CLAUDE.md` → Quick Reference table for instant fixes
