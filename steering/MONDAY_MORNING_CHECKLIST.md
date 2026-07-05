# Monday Morning Deployment Checklist (2026-07-07)

**Status:** System stalled Friday evening due to stuck loaders. Recovery needed before live trading.

---

## Pre-Market (Before 9:30 AM ET)

### 9:15 AM — System Health Check (5 min)

```bash
# 1. Check if loaders are running and healthy
aws ecs list-tasks --cluster algo-loaders --launch-type EC2 | jq '.taskArns | length'

# 2. Verify data freshness (should be same day)
psql $DATABASE_URL -c "
  SELECT table_name, MAX(created_at) as last_update, 
         CURRENT_TIMESTAMP - MAX(created_at) as age
  FROM (
    SELECT 'algo_trades' as table_name, MAX(created_at) FROM algo_trades
    UNION ALL SELECT 'buy_sell_daily', MAX(created_at) FROM buy_sell_daily
    UNION ALL SELECT 'market_health_daily', MAX(created_at) FROM market_health_daily
  ) t GROUP BY table_name ORDER BY last_update DESC
"

# 3. Check circuit breaker (should allow trading, not halted)
psql $DATABASE_URL -c "
  SELECT trading_halted, halt_reason, halted_at FROM circuit_breaker_status LIMIT 1
"

# 4. Check dashboard (should load without "data unavailable" errors)
curl -s http://localhost:5000/api/algo/market-health | jq '.data_unavailable'
```

**Go/No-Go Decision:**
- ✅ GO if: All data fresh (< 4 hours old), circuit breaker allows trading, dashboard loads
- ❌ NO-GO if: Any data > 4 hours old, circuit breaker halted, dashboard errors

### 9:20 AM — If NO-GO, Emergency Recovery

```bash
# ONLY if data is stale or circuit breaker halted:

# 1. Kill stuck loaders (if any still running > 2 hours)
STUCK_TASKS=$(aws ecs list-tasks --cluster algo-loaders | jq -r '.taskArns[]')
for TASK in $STUCK_TASKS; do
  STARTED=$(aws ecs describe-tasks --cluster algo-loaders --tasks $TASK | \
    jq -r '.tasks[0].createdAt')
  AGE_HOURS=$(( ($(date +%s) - $(date -d "$STARTED" +%s)) / 3600 ))
  if [ $AGE_HOURS -gt 2 ]; then
    echo "Killing stuck task: $TASK (age: ${AGE_HOURS}h)"
    aws ecs stop-task --cluster algo-loaders --task $TASK
  fi
done

# 2. Manually restart critical loaders
echo "Restarting critical loader chain..."
python loaders/load_market_health_daily.py --parallelism 4
python loaders/load_market_exposure_daily.py
python loaders/load_signal_quality_scores.py --parallelism 4

# 3. Verify restart succeeded
echo "Verifying restart..."
psql $DATABASE_URL -c "
  SELECT table_name, MAX(created_at) FROM algo_trades, buy_sell_daily, market_health_daily
  GROUP BY table_name
"

# 4. Re-check circuit breaker
psql $DATABASE_URL -c "SELECT trading_halted, halt_reason FROM circuit_breaker_status"
```

### 9:25 AM — Final Verification

```bash
# Run orchestrator in dry-run mode to validate pipeline
python orchestrator/main.py --dry-run

# Expected output:
# - All 9 phases validate
# - No data quality errors
# - Position sizing calculations OK
# - Trading signals generated
```

**Decision:**
- ✅ If dry-run succeeds: Proceed to market open
- ❌ If dry-run fails: Halt trading, investigate in detail

---

## During Market Hours (9:30 AM - 4:00 PM ET)

### Every 30 minutes — Monitor Loader Status

```bash
# Check for any newly stuck loaders
psql $DATABASE_URL -c "
  SELECT loader_name, status, started_at, 
         EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - started_at)) / 3600 as hours_running
  FROM data_loader_status
  WHERE status = 'RUNNING'
  ORDER BY started_at ASC
"

# Alert if any loader running > 2 hours
```

### EOD (4:00 PM ET) — Pre-Evening-Run Prep

1. Verify all morning loaders completed successfully
2. Check that positions were updated with latest data
3. Verify 5:30 PM orchestrator can run

---

## End-of-Day (5:30 PM ET)

### Manual Orchestrator Run (If Needed)

```bash
# Trigger orchestrator manually if EventBridge rule didn't fire
python orchestrator/main.py --force

# Check results
psql $DATABASE_URL -c "
  SELECT phase, status, started_at, completed_at, error_message
  FROM orchestrator_execution_log
  ORDER BY phase_number DESC
  LIMIT 10
"
```

---

## Alert Thresholds (Oncall Wakeup Conditions)

Page oncall if ANY of these occur:

1. **Any loader running > 2 hours**
   - Likely stuck/hung
   - Action: Kill task and restart

2. **Data staleness > 4 hours**
   - Critical loaders not running
   - Action: Check EventBridge rules, check ECS cluster

3. **Circuit breaker halted trading**
   - Data quality issue or safety gate triggered
   - Action: Check halt reason, investigate root cause

4. **Dashboard showing "data unavailable"**
   - API layer issue or upstream loader failure
   - Action: Check load_* logs and database error messages

5. **Position count decreases unexpectedly**
   - Possible data loss or corruption
   - Action: Run reconciliation query

---

## Rollback Procedure (If Critical Issue)

If the system is behaving unexpectedly and you cannot diagnose:

```bash
# 1. Halt trading immediately
psql $DATABASE_URL -c "
  UPDATE circuit_breaker_status 
  SET trading_halted = true, halt_reason = 'Emergency halt - investigating'
  WHERE circuit_breaker_id = 1
"

# 2. Disable 5:30 PM orchestrator run
aws events disable-rule --name 'algo-orchestrator-evening-run'

# 3. Keep system running but in diagnostic mode
# (don't kill processes, collect logs)

# 4. Contact development team
echo "System halted. Collecting diagnostics..."
aws logs get-log-events --log-group-name /ecs/algotrade-loaders \
  --log-stream-name 'latest' > /tmp/ecs-logs.txt
echo "Logs saved to /tmp/ecs-logs.txt for analysis"
```

---

## Success Criteria

System is ready for live trading when:

- ✅ All data tables updated within last 2 hours
- ✅ Circuit breaker allows trading (not halted)
- ✅ Dashboard loads without errors
- ✅ Orchestrator dry-run succeeds
- ✅ No loaders stuck > 2 hours
- ✅ No ERROR/FATAL messages in logs (only WARN)
- ✅ Positions count > 0
- ✅ Latest trading signals available

---

## Contacts & Resources

**Deployment Issues:**
- Check `/steering/OPERATIONS.md` for CI/CD procedures
- Check `/steering/COMMON_OPERATIONS.md` for troubleshooting

**Database Issues:**
- Check `/steering/DATABASE_AND_ENVIRONMENTS.md` for connection help
- RDS endpoint: Check AWS RDS console

**AWS Infrastructure:**
- EventBridge rules: AWS Lambda console → EventBridge rules
- ECS tasks: AWS ECS console → Cluster: algo-loaders
- CloudWatch logs: AWS CloudWatch → Log Groups → /ecs/algotrade-loaders

**Escalation:**
- If stuck > 30 min: Halt trading, collect logs, create incident
- If data loss: Trigger recovery procedures in GOVERNANCE.md
