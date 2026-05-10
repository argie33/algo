# IMPLEMENTATION ROADMAP — Getting to Production-Ready

**Current State:** Deployed but blocked by stale data
**Target State:** Production-ready with verified end-to-end execution
**Estimated Timeline:** 7-10 days for full completion

---

## 🎯 MASTER PLAN OVERVIEW

```
WEEK 1 (Days 1-5): FIX CRITICAL BLOCKERS
├─ Day 1: Diagnose & fix data loader issue
├─ Day 2: Verify end-to-end algo execution
├─ Day 3: Test EventBridge scheduler
├─ Day 4: Verify API-frontend wiring
└─ Day 5: Test notification system

WEEK 2 (Days 6-10): CLOSE INTEGRATION GAPS
├─ Day 6: Implement missing UI features
├─ Day 7: Performance optimization
├─ Day 8: Security hardening
├─ Day 9: Load testing & scaling
└─ Day 10: Documentation & runbooks
```

---

## 📅 WEEK 1: CRITICAL BLOCKERS

### Day 1: Fix Data Loader (4 hours)

**Goal:** Get price_daily data fresh and buy_sell_daily complete

#### 1a. Diagnose (30 mins)
```bash
# Run all diagnostic commands from SYSTEM_VERIFICATION_REPORT.md
# Output findings to: DEBUG_FINDINGS.txt
```

