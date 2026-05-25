# AWS Readiness Checklist - May 24, 2026

## ✅ LOCAL SYSTEM STATUS (VERIFIED)
```
Database:        localhost PostgreSQL (local dev)
Status:          ✓ FULLY FUNCTIONAL
Data Presence:   ✓ 8M+ price records
Data Freshness:  ✓ 2 days old (May 22)
Orchestrator:    ✓ Running (last run 19:59:59 May 24)
API Routes:      ✓ All data ready
```

## 🏗️ AWS DEPLOYMENT STATUS

### Infrastructure Deployed ✓
- RDS: algo-db.*.us-east-1.rds.amazonaws.com
- API Lambda: algo-api-dev
- Orchestrator Lambda: algo-algo-dev
- Frontend: CloudFront
- ECS Cluster: algo-cluster with loaders

### Critical Path to Verify in AWS

#### Phase 1: Database Connectivity (MUST VERIFY)
**What**: API Lambda can connect to RDS via Secrets Manager
**How**: Test `/api/health` endpoint
**Success**: Returns 200 with database status

```bash
API_ENDPOINT=$(aws apigatewayv2 get-apis --query 'Items[0].ApiEndpoint' --output text)
curl ${API_ENDPOINT}/api/health/detailed
# Expected: { "status": "healthy", "dbStatus": "connected", "tables": {...} }
```

**If fails**: Check:
- Lambda environment variables (DB_SECRET_ARN, DB_HOST, etc.)
- RDS security group allows port 5432 from Lambda
- Secrets Manager contains valid credentials
- VPC configuration (Lambda in private subnet, routing)

---

#### Phase 2: Data Flow from Loaders (MUST VERIFY)
**What**: EventBridge rules trigger ECS loaders → data writes to RDS
**How**: Monitor CloudWatch logs

```bash
# Check EventBridge rules are enabled
aws events list-rules --name-prefix algo --state ENABLED

# Check ECS cluster has active tasks
aws ecs describe-clusters --clusters algo-cluster

# Check recent ECS task executions
aws ecs list-tasks --cluster algo-cluster --desired-status RUNNING

# Monitor loader logs
aws logs tail /ecs/algo-cluster --follow

# Wait 10 min for scheduled loader, then check RDS:
aws rds describe-db-instances --db-instance-identifier algo-db
# Check: MultiAZ, BackupRetentionPeriod, EngineVersion
```

**If data not flowing**:
- Loaders may be failing (check ECS task logs)
- EventBridge rules may not be enabled
- ECS tasks may not have proper IAM permissions
- RDS may not be reachable from ECS

---

#### Phase 3: Orchestrator Execution (MUST VERIFY)
**What**: Orchestrator Lambda runs on schedule, completes 7 phases
**How**: Invoke manually first, then check logs

```bash
# Manual test invocation
aws lambda invoke \
  --function-name algo-algo-dev \
  --log-type Tail \
  /tmp/orchestrator-output.json | jq '.LogResult' -r | base64 -d

# Check for Phase 1-7 execution
# Expected: Phase 1 passes → Phase 2-7 execute → SUCCESS or HALT

# Check orchestrator logs
aws logs tail /aws/lambda/algo-algo-dev --follow
```

**If orchestrator fails**:
- Phase 1 fail → data not fresh/complete (loaders issue)
- Phase 2-4 fail → position/exit logic issues
- Phase 5 fail → signal generation issue
- Phase 6-7 fail → Alpaca or account issues

---

#### Phase 4: Frontend Data Display (MUST VERIFY)
**What**: Frontend pages load and display data from API
**How**: Open browser and check Network tab

```
1. Navigate to: https://d2u93283nn45h2.cloudfront.net
2. Open DevTools → Network tab
3. Check API calls:
   - /api/scores/stockscores → should return 200 with data
   - /api/signals/stocks → should return 200 with signals
   - /api/market → should return 200 with market data
4. Check Console for JS errors
```

**If pages show no data**:
- API returning 500 → Lambda cold-start or DB connection
- API returning 200 but empty → Loaders haven't populated
- API returning data but not displayed → Frontend JS issue

---

#### Phase 5: Live Trading (MUST VERIFY)
**What**: Orchestrator can place trades in Alpaca
**How**: Check algo_trades table after orchestrator runs

