# Live Monitoring & Troubleshooting Guide - 2026-05-19

## Real-Time Monitoring During Deployment & Live Trading

---

## 1. GITHUB ACTIONS DEPLOYMENT (NOW - Next 5 minutes)

### Monitor Deployment Status
**URL**: https://github.com/argie33/algo/actions

**Watch for**:
```
✅ PASS - resolve-infra completes (1-2 min)
✅ PASS - deploy-algo-lambda code upload (1-2 min)
✅ PASS - Configure Algo Lambda Environment Variables (30-60 sec)
✅ PASS - deploy-api-lambda completes (1-2 min)
✅ PASS - deploy-frontend completes (2-3 min)
```

### If Deployment Fails
**Common issues & fixes**:

| Error | Cause | Fix |
|-------|-------|-----|
| `InvalidParameterValueException` | Credentials format wrong | Check GitHub Secrets are exactly right |
| `ThrottlingException` | AWS rate limit | Wait 1 min, rerun workflow |
| `AccessDenied` | IAM role missing permission | Check algo-svc-github-actions-dev role |
| `Timeout` | VPC cold start | Non-fatal, will work next time |
| `Secret not found` | GitHub Secrets missing | Add ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY |

**How to rerun**:
1. Go to https://github.com/argie33/algo/actions
2. Click the failed workflow
3. Click "Re-run jobs" → "Re-run all jobs"

---

## 2. LAMBDA CONFIGURATION VERIFICATION (After deployment completes)

### Verify Credentials Were Injected
```bash
# Check that Alpaca credentials are in Lambda environment
aws lambda get-function-configuration \
  --function-name algo-algo-dev \
  --region us-east-1 \
  --query 'Environment.Variables.APCA_API_KEY_ID' \
  --output text

# Should output: PK3CYOVDIZ7T35XMNUJX6CIONG
```

### Check Lambda Logs
```bash
# Watch real-time Lambda logs
aws logs tail /aws/lambda/algo-algo-dev --follow --region us-east-1

# Or check last 100 lines
aws logs tail /aws/lambda/algo-algo-dev --max-items 100 --region us-east-1
```

### Verify Function Ready
```bash
aws lambda get-function \
  --function-name algo-algo-dev \
  --region us-east-1 \
  --query 'Configuration.State' \
  --output text

# Should output: Active
```

---

## 3. PRE-MARKET TEST (Before 9:30am, optional)

### Manual Dry-Run Test
```bash
# This will simulate the 9:30am orchestrator run
aws lambda invoke \
  --function-name algo-algo-dev \
  --region us-east-1 \
  --log-type Tail \
  --query 'LogResult' \
  --output text | base64 --decode

# Should show all 10 phases executing
```

### Expected Output
```
Phase 1: data_freshness [OK]
Phase 2: circuit_breakers [OK]
Phase 3a: reconciliation [OK]  ← Should work now
Phase 6: entry_execution [OK]   ← Should work now
...
```

### If Phases Still Fail
```
[FAIL] Phase 6: entry_execution [ERROR]
  Error: Alpaca credentials not found or invalid

Fix:
  1. Verify: aws lambda get-function-configuration --function-name algo-algo-dev
  2. Check: APCA_API_KEY_ID and APCA_API_SECRET_KEY are set
  3. If missing: Re-run GitHub Actions workflow
  4. If invalid: Check credentials in GitHub Secrets
```

---

## 4. MARKET OPEN MONITORING (9:30am ET)

### What to Watch

**A. EventBridge Trigger**
```bash
# Check if EventBridge scheduled rule is enabled
aws events describe-rule \
  --name algo-orchestrator-schedule \
  --region us-east-1 \
  --query 'State' \
  --output text

# Should output: ENABLED
```

**B. Lambda Execution**
```bash
# Watch Lambda logs in real-time (start ~9:28am)
aws logs tail /aws/lambda/algo-algo-dev --follow --region us-east-1 --since 10m

# Should show orchestrator starting at 9:30:00
```

**C. CloudWatch Metrics**
- **URL**: https://console.aws.amazon.com/cloudwatch
- **Go to**: Lambda → algo-algo-dev
- **Watch**: Invocations, Duration, Errors, Throttles

