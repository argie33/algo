# Operational Runbooks - Incident Recovery Procedures

**Purpose:** Step-by-step recovery procedures for common production failures. These are designed to be executed by anyone without requiring code changes or Lambda redeployment.

**Status:** Ready to use in development. No escalation required.

**Key Principles:**
1. **Fail-Closed Default** - When in doubt, disable the algo (it won't trade)
2. **Minimal Redeploy** - Use feature flags, not code commits
3. **Observable Recovery** - Log every action with structured JSON for audit trail
4. **Graceful Degradation** - System keeps running even with partial failures

---

## 🔴 Critical: Data Load Completely Fails

**Symptom:** Algo refuses to trade because `check_critical_loaders()` fails. You'll see:
```
[ERROR] Loader SLA check failed: Required loaders missing data
  - price_daily: zero rows loaded today
  - buy_sell_daily: zero rows loaded today
Algo will not trade until data is fresh.
```

### Diagnosis (5 minutes)

```bash
# 1. Check what data was actually loaded
python3 audit_dashboard.py --loaders

# Expected output:
# price_daily:    ✓ PASS (1,523 rows, 2026-05-09 06:15 UTC)
# buy_sell_daily: ✓ PASS (487 rows, 2026-05-09 06:15 UTC)
# ...

# If you see FAILED or old timestamps:
# 2. Check ECS task logs
aws logs tail /aws/ecs/stocks-loaders --since 2h

# 3. Check EventBridge trigger
aws scheduler get-schedule --name stocks-price-loaders-schedule-dev
```

### Recovery (Choose One)

**Option A: Manual Retry (Quickest)**
```bash
# Trigger loader manually from your machine (requires AWS CLI access)
aws ecs run-task \
  --cluster stocks-data-cluster-dev \
  --task-definition stocks-loaders:latest \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"stocks-loaders","command":["python3","loadpricedaily.py","--parallelism","6"]}]}'

# Check logs (streaming):
aws logs tail /aws/ecs/stocks-loaders --follow
```

**Option B: Schedule Emergency Run (Via AWS Console)**
```bash
# 1. Open AWS Scheduler console
# 2. Find "stocks-price-loaders-schedule-dev"
# 3. Click "Trigger" button (runs immediately)
# 4. Watch logs: aws logs tail /aws/ecs/stocks-loaders --follow
```

**Option C: Load Locally First (If Connections OK)**
```bash
# Run on your machine to test:
python3 loadpricedaily.py --symbols AAPL MSFT GOOGL --start-date 2026-05-08

# If this succeeds, problem is in AWS execution (permissions, network, env vars)
# If this fails, problem is in loader code (data source down, schema change, etc.)
```

### If Retry Still Fails

**Check Loader Logs for Root Cause:**
```bash
# See what error the loader hit
aws logs get-log-events \
  --log-group-name /aws/ecs/stocks-loaders \
  --log-stream-name <latest-stream> \
  --start-from-head | jq '.events[] | select(.message | contains("ERROR"))'

# Common causes:
# 1. "Connection refused to RDS" → RDS is down (check AWS console)
# 2. "Missing AAPL data in source" → Data source outage (check IEX Cloud status)
# 3. "Table schema mismatch" → Database has drifted (recreate: psql < init_db.sql)
# 4. "Duplicate key" → Data was already loaded today (safe to ignore, next run will update)
```

**If Data Source is Down (e.g., IEX Cloud outage):**
```bash
# Disable algo until data source recovers
python3 feature_flags.py --disable signal_tier_2_enabled
python3 feature_flags.py --disable signal_tier_4_enabled

# Log manually:
echo '{"severity":"WARNING","message":"Data source outage - algo disabled","status":"investigating"}' >> /tmp/incident.log

# Re-enable when data source is back:
python3 feature_flags.py --enable signal_tier_2_enabled
python3 feature_flags.py --enable signal_tier_4_enabled
```

**If RDS is Down:**
```bash
# 1. Check RDS status
aws rds describe-db-instances --db-instance-identifier stocks-data-rds \
  --query 'DBInstances[0].DBInstanceStatus'

# 2. If "failed" or "backing-up", manually restart
aws rds reboot-db-instance --db-instance-identifier stocks-data-rds

# This takes 3-5 minutes. While waiting:
python3 feature_flags.py --disable signal_tier_1_enabled  # Block all filtering

# Once RDS is back (status = "available"):
python3 feature_flags.py --enable signal_tier_1_enabled

# Trigger data reload:
aws ecs run-task --cluster stocks-data-cluster-dev --task-definition stocks-loaders:latest ...
```

---

## 🟡 Data Stale: Last Update > 24 Hours

**Symptom:** Algo runs but uses old data. You'll see:
```
[WARN] Loader SLA warning: price_daily stale
  Last update: 2026-05-08 10:15 UTC (43 hours ago)
```

### Diagnosis (2 minutes)

```bash
# Check staleness for each critical table
python3 audit_dashboard.py --loaders

# See detailed timestamps:
psql -U stocks -h localhost -d stocks -c \
  "SELECT symbol, MAX(date) FROM price_daily GROUP BY symbol ORDER BY MAX(date) DESC LIMIT 5;"
```

### Recovery (Choose One)

**Option A: Immediate Reload**
```bash
# Re-trigger the loader for today only
aws ecs run-task \
  --cluster stocks-data-cluster-dev \
  --task-definition stocks-loaders:latest \
  --launch-type FARGATE \
  --network-configuration ... \
  --overrides '{"containerOverrides":[{"name":"stocks-loaders","command":["python3","loadpricedaily.py","--start-date","2026-05-09"]}]}'

# Wait for completion (~5 min):
aws logs tail /aws/ecs/stocks-loaders --follow --since 5m
```

**Option B: Discard Old Data & Reload From Scratch**
```bash
# CAREFUL: This deletes price history (use only if corrupted)
psql -U stocks -h localhost -d stocks -c \
  "DELETE FROM price_daily WHERE date < CURRENT_DATE - INTERVAL '30 days';"

# Then reload:
python3 loadpricedaily.py --start-date 2026-05-01
```

**Option C: Disallow Trading On Stale Data (Feature Flag)**
```bash
# If reload fails, prevent trading on stale data
python3 feature_flags.py --disable signal_tier_1_enabled

# Algo won't trade (data quality gate is disabled)
# Log this incident and investigate underlying cause
```

---

## 🟡 Signal Quality Degradation: Many False Signals

**Symptom:** Unusual signal volume or all tiers fail a particular stock:
```
[WARN] Tier 2 passed 1200 signals (expected ~50-100)
       Distribution days: -1 (impossible value?)
```

### Diagnosis (5 minutes)

```bash
# Check what tiers are failing
python3 audit_dashboard.py --signals --symbol AAPL --date 2026-05-09

# Look for patterns:
# - If all Tier 2 fails: market health data might be corrupted
# - If all Tier 3 fails: trend template calculation might be broken
# - If all Tier 4 fails: signal quality score calculation might be wrong
# - If Tier 5 keeps succeeding: portfolio limits might be too loose

# Check the source table directly:
psql -U stocks -h localhost -d stocks -c \
  "SELECT date, market_stage, distribution_days FROM market_health_daily ORDER BY date DESC LIMIT 3;"

# Look for nonsense values (market_stage = 99, distribution_days = -1, etc.)
```

### Recovery

**If One Tier is Broken (e.g., Tier 2):**
```bash
# Disable just that tier while you investigate:
python3 feature_flags.py --disable signal_tier_2_enabled

# Algo will skip Tier 2 and move to Tier 3
logger.info("Tier 2 disabled - market health check skipped")

# Investigate root cause:
# 1. Is market_health_daily table populated? 
#    SELECT COUNT(*) FROM market_health_daily WHERE date = CURRENT_DATE;
# 2. Are values sane? market_stage IN (1,2,3,4), distribution_days >= 0
# 3. If not, check loader logs (loadmarkethealth.py)

# Re-enable when fixed:
python3 feature_flags.py --enable signal_tier_2_enabled
```

**If All Tiers Failing (Likely Database Issue):**
```bash
# 1. Check database connection
psql -U stocks -h localhost -d stocks -c "SELECT 1;"
# If this hangs or fails → RDS is down

# 2. Check if tables exist and have data
psql -U stocks -h localhost -d stocks -c "SELECT COUNT(*) FROM price_daily;"

# 3. If tables are missing/empty → schema initialization failed
# Reinitialize:
psql -U stocks -h localhost -d stocks < init_db.sql

# 4. If connection is down → restart RDS (see "RDS is Down" section above)

# While investigating, disable all filters to prevent bad trades:
python3 feature_flags.py --disable signal_tier_1_enabled
python3 feature_flags.py --disable signal_tier_2_enabled
python3 feature_flags.py --disable signal_tier_3_enabled
python3 feature_flags.py --disable signal_tier_4_enabled
python3 feature_flags.py --disable signal_tier_5_enabled
```

---

## 🟠 Stuck Order: Order Pending >30 Min

**Symptom:** Algo placed order but never filled. You'll see:
```
[ALERT] Stuck Order
  Symbol: AAPL
  Alpaca Order ID: abc123def456
  Pending for: 35 minutes
  Signal Price: $150.25
  Current Price: $150.32
```

### Diagnosis (2 minutes)

```bash
# Check all pending orders
python3 order_reconciler.py --check

# Output shows discrepancies:
# [STUCK] AAPL - Order stuck for 35 minutes
# [FILLED_UNKNOWN] MSFT - Order filled in Alpaca but local says pending
# [ORPHANED] GOOGL - Order not found in Alpaca
```

### Recovery (Choose One)

**Option A: Cancel Stuck Order (Safest)**
```bash
# Cancel in Alpaca and mark locally:
python3 order_reconciler.py --cancel-order AAPL abc123def456

# Logs will show:
# [INFO] Cancelled AAPL order abc123def456 in Alpaca
# [INFO] Marked AAPL order as cancelled locally

# Then manually place a new order if needed:
python3 algo_order_executor.py --place-order AAPL BUY 100 @market
```

**Option B: Force Sell (If Order Filled But Not Known Locally)**
```bash
# If Alpaca filled but we didn't know:
python3 order_reconciler.py --force-sell AAPL 100

# This immediately sells 100 shares at market
# Logs show the action in audit trail
```

**Option C: Update From Alpaca (If Filled Unknown)**
```bash
# If order is actually filled in Alpaca, sync to local DB:
python3 order_reconciler.py --check
# This auto-detects FILLED_UNKNOWN and updates the database

# Verify:
psql -U stocks -h localhost -d stocks -c \
  "SELECT symbol, status, exit_price FROM algo_trades WHERE symbol='AAPL' ORDER BY created_at DESC LIMIT 1;"
```

**If Nothing Works (Order Is Truly Corrupted):**
```bash
# Manually mark as cancelled in database
psql -U stocks -h localhost -d stocks -c \
  "UPDATE algo_trades SET status='CANCELLED', exit_reason='Manual recovery - stuck order' WHERE alpaca_order_id='abc123def456';"

# Log the incident:
echo '[ERROR] Manual recovery: cancelled corrupted order abc123def456' >> /tmp/incidents.log

# Verify position is no longer open:
psql -U stocks -h localhost -d stocks -c \
  "SELECT symbol, status FROM algo_positions WHERE symbol='AAPL';"
```

---

## 🟠 Orphaned Order: Order Not Found in Alpaca

**Symptom:** We have a pending order locally but Alpaca has no record:
```
[ALERT] Orphaned Order
  Symbol: MSFT
  Alpaca Order ID: unknown
  Pending for: 8 minutes
  Likely cause: Network failure when placing order
```

### Diagnosis

```bash
# Confirm orphaned status
python3 order_reconciler.py --check

# Check if order is in Alpaca API at all:
python3 -c "from algo_alpaca import get_alpaca_client; c = get_alpaca_client(); print(c.list_orders(limit=100))"
```

### Recovery

**Option A: Cancel Locally (Safest)**
```bash
# If order never made it to Alpaca, just cancel locally
psql -U stocks -h localhost -d stocks -c \
  "UPDATE algo_trades SET status='CANCELLED', exit_reason='Never reached Alpaca - network failure' WHERE symbol='MSFT' AND status='PENDING';"

# Retry later if you want:
# The next algo run will generate a new signal for MSFT if it still qualifies
```

**Option B: Check Alpaca Directly, Then Sync**
```bash
# Maybe the order ID was just not recorded locally?
# Check Alpaca web UI or API for any open orders on MSFT:
python3 -c "
from algo_alpaca import get_alpaca_client
c = get_alpaca_client()
for order in c.list_orders(status='open'):
    if 'MSFT' in str(order.symbol):
        print(f'Found: {order.id} - {order.symbol} {order.side} {order.qty} @ {order.limit_price}')
"

# If found, manually update local DB with correct order ID:
psql -U stocks -h localhost -d stocks -c \
  "UPDATE algo_trades SET alpaca_order_id='correct-order-id' WHERE symbol='MSFT' AND status='PENDING';"
```

---

## 🟠 Slippage Spike: Execution Quality Degraded

**Symptom:** Fill prices are worse than expected:
```
[WARN] Slippage Alert
  Average slippage: -$0.35 (worse than usual -$0.07)
  Worst fill: TSLA @ $4289.82 (expected $4290.00 = -$0.18 slippage = 0.004%)
```

### Diagnosis (5 minutes)

```bash
# Check slippage report
python3 slippage_tracker.py --date 2026-05-09

# Output shows:
# Overall Statistics:
#   Trades: 5
#   Avg Slippage: $0.035
#   Worst Trade: TSLA -$0.18
#
# Per-Symbol Breakdown:
#   TSLA: 1 trades, avg -$0.18

# Is this just market volatility or a real problem?
# Check bid-ask spreads:
psql -U stocks -h localhost -d stocks -c \
  "SELECT symbol, open, high, low, close FROM price_daily WHERE symbol='TSLA' ORDER BY date DESC LIMIT 1;"
```

### Recovery

**If It's Just Bad Market Conditions:**
```bash
# Nothing to do - slippage happens. This is recorded for audit.
# Algo should still be profitable if trading edge is good.
echo 'Slippage spike noted. No action needed - market was just volatile.' >> /tmp/audit.log
```

**If Slippage is Consistently Bad (>5 ticks):**
```bash
# Problem might be:
# 1. Order size too large (moving the market)
# 2. Using market orders instead of limit orders
# 3. Placing orders during low-liquidity hours

# Temporary fix: Disable large positions via tier 5
python3 feature_flags.py --set rollout_tier5_pct rollout 50
# Now only 50% of signals get to Tier 5 (smaller positions)

# Measure improvement over next 5 trades:
python3 slippage_tracker.py --date 2026-05-09
# If slippage improves, keep it at 50%. If still bad, go to 25%.

# Root cause: Need to change order sizing or type (discuss with team)
```

---

## 🔴 Lambda Timeout: Algo Takes Too Long

**Symptom:** Algo Lambda returns before completing all 7 phases:
```
[ERROR] Task timed out after 900 seconds (15 minutes)
  Phase 5/7 incomplete - signal ranking timed out
```

### Diagnosis (10 minutes)

```bash
# Check Lambda logs
aws logs tail /aws/lambda/algo-orchestrator --follow --since 30m

# Look for timing info:
# [PERF] Phase 1: 2.3s
# [PERF] Phase 2: 1.1s
# [PERF] Phase 3: 45.2s ← This one is slow!
# [PERF] Phase 4: 120.3s ← This one is slooow!
# [PERF] Phase 5: timed out

# Check which phase is bottleneck:
# Phase 1-3: Usually fast (<60s total)
# Phase 4 (signal quality): Can be slow if many candidates
# Phase 5 (ranking): Can be slow if many candidates

# Check Lambda timeout setting:
aws lambda get-function-configuration --function-name algo-orchestrator \
  --query 'Timeout'
# Should be at least 900 (15 min)
```

### Recovery (Choose One)

**Option A: Increase Lambda Timeout (Quickest)**
```bash
# Update timeout to 30 minutes (1800 seconds)
aws lambda update-function-configuration \
  --function-name algo-orchestrator \
  --timeout 1800

# This is IaC change - update terraform/modules/compute/main.tf:
# resource "aws_lambda_function" "algo_orchestrator" {
#   ...
#   timeout = 1800  # was 900
# }

# Deploy:
gh workflow run deploy-algo-orchestrator.yml
```

**Option B: Increase Memory (Sometimes Faster)**
```bash
# More memory = more CPU. Try 2048 MB (was probably 1024 MB)
aws lambda update-function-configuration \
  --function-name algo-orchestrator \
  --memory-size 2048

# Update terraform:
# resource "aws_lambda_function" "algo_orchestrator" {
#   memory_size = 2048  # was 1024
# }

# Deploy:
gh workflow run deploy-algo-orchestrator.yml
```

**Option C: Optimize Slow Phase (Best Long-term)**
```bash
# If Phase 4 (signal quality) is slow:
# The SQS calculation is expensive for large candidate lists

# Disable tiers that generate too many candidates:
python3 feature_flags.py --set rollout_tier1_pct rollout 50
# Now only 50% of symbols go through Tier 1

# This reduces candidates → Phase 4 runs faster → no timeout

# Measure:
aws logs tail /aws/lambda/algo-orchestrator --follow --since 5m
# If [PERF] Phase 4 is now <30s, you've solved it!

# Re-enable gradually:
python3 feature_flags.py --set rollout_tier1_pct rollout 100
```

---

## 🔴 Lambda Out of Memory: Algo Crashes

**Symptom:** Lambda crashes without logs or timing info:
```
[ERROR] Process exited before completing request
Likely cause: Out of memory (process killed by kernel)
```

### Diagnosis (5 minutes)

```bash
# Check CloudWatch logs (may be incomplete)
aws logs tail /aws/lambda/algo-orchestrator --since 10m | tail -20

# Check Lambda configuration
aws lambda get-function-configuration --function-name algo-orchestrator \
  --query 'MemorySize'

# Typical: 1024 MB (1 GB)
# If running many candidates (50+), this can be insufficient
```

### Recovery

**Increase Lambda Memory:**
```bash
# Jump to 3008 MB (max efficient, about $0.10/run extra)
aws lambda update-function-configuration \
  --function-name algo-orchestrator \
  --memory-size 3008

# Update terraform and deploy:
gh workflow run deploy-algo-orchestrator.yml

# Re-run algo:
aws lambda invoke --function-name algo-orchestrator /tmp/out.json
```

**Or Reduce Candidate Load:**
```bash
# If you don't want to spend more on Lambda, reduce load:
python3 feature_flags.py --set rollout_tier1_pct rollout 50
# Now only 50% of symbols are evaluated

# This cuts memory usage by ~50%
```

---

## 🟡 Database Connection Fails: Lambda Can't Reach RDS

**Symptom:** All Lambda invocations fail immediately:
```
[ERROR] Unable to connect to database: Connection refused
  Host: stocks-data-rds.xxx.us-east-1.rds.amazonaws.com
  Port: 5432
```

### Diagnosis (5 minutes)

```bash
# 1. Check RDS status
aws rds describe-db-instances --db-instance-identifier stocks-data-rds \
  --query 'DBInstances[0].{Status:DBInstanceStatus,Engine:Engine}'

# Should show: Status = "available"

# 2. Check Lambda security group can reach RDS security group
aws ec2 describe-security-groups --group-ids sg-lambda --query 'SecurityGroups[0].IpPermissions'

# Should have rule allowing TCP 5432 to RDS security group

# 3. Test manually from your machine
psql -h stocks-data-rds.xxx.us-east-1.rds.amazonaws.com -U stocks -d stocks -c "SELECT 1;"
```

### Recovery

**If RDS is Down:**
```bash
# Restart RDS
aws rds reboot-db-instance --db-instance-identifier stocks-data-rds

# Takes 3-5 minutes. During this time:
# Lambda will fail. Disable algo:
python3 feature_flags.py --disable signal_tier_1_enabled

# Once RDS is back (Status = "available"):
aws rds describe-db-instances --db-instance-identifier stocks-data-rds \
  --query 'DBInstances[0].DBInstanceStatus'

# Re-enable:
python3 feature_flags.py --enable signal_tier_1_enabled

# Retry algo run:
aws lambda invoke --function-name algo-orchestrator /tmp/out.json
```

**If RDS is Up But Lambda Can't Reach It:**
```bash
# Problem: Lambda not in VPC, or security group rules wrong

# Check Lambda configuration:
aws lambda get-function-configuration --function-name algo-orchestrator \
  --query '{VpcConfig:VpcConfig, SecurityGroupIds:Environment.Variables.DB_HOST}'

# If VpcConfig is empty → Lambda needs VPC access (infrastructure issue)
# If VpcConfig exists → Check security group allows egress

# Temporary: Use Lambda layer to add debugging
# Long-term: Fix VPC/security group configuration (infrastructure work)
```

---

## 🟡 API Latency Spike: Website Slow

**Symptom:** Frontend pages loading slowly, API calls taking 5+ seconds:
```
GET /api/portfolio took 7.2 seconds
GET /api/signals took 12.1 seconds (should be <2s)
```

### Diagnosis (5 minutes)

```bash
# Check API Lambda logs
aws logs tail /aws/lambda/stocks-api --since 30m --grep "duration"

# Look for slow query patterns:
# [PERF] Query signal_quality_scores took 4.2s
# [PERF] Query algo_positions took 8.1s (too slow!)

# Check if database is the bottleneck:
psql -U stocks -h localhost -d stocks -c "SELECT datname, tup_fetched FROM pg_stat_database WHERE datname='stocks';"

# Check for slow queries in CloudWatch Insights:
# fields @timestamp, @duration, @message | stats avg(@duration) by @message | sort avg(@duration) desc
```

### Recovery

**If Database is Slow:**
```bash
# 1. Check table sizes (maybe one table is bloated?)
psql -U stocks -h localhost -d stocks -c \
  "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) FROM pg_tables WHERE schemaname != 'pg_catalog' ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC LIMIT 10;"

# 2. Check index usage:
psql -U stocks -h localhost -d stocks -c \
  "SELECT indexname, idx_scan FROM pg_stat_user_indexes ORDER BY idx_scan ASC LIMIT 10;"
# If idx_scan = 0 → Unused index (remove it)

# 3. Vacuum and analyze:
psql -U stocks -h localhost -d stocks -c "VACUUM ANALYZE;"

# 4. If still slow, enable query logging:
# ALTER SYSTEM SET log_min_duration_statement = 1000;  -- log queries >1s
# SELECT pg_reload_conf();
# Then: tail logs and identify slow queries
```

**If Lambda is Slow:**
```bash
# 1. Add more memory (more CPU)
aws lambda update-function-configuration \
  --function-name stocks-api \
  --memory-size 2048  # was 1024

# 2. Check if cold starts are the issue:
# CloudWatch Insights: fields @duration | stats avg(@duration) by @initDuration > 0
# If initDuration > 1s, you have cold start problem
# Solution: Use Provisioned Concurrency (cost + complexity tradeoff)

# 3. Add caching layer (Redis):
# Already in docker-compose, but not wired up in Lambda
# This is architectural work (not runbook-level)
```

---

## 🟢 All Quiet: Normal Operational Checks

**When Everything Works, You Should Still Check:**

```bash
# Run daily health checks (add to calendar reminder 8am ET)
python3 audit_dashboard.py --loaders
# Should show all loaders PASS'd with fresh timestamps

python3 order_reconciler.py --check
# Should show: "All orders reconciled [OK]"

python3 slippage_tracker.py --date $(date +%Y-%m-%d)
# Should show: avg slippage between -$0.05 and +$0.10

# Check CloudWatch alarms
aws cloudwatch describe-alarms --alarm-names stocks-rds-cpu \
  --query 'MetricAlarms[0].StateValue'
# Should be: OK

# Check Lambda performance
aws logs insights query \
  --log-group-name /aws/lambda/algo-orchestrator \
  --query 'fields @duration | stats avg(@duration)' \
  --start-time 1h
# Should be: <30s
```

---

## Emergency Contacts & Escalation

**If Runbook Procedures Don't Fix It:**

1. **Check logs comprehensively:**
   ```bash
   aws logs tail /aws/lambda/algo-orchestrator --since 1h
   aws logs tail /aws/ecs/stocks-loaders --since 1h
   aws logs tail /aws/lambda/stocks-api --since 1h
   ```

2. **Post incident summary:**
   ```bash
   echo '{
     "incident": "describe the problem",
     "time": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
     "steps_taken": ["disabled tier X", "restarted RDS", ...],
     "current_status": "investigating | resolved | escalated",
     "notes": "any additional context"
   }' >> /tmp/incidents.json
   ```

3. **Escalate if needed:**
   - Data source down (IEX Cloud, Yahoo Finance) → Check their status page
   - AWS infrastructure issue → AWS Support case
   - Code logic error → Pull latest code, run locally to debug

---

## Key Runbook Principles

✅ **DO:**
- Use feature flags to disable broken components (no redeploy needed)
- Check logs for root cause (don't guess)
- Document what you did (for post-mortem)
- Test recovery locally first when possible
- Keep incident timeline (for learning)

❌ **DON'T:**
- Hard-delete data without backup (VACUUM only removes space, DELETE is permanent)
- Force-kill processes (let them timeout gracefully)
- Restart services without checking dependencies
- Ignore strange values (investigate root cause, not just symptoms)
- Mix multiple fixes (change one thing at a time, measure impact)

---

**This is your safety net. Print it. Keep it by your desk. You've got this.**