```bash
# After orchestrator completes, check:
psql -h algo-db.*.us-east-1.rds.amazonaws.com -U stocks -d stocks -c \
  "SELECT symbol, side, qty, status, created_at FROM algo_trades ORDER BY created_at DESC LIMIT 5;"

# Check Alpaca account
aws secretsmanager get-secret-value --secret-id algo/alpaca | jq -r '.SecretString' | jq .

# Verify trading config
aws lambda get-function-configuration --function-name algo-algo-dev | jq '.Environment.Variables | {ORCHESTRATOR_DRY_RUN, ALPACA_PAPER_TRADING, ALGO_LIVE_TRADING}'
```

---

## 🔍 CURRENT BLOCKERS ANALYSIS

### Unknown (Requires AWS Verification)
1. **Loaders Running?** 
   - Unknown if EventBridge rules are triggering ECS tasks
   - Unknown if ECS tasks are running successfully
   - Unknown if data is being written to RDS

2. **API Lambda Working?**
   - Timeout fixed (300s), but haven't tested in AWS
   - Cold-start performance unknown
   - Database connection in VPC unknown

3. **Orchestrator Executing?**
   - Schedule configured, but haven't verified actual execution
   - Data freshness gates unknown
   - Phase success rate unknown

4. **Frontend Working?**
   - CloudFront deployed, but data flow unknown
   - API connectivity from CloudFront unknown
   - CORS configuration untested

5. **Alpaca Integration?**
   - Credentials stored, but untested
   - Live vs paper mode needs verification
   - Order execution untested

---

## 📋 VERIFICATION STEPS (IN ORDER)

### Step 1: Verify API Lambda (5 min)
```bash
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/health
# Should return: { "status": "healthy", "version": "v2-2026-05-21" }

curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health/detailed
# Should return: { "status": "healthy", "dbStatus": "connected", "tables": {...} }
```
**If 500**: Check `/aws/lambda/algo-api-dev` logs

**If 200 but dbStatus=disconnected**: Check RDS security group, Secrets Manager

### Step 2: Test API Endpoints (5 min)
```bash
# Test each endpoint
curl 'https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores?limit=1'
curl 'https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/signals/stocks?limit=1'
curl 'https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/prices/history/AAPL?limit=1'
```
**If empty**: Loaders haven't run
**If 500**: Lambda error
**If 200 with data**: ✓ API working

### Step 3: Check Loaders (10-20 min)
```bash
# Check if any loaders have run
aws logs filter-log-events --log-group-name /ecs/algo-cluster --filter-pattern "Loaded"

# Manually trigger test loader
aws ecs run-task --cluster algo-cluster --task-definition algo-stock-prices-daily-loader --launch-type FARGATE

# Monitor for 10 minutes, then query RDS for new data
```
**If no data**: Loaders not running
**If data appears**: ✓ Loaders working

### Step 4: Invoke Orchestrator (15 min)
```bash
aws lambda invoke --function-name algo-algo-dev /tmp/out.json
cat /tmp/out.json | jq .

aws logs tail /aws/lambda/algo-algo-dev --follow
```
**Check output for**: PHASE 1 PASS → PHASES 2-7 → SUCCESS
**If Phase 1 fails**: Data not fresh
**If later phases fail**: Check specific phase logs

### Step 5: Check Frontend (5 min)
Open browser: https://d2u93283nn45h2.cloudfront.net
- Click through all pages
- Monitor Network tab for API calls
- Check console for errors

**If empty pages**: Check API endpoints
**If 404 or errors**: Check CloudFront + API integration

---

## 🎯 SUCCESS CRITERIA

When ALL of these are true, system is fully operational:
- [ ] API `/health` returns 200 with database connected
- [ ] API `/api/scores` returns 200 with 50+ items
- [ ] API `/api/signals/stocks` returns 200 with signals
- [ ] API `/api/prices/history/AAPL` returns 200 with price data
- [ ] Loaders have populated RDS with recent data (< 2 days old)
- [ ] Orchestrator Phase 1-7 completes successfully
- [ ] Frontend pages load and display data
- [ ] Alpaca trades are being logged in algo_trades table

---

## 🚀 DEPLOYMENT SUMMARY

**What's Fixed:**
- API Lambda timeout increased (120s → 300s) ✓
- Diagnostic tools created ✓
- Integration tests written ✓
- Local system verified working ✓

**What's Remaining:**
- Deploy Terraform changes to AWS
- Verify API Lambda connectivity
- Verify loaders are running in ECS
- Verify orchestrator execution
- Verify frontend data display
- Verify live Alpaca trading

**Estimated Time to Full Operation:** 30 min - 2 hours (depending on what's blocking)
