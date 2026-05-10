# Connection Pool Monitoring & RDS Connection Limits

## Overview

This document covers monitoring database connection pools to detect and prevent connection exhaustion.

## The Problem

PostgreSQL has a `max_connections` limit (typically 100-1000). When all connections are in use, new connection attempts fail with:

```
FATAL: too many connections
FATAL: remaining connection slots are reserved for non-replication superuser connections
```

With 40+ loaders × 8 workers = 320 potential connections, we need visibility into:
- Current connection count
- Wait times for connection acquisition
- Failed connection attempts
- Pool exhaustion events

## Solution Architecture

```
Loaders (40+ × 8 workers = 320 potential connections)
    ↓ (multiplex to)
RDS Proxy (max 100 connections to RDS)
    ↓ (handles pooling, multiplexing)
RDS PostgreSQL (max_connections ~100-200)
    ↓ (monitored by)
CloudWatch Alarms (alert on >80% utilization)
```

## Monitoring Components

### 1. CloudWatch Alarms (Terraform)

Automatically deployed with database module:

| Alarm | Threshold | Triggered By |
|-------|-----------|--------------|
| `rds-connection-ratio-high` | >70% of max | Active connections / max |
| `rds-too-many-connections` | Any occurrence | Parsed from RDS logs |
| `rds-connection-timeout` | Any timeout | Parsed from RDS logs |

Check alarm status:

```bash
aws cloudwatch describe-alarms \
  --alarm-names algo-rds-connection-ratio-high-prod \
  --query 'MetricAlarms[0].StateValue'
```

### 2. Application-Level Monitoring

Application code monitors connection wait times and failures:

```python
from connection_pool_monitor import get_pool_monitor

monitor = get_pool_monitor("loader_pool")

# Record actual usage
monitor.record_active_connections(count=45, max_connections=100)

# Track wait times
start = time.time()
conn = db.get_connection()
wait_ms = (time.time() - start) * 1000
monitor.record_connection_wait(wait_ms)

# Track failures
try:
    conn = db.get_connection(timeout=2)
except Exception as e:
    monitor.record_failed_connection(str(e))

# Check health
stats = monitor.get_stats()
print(f"Utilization: {stats['utilization_percent']}%")
print(f"Avg wait time: {stats['avg_wait_ms']}ms")
```

## Integration with Loaders

### Example: Monitoring Optimized Loader

```python
from loader_base_optimized import OptimizedLoader
from connection_pool_monitor import get_pool_monitor, get_health_checker

class MonitoredOptimizedLoader(OptimizedLoader):
    def __init__(self, source_name):
        super().__init__()
        self.monitor = get_pool_monitor(source_name)
        
        # Start background health checks
        self.health_checker = get_health_checker(source_name, auto_start=True)

    def connect(self):
        """Connect with monitoring."""
        start = time.time()
        try:
            super().connect()
            wait_ms = (time.time() - start) * 1000
            self.monitor.record_connection_wait(wait_ms)
        except Exception as e:
            self.monitor.record_failed_connection(str(e))
            raise

    def finalize(self):
        """Finalize with stats."""
        super().finalize()
        
        # Record final connection count
        self.monitor.record_active_connections(
            count=self.cur.connection.get_dsn_parameters().get('dbname'),  # Pseudo-code
            max_connections=100
        )
        
        # Stop health checker
        self.health_checker.stop()
```

## Operational Tasks

### Check Current Pool Health

```bash
# View all connection pool metrics
aws cloudwatch get-metric-statistics \
  --namespace "algo/ConnectionPool/loader_pool" \
  --metric-name ActiveConnections \
  --start-time 2026-05-09T12:00:00Z \
  --end-time 2026-05-09T13:00:00Z \
  --period 300 \
  --statistics Average,Maximum
```

### View RDS Connection Events

Check CloudWatch Logs for connection-related errors:

```bash
aws logs filter-log-events \
  --log-group-name /aws/rds/instance/algo-db/postgresql \
  --filter-pattern "[...] connection*" \
  --start-time $(date -d '1 hour ago' +%s)000
```

### Diagnose High Utilization

If alarms trigger (>80% utilization):

1. **Check active connections**:
   ```bash
   psql -h <rds-host> -U postgres -c "SELECT count(*) FROM pg_stat_activity;"
   ```

2. **Check long-running queries** (may be holding connections):
   ```bash
   psql -h <rds-host> -U postgres -c "
     SELECT query, state, wait_event, query_start
     FROM pg_stat_activity
     WHERE state != 'idle'
     ORDER BY query_start;
   "
   ```

