# 6-Week Execution Plan — Data Loading & Stability Focus
**Dev Environment Only** | No VPC work | Focus: Credentials, RDS, Data Loading, Observability

---

## Week 1: Credential Security Lockdown (Critical)

### Mon-Tue: Credential Manager & Secrets Migration
**Goal:** Centralized, safe credential handling. No more empty password defaults.

**Tasks:**
1. Create `credential_manager.py` (singleton)
   ```python
   class CredentialManager:
       def get_db_password(self) -> str:
           # Try Secrets Manager, fall back to env var
           # NEVER return empty string — raise CredentialNotFoundError
       def get_alpaca_keys(self) -> tuple:
           # Similar, cache result
       def get_smtp_password(self) -> str:
           # Similar
   ```

2. Update all 200+ credential refs to use it
   - `algo_config.py` — use credential_manager instead of os.getenv
   - All loaders — use credential_manager.get_db_password()
   - `algo_orchestrator.py` — use credential_manager for Alpaca keys
   - `algo_alerts.py` — use credential_manager for SMTP

3. Remove all `os.getenv("DB_PASSWORD", "")` — replace with credential_manager

4. Test locally: `python3 algo_run_daily.py` should work with .env.local

**Deliverable:** No empty password defaults, all credentials go through manager

### Wed: Lambda & ECS Configuration
**Goal:** Tell AWS where credentials really are.

**Tasks:**
1. Update `lambda_function.py` to pass credential_manager to orchestrator
2. Update ECS task definitions to use Secrets Manager ARN for DB credentials
3. Update GitHub Actions secrets (keep as backup for local testing)

**Deliverable:** Lambda and ECS both fetch secrets safely

### Thu: Testing
**Goal:** Verify loaders and algo still work.

**Tasks:**
1. Local test: `python3 algo_run_daily.py` (uses .env.local)
2. Deploy and test Lambda: `aws lambda invoke --function-name algo-orchestrator /tmp/out.json`
3. Trigger one loader: `aws ecs run-task --cluster stocks-data-cluster --task-definition loadpricedaily:1`
4. Check RDS for new data: `psql -h localhost -U stocks -d stocks -c "SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE;"`

**Deliverable:** All code paths tested, data loads, no credential leaks

### Fri: Audit & Lock Down
**Goal:** Verify no credentials are hardcoded.

**Tasks:**
1. Grep for any remaining `os.getenv(".*PASSWORD"` — should find 0
2. Grep for any hardcoded Alpaca keys — should find 0
3. Review CloudWatch logs for credential leaks — none should appear
4. Document: "All credentials now managed via credential_manager"

**Deliverable:** Zero credential refs outside credential_manager

---

## Week 2: RDS & Resilience

### Mon: RDS Security Hardening
**Goal:** Lock down database access, enable encryption.

**Tasks:**
1. Update security group: remove 0.0.0.0/0, allow only:
   - ECS cluster security group (port 5432)
   - Lambda execution role (port 5432)
   - Bastion if exists (port 5432)
   - NOT public access
   
   ```bash
   # Remove old rule
   aws ec2 revoke-security-group-ingress --group-id sg-xxxxx \
     --protocol tcp --port 5432 --cidr 0.0.0.0/0
   
   # Add ECS cluster rule
   aws ec2 authorize-security-group-ingress --group-id sg-xxxxx \
     --protocol tcp --port 5432 --source-group sg-ecs-cluster
   
   # Add Lambda execution rule
   aws ec2 authorize-security-group-ingress --group-id sg-xxxxx \
     --protocol tcp --port 5432 --source-group sg-lambda-exec
   ```

2. Enable encryption at rest:
   ```bash
   aws rds create-db-instance-read-replica \
     --db-instance-identifier stocks-data-rds-encrypted \
     --source-db-instance-identifier stocks-data-rds \
     --storage-encrypted
   # (Creates encrypted copy, then promote)
   ```

3. Verify: Try connecting from your laptop → should fail. Try from Lambda → should work.

**Deliverable:** RDS locked down, only Lambda/ECS can connect

### Tue: Enable Multi-AZ
**Goal:** Survive RDS primary failure without manual intervention.

**Tasks:**
1. Enable Multi-AZ:
   ```bash
   aws rds modify-db-instance --db-instance-identifier stocks-data-rds \
     --multi-az --apply-immediately
   ```

2. Wait for failover to complete (~5 min, might see brief connection loss)

