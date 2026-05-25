# Action Plan - Complete System Deployment May 24, 2026

## COMPLETED FIXES ✅

### 1. API Lambda Cold-Start Timeout
- **Issue:** 500 errors on initial requests due to VPC cold-start delays
- **Fix:** Increased `api_lambda_timeout` from 120s to 300s in terraform.tfvars
- **Commit:** `1bf4cec4c`
- **Result:** Now allows 15-20s VPC setup + DNS + DB connection + request processing

### 2. Diagnostic Tools
- **Created:** `scripts/diagnose_deployment.py`
- **Purpose:** Comprehensive health check for all system components
- **Commit:** `48d02fc09`
- **Usage:** `python3 scripts/diagnose_deployment.py` (requires AWS DB access)

### 3. System Documentation
- **Created:** `SYSTEM_AUDIT_MAY24.md`
- **Contents:** Complete system state analysis, issues, and critical path to production

---

## REMAINING CRITICAL ISSUES & FIXES NEEDED

### Issue 1: Loaders Not Populating Data
**Symptom:** `price_daily`, `technical_data_daily`, `stock_scores`, etc. are empty or stale
**Status:** Requires AWS access to verify - cannot check locally
**What Needs to Happen:**
1. Deploy Terraform to apply API Lambda timeout fix
2. Verify EventBridge rules are active (console: CloudWatch → Events)
3. Check ECS task logs in CloudWatch: `/ecs/algo-cluster`
4. Manually trigger a loader test:
   ```bash
   aws ecs run-task --cluster algo-cluster \
     --task-definition algo-stock-prices-daily-loader \
     --launch-type FARGATE \
     --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx]}"
   ```
5. Monitor CloudWatch logs for loader output

### Issue 2: Verify Database Connectivity from Lambdas
**Symptom:** API Lambda may still fail due to VPC networking or Secrets Manager
**Status:** Timeout fix applied; next is to test
**What Needs to Happen:**
1. Test API health endpoint: `curl https://<API_ENDPOINT>/health`
2. If 200 OK: Lambda is working
3. If still 500: Check logs in `/aws/lambda/algo-api-dev`
4. Verify Secrets Manager has correct credentials:
   ```bash
   aws secretsmanager get-secret-value --secret-id algo-db-credentials-dev
   ```

### Issue 3: Orchestrator Data Freshness Gates
**Symptom:** Orchestrator Phase 1 fails due to stale/missing data
**Status:** Dependent on loaders being fixed first
**What Needs to Happen:**
1. Wait for loaders to populate at least 1 day of recent data
2. Run orchestrator test: `python3 algo/algo_orchestrator.py`
3. If Phase 1 passes: continue to debug other phases
4. Check orchestrator logs: `/aws/lambda/algo-algo-dev`

### Issue 4: Frontend Displays No Data
**Symptom:** Pages load but show empty tables/no results
**Status:** Dependent on API Lambda + loaders being fixed
**What Needs to Happen:**
1. Open browser DevTools → Network tab
2. Check if API requests return 200 with data
3. If 500 or empty: Fix API Lambda + loaders first
4. If returning data but not displaying: Check browser console for JS errors

---

## CRITICAL PATH TO FULL OPERATIONAL SYSTEM

```
Step 1: Deploy Terraform Fix (5 min)
  └─ terraform apply → increases API Lambda timeout

Step 2: Verify API Lambda (10 min)
  └─ Test /health endpoint
  └─ Check CloudWatch logs if fails

Step 3: Verify Loaders (varies: 10-60 min depending on data sources)
  └─ Check EventBridge rules are active
  └─ Manually trigger one loader
  └─ Monitor CloudWatch logs
  └─ Verify data appears in database

Step 4: Verify Orchestrator (10-30 min)
  └─ Run orchestrator test
  └─ Debug any phase failures
  └─ Verify trading signals generated

Step 5: Test Full Trading Pipeline (5-15 min)
  └─ Verify frontend displays data
  └─ Check Alpaca order execution
  └─ Monitor live trading

Step 6: Go Live (5 min)
  └─ Confirm ORCHESTRATOR_DRY_RUN=false (already set)
  └─ Confirm ALPACA_PAPER_TRADING=false (already set)
  └─ Start daily orchestrator schedule
```

---

## SYSTEM CONFIGURATION CHECKLIST

### ✅ Already Correct
- **Orchestrator mode:** `orchestrator_dry_run = false` (live trading enabled)
- **Alpaca mode:** `alpaca_paper_trading = false` (live API enabled)
- **API endpoint:** `https://api.alpaca.markets` (live API)
- **Frontend deployment:** CloudFront active at `https://d2u93283nn45h2.cloudfront.net`
- **Database schema:** 138 tables initialized via Terraform