3. **Kill idle connections** (frees up slots):
   ```bash
   psql -h <rds-host> -U postgres -c "
     SELECT pg_terminate_backend(pid)
     FROM pg_stat_activity
     WHERE state = 'idle' AND query_start < now() - interval '10 minutes';
   "
   ```

4. **Check RDS Proxy stats**:
   ```bash
   aws rds-proxy describe-db-proxy-targets \
     --db-proxy-name algo-db-proxy-prod \
     --query 'Targets[*].[DBProxyName,TargetArn,TargetHealth.State]'
   ```

### Scale Up Database

If consistently hitting >80% utilization:

1. **Increase RDS max_connections** (requires instance restart):
   ```bash
   aws rds modify-db-instance \
     --db-instance-identifier algo-db \
     --db-parameter-group-name algo-pg14-params-updated \
     --apply-immediately
   
   # Update parameter group:
   # max_connections = 200 (from 100)
   ```

2. **Increase RDS instance size** (faster but more expensive):
   ```bash
   aws rds modify-db-instance \
     --db-instance-identifier algo-db \
     --db-instance-class db.t3.small \
     --apply-immediately
   ```

3. **Enable RDS Proxy if not already** (multiplexes connections):
   - Already deployed - should multiplex 320 app connections to ~100 RDS connections

4. **Reduce loader parallelism** (quick fix for dev/staging):
   ```bash
   # Set --parallelism=4 instead of 8
   python loadpricedaily.py --parallelism 4
   ```

## Troubleshooting

### "FATAL: too many connections" Error

**Cause**: Database max_connections limit reached

**Diagnosis**:
```bash
# Check current connections
psql -h <rds-host> -U postgres -c \
  "SELECT count(*) as active FROM pg_stat_activity WHERE state != 'idle';"

# Check max_connections setting
psql -h <rds-host> -U postgres -c "SHOW max_connections;"
```

**Fix**:
```python
# Option 1: Use RDS Proxy (already deployed)
# Just ensure all loaders connect through proxy endpoint

# Option 2: Reduce parallelism (quick)
# Set --parallelism=4 or lower

# Option 3: Increase max_connections
# Requires database restart
```

### High Connection Wait Times (>5 seconds)

**Cause**: Pool is saturated, connections waiting in queue

**Diagnosis**:
```bash
aws cloudwatch get-metric-statistics \
  --namespace "algo/ConnectionPool/loader_pool" \
  --metric-name P95WaitTime \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S)Z \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S)Z \
  --period 300 \
  --statistics Maximum
```

**Fix**:
1. Reduce concurrent loaders (scale down workers)
2. Increase RDS instance capacity
3. Optimize loader queries (reduce execution time)

### Connection Leaks (Connections Growing Over Time)

**Cause**: Loaders not properly closing connections

**Diagnosis**:
```bash
# Check if connections growing
for i in {1..10}; do
  count=$(psql -h <rds-host> -U postgres -c \
    "SELECT count(*) FROM pg_stat_activity;" | tail -1)
  echo "$(date): $count connections"
  sleep 60
done
```

**Fix**:
1. Ensure all loaders call `disconnect()` in finally block
2. Check for exceptions preventing cleanup
3. Add timeout to connection acquisition

## Metrics Reference

### CloudWatch Metrics Published

Namespace: `algo/ConnectionPool/<pool_name>`

| Metric | Unit | Description |
|--------|------|-------------|
| `ActiveConnections` | Count | Current active connections |
| `UtilizationPercent` | Percent | % of max connections in use |
| `FailedAttempts` | Count | Failed connection attempts |
| `ExhaustionEvents` | Count | Times pool was exhausted |
| `AvgWaitTime` | Milliseconds | Average wait for connection |
| `P95WaitTime` | Milliseconds | 95th percentile wait time |

### RDS Instance Limits

| Instance Class | Max Connections | Typical Max |
|---|---|---|
| `db.t3.micro` | 100 | 80 (safe margin) |
| `db.t3.small` | 200 | 150 |
| `db.t3.medium` | 400 | 300 |
| `db.r5.large` | 1000 | 800 |

Current instance: Check Terraform for `var.db_instance_class`

## References

- Code: `connection_pool_monitor.py`
- PostgreSQL docs: [max_connections](https://www.postgresql.org/docs/current/runtime-config-connection-default.html)
- AWS RDS docs: [Parameter Groups](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithParameterGroups.html)
- RDS Proxy docs: [Connection pooling](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.html)