3. Test failover:
   ```bash
   # Force failover to secondary
   aws rds reboot-db-instance --db-instance-identifier stocks-data-rds \
     --force-failover
   
   # Verify app reconnects automatically
   # (should work, Lambda reconnects)
   ```

**Deliverable:** RDS survives primary failure, app auto-reconnects

### Wed: Disaster Recovery Runbook
**Goal:** Know how to recover from RDS catastrophic failure (tested once).

**Create runbook:** `docs/runbook-rds-recovery.md`

**Procedure:**
```
1. Assess damage:
   - Check AWS console: RDS status
   - Check CloudWatch logs: latest error
   
2. If entire RDS is gone:
   - List available backups:
     aws rds describe-db-snapshots --db-instance-identifier stocks-data-rds
   
   - Restore from snapshot:
     aws rds restore-db-instance-from-db-snapshot \
       --db-instance-identifier stocks-data-rds-recovered \
       --db-snapshot-identifier <snapshot-id>
   
   - Wait ~10 min for restore
   
   - Update Secrets Manager to point to new endpoint
   
   - Restart Lambda + ECS
   
   - Verify: data is there, algo runs

3. If data is corrupted but RDS is up:
   - Identify last good backup timestamp
   - Manual PITR (point-in-time recovery) to before corruption
   - Document what happened in post-mortem

RTO: 10-15 min (restore + restart)
RPO: Last backup (7 days at most)
```

**Test it once:**
1. Create RDS snapshot manually
2. Delete current RDS instance
3. Restore from snapshot
4. Verify data is there
5. Verify Lambda can connect
6. Delete restored instance, restore original

**Deliverable:** Runbook written, tested once, RTO/RPO documented

### Thu-Fri: Testing & Verification
**Tasks:**
1. Run algo: `aws lambda invoke --function-name algo-orchestrator /tmp/out.json`
2. Check data loaded: `psql -h <RDS> -U stocks -d stocks -c "SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE;"`
3. Trigger one loader: watch it load data
4. Verify RDS failover still works
5. Verify credentials are fetched safely (check logs for no leaks)

**Deliverable:** All systems working, security hardened, recovery plan in place

---

## Week 3: Data Loading Reliability

### Mon: Unified Data Quality Layer
**Goal:** All loaders use same validation rules, no silent failures.

**Create:** `algo_data_quality_gate.py`

```python
class DataQualityGate:
    """Unified validation for all data loads"""
    
    def validate(self, symbol: str, data: dict) -> tuple[bool, str]:
        """
        Returns: (is_valid, reason)
        Checks:
        1. Schema valid (required columns present)
        2. No outliers (>3σ from recent mean)
        3. Volume > 0 (not zero-volume day)
        4. Freshness (data is from today if loading today)
        """
        checks = [
            self._schema_check(symbol, data),
            self._outlier_check(symbol, data),
            self._volume_check(symbol, data),
            self._freshness_check(symbol, data),
        ]
        
        failed = [c for c in checks if not c[0]]
        if failed:
            return False, f"Failed: {failed[0][1]}"
        return True, "OK"

# All loaders use:
if not gate.validate(symbol, data):
    logger.error(f"Data quality failed for {symbol}: {reason}")
    skip_this_symbol()  # Don't insert bad data
    continue
```

**Update all loaders:**
- `loadpricedaily.py`
- `loadpriceweekly.py`
- `loadpricemonthly.py`
- `loadstockscores.py`
- `loadbuyselldaily.py`
- All others

**Deliverable:** Unified quality checks, no bad data inserted

### Tue: Loader SLA Tracking
**Goal:** Know which loaders succeeded/failed each day.

**Create:** `algo_loader_sla_tracker.py`

```python
class LoaderSLATracker:
    """Track per-loader success metrics"""
    
    def log_load_attempt(self, loader_name: str, symbols: int, success: bool, duration: float):
        """Insert into algo_loader_sla table"""
        # Columns: date, loader_name, symbols_attempted, symbols_loaded, success, duration_sec
        
    def daily_report(self):
        """Generate: which loaders ran, which failed, which were slow"""
        # SELECT loader_name, COUNT(*) as attempts, 
        #        SUM(CASE WHEN success THEN 1 ELSE 0 END) as succeeded,
        #        AVG(duration_sec) as avg_duration
        # FROM algo_loader_sla
        # WHERE date = TODAY
        # GROUP BY loader_name
        
    def alert_if_needed(self):
        """If any loader failed, send alert with recovery steps"""
```

**Integrate into each loader:**
- Start of load: `tracker.start_load("loadpricedaily")`
- End of load: `tracker.log_load_attempt("loadpricedaily", 500, success=True, duration=45.2)`

