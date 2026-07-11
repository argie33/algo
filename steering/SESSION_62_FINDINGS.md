# Session 62: Dashboard Data Issues - Root Cause Analysis & Fixes

**Date:** 2026-07-10  
**Status:** Data Quality Issues Identified - Partial Fixes Applied

## Summary

Dashboard shows "data not available" on all panels due to incomplete data for 2026-07-10. While the API and database are operational, derived data tables lack the required coverage to generate trading signals.

---

## Issues Identified

### 1. ✅ FIXED: Price Loader Intervals (Minor)
**Issue:** terraform/modules/loaders/main.tf reverted to loading 1d,1wk,1mo intervals  
**Problem:** Increases yfinance API calls >10k/hour, causing rate limiting  
**Fix Applied:** Restored daily-only (1d) optimization to prevent rate limiting  
**Severity:** LOW - optimization only, doesn't block functionality

### 2. 🔴 BLOCKED: AWS IAM Permissions (Critical - Session 61 Carryover)
**Issue:** `algo-developer` IAM user lacks permissions:
- `dynamodb:DescribeTable` on `algo-loader-config-dev`
- `cloudwatch:PutMetricData`

**Impact:**  
- Loaders can't fetch DynamoDB config (fall back to hardcoded defaults)
- Metrics collection broken
- Loader parallelism and configuration unavailable

**Status:** AWS infrastructure fix required - beyond local dev scope  
**Mitigation:** Works locally without AWS credentials (LOCAL_MODE=true)

### 3. ❌ INCOMPLETE DATA: Coverage Gap for 2026-07-10
**Issue:** Derived data tables have insufficient 2026-07-10 coverage

| Table | Date | Count | Expected | Status |
|-------|------|-------|----------|--------|
| price_daily | 2026-07-10 | 10,323 symbols | ✓ | ✅ Complete |
| technical_data_daily | 2026-07-10 | 10 symbols | 10,323 | ❌ Incomplete |
| buy_sell_daily | 2026-07-10 | 0 rows | 406+ signals | ❌ Missing |
| market_health_daily | 2026-07-10 | N/A | Fresh data | ❌ Stale (1 day old) |
| algo_signals | 2026-07-10 | 10 BUY | 406+ signals | ⚠️  Low coverage |

**Dependency Chain Impact:**
```
price_daily (10,323) ✓
  ↓
technical_data_daily (only 10/10,323) ✗
  ↓
buy_sell_daily (blocked - coverage < 73%) ✗
  ↓
dashboard.py (shows "data unavailable") ✗
```

**Root Cause:** technical_data_daily loader only processed 10 symbols instead of all 10,323

**Hypothesis:** When manually triggered, the loader may:
- Have processed only symbols with algo_signals entries
- Been interrupted before completion
- Hit a filter/limit not present in automated execution
- Encountered database/memory issue

---

## Why Dashboard Shows "Data Unavailable"

The renderers check for error responses or missing data:

```python
if has_error(ctx.mkt) or has_error(ctx.cfg):
    # Show: "Market/Config Error - Dashboard data unavailable"
```

Current data issues cause:
1. **Market panel:** market_health_daily is stale (2026-07-09)
2. **Signals panel:** buy_sell_daily for 2026-07-10 missing (buy_sell_daily < 73% threshold)
3. **Other panels:** Partial data availability cascades to failures

---

## API & Database Status

### ✅ Working
- API dev_server: Responds correctly on port 3001
- Endpoints return proper 200 responses:
  - `/api/algo/portfolio` - 200 ✓
  - `/api/algo/config` - 200 ✓
  - `/api/algo/last-run` - 200 ✓
  - `/api/market/status` - 200 ✓
- Dev token authentication: `Bearer dev-admin` works
- Database connection: Operational (localhost:5432)
- Price data: 8.6M+ prices loaded

### ✅ Orchestrator
- Recent runs successful (2026-07-10, multiple times)
- Overall status: "success" 
- No halt reasons or phase errors

### ❌ Data Generation
- technical_data_daily loader: Completes but processes only 10/10,323 symbols
- buy_sell_daily loader: Blocked by coverage check (< 73% minimum required)
- Signal generation: Only 10 signals for 2026-07-10 (vs 406 expected for 2026-07-09)

---

## Solutions

### Immediate (Local Development)
1. **Manually regenerate technical_data_daily for all symbols**
   ```bash
   # Run with INTRADAY_MODE to load only 2026-07-10
   INTRADAY_MODE=true python3 loaders/load_technical_data_daily.py
   ```
   Expected: 10,323+ rows for 2026-07-10
   
2. **Once technical data generated, trigger buy_sell_daily**
   ```bash
   python3 loaders/load_buy_sell_daily.py
   ```
   Expected: 406+ signal rows for 2026-07-10

3. **Regenerate market_health_daily**
   ```bash
   python3 loaders/load_market_health_daily.py
   ```
   Expected: Fresh health metrics for 2026-07-10

### Production (AWS)
1. **Fix IAM permissions for algo-developer user** (Session 61 blocker)
   ```terraform
   # Add to algo-developer policy
   {
     "Effect": "Allow",
     "Action": [
       "dynamodb:DescribeTable",
       "dynamodb:GetItem",
       "cloudwatch:PutMetricData"
     ],
     "Resource": [
       "arn:aws:dynamodb:us-east-1:*:table/algo-loader-config-dev",
       "arn:aws:logs:us-east-1:*:*"
     ]
   }
   ```

2. **Ensure EventBridge loaders run correctly for 2026-07-10**
   - Verify loader parallelism settings (not exceeding RDS connection pool)
   - Check DynamoDB config table has correct loader settings
   - Monitor CloudWatch logs for loader completion

3. **Redeploy Lambda with latest code**
   ```bash
   gh workflow run deploy-api-lambda.yml
   ```

---

## Data Regeneration Commands

**Full rebuild (all tables for 2026-07-10):**
```bash
# Terminal 1: Start API
python3 api-pkg/dev_server.py

# Terminal 2: Regenerate technical data
INTRADAY_MODE=true python3 loaders/load_technical_data_daily.py

# Terminal 3: Regenerate signals  
python3 loaders/load_buy_sell_daily.py

# Terminal 4: Regenerate market health
python3 loaders/load_market_health_daily.py

# Terminal 5: Run dashboard
python3 -m dashboard --local -w 30
```

---

## Testing Checklist

After applying fixes:

- [ ] `technical_data_daily` has 10,000+ rows for 2026-07-10
- [ ] `buy_sell_daily` has 400+ signals for 2026-07-10  
- [ ] `market_health_daily` has fresh data for 2026-07-10
- [ ] Dashboard renders without "data unavailable" panels
- [ ] All 4 portfolio positions display correctly
- [ ] Signals panel shows today's BUY/SELL signals
- [ ] Market health panel shows current status
- [ ] Trade history shows recent trades

---

## Related Documents

- `steering/AWS_LAMBDA_503_FIX.md` - Lambda cold start fixes
- `steering/DATA_LOADERS.md` - Loader architecture & dependencies
- `CLAUDE.md` - Quick start & common issues
- Session 61 findings: AWS IAM blocker, yfinance rate limiting

---

## Next Steps

1. **Local testing:** Apply immediate fixes above
2. **Validation:** Run dashboard and verify all panels render
3. **Production:** Coordinate with AWS to fix IAM permissions
4. **Monitoring:** Add alerts for loader coverage < 73% to prevent future failures