**D. Dashboard**
- **URL**: Your frontend dashboard
- **Watch**: New positions appearing, P&L updating

**E. Database Activity**
```bash
# Check orchestrator audit log
psql -h localhost -U stocks -d stocks -c \
  "SELECT * FROM algo_audit_log ORDER BY created_at DESC LIMIT 20;"

# Should show new entries from 9:30am run
```

---

## 5. CRITICAL ISSUES TO WATCH FOR

### Issue 1: Credentials Not Found
**Symptoms**:
- Phase 3a shows [SKIP] or [ERROR]
- Phase 6 shows [SKIP] or [ERROR]
- Logs: "Alpaca credentials not found"

**Diagnosis**:
```bash
aws lambda get-function-configuration --function-name algo-algo-dev \
  --query 'Environment.Variables' | jq .
```

**Quick Fix**:
- Redeploy via GitHub Actions (push to main)
- Or manually set via AWS Console:
  - Lambda → algo-algo-dev → Configuration → Environment variables
  - Add: APCA_API_KEY_ID = PK3CYOVDIZ7T35XMNUJX6CIONG
  - Add: APCA_API_SECRET_KEY = DSJ3NVx42NcCqgeUwdyDQDi5qurSYX3PL84kDhm3sy28

### Issue 2: Orders Not Executing
**Symptoms**:
- Phase 6 completes but shows 0 trades
- Alpaca account shows no new positions
- Logs: "No eligible signals after filtering"

**Diagnosis**:
- Check market stage: Is it >= 2?
- Check signal quality: Are signals passing Tier 1-5 filters?
- Check portfolio capacity: Are we at max_positions?

**Query**:
```bash
psql -h localhost -U stocks -d stocks -c \
  "SELECT market_stage, COUNT(*) FROM market_health_daily GROUP BY market_stage;"
```

**Fix**:
- If market_stage != 2: Circuit breaker working as designed (wait for stage change)
- If signals filtered out: Check filter_pipeline_log for which tier rejected them
- If at max positions: Phase 4 (exits) must execute first

### Issue 3: Alpaca API Errors
**Symptoms**:
- Phase 3a or Phase 6 fails with API error
- Logs: "Connection timeout" or "HTTP 401/403"
- Orders partially filled

**Possible Causes**:
1. Credentials invalid/expired
2. Alpaca API down
3. Rate limit exceeded
4. Invalid order parameters

**Quick Diagnostics**:
```bash
# Test Alpaca connectivity
curl -H "Authorization: Bearer YOUR_KEY" \
  https://paper-api.alpaca.markets/v2/account

# Check rate limits in headers
# Should show: X-RateLimit-Remaining: 180 (or similar)
```

**Fix**:
- If 401/403: Rotate credentials (get new ones from Alpaca, update GitHub Secrets)
- If timeout: Wait, Alpaca may be under load
- If rate limit: Reduce request frequency or increase interval between runs

### Issue 4: Database Connection Failed
**Symptoms**:
- Phase 1 fails immediately
- Logs: "psycopg2.OperationalError: could not connect to server"

**Diagnosis**:
```bash
# Check RDS status
aws rds describe-db-instances \
  --db-instance-identifier algo-stocks-dev \
  --query 'DBInstances[0].DBInstanceStatus' \
  --output text

# Should output: available
```

**Fix**:
- If not available: Wait for RDS to recover
- If connection issue: Check VPC security groups allow Lambda → RDS
- Check RDS credentials haven't been rotated unexpectedly

### Issue 5: No Orders Placed Despite Passing Filters
**Symptoms**:
- Phase 5 shows signals evaluated
- Phase 6 shows orders attempted but 0 executed
- Logs: "Order rejected: insufficient buying power" or similar

**Diagnosis**:
```bash
# Check Alpaca account balance
curl -H "Authorization: Bearer YOUR_KEY" \
  https://paper-api.alpaca.markets/v2/account | jq '.buying_power'
```

**Fix**:
- Add buying power to paper account (via Alpaca dashboard)
- Reduce trade size in configuration
- Check margin requirements aren't too high

---

## 6. QUICK FIX COMMANDS