**Create:** `docs/runbook-loader-failure.md`
```
If loadpricedaily failed:
1. Check error in CloudWatch: /aws/ecs/stocks-data-cluster
2. Common reasons: API rate limit, DB connection lost, bad data source
3. Manual retry: aws ecs run-task --cluster stocks-data-cluster --task-definition loadpricedaily:1
4. Verify: psql -c "SELECT COUNT(*) FROM price_daily WHERE date = CURRENT_DATE"
5. Document in #incidents Slack channel
```

**Deliverable:** Can see which loaders succeeded/failed each day, runbook for recovery

### Wed: Integrate Loader Monitor into Orchestrator
**Goal:** Algo fails closed if data didn't load.

**Already exists:** `algo_loader_monitor.py` (from recent commits)

**Just wire it up in Phase 1 of orchestrator:**
```python
# algo_orchestrator.py, Phase 1
def phase_1_data_freshness_check():
    # New: Check loader health BEFORE proceeding
    loader_monitor = LoaderMonitor()
    findings = loader_monitor.audit_all()
    
    for severity, check_name, message in findings:
        if severity == "CRITICAL":
            logger.critical(f"Loader check failed: {message}")
            alerts.send_critical_alert(f"Algo halted: {message}")
            return False, "Loader data insufficient"
    
    # Existing: freshness checks
    if not self.data_is_fresh():
        return False, "Data is stale"
    
    return True, "OK"
```

**Deliverable:** Algo won't trade on zero data or missing loaders

### Thu-Fri: End-to-End Testing
**Tasks:**
1. Run `python3 algo_run_daily.py` locally — should work
2. Trigger loaders manually: `aws ecs run-task --cluster stocks-data-cluster --task-definition loadpricedaily:1`
3. Wait for completion
4. Check SLA tracker: `SELECT * FROM algo_loader_sla ORDER BY date DESC LIMIT 5`
5. Verify algo ran: check P&L, positions, trades
6. Verify no data quality issues: check logs

**Deliverable:** Data loads reliably, SLA tracked, algo runs, all tests pass

---

## Week 4: Observability Phase 1 (See What's Happening)

### Mon-Tue: Structured Logging
**Goal:** Logs are searchable, can follow a trade end-to-end.

**Update logging to JSON:**
```python
import json
import logging

class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": record.created,
            "level": record.levelname,
            "trace_id": record.trace_id,  # Unique ID for this run
            "module": record.name,
            "message": record.getMessage(),
            "data": getattr(record, "data", {}),
        })

logging.basicConfig(level=logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger = logging.getLogger(__name__)
```

**Add trace IDs to orchestrator:**
```python
# algo_orchestrator.py
import uuid

class Orchestrator:
    def __init__(self):
        self.trace_id = str(uuid.uuid4())[:8]
    
    def run(self):
        logger.info("Orchestrator starting", extra={"data": {"trace_id": self.trace_id}})
        # Every log in this run will have same trace_id
        
        # Loaders also get the trace_id:
        result = loader.load(symbol, trace_id=self.trace_id)
```

**Update CloudWatch Insights to query by trace_id:**
```
fields @timestamp, @message, trace_id, level
| filter trace_id = "abc12345"
| sort @timestamp asc
```

**Deliverable:** Logs are JSON, searchable by trace_id, can follow a trade through all systems

### Wed: Alert Routing Rules
**Goal:** Critical alerts come as SMS, warnings as email, info goes to logs.

**Update:** `algo_alerts.py`

```python
class AlertManager:
    def send_alert(self, level: str, message: str, runbook_link: str = None):
        if level == "CRITICAL":
            # SMS via Twilio (or SNS SMS)
            self.send_sms(message)
            self.send_email(f"CRITICAL: {message}\n\nRunbook: {runbook_link}")
        elif level == "WARNING":
            # Email + Slack
            self.send_email(message)
            self.send_slack(f":warning: {message}")
        elif level == "INFO":
            # Just log
            logger.info(message)

# Usage:
alerts.send_alert("CRITICAL", "Algo halt: no data loaded", 
                  runbook_link="docs/runbook-loader-failure.md")
```

**Deliverable:** Smart alert routing, no alert spam

### Thu: Audit Trail Dashboard
**Goal:** Query: "what happened on 2026-05-09?"

**Create:** `algo_audit_dashboard.py`

