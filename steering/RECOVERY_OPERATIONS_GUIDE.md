# Recovery Operations Guide

**For:** Operations Team, On-Call Engineers  
**Purpose:** Quick reference for handling and recovering from system failures  
**Last Updated:** July 19, 2026

---

## Quick Failure Response Flowchart

```
System Alert Received
│
├─ Is trading halted? (check DynamoDB halt_flag)
│  ├─ YES: Go to section 1.1 (Halt Flag Recovery)
│  └─ NO: Continue
│
├─ Dashboard shows "Data Not Available"?
│  ├─ YES: Go to section 2.1 (Data Freshness)
│  └─ NO: Continue
│
├─ Orchestrator Phase Failed?
│  ├─ Phase 1-5: Go to section 3.x (Phase-specific)
│  └─ Phase 6-9: Go to section 4.x (Trading phases)
│
└─ Other: Check logs and section 5 (General Troubleshooting)
```

---

## 1. Halt Flag Issues

### 1.1 Trading Halted - Stale Data Detected

**Symptoms:**
- Dashboard shows "Trading Halted" message
- Orchestrator logs: `[HALT_FLAG_ACTIVE]`
- No new orders submitted despite market being open

**Root Causes:**
- Data older than thresholds (price >2h old, technical indicators >4h old)
- Market regime halted trading (volatility too high)
- Circuit breaker triggered (portfolio loss too large)

**Recovery Steps:**

1. **Check why halt was set:**
   ```sql
   SELECT halt_flag, triggered_at, reason, halt_count 
   FROM algo_orchestrator_state 
   WHERE key = 'orchestrator_halt';
   ```

2. **Identify the issue:**
   - If `reason` contains "Data freshness": Go to section 2 (Data Freshness)
   - If `reason` contains "Circuit breaker": Go to section 3 (Circuit Breaker)
   - If `reason` contains "Market regime": Market volatility high, wait for reset

3. **Fix the root cause:**
   - For stale data: Restart loaders manually
   - For circuit breaker: Wait for auto-reset (next trading day 9:30 AM)
   - For market regime: Monitor and resume when regime stabilizes

4. **Clear halt flag (only after fixing root cause):**
   ```sql
   UPDATE algo_orchestrator_state 
   SET halt_flag = FALSE, 
       reason = 'Manually cleared by operator after [fixing specific issue]',
       reset_at = now()
   WHERE key = 'orchestrator_halt';
   ```

5. **Verify trading resumes:**
   - Check dashboard within 2 min for normal operation
   - Monitor Phase 5 signals
   - Watch Phase 8 order execution

---

### 1.2 Halt Flag Stuck from Prior Day

**Symptoms:**
- Halt flag active, but `triggered_at` is from yesterday
- Data is fresh today, but halt still blocking entry
- Error: `[PROACTIVE_CLEAR] Halt from {prior_date} detected at orchestrator startup`

**Root Cause:** System didn't auto-clear halt at market open (9:30 AM ET).

**Recovery Steps:**

1. **Verify time is past market open:**
   ```bash
   # Check current time in ET
   python -c "from utils.infrastructure import EASTERN_TZ; print(datetime.now(EASTERN_TZ))"
   ```

2. **Clear the stale halt:**
   ```sql
   UPDATE algo_orchestrator_state 
   SET halt_flag = FALSE, 
       reason = 'Auto-cleared: Halt from prior trading day',
       reset_at = now()
   WHERE key = 'orchestrator_halt' 
     AND triggered_at::date < now()::date;
   ```

3. **Restart orchestrator** (if running in Lambda/local dev):
   - AWS: Wait for next scheduled run (EventBridge will refresh)
   - Local: `python start_dashboard_dev.py` (will restart orchestrator)

---

### 1.3 Halt Flag Check Failed (DynamoDB Unavailable)

**Symptoms:**
- Orchestrator logs: `[CRITICAL] Could not check halt flag in DynamoDB`
- Alert: "DynamoDB halt flag check failed. Emergency halt mechanism DISABLED."
- Orchestrator stops trading (fail-closed)

**Root Cause:** DynamoDB unreachable, AWS credentials invalid, or region misconfigured.

**Recovery Steps:**

