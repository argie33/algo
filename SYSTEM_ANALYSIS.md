# SYSTEM ANALYSIS - 2026-07-07

## VERIFIED WORKING
- [x] Database connectivity (PostgreSQL RDS)
- [x] Stock scores computation (3957 with growth scores, others lack SEC data)
- [x] Growth metrics loaded (4064 records available)
- [x] Positions tracked (3 open positions in database)
- [x] Dashboard components exist (panels, fetchers, API routes)
- [x] API endpoint files exist
- [x] Phase 1 data freshness checks implemented
- [x] Metrics tables schema correct

## CRITICAL ISSUES TO FIX

### 1. ALPACA CREDENTIALS (BLOCKING ORCHESTRATOR)
**Problem:** Alpaca API key/secret not in environment variables
**Impact:** Paper trading cannot connect to Alpaca API
**Fix Required:**
- Verify credentials stored in AWS Secrets Manager (algo/alpaca)
- Ensure Lambda IAM can access Secrets Manager
- Verify credential manager loads them correctly
- Test Alpaca connectivity in orchestrator

### 2. DASHBOARD/API DEPLOYMENT
**Problem:** Unclear if Lambda APIs and dashboard are deployed
**Impact:** Users can't see growth scores or positions on dashboard
**Fix Required:**
- Verify API Lambda (algo-api-dev) is deployed and healthy
- Verify orchestrator Lambda (algo-orchestrator) is deployed
- Verify CloudFront/S3 dashboard is deployed
- Test API endpoints are accessible
- Check CloudWatch logs for errors

### 3. DATA FRESHNESS & METRICS PIPELINE TIMING
**Problem:** Stock scores computed before metrics loaded
**Impact:** Incomplete scores in morning runs
**Fix Required:**
- Verify EOD pipeline completes metrics load (4:05 PM - 6:00 PM)
- Verify stock_scores computed after metrics (not during morning pipeline)
- Add Phase 9 step to force stock_scores recompute if metrics stale
- Verify 9:30 AM orchestrator run uses fresh scores

### 4. GITHUB ACTIONS DEPLOYMENT
**Problem:** Unclear if all workflows properly deploy credentials
**Impact:** Production deployments may lack Alpaca credentials
**Fix Required:**
- Verify deploy-all-infrastructure.yml passes ALPACA vars
- Check if TF_VAR_alpaca_api_key_id/secret are set in CI
- Verify Terraform applies Alpaca secret to Secrets Manager
- Test full GitHub Actions workflow end-to-end

## NEXT STEPS
1. Set Alpaca credentials for local testing
2. Verify Lambda deployments are current
3. Test API endpoints
4. Run orchestrator end-to-end test
5. Verify dashboard displays data correctly