```python
# Simple web interface (or SQL query interface)
@app.get("/api/audit-trail")
def get_audit_trail(date: str, symbol: str = None):
    """
    Query: date=2026-05-09, symbol=AAPL
    Returns: all decisions made for that symbol on that date
    """
    query = f"""
    SELECT timestamp, symbol, action, reason, result
    FROM algo_audit_log
    WHERE DATE(timestamp) = '{date}'
    """
    if symbol:
        query += f" AND symbol = '{symbol}'"
    query += " ORDER BY timestamp ASC"
    
    return db.query(query)

# Usage:
# curl "http://localhost:5000/api/audit-trail?date=2026-05-09&symbol=AAPL"
# Response: all AAPL decisions that day
```

**Deliverable:** Can query "why was this trade made?" in 10 seconds

### Fri: Testing
**Tasks:**
1. Run algo, generate logs
2. View logs in CloudWatch: filter by trace_id
3. Trigger an alert (force a failure), verify SMS/email received
4. Query audit dashboard: "what happened on 2026-05-09?"
5. Verify all trades are audited

**Deliverable:** Full visibility into system, can debug quickly

---

## Week 5: Observability Phase 2 (Metrics & Dashboards)

### Mon: Metrics Collection
**Goal:** Collect key metrics (execution latency, fills, signal success rate).

**Add Prometheus client:**
```python
from prometheus_client import Counter, Histogram, Gauge

# Execution metrics
execution_latency = Histogram('execution_latency_seconds', 'Time to execute a trade')
filled_orders = Counter('filled_orders_total', 'Total filled orders', ['symbol'])
rejected_orders = Counter('rejected_orders_total', 'Total rejected orders')

# Data metrics
loader_success = Counter('loader_success_total', 'Successful data loads', ['loader'])
loader_failures = Counter('loader_failures_total', 'Failed data loads', ['loader'])

# Trading metrics
daily_pnl = Gauge('daily_pnl_dollars', 'Daily P&L')
position_count = Gauge('position_count', 'Number of open positions')
max_drawdown = Gauge('max_drawdown_percent', 'Max drawdown %')

# Usage:
with execution_latency.time():
    order = executor.execute(symbol, shares)

filled_orders.labels(symbol='AAPL').inc()
daily_pnl.set(pnl_amount)
```

**Integrate into orchestrator:**
- Track: Phase 1 duration, Phase 2 duration, Phase 3 duration, Phase 4 duration, Phase 5 duration
- Track: Total signals generated, signals filtered out, signals executed
- Track: Fills, partial fills, rejected orders, slippage

**Deliverable:** Metrics flowing to Prometheus

### Tue: Prometheus Setup (or CloudWatch)
**Goal:** Scrape metrics, store them, query them.

**Option A: Local Prometheus (simple)**
```bash
# docker-compose.yml addition
prometheus:
  image: prom/prometheus
  ports:
    - "9090:9090"
  volumes:
    - ./prometheus.yml:/etc/prometheus/prometheus.yml
  command:
    - "--config.file=/etc/prometheus/prometheus.yml"

# prometheus.yml
global:
  scrape_interval: 30s

scrape_configs:
  - job_name: 'algo'
    static_configs:
      - targets: ['localhost:8000']  # Your Flask/FastAPI metrics endpoint
```

**Option B: CloudWatch (AWS native)**
```python
# Push metrics to CloudWatch
client = boto3.client('cloudwatch')
client.put_metric_data(
    Namespace='StockAlgo',
    MetricData=[
        {'MetricName': 'ExecutionLatency', 'Value': 1.23, 'Unit': 'Seconds'},
        {'MetricName': 'DailyPnL', 'Value': 500.0, 'Unit': 'None'},
    ]
)
```

**Deliverable:** Metrics persisted, queryable

### Wed-Fri: Grafana Dashboard
**Goal:** Visual dashboard showing system health.

**Create Grafana dashboard:** `grafana/algo-system-health.json`

```json
{
  "panels": [
    {
      "title": "Execution Latency (last 24h)",
      "targets": [{"expr": "execution_latency_seconds"}]
    },
    {
      "title": "Filled vs Rejected Orders",
      "targets": [
        {"expr": "filled_orders_total"},
        {"expr": "rejected_orders_total"}
      ]
    },
    {
      "title": "Loader Success Rate (%)",
      "targets": [{"expr": "rate(loader_success_total[1h]) / (rate(loader_success_total[1h]) + rate(loader_failures_total[1h]))"}]
    },
    {
      "title": "Daily P&L & Drawdown",
      "targets": [
        {"expr": "daily_pnl_dollars"},
        {"expr": "max_drawdown_percent"}
      ]
    },
    {
      "title": "Open Positions",
      "targets": [{"expr": "position_count"}]
    }
  ]
}
```

