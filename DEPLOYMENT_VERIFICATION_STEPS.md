# Deployment Verification Steps

**Timeline:** May 15, 2026 - Production Deployment

## Phase 1: Monitor CI/Deployment (Current - ~30-45 min)

**Watch GitHub Actions:**
- URL: https://github.com/argie33/algo/actions
- Workflow: `deploy-all-infrastructure.yml`

**Expected Progress:**
1. **CI Tests** (5-10 min)
   - lint-and-type job
   - unit-tests job  
   - edge-case-tests job
   - integration-tests job (marked with --run-db)
   - backtest-regression job
   - ✅ All should PASS

2. **Terraform Deployment** (10-15 min)
   - Apply RDS instance
   - Create Lambda functions
   - Setup API Gateway
   - Deploy CloudFront
   - Configure EventBridge scheduler

3. **System Initialization** (5-10 min)
   - Database schema creation
   - Index creation
   - Initial data structures

## Phase 2: Verify System Health (After deployment)

**Run verification script:**
```bash
python3 verify_deployment.py
```

**This will check:**
✅ API health endpoint responding
✅ Database connected and initialized
✅ Schema has correct tables
✅ Critical tables exist
✅ Data can be inserted
✅ Calculation columns in place

## Phase 3: Monitor Data Loading (4:05pm ET)

**EventBridge triggers data pipeline:**
- 4:05pm ET = 20:05 UTC (daily Mon-Fri)
- Wait 2-3 minutes for loaders to complete

**Check data loaded:**
```sql
-- Quick check in RDS
SELECT COUNT(*) FROM price_daily WHERE created_at > NOW() - INTERVAL '24 hours';
SELECT COUNT(*) FROM market_exposure_daily WHERE date = CURRENT_DATE;
SELECT COUNT(*) FROM algo_risk_daily WHERE report_date = CURRENT_DATE;
```

## Phase 4: Verify Calculations Working

**Check market exposure:**
```sql
-- Should see data with proper columns
SELECT * FROM market_exposure_daily 
WHERE date = CURRENT_DATE 
LIMIT 1;

-- Verify columns:
-- market_exposure_pct, long_exposure_pct, short_exposure_pct, 
-- exposure_tier, is_entry_allowed
```

**Check VaR calculations:**
```sql
-- Should see risk metrics
SELECT * FROM algo_risk_daily 
WHERE report_date = CURRENT_DATE 
LIMIT 1;

-- Verify columns:
-- var_pct_95, cvar_pct_95, portfolio_beta, stressed_var_pct
```

## Phase 5: Test API Endpoints

**Health check:**
```bash
curl https://kx4kprv8ph.execute-api.us-east-1.amazonaws.com/health
```

**Test endpoints (once data loaded):**
```bash
curl https://kx4kprv8ph.execute-api.us-east-1.amazonaws.com/api/markets
curl https://kx4kprv8ph.execute-api.us-east-1.amazonaws.com/api/signals
```

## Phase 6: Monitor Logs

**CloudWatch logs to check:**
1. `/aws/lambda/algo-algo-dev` - Orchestrator execution
2. `/aws/lambda/algo-api-dev` - API requests
3. `/ecs/*` - Data loader execution

**Look for:**
✅ No ERROR entries
✅ Successful data persists
✅ Calculations complete
❌ No NameError or AttributeError

## Success Criteria

✅ **Deployment successful when:**
- CI tests all pass
- Terraform infrastructure deployed
- Database schema initialized
- API health check responds 200
- Data loaders executed at 4:05pm
- market_exposure_daily has fresh data
- algo_risk_daily has fresh VaR calculations
- No errors in CloudWatch logs

❌ **Rollback if:**
- CI tests fail (indicates code issue)
- API returns 500 (indicates Lambda issue)
- Database connection fails (indicates RDS issue)
- Data doesn't load (indicates loader issue)

## Timeline

| Time | Action | Status |
|------|--------|--------|
| 15:30 | Deployment triggered | 🚀 IN PROGRESS |
| 15:35-15:50 | CI tests running | ⏳ WATCH |
| 15:50-16:05 | Terraform deploying | ⏳ WATCH |
| 16:05 | System live | ✅ VERIFY |
| 16:10 | Run verification script | ⏳ TODO |
| 16:05-16:10 (ET) | Wait for next data load | ⏳ TONIGHT |
| 20:05 UTC (4:05pm ET) | EventBridge triggers loaders | ⏳ TONIGHT |
| 20:10 UTC | Verify data loaded | ⏳ TONIGHT |

## Rollback Plan

If any phase fails:

1. Check GitHub Actions for error messages
2. Review CloudWatch logs for specific errors
3. Identify the failing component
4. Create targeted fix commit
5. Push to trigger redeployment
6. Repeat from Phase 1

## Success Outcomes

Once all phases complete:
1. Trading system operational in AWS
2. Data loading automatically every market day
3. Market exposure calculations persisting
4. VaR/risk metrics saved correctly
5. API accessible for external integration
6. Orchestrator ready for execution

**Status:** 🚀 LIVE