### Re-deploy Immediately (if something breaks)
```bash
git push origin main
# GitHub Actions runs automatically, takes 3-5 minutes
```

### Manually Update Lambda Credentials
```bash
aws lambda update-function-configuration \
  --function-name algo-algo-dev \
  --environment Variables={APCA_API_KEY_ID=PK3CYOVDIZ7T35XMNUJX6CIONG,APCA_API_SECRET_KEY=DSJ3NVx42NcCqgeUwdyDQDi5qurSYX3PL84kDhm3sy28} \
  --region us-east-1

# Wait for update
aws lambda wait function-updated --function-name algo-algo-dev
```

### Kill Stale Orchestrator Locks
```bash
# If orchestrator says "already running"
rm /tmp/algo_orchestrator.lock
rm /tmp/algo_orchestrator_halt
```

### View Real-Time Orchestrator Logs
```bash
aws logs tail /aws/lambda/algo-algo-dev --follow
```

### Check Database for Issues
```bash
psql -h localhost -U stocks -d stocks

# Check latest audit entries
SELECT * FROM algo_audit_log ORDER BY created_at DESC LIMIT 20;

# Check for errors
SELECT * FROM algo_audit_log WHERE status = 'error' ORDER BY created_at DESC;

# Check positions
SELECT * FROM algo_positions_daily WHERE date = CURRENT_DATE;
```

---

## 7. ESCALATION PROCEDURE

### If Something is Broken

**Step 1: Collect Diagnostics** (2 minutes)
```bash
# Get Lambda logs
aws logs tail /aws/lambda/algo-algo-dev --since 30m > logs.txt

# Get database errors
psql -c "SELECT * FROM algo_audit_log WHERE status IN ('error', 'halt') LIMIT 50;" > db_errors.txt

# Get function configuration
aws lambda get-function-configuration --function-name algo-algo-dev > lambda_config.json

# Save Alpaca account status
curl -H "Authorization: Bearer $KEY" https://paper-api.alpaca.markets/v2/account > alpaca_status.json
```

**Step 2: Identify Root Cause** (2-5 minutes)
- Check logs for error messages
- Compare against "Critical Issues" section above
- Check CloudWatch metrics for anomalies

**Step 3: Apply Fix** (1-5 minutes)
- See specific issue section for fix
- Re-deploy if code change needed
- Update credentials if auth issue
- Check resources if infrastructure issue

**Step 4: Verify** (2 minutes)
- Re-run Phase via manual Lambda invoke
- Check logs show [OK] instead of [ERROR]
- Verify no side effects in database

---

## 8. WHAT TO DO RIGHT NOW

### Immediate Actions
1. ✅ GitHub Actions deployment is running
2. ⏳ Monitor workflow at: https://github.com/argie33/algo/actions
3. ⏳ Wait for "Configure Algo Lambda Environment Variables" step to pass
4. ⏳ Once complete, verify credentials injected (see section 2)
5. ⏳ At 9:25am ET, start monitoring Lambda logs
6. ⏳ At 9:30am ET, watch orchestrator execution

### Have These Ready
- AWS console open to Lambda function
- Terminal with `aws logs tail` command
- This guide bookmarked
- Alpaca account dashboard open
- Your frontend dashboard
- Database terminal (psql) open

### Response Time
- **Credential issue**: < 2 min (re-run workflow)
- **Data issue**: < 5 min (check database)
- **API issue**: < 3 min (diagnose & retry)
- **Order failure**: < 2 min (check buying power, retry)

---

## 9. SUCCESS CRITERIA

System is **LIVE and WORKING** when:
1. ✅ GitHub Actions workflow completes with no errors
2. ✅ Lambda has APCA_API_KEY_ID in environment variables
3. ✅ At 9:30am: Orchestrator invokes (check logs)
4. ✅ At 9:30am: Phase 3a shows [OK] (not [SKIP])
5. ✅ At 9:30am: Phase 6 shows [OK] (not [SKIP])
6. ✅ At 9:30am: Orders appear in Alpaca account
7. ✅ At 9:30am: Dashboard shows new trades

---

## Ready to Go Live

All systems are deployed and monitored. Issues will be caught and fixed immediately.

**Let's watch this thing run.**