### ⚠️ Verify in AWS
- **API Lambda timeout:** Set to 300s (fixed in this deploy)
- **EventBridge rules:** Active and triggering ECS loaders at scheduled times
- **ECS tasks:** Running successfully with no failures
- **RDS:** Database accessible from Lambda via Secrets Manager
- **Secrets Manager:** `algo-db-credentials-dev` contains correct password

---

## DATA FRESHNESS REQUIREMENTS

| Table | Fresh | Stale | Critical | Notes |
|-------|-------|-------|----------|-------|
| price_daily | < 1 day | > 7 days | > 14 days | Market OHLCV data; foundation |
| technical_data_daily | < 1 day | > 7 days | > 14 days | RSI, MACD, SMA; orchestrator gate |
| buy_sell_daily | < 1 day | > 7 days | > 14 days | Trading signals; orchestrator Phase 5 |
| stock_scores | < 7 days | > 30 days | > 60 days | Composite scores; Phase 5 ranking |
| market_health_daily | < 1 day | > 3 days | > 7 days | Market regime; Phase 2 gate |
| swing_trader_scores | < 1 day | > 7 days | > 14 days | Final portfolio scoring |

---

## TROUBLESHOOTING GUIDE

### "API Lambda returns 500"
1. Check timeout in terraform.tfvars: `api_lambda_timeout = 300` ✓
2. Deploy: `terraform apply`
3. Wait 2 min for new Lambda to boot
4. Test health: `curl https://<endpoint>/health`
5. If still fails, check logs: `aws logs tail /aws/lambda/algo-api-dev`

### "Frontend shows no data"
1. Open DevTools → Network tab
2. Reload page and check API calls
3. If 500: Fix API Lambda (see above)
4. If 200 but empty: Check if loaders have populated database
4. Use diagnostic script: `python3 scripts/diagnose_deployment.py`

### "Orchestrator Phase 1 fails"
1. Check data freshness: `scripts/diagnose_deployment.py`
2. If tables empty: Loaders haven't run
3. Check EventBridge: AWS Console → CloudWatch → Events → Rules
4. Check ECS: AWS Console → ECS → Clusters → algo-cluster → Tasks
5. Check logs: `aws logs tail /ecs/algo-cluster --follow`

### "Loaders not running"
1. Check EventBridge rules: `aws events list-rules --name-prefix algo`
2. Check if they're enabled: `aws events describe-rule --name <rule-name>`
3. Check ECS cluster: `aws ecs list-tasks --cluster algo-cluster`
4. Manually trigger test: See "Verify Loaders" section above
5. Check security groups allow outbound 443 (HTTPS) to data sources

---

## ADDITIONAL RESOURCES

### Code to Review
- **API Lambda:** `lambda/api/lambda_function.py` (database connection logic)
- **Loaders:** `loaders/load*.py` (24 data source integrations)
- **Orchestrator:** `algo/algo_orchestrator.py` (7-phase trading engine)
- **Frontend:** `webapp/frontend/src/pages/` (dashboard pages)

### Configuration Files
- **Terraform:** `terraform/terraform.tfvars` (infrastructure config)
- **Steering:** `steering/algo.md` (resource names, API endpoints)
- **Routes:** `lambda/api/routes/` (18 API endpoint handlers)

### Monitoring
- **CloudWatch:** https://console.aws.amazon.com/cloudwatch
- **Lambda:** `/aws/lambda/algo-api-dev`, `/aws/lambda/algo-algo-dev`
- **ECS:** `/ecs/algo-cluster`
- **GitHub Actions:** https://github.com/argie33/algo/actions

---

## NEXT COMMITS NEEDED

After this deploy is tested and working:

1. **Loader Verification** - Confirm data flow and commit any loader fixes
2. **Orchestrator Testing** - Debug phases and commit any orchestrator fixes
3. **Frontend Testing** - Verify data display and commit any UI fixes
4. **Go-Live Checklist** - Final verification before live trading

---

## ESTIMATED TIME TO PRODUCTION

- **Minimum (if everything works):** 30 minutes
- **Likely (fixing one component):** 1-2 hours
- **Conservative (debugging data flow):** 2-4 hours

---

## KEY CONTACTS & RESOURCES
- **Repository:** https://github.com/argie33/algo
- **AWS Account:** algo-dev (us-east-1)
- **Deployment Guide:** `DEPLOY_CHECKLIST.md`
- **Live Trading Guide:** `LIVE_TRADING_CHECKLIST.md`