**Deliverable:** Real-time dashboard visible at `http://localhost:3000/d/algo-health`

---

## Week 6: Data Loading Hardening & Final Testing

### Mon-Tue: Data Freshness SLA
**Goal:** Know exactly what's fresh and what's stale.

**Create:** `algo_freshness_metrics.py`

```python
class FreshnessMetrics:
    def calculate_freshness(self):
        """Per-symbol: how old is the data?"""
        query = """
        SELECT symbol, DATE(MAX(date)) as latest_date,
               CURRENT_DATE - DATE(MAX(date)) as days_old
        FROM price_daily
        GROUP BY symbol
        ORDER BY days_old DESC
        """
        results = db.query(query)
        
        # Log as metrics
        for symbol, latest_date, days_old in results:
            freshness_days.labels(symbol=symbol).set(days_old)
            
        # Alert if any critical symbol is stale
        critical_symbols = ['AAPL', 'MSFT', 'NVDA', 'TSLA']
        stale = [r for r in results if r[0] in critical_symbols and r[2] > 1]
        if stale:
            alerts.send_alert("WARNING", f"Stale data: {stale}")
```

**Deliverable:** Freshness tracked as metric, alerts on stale data

### Wed: Load Testing (Make Sure Nothing Breaks)
**Goal:** Verify system handles full load (all loaders, all signals, all trades).

**Tasks:**
1. Run full pipeline locally: `python3 algo_run_daily.py` — should complete in < 5 min
2. Trigger all loaders simultaneously: `python3 trigger_all_loaders.py` — should complete in < 10 min
3. Check RDS: load not spiking above 50%
4. Check Lambda memory: not exceeding 1GB
5. Verify no timeouts or OOM kills

**Deliverable:** System can handle full load without degradation

### Thu: Integration Testing
**Tasks:**
1. Data loads → Algo runs → Trades execute → Reconciliation passes
2. Verify audit trail: can query all decisions
3. Verify SLA tracking: loaders show success
4. Verify freshness: all symbols <= 1 day old
5. Verify no data quality issues: zero rejected records

**Deliverable:** Full end-to-end pipeline verified

### Fri: Documentation & Handoff
**Tasks:**
1. Update STATUS.md with new SLA metrics
2. Create README: "How to monitor system health"
3. Update DECISION_MATRIX.md with new runbooks
4. Document: credential_manager usage
5. Document: alert routing rules

**Deliverable:** Team can operate system without your constant guidance

---

## Summary: What You'll Have After 6 Weeks

✅ **Week 1:** Credential security — no leaks, centralized, safe  
✅ **Week 2:** RDS hardened & resilient — locked down, Multi-AZ, recovery tested  
✅ **Week 3:** Data loading reliable — quality gates, SLA tracked, failures detected  
✅ **Week 4:** Observability Phase 1 — logs searchable, alerts smart, audit trail queryable  
✅ **Week 5:** Observability Phase 2 — metrics dashboard, system health visible  
✅ **Week 6:** Hardening & confidence — load tested, full pipeline verified, documented  

**Result:** Production-quality system where:
- Data loads reliably (or algo fails closed)
- Failures are visible and alerting (SMS for critical)
- Can recover from any disaster in 15 minutes
- Team can operate without your constant supervision
- Audit trail answers "why was this trade made?"

---

## Start: Pick one task from Week 1

**Easiest psychological start:** Monday, 9am, run these two commands:

```bash
# 1. Create credential_manager.py (stub for now)
cat > credential_manager.py << 'EOF'
import os

class CredentialManager:
    def get_db_password(self) -> str:
        pwd = os.getenv("DB_PASSWORD")
        if not pwd or pwd == "":
            raise ValueError("DB_PASSWORD not set or empty")
        return pwd
    
    def get_alpaca_api_key(self) -> str:
        key = os.getenv("APCA_API_KEY_ID")
        if not key or key == "":
            raise ValueError("APCA_API_KEY_ID not set or empty")
        return key
    
    def get_alpaca_secret(self) -> str:
        secret = os.getenv("APCA_API_SECRET_KEY")
        if not secret or secret == "":
            raise ValueError("APCA_API_SECRET_KEY not set or empty")
        return secret

credential_manager = CredentialManager()
EOF

# 2. Test it
python3 -c "from credential_manager import credential_manager; print(credential_manager.get_db_password())"

# 3. Update algo_config.py to use it
# (Then do the grep audit to find all other credential refs)
```

Ready to start?