1. **Verify DynamoDB is accessible:**
   ```bash
   aws dynamodb describe-table \
     --table-name algo_orchestrator_state \
     --region us-east-1
   ```

2. **Check AWS credentials:**
   ```bash
   aws sts get-caller-identity
   ```

3. **If credentials expired/invalid:**
   - Regenerate credentials in AWS IAM
   - Update in AWS Secrets Manager if using credential rotation
   - Verify ORCHESTRATOR_EXECUTION_ROLE has DynamoDB permissions

4. **If DynamoDB down:**
   - Check AWS service health page
   - Manually verify with boto3:
     ```python
     import boto3
     dynamodb = boto3.resource('dynamodb')
     table = dynamodb.Table('algo_orchestrator_state')
     print(table.table_status)  # Should be 'ACTIVE'
     ```

5. **Resume trading (after fixing):**
   - Restart orchestrator/dashboard
   - Orchestrator will attempt halt_flag check
   - If successful, trading resumes normally

---

## 2. Data Freshness Issues

### 2.1 Dashboard Shows "Data Not Available"

**Symptoms:**
- Price panel: "Data not available"
- Technical indicators: "Data not available"
- All data panels empty

**Root Causes:**
- Loaders haven't completed their daily run
- Loader failures (crash, API error, timeout)
- Database connectivity issue

**Recovery Steps:**

1. **Check loader status:**
   ```sql
   SELECT loader_name, status, last_updated, row_count, error_message
   FROM data_loader_status
   ORDER BY last_updated DESC;
   ```

2. **Check which loaders failed:**
   - Status = "FAILED": See error_message for details
   - Status = "RUNNING": Wait (loaders still executing)
   - last_updated > 4 hours ago: Loaders haven't run today

3. **If loaders failed, check logs:**
   ```bash
   # AWS: Check CloudWatch logs for ECS tasks
   aws logs tail /ecs/algo-price-loader --follow
   
   # Local: Check console output from orchestrator
   ```

4. **Manually trigger loaders:**
   ```bash
   # Morning data (prices + technical indicators)
   python3 scripts/run_local_orchestrator.py --morning
   
   # Or trigger specific loader
   python3 scripts/trigger_morning_pipeline.py
   ```

5. **Verify data loaded:**
   - Wait 5-10 min for loader to complete
   - Dashboard should show prices within 1-2 min
   - Check data freshness:
     ```sql
     SELECT COUNT(*) as prices_loaded, MAX(last_updated) as latest
     FROM prices
     WHERE last_updated > now() - interval '1 hour';
     ```

6. **If still no data:**
   - Check orchestrator logs for errors
   - Verify database connectivity
   - Check API credentials (Alpaca, SEC, etc.)

---

### 2.2 Data Older Than Expected (Stale Data)

**Symptoms:**
- Prices last updated 3+ hours ago
- Technical indicators older than 4 hours
- Orchestrator Phase 1 sets halt flag