**Expected Findings:**
- [ ] ECS cluster status (is it running?)
- [ ] Task definition status (do they exist?)
- [ ] CloudWatch logs (what's failing?)
- [ ] EventBridge rules (are they configured?)
- [ ] IAM permissions (can tasks access RDS/S3/Secrets?)

#### 1b. Root Cause Analysis (1 hour)
Based on findings from 1a, determine:
- Is the problem in CloudFormation (resources not deployed)?
- Is the problem in EventBridge (rules not firing)?
- Is the problem in the loader code (execution failing)?
- Is the problem in IAM (permissions missing)?
- Is the problem in networking (VPC/subnet issues)?

#### 1c. Fix (1 hour)
Apply the fix based on root cause:
- **If CloudFormation:** Deploy missing stacks: `gh workflow run deploy-app-ecs-tasks.yml`
- **If EventBridge:** Enable rules: `aws events enable-rule --name <rule-name>`
- **If loader code:** Debug and fix the Python loader script
- **If IAM:** Update task role policy to grant needed permissions
- **If networking:** Update security groups or network configuration

#### 1d. Verify (1.5 hours)
```bash
# Run the loader manually
python3 load_pricing_loader.py  # Should complete without error
python3 algo_run_daily.py       # Should complete Phase 0+ successfully

# Check data is fresh
psql -h localhost -U stocks -d stocks \
  -c "SELECT symbol, MAX(date) FROM price_daily GROUP BY symbol LIMIT 5;"

# Verify we have enough signals
psql -h localhost -U stocks -d stocks \
  -c "SELECT COUNT(*) FROM buy_sell_daily WHERE date = CURRENT_DATE;"
```

**Success Criteria:**
- ✅ price_daily age < 7 hours
- ✅ buy_sell_daily has 800+ rows
- ✅ `algo_run_daily.py` completes Phase 0 successfully
- ✅ Algo continues to Phase 1+

**Deliverable:** `DEBUG_FINDINGS.txt` + `FIX_APPLIED.txt` + Verified local test run

---

### Day 2: Verify End-to-End Algo Execution (3 hours)

**Goal:** Confirm algo runs completely from data → signals → trades → reconciliation

#### 2a. Run Full Algo Pipeline Locally (1 hour)
```bash
# Start Docker
docker-compose up -d

# Run full algo day
python3 algo_run_daily.py 2>&1 | tee ALGO_RUN_LOG.txt

# Expected output: Should complete all 7+ phases
# - Phase 0: Data quality validation ✅
# - Phase 1: Circuit breaker checks ✅
# - Phase 2: Position monitoring ✅
# - Phase 3: Exit execution ✅
# - Phase 4: Pyramid additions ✅
# - Phase 5: Signal generation ✅
# - Phase 6: Entry execution ✅
# - Phase 7: Reconciliation ✅
```

#### 2b. Verify Trade Execution (1 hour)
```bash
# Check if any trades were generated
psql -h localhost -U stocks -d stocks \
  -c "SELECT symbol, entry_price, stop_price, quantity, created_at FROM algo_trades ORDER BY created_at DESC LIMIT 10;"

# Check Alpaca paper trading account
# (Requires API credentials)
alpaca_api.list_positions()  # Should show algo trades

# Compare with audit log
psql -h localhost -U stocks -d stocks \
  -c "SELECT phase, message FROM algo_audit_log WHERE created_at > NOW() - INTERVAL '1 hour' ORDER BY created_at;"
```

#### 2c. Verify Reconciliation (30 mins)
```bash
# Check if trades match between DB and Alpaca
psql -h localhost -U stocks -d stocks \
  -c "SELECT symbol, COUNT(*) as db_count FROM algo_trades GROUP BY symbol;" > DB_TRADES.txt

# Compare with Alpaca positions
# (Should be reconciled with no orphans or mismatches)
```

**Success Criteria:**
- ✅ Algo runs to completion without errors
- ✅ Signals are generated for qualified candidates
- ✅ Orders placed (or dry-run logged)
- ✅ Fills recorded in database
- ✅ Audit log shows complete decision chain (15+ fields)
- ✅ Reconciliation matches Alpaca account

**Deliverable:** `ALGO_RUN_LOG.txt` + `TRADES_VERIFICATION.txt` + Screenshots of positions

---

### Day 3: Test EventBridge Scheduler (2 hours)

**Goal:** Confirm algo runs automatically at 5:30pm ET every weekday

#### 3a. Check Scheduler Configuration (30 mins)
```bash
# Verify algo orchestrator schedule exists
aws scheduler get-schedule --name algo-orchestrator-schedule --region us-east-1

# Expected output:
# - Name: algo-orchestrator-schedule
# - ScheduleExpression: cron(0 22 ? * MON-FRI *)  [= 5:30pm ET]
# - State: ENABLED
# - Target: algo-orchestrator Lambda function
```

If missing or disabled:
```bash
# Deploy or enable
gh workflow run deploy-algo-orchestrator.yml --repo argie33/algo
aws scheduler update-schedule --name algo-orchestrator-schedule --state ENABLED --region us-east-1
```

#### 3b. Check Lambda Logs (1 hour)
```bash
# Check last 5 executions
aws logs tail /aws/lambda/algo-orchestrator --follow --region us-east-1 --since 7d

# Look for:
# - Lambda invoked at ~5:30pm ET
# - Successful completions (no timeouts or errors)
# - Complete phase logs from Phase 0-7
```

If no recent executions:
- EventBridge rule is not firing
- Check rule is enabled: `aws events describe-rule --name algo-orchestrator-rule`
- Check rule has correct target: `aws events list-targets-by-rule --rule algo-orchestrator-rule`

#### 3c. Verify Data is Updated After Scheduled Run (30 mins)
```bash
# Next scheduled run is at 5:30pm ET
# After it runs, verify:
# 1. New positions appear in database
# 2. CloudWatch logs show execution
# 3. Alpaca account reflects new trades

# Check timestamp of latest trade
psql -h localhost -U stocks -d stocks \
  -c "SELECT MAX(created_at) FROM algo_trades;" > LATEST_TRADE_TIME.txt
```

**Success Criteria:**
- ✅ EventBridge scheduler exists and is ENABLED
- ✅ Lambda executes at ~5:30pm ET ±5 minutes
- ✅ No timeout errors (Lambda must complete in < 300 seconds)
- ✅ New trades appear after each run
- ✅ CloudWatch logs show complete phase logs

**Deliverable:** `SCHEDULER_VERIFICATION.txt` + CloudWatch logs + Trade timestamps

---

### Day 4: Test API-Frontend Wiring (3 hours)

**Goal:** Verify all 25 API endpoints connect correctly from frontend

#### 4a. Start Frontend Development Server (30 mins)
```bash
cd webapp
npm run dev  # Starts dev server at http://localhost:3000

# Open in browser and check:
# 1. Can you login? (Cognito auth)
# 2. Do pages load? (No 404 or network errors)
# 3. Check browser console for errors (F12 → Console tab)
```

#### 4b. Test 5 Critical Endpoints (1 hour)
```bash
# Use browser Network tab (F12 → Network) to verify:

# 1. /algo/status
curl -H "Authorization: Bearer <TOKEN>" \
  https://kx4kprv8ph.execute-api.us-east-1.amazonaws.com/algo/status

# 2. /algo/positions
curl -H "Authorization: Bearer <TOKEN>" \
  https://kx4kprv8ph.execute-api.us-east-1.amazonaws.com/algo/positions

# 3. /markets
curl -H "Authorization: Bearer <TOKEN>" \
  https://kx4kprv8ph.execute-api.us-east-1.amazonaws.com/markets

# 4. /algo/trades
curl -H "Authorization: Bearer <TOKEN>" \
  https://kx4kprv8ph.execute-api.us-east-1.amazonaws.com/algo/trades

# 5. /algo/config
curl -H "Authorization: Bearer <TOKEN>" \
  https://kx4kprv8ph.execute-api.us-east-1.amazonaws.com/algo/config

# Check for:
# - Response code 200 (not 400/401/403/500)
# - Response body is valid JSON
# - Response time < 200ms
```

**Expected Issues & Fixes:**
| Issue | Fix |
|-------|-----|
| 401 Unauthorized | Check JWT token in Authorization header |
| 403 Forbidden | Check Cognito user is authorized |
| 404 Not Found | Check API Gateway route is configured |
| 500 Internal Server Error | Check Lambda logs |
| CORS error | Check API Gateway CORS configuration |
| Timeout | Lambda execution too slow, needs optimization |

#### 4c. Frontend Pages Integration Test (1.5 hours)
```
Open each major page in browser and verify:

[ ] Markets page
    - Data loads (< 2s)
    - No console errors
    - Tables/charts render
    - Sorting/filtering works

[ ] Positions page
    - Shows current positions
    - P&L updates in real-time
    - Stop levels are correct

[ ] Trades page
    - Shows trade history
    - Partial exits visible
    - R-multiple calculations correct

[ ] Algo Dashboard
    - Phase status visible
    - Signal counts accurate
    - Market exposure chart visible

[ ] Service Health
    - Data freshness shown
    - Loader status visible
    - Patrol log accessible

[ ] Settings page
    - User preferences editable
    - API credentials stored securely
    - Theme toggle works
```

**Success Criteria:**
- ✅ All 5 critical endpoints return 200 + valid JSON
- ✅ Response times < 200ms
- ✅ No CORS errors
- ✅ No 401/403/500 errors
- ✅ All major frontend pages load without errors
- ✅ Data appears to be correct (matches database)
- ✅ No JS console errors

**Deliverable:** `ENDPOINT_TEST_RESULTS.txt` + Screenshots of each page + Browser console log

---

### Day 5: Test Notification System (2 hours)

**Goal:** Verify SMS, Email, and Slack alerts are sent when triggered

#### 5a. Check Notification Configuration (30 mins)
```bash
# Verify notification secrets are configured
aws secretsmanager get-secret-value --secret-id stocks-notification-config --region us-east-1

# Expected fields:
# - smtp_server, smtp_port, from_email, password (Email)
# - twilio_account_sid, twilio_auth_token, from_number, to_number (SMS)
# - slack_webhook_url, slack_channel (Slack)
```

#### 5b. Trigger Test Alert (30 mins)
```bash
# Create a test alert in database
psql -h localhost -U stocks -d stocks << EOF
INSERT INTO notifications (kind, severity, title, message, status, created_at)
VALUES ('test_alert', 'critical', 'Test Alert', 'This is a test notification', 'pending', NOW());
EOF

# Run alert router
python3 alert_router.py  # Should send email/SMS/Slack

# Check notification table
psql -h localhost -U stocks -d stocks \
  -c "SELECT kind, severity, status, sent_at FROM notifications ORDER BY created_at DESC LIMIT 10;"
```

#### 5c. Verify Receipt (1 hour)
- [ ] Email received in mailbox (check spam folder)
- [ ] SMS received on phone (if Twilio configured)
- [ ] Slack message posted to #alerts channel (if Slack configured)
- [ ] `sent_at` timestamp updated in database

**Success Criteria:**
- ✅ Notification secrets are configured
- ✅ Alert router completes without errors
- ✅ Email/SMS/Slack received
- ✅ `notifications.status` changed from `pending` to `sent`

**Deliverable:** `NOTIFICATION_TEST_LOG.txt` + Screenshots of email/SMS/Slack

---

## 📊 WEEK 1 VERIFICATION SUMMARY

**Before Moving to Week 2, Verify:**

```bash
# Checklist:
[ ] SYSTEM_VERIFICATION_REPORT.md completed and findings documented
[ ] Data loader fixed - price_daily is fresh (< 7h old)
[ ] End-to-end algo run completes all 7+ phases without error
[ ] Trades appear in database and Alpaca
[ ] EventBridge scheduler fires at 5:30pm ET
[ ] New trades appear after scheduled run
[ ] All 25 API endpoints respond with 200 + valid JSON
[ ] Frontend pages load and display data correctly
[ ] Notifications send via email/SMS/Slack
[ ] No JavaScript errors in browser console

If ALL boxes checked: Ready for Week 2 ✅
If ANY box unchecked: Fix before proceeding 🔴
```

---

## 📅 WEEK 2: INTEGRATION GAPS (Days 6-10)

### Day 6: Missing UI Features (3 hours)
- [ ] Implement Audit Trail Viewer (see decisions made)
- [ ] Implement Pre-Trade Simulation (show impact before commit)
- [ ] Implement Backtest Visualization (equity curves, trades, metrics)
- [ ] Implement Performance Metrics Dashboard (Sharpe, Sortino, MDD, Calmar)
- [ ] Integrate sector rotation exposure feed

### Day 7: Performance Optimization (2 hours)
- [ ] Add database indexes on date, symbol, created_at
- [ ] Implement API response caching
- [ ] Migrate to TimescaleDB for time-series queries
- [ ] Implement pagination for large datasets
- [ ] Profile slow endpoints and optimize queries

### Day 8: Security Hardening (2 hours)
- [ ] Move Lambda functions to VPC with NAT gateway
- [ ] Remove public RDS access (0.0.0.0/0)
- [ ] Add WAF to CloudFront
- [ ] Enable RDS encryption at rest
- [ ] Implement request signing for inter-service calls

### Day 9: Load Testing & Scaling (2 hours)
- [ ] Run load test (concurrent users, trades)
- [ ] Identify bottlenecks
- [ ] Optimize database queries
- [ ] Scale Lambda concurrency
- [ ] Document scaling procedures

### Day 10: Documentation & Runbooks (2 hours)
- [ ] Update STATUS.md with current state
- [ ] Create runbooks for common issues
- [ ] Document incident response procedures
- [ ] Create operator guide for production support
- [ ] Add monitoring/alerting dashboard

---

## ✅ PRODUCTION READINESS CHECKLIST

### Technical Requirements
- [ ] Data freshness verified (all loaders on schedule)
- [ ] End-to-end execution tested (signal → trade → reconciliation)
- [ ] EventBridge scheduler verified
- [ ] API endpoints all functional
- [ ] Frontend-backend data contract verified
- [ ] Notifications working via all channels
- [ ] Database optimized and indexed
- [ ] Lambda functions in VPC
- [ ] RDS not publicly accessible
- [ ] All 127 tests passing
- [ ] Load testing completed
- [ ] No JavaScript console errors
- [ ] Performance < 200ms for APIs, < 2s for pages

### Operational Requirements
- [ ] Runbooks created for 10+ failure scenarios
- [ ] On-call procedures documented
- [ ] Incident response playbook created
- [ ] Scaling procedures documented
- [ ] Backup/recovery procedures tested
- [ ] Monitoring dashboard operational
- [ ] Alerting configured and tested
- [ ] Cost tracking enabled
- [ ] Logging aggregation working
- [ ] Team training completed

### Documentation Requirements
- [ ] Architecture diagram current
- [ ] Data flow documented
- [ ] API documentation complete
- [ ] Configuration parameters documented
- [ ] Troubleshooting guide comprehensive
- [ ] Deployment procedures clear
- [ ] Code comments explain WHY (not WHAT)
- [ ] README files accurate

---

## 🎬 GETTING STARTED TODAY

### Right Now (30 minutes):
1. Read `SYSTEM_VERIFICATION_REPORT.md` completely
2. Run the diagnostic commands from "Day 1: Diagnose"
3. Document findings in `DEBUG_FINDINGS.txt`
4. Share findings with team

### Today (4 hours):
1. Complete "Day 1: Fix Data Loader" steps
2. Run `algo_run_daily.py` successfully
3. Verify data is fresh

### Tomorrow:
1. Complete "Day 2: End-to-End Verification"
2. Confirm trades execute and reconcile

### Week 1:
1. Complete all 5 days of critical blockers
2. Verify every success criterion is met

### Week 2:
1. Close integration gaps
2. Production hardening
3. Documentation

---

## 📞 WHEN YOU'RE BLOCKED

**If diagnosis doesn't reveal root cause:**
- [ ] Check CloudFormation stack events: `aws cloudformation describe-stack-events --stack-name <stack>`
- [ ] Check IAM policies: Do ECS tasks have permissions?
- [ ] Check VPC/networking: Can tasks reach RDS? Can Lambda reach RDS?
- [ ] Check logs: CloudWatch → Logs Insights for errors

**If a fix doesn't work:**
- [ ] Verify the fix was actually applied
- [ ] Check if a redeploy is needed: `gh workflow run deploy-app-ecs-tasks.yml`
- [ ] Check if credentials are stale (need refresh)
- [ ] Review CloudFormation drift (manual changes?)

---

## 📈 SUCCESS METRICS

**Week 1 Complete:**
- ✅ 112+ unit tests passing
- ✅ End-to-end algo execution verified
- ✅ EventBridge scheduler confirmed running
- ✅ All API endpoints functional
- ✅ Frontend-backend wiring verified
- ✅ Notifications working

**Week 2 Complete:**
- ✅ All 7 UI gaps closed
- ✅ Performance optimized (< 200ms APIs)
- ✅ Security hardened (VPC, no public access)
- ✅ Load tested (100+ concurrent users)
- ✅ Production runbooks created
- ✅ Team trained

**Result:** Production-ready trading algorithm on AWS

---

**Document Version:** 1.0
**Created:** 2026-05-09
**Owner:** Team
**Status:** Ready to execute