**Root Causes:**
- EventBridge scheduler disabled or misconfigured
- Loader failed silently (shouldn't happen but verify)
- Previous orchestrator run didn't complete

**Recovery Steps:**

1. **Check EventBridge schedule:**
   ```bash
   aws scheduler get-schedule-group \
     --name algo-pipeline-schedules
   
   # List all schedules
   aws scheduler list-schedules \
     --group-name algo-pipeline-schedules
   ```

2. **Verify schedules are enabled:**
   - Morning pipeline: Should run 2:00 AM ET Mon-Fri
   - EOD pipeline: Should run 4:05 PM ET Mon-Fri
   - If disabled: Contact admin or enable via console

3. **Manually run loaders:**
   ```bash
   python3 scripts/run_local_orchestrator.py --morning
   python3 scripts/run_local_orchestrator.py --afternoon
   python3 scripts/run_local_orchestrator.py --evening
   ```

4. **Monitor loader progress:**
   ```bash
   python3 scripts/monitor_data_staleness.py --watch 30
   # Shows real-time staleness check every 30 seconds
   ```

5. **If loaders hang:**
   - Check for stuck processes:
     ```bash
     python3 scripts/run_local_orchestrator.py --run-all --kill-hung-loaders
     ```
   - Or manually kill:
     ```bash
     # AWS ECS
     aws ecs list-tasks --cluster algo-cluster --desired-status RUNNING
     aws ecs stop-task --cluster algo-cluster --task <task-arn>
     
     # Local
     pkill -f "python.*run_local_orchestrator"
     ```

---

### 2.3 Loader Timeout or API Error

**Symptoms:**
- Loader status shows: "FAILED"
- Error: "HTTP 500", "Connection timeout", "Rate limited"
- Specific loader affected (e.g., price_loader, technical_indicators_loader)

**Recovery Steps:**

1. **Check loader error details:**
   ```sql
   SELECT loader_name, status, error_message, attempted_at
   FROM data_loader_status
   WHERE loader_name = 'price_loader' 
   ORDER BY attempted_at DESC LIMIT 5;
   ```

2. **Identify if error is transient:**
   - HTTP 500: API server error → Wait, retry
   - Timeout: Network or service slow → Wait, retry
   - Rate limited: API quota exceeded → Wait (usually 1 hour)
   - Invalid credentials: Won't recover on its own → Fix credentials

3. **For transient errors, retry:**
   ```bash
   python3 scripts/run_local_orchestrator.py --morning --loader=price_loader
   ```

4. **For credential errors:**
   - Update credentials in AWS Secrets Manager
   - For local dev: Update `.env` file
   - Restart orchestrator

5. **If specific API is down:**
   - Check API status page (e.g., Alpaca status.alpaca.markets)
   - Wait for API recovery
   - Retry loader after 5-10 min

---

## 3. Database Issues

### 3.1 "Connection Refused" Error

**Symptoms:**
- Orchestrator logs: `psycopg2.OperationalError: connection refused`
- Loaders failing with database errors
- All operations fail to query/write database

**Root Causes:**
- PostgreSQL container/service not running
- Wrong hostname or port in connection string
- Database crashed and needs restart

**Recovery Steps:**

1. **Check if PostgreSQL is running:**
   ```bash
   # Local
   pg_isready -h localhost -p 5432
   
   # AWS RDS
   aws rds describe-db-instances --db-instance-identifier algo-db --query 'DBInstances[0].DBInstanceStatus'
   ```

2. **If not running, start it:**
   ```bash
   # Local (Docker)
   docker start algo-postgres
   
   # AWS RDS (restart via console or CLI)
   aws rds reboot-db-instance --db-instance-identifier algo-db
   ```

3. **Verify connection works:**
   ```bash
   python3 -c "import psycopg2; psycopg2.connect('dbname=stocks user=stocks host=localhost')"
   # Should complete without error
   ```

4. **If still failing, check connection string:**
   ```bash
   # Verify environment variables
   echo $PGHOST $PGPORT $PGUSER $PGDATABASE
   
   # Or check hard-coded values in code
   grep -r "psycopg2.connect" algo/
   ```

5. **Restart orchestrator/loaders after fix:**
   ```bash
   python3 start_dashboard_dev.py
   ```

---

### 3.2 Query Timeout

**Symptoms:**
- Orchestrator logs: `psycopg2.OperationalError: connection timeout`
- Specific query taking >30 seconds
- Phase hangs and doesn't complete

**Root Causes:**
- Database CPU/load too high
- Query hitting full table scan instead of index
- Connection pool exhausted (hung loaders holding connections)

**Recovery Steps:**

1. **Check database load:**
   ```sql
   SELECT datname, count(*) as connections 
   FROM pg_stat_activity 
   GROUP BY datname;
   ```

2. **Check for hung queries:**
   ```sql
   SELECT pid, usename, state, query, query_start
   FROM pg_stat_activity
   WHERE state != 'idle' 
   ORDER BY query_start;
   ```

3. **Kill hung queries (if safe):**
   ```sql
   SELECT pg_terminate_backend(pid) 
   FROM pg_stat_activity 
   WHERE usename = 'stocks' 
     AND state = 'active'
     AND query_start < now() - interval '10 min';
   ```

4. **Check for hung loaders holding connections:**
   ```bash
   # AWS ECS
   aws ecs list-tasks --cluster algo-cluster --desired-status RUNNING
   
   # See Section 1 for killing hung loaders
   ```

5. **Increase connection timeout (if needed):**
   - Edit orchestrator config
   - Increase timeout to 60s (from 30s)
   - Monitor whether queries legitimately need more time

---

### 3.3 Disk Full Error

**Symptoms:**
- Orchestrator logs: `FATAL: disk full`
- Loaders fail to write data
- Database read-only

**Root Causes:**
- Log files consuming disk space
- Database table bloat
- Not enough disk allocated for expected data volume

**Recovery Steps:**

1. **Check available disk space:**
   ```bash
   # Local
   df -h /var/lib/postgresql
   
   # AWS RDS
   aws rds describe-db-instances --db-instance-identifier algo-db --query 'DBInstances[0].AllocatedStorage'
   
   # Also check actual usage:
   aws cloudwatch get-metric-statistics \
     --namespace AWS/RDS \
     --metric-name DatabaseConnections \
     --dimensions Name=DBInstanceIdentifier,Value=algo-db \
     --start-time 2026-07-19T00:00:00Z \
     --end-time 2026-07-19T23:59:59Z \
     --period 3600
   ```

2. **Free up disk space (in priority order):**
   ```bash
   # 1. Rotate and delete old logs
   rm -f /var/log/algo/*.log.* 
   # (Keep recent logs for 7 days)
   
   # 2. Truncate PostgreSQL WAL archive
   sudo systemctl stop postgresql
   sudo rm -f /var/lib/postgresql/*/pg_wal/archive_status/*
   sudo systemctl start postgresql
   
   # 3. Vacuum database
   psql stocks -c "VACUUM ANALYZE;"
   ```

3. **Expand disk allocation:**
   ```bash
   # AWS RDS: Can't shrink, only expand
   aws rds modify-db-instance \
     --db-instance-identifier algo-db \
     --allocated-storage 200 \
     --apply-immediately
   # (Wait 5-10 min for resize)
   
   # Local Docker: Expand container storage limits
   ```

4. **Resume operations:**
   - Database should become writable
   - Retry failed loaders
   - Monitor disk usage going forward

---

## 4. API and Broker Failures

### 4.1 Alpaca API Returning Errors

**Symptoms:**
- Orchestrator logs: `HTTP 500`, `HTTP 503`, or `Connection timeout`
- Phase 6 (Exit Execution) failing
- Phase 3 (Position Monitor) unable to get positions

**Root Causes:**
- Alpaca API down for maintenance
- Network connectivity issue
- Alpaca credentials invalid/expired

**Recovery Steps:**

1. **Check Alpaca status:**
   - Visit: https://status.alpaca.markets/
   - Check for maintenance or incidents

2. **Verify credentials:**
   ```bash
   # Local: Check environment variables
   echo $APCA_API_KEY_ID $APCA_API_SECRET_KEY
   
   # AWS: Check Secrets Manager
   aws secretsmanager get-secret-value --secret-id algo/alpaca
   ```

3. **Test connectivity:**
   ```python
   from alpaca.trading.client import TradingClient
   client = TradingClient(api_key="...", secret_key="...")
   account = client.get_account()
   print(account)
   ```

4. **If API down:**
   - Wait for recovery (typically <30 min for maintenance)
   - Retry loaders after 5-10 min

5. **If credentials invalid:**
   - Regenerate API keys in Alpaca dashboard
   - Update in AWS Secrets Manager
   - Verify both read and trade permissions granted

6. **If network issue:**
   - Check DNS resolution: `nslookup api.alpaca.markets`
   - Check network connectivity: `curl -I https://api.alpaca.markets/v2/account`
   - Verify egress IP whitelist (if applicable)

---

### 4.2 Order Submission Fails

**Symptoms:**
- Phase 8 logs: `Order submission failed`
- Position not opened or closed
- Error: "Insufficient buying power", "Symbol not found", "Market order in after-hours"

**Root Causes:**
- Market hours check failed
- Not enough cash for order
- Invalid symbol
- Order placed in after-hours (4 PM - 9:30 AM ET)

**Recovery Steps:**

1. **Check if market is open:**
   ```python
   from algo.infrastructure import MarketCalendar
   from datetime import datetime, timezone
   from utils.infrastructure import EASTERN_TZ
   
   now_et = datetime.now(EASTERN_TZ)
   is_open = MarketCalendar.is_market_open(now_et)
   print(f"Market open: {is_open}")
   ```

2. **Verify cash available:**
   ```sql
   SELECT cash, equity 
   FROM algo_positions_summary 
   ORDER BY updated_at DESC LIMIT 1;
   ```

3. **Check if symbol is valid:**
   ```python
   from alpaca.trading.client import TradingClient
   client = TradingClient(...)
   asset = client.get_asset('AAPL')
   print(asset.tradable)
   ```

4. **Verify order size is valid:**
   - Order must be > $1 (minimum order value)
   - Can't use full cash (need margin buffer)
   - Current algo uses $x per position limit (see config)

5. **If order failed but cash reserved:**
   ```sql
   SELECT position_id, symbol, shares, cost_basis
   FROM algo_positions
   WHERE status = 'pending' OR status = 'opening';
   ```

6. **Manual cleanup if needed:**
   ```bash
   # Cancel stuck orders in Alpaca
   python3 -c "
   from alpaca.trading.client import TradingClient
   client = TradingClient(...)
   orders = client.get_orders(status='open')
   for order in orders:
       client.cancel_order_by_id(order.id)
       print(f'Cancelled {order.id}')
   "
   ```

---

## 5. Performance and Resource Issues

### 5.1 Orchestrator Phase Hangs

**Symptoms:**
- Orchestrator running for >2 hours
- Specific phase not completing
- No new log entries

**Root Causes:**
- Infinite loop in phase logic (shouldn't happen but verify)
- Deadlock on database locks
- Waiting for external API that never responds

**Recovery Steps:**

1. **Identify which phase is hung:**
   ```bash
   # Check orchestrator logs
   grep "PHASE.*started\|PHASE.*completed" orchestrator.log | tail -20
   ```

2. **Get process ID:**
   ```bash
   ps aux | grep orchestrator
   # Note the PID
   ```

3. **Check what it's doing:**
   ```bash
   # See open files/connections
   lsof -p <PID> | grep -E "REG|SOCK"
   
   # See network connections
   netstat -anp | grep <PID>
   ```

4. **If hung on network:**
   - Phase is waiting for API response
   - Usually safe to kill: next run will retry
   - Kill phase: `kill -TERM <PID>` (graceful) or `kill -9 <PID>` (force)

5. **If hung on database:**
   - May have acquired lock
   - Query may be in progress
   - Verify with:
     ```sql
     SELECT pg_terminate_backend(pid) 
     FROM pg_stat_activity 
     WHERE usename = 'stocks' 
       AND query_start < now() - interval '1 hour';
     ```

6. **Restart orchestrator:**
   ```bash
   # Local
   python3 start_dashboard_dev.py
   
   # AWS (will auto-restart on next scheduled run)
   # Or manually trigger: aws lambda invoke --function-name algo-orchestrator --payload '{}' out.json
   ```

---

### 5.2 High Memory Usage or OOM

**Symptoms:**
- Container memory limit exceeded
- Orchestrator logs: `MemoryError` or `Out of memory`
- Phase 7 (Signal Ranking) crashes

**Root Causes:**
- Phase 7 ranking 4800+ stocks at once
- Data frame too large in memory
- Memory leak in phase logic

**Recovery Steps:**

1. **Check memory usage:**
   ```bash
   # Local
   ps aux | grep orchestrator
   # Check RSS column
   
   # AWS ECS
   aws cloudwatch get-metric-statistics \
     --namespace AWS/ECS \
     --metric-name MemoryUtilization \
     --dimensions Name=ServiceName,Value=algo-orchestrator \
     --start-time 2026-07-19T00:00:00Z \
     --end-time 2026-07-19T23:59:59Z \
     --period 300
   ```

2. **Increase memory allocation:**
   ```bash
   # Local (Docker): Edit docker-compose or container settings
   # AWS ECS: Update task definition memory limit (1GB → 2GB)
   ```

3. **Optimize memory usage:**
   - Phase 7 can be split into batches (rank 500 stocks at a time)
   - Add garbage collection: `import gc; gc.collect()`
   - Stream large data instead of loading all at once

4. **Restart orchestrator:**
   - Stop current run (if hung)
   - Increase memory
   - Restart

---

## 6. General Troubleshooting

### 6.1 How to Check System Health

**Quick Health Check Command:**
```bash
python scripts/check_system_health.py
```

This checks:
- Database connectivity
- Dev server availability
- Orchestrator execution status
- Dashboard module imports
- Data freshness (all loaders)
- Lock status
- Halt flag status

**Expected Output:**
```
✓ Database: Connected (8.6M prices)
✓ Dev Server: Running on localhost:3001
✓ Orchestrator: Last run 2h ago (completed successfully)
✓ Dashboard Modules: All imports OK
✓ Data Freshness: All current (last 30 min)
✓ Locks: No stale locks detected
✓ Halt Flag: Not set
```

### 6.2 Viewing Logs

**Local Dashboard Logs:**
```bash
# Most recent logs
tail -f ~/.algo/orchestrator.log

# Last 100 lines
tail -100 ~/.algo/orchestrator.log

# Search for errors
grep -i error ~/.algo/orchestrator.log
```

**AWS Lambda Logs:**
```bash
# View logs in CloudWatch
aws logs tail /aws/lambda/algo-orchestrator --follow

# Search for specific error
aws logs filter-log-events \
  --log-group-name /aws/lambda/algo-orchestrator \
  --filter-pattern "ERROR"
```

**ECS Task Logs:**
```bash
# Get task logs
aws logs tail /ecs/algo-price-loader --follow

# Get logs for specific date range
aws logs filter-log-events \
  --log-group-name /ecs/algo-price-loader \
  --start-time 1689811200000 \
  --end-time 1689897600000
```

### 6.3 Contacting Support

If issue not resolved by above steps:

1. **Gather diagnostics:**
   ```bash
   python scripts/check_system_health.py > diagnostics.txt
   tail -1000 ~/.algo/orchestrator.log >> diagnostics.txt
   ```

2. **Collect recent alerts:**
   ```sql
   SELECT * FROM algo_alerts 
   ORDER BY created_at DESC LIMIT 20;
   ```

3. **Check error patterns:**
   ```bash
   grep -i "error\|failed\|exception" orchestrator.log \
     | tail -50 \
     | sort | uniq -c | sort -rn
   ```

4. **Provide to support team:**
   - Attach diagnostics.txt
   - Attach last 100 lines of orchestrator.log
   - Describe: What were you trying to do when failure occurred
   - Describe: Expected vs actual behavior

---

## 7. Prevention Measures

### Daily Monitoring

- [ ] Dashboard loads without "Data Not Available"
- [ ] Price data refreshed in last 2 hours
- [ ] No active halt flags
- [ ] No repeated errors in logs

### Weekly Tasks

- [ ] Review orchestrator success rate: `SELECT COUNT(*) as runs, SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as succeeded FROM algo_orchestrator_runs WHERE started_at > now() - '7 days'::interval;`
- [ ] Check alert frequency: Any new alert types?
- [ ] Verify database size growing normally
- [ ] Test manual loader trigger (one loader)

### Monthly Tasks

- [ ] Run chaos engineering tests: `python scripts/failure_scenario_simulator.py --all`
- [ ] Review recovery procedures (update if changed)
- [ ] Capacity planning: Will current hardware handle 10x more data?
- [ ] Update runbooks based on new failure patterns

---

## 8. Emergency Contacts

**On-Call Engineer:** [Your name/contact]  
**Database Admin:** [Name/contact]  
**Cloud Ops (AWS):** [Name/contact]  
**Broker Support (Alpaca):** support@alpaca.markets | 24/7

---

## 9. Post-Recovery Checklist

After recovering from any failure, verify:

- [ ] Halt flag cleared (if it was set)
- [ ] Data freshness within acceptable thresholds
- [ ] Positions match Alpaca (Phase 4 reconciliation)
- [ ] No orphaned orders or trades
- [ ] Dashboard showing prices and portfolio normally
- [ ] No new errors in logs
- [ ] Alert count back to normal

Only after all checks pass: **Resume normal trading**

