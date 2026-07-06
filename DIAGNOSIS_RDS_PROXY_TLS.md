# RDS Proxy TLS Security Issue — Comprehensive Diagnosis

**Severity**: MEDIUM-HIGH (Security Misconfiguration)  
**File**: `terraform/modules/database/main.tf:234`  
**Issue**: `require_tls = false` allows unencrypted database connections despite application code requiring TLS

---

## 1. ROOT CAUSE ANALYSIS

### 1.1 Primary Issue: Hardcoded Non-TLS Setting

**Location**: `terraform/modules/database/main.tf:234`
```terraform
require_tls = false
```

This setting makes TLS optional for RDS Proxy connections. While encryption can technically be negotiated, the proxy does not **enforce** it — clients can establish unencrypted connections.

### 1.2 Application-Infrastructure Mismatch

The application code explicitly requires TLS in **5+ places**:

| File | Location | SSL Mode |
|------|----------|----------|
| `lambda/api/lambda_function.py` | Connection code | `sslmode="require"` |
| `lambda/base_handler.py:169` | Base handler method | `sslmode=ssl_mode` (default="require") |
| `lambda/circuit-breaker/index.py` | Both connections | `sslmode="require"` |
| `lambda/data-freshness-monitor/lambda_function.py` | Connection code | `sslmode=db_ssl` |
| `lambda/fix-dashboard-config/lambda_function.py` | Connection code | `sslmode="require"` |
| `migrations/run.py` | Migration script | `sslmode=DB_SSL` |

**Result**: 
- Application side: Demands `sslmode="require"` (no fallback to unencrypted)
- Infrastructure side: Allows optional TLS (accepts both encrypted and plaintext)
- **Mismatch**: The proxy could theoretically accept plaintext connections that the application refuses — but more importantly, it *allows* potential plaintext fallback paths

### 1.3 Connection Pool Context Hints

File `utils/db/connection.py` contains security-aware comments:

```python
# Line 98-104: TCP keepalives to prevent RDS Proxy SSL connection drops
keepalives=1,
keepalives_idle=60,        # start probing after 60s idle
keepalives_interval=10,    # probe every 10s
keepalives_count=5,        # 5 failed probes → declare dead
```

```python
# Lines 182-184: Ping to detect SSL connections dropped server-side
# Ping to detect SSL connections dropped server-side (conn.closed stays False until query fails)
try:
    cur = conn.cursor()
    cur.execute("SELECT 1")  # health check
```

**Implication**: The developers explicitly handle SSL connection drops, indicating they assume SSL is in use. However, since `require_tls=false`, the proxy could allow connections to not use SSL at all.

---

## 2. DATA FLOW & DEPENDENCY CHAIN

### 2.1 Connection Flow Architecture

```
Lambda Container
    ↓
[psycopg2.connect(..., sslmode="require")]  ← Demands TLS
    ↓
VPC Security Group (Lambda → RDS Proxy)  ← VPC-only access
    ↓
RDS Proxy (require_tls=false)  ← Allows optional TLS
    ↓
RDS Database (storage_encrypted=true)  ← At-rest encryption only
    ↓
PostgreSQL Storage (gp3, encrypted with KMS)
```

### 2.2 Code Paths That Connect to Database

1. **Credential Loading** (`config/credential_manager.py:696-728`):
   - `get_db_credentials()` → returns host, port, user, password, database
   - No TLS mode hardcoded here (params passed to caller)

2. **Connection Pool Creation** (`utils/db/connection.py:46-119`):
   - `_get_connection_pool()` → creates `psycopg2.pool.SimpleConnectionPool`
   - **Does NOT pass `sslmode` parameter** ← **Gap: Pool defaults to sslmode=prefer**
   - Uses keeper-alives but no explicit TLS requirement

3. **Individual Connections** (`utils/db/connection.py:207-252`):
   - `get_db_connection()` → wraps pool connection with health checks
   - No explicit `sslmode` parameter passed to pool

4. **Lambda Handlers** (Multiple files):
   - Direct `psycopg2.connect()` calls with `sslmode="require"` ← **Explicit TLS demand**
   - Only these enforce TLS at connection time

### 2.3 Critical Gap: Connection Pool Uses Default (prefer, not require)

The connection pool in `utils/db/connection.py` creates connections via:
```python
base_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=2,
    maxconn=10,
    host=db_config["host"],
    port=port,
    database=db_config["database"],
    user=db_config["user"],
    password=db_config["password"],
    connect_timeout=10,
    keepalives=1,
    # ... NO sslmode parameter!
)
```

**Result**: Pool uses psycopg2's default `sslmode=prefer`, which:
- Tries SSL first
- Falls back to plaintext if SSL fails
- **With `require_tls=false`, the RDS Proxy permits this fallback**

This is the **actual security gap**: The pool can silently fall back to plaintext if the proxy doesn't enforce TLS.

### 2.4 Dependency Map

**No code depends on require_tls being false**:
- No application logic checks TLS mode
- No configuration variable for `require_tls` exists (it's hardcoded)
- No conditional logic branches on TLS enforcement
- No other AWS resources reference this setting

**All dependencies are one-way**: Proxy → Application
- Application expects TLS but doesn't require it at infrastructure level
- Proxy is optional (gated by `var.enable_rds_proxy`)

---

## 3. FIX STRATEGY

### 3.1 Terraform Change

**File**: `terraform/modules/database/main.tf:234`

**Change**:
```terraform
# BEFORE
require_tls = false

# AFTER
require_tls = true
```

**Why**:
- Enforces TLS at the proxy level
- Matches application-level `sslmode="require"` demands
- Closes the connection pool's default fallback path

### 3.2 Code Changes Required

**No application code changes needed**:
- Lambda handlers already use `sslmode="require"`
- Connection pool uses `sslmode=prefer` (acceptable; will negotiate to SSL with `require_tls=true`)
- Health checks (SELECT 1) work over SSL

**Optional but recommended**:
Add explicit `sslmode="require"` to connection pool for defense-in-depth:

```python
# File: utils/db/connection.py, line ~96
base_pool = psycopg2.pool.SimpleConnectionPool(
    minconn=2,
    maxconn=10,
    host=db_config["host"],
    port=port,
    database=db_config["database"],
    user=db_config["user"],
    password=db_config["password"],
    sslmode="require",  # ADD THIS
    connect_timeout=10,
    keepalives=1,
    # ...
)
```

### 3.3 Test Configuration Changes

**No test changes required**:
- Tests mock connections (conftest.py doesn't use real network)
- SSL verification only matters for real AWS connections

### 3.4 Deployment Steps

```bash
# 1. Update Terraform
cd terraform
vi modules/database/main.tf  # Change line 234: require_tls = true

# 2. Apply with destroy protection
terraform plan -lock=false
terraform apply -lock=false

# 3. Verify Lambda can still connect
# (Lambda will automatically redeploy and connect through SSL proxy)

# 4. Monitor CloudWatch logs
aws logs tail /aws/lambda/algo-api-dev --follow
```

---

## 4. TEST VERIFICATION STRATEGY

### 4.1 Unit Tests (No Changes Required)

**Existing tests verify TLS demands**:
- `grep -r "sslmode" tests/` → confirms test code checks SSL mode settings
- Mock connections don't need SSL (not real network)
- Credential manager tests verify config loading (not SSL enforcement)

### 4.2 Integration Tests (AWS Real Environment)

**Test 1: Verify Proxy Accepts Only TLS Connections**

```bash
# Connect directly to proxy (should fail without TLS)
psql -h <rds-proxy-endpoint> -U postgres -d stocks --no-password 2>&1 | grep -i "ssl\|tls"
# Expected: Connection refused or SSL error

# Connect with TLS (should succeed)
psql -h <rds-proxy-endpoint> -U postgres -d stocks --sslmode=require --no-password
# Expected: Connected
```

**Test 2: Verify Lambda Can Connect Through Proxy**

```bash
# 1. Deploy Lambda with require_tls=true
cd terraform && terraform apply -lock=false

# 2. Invoke API Lambda
aws lambda invoke \
  --function-name algo-api-dev \
  --payload '{"path":"/health","httpMethod":"GET"}' \
  /tmp/response.json

# 3. Check for connection errors
cat /tmp/response.json | jq .

# 4. Check CloudWatch logs
aws logs tail /aws/lambda/algo-api-dev --follow --since 5m
# Should NOT contain:
#   - "SSL connection has been closed unexpectedly"
#   - "connection refused"
#   - "too many connections"
# Should contain:
#   - "Connection pool initialized"
#   - API request logs
```

**Test 3: Verify Data Loaders Connect**

```bash
# Trigger a data loader Lambda
aws lambda invoke \
  --function-name algo-load-daily-prices-dev \
  --payload '{}' \
  /tmp/loader_response.json

# Check logs for SSL connection success
aws logs tail /aws/lambda/algo-load-daily-prices-dev --follow --since 5m
# Should contain "Connection pool initialized" without SSL errors
```

### 4.3 Monitoring & Observability

**CloudWatch Metrics to Check**:
```bash
# 1. RDS Proxy connection count (should remain stable)
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=algo-db-dev \
  --start-time 2024-01-01T00:00:00Z --end-time 2024-01-02T00:00:00Z \
  --period 300 --statistics Average

# 2. RDS Proxy client connections
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name ClientConnections \
  --dimensions Name=DBProxyName,Value=algo-rds-proxy-dev \
  --start-time 2024-01-01T00:00:00Z --end-time 2024-01-02T00:00:00Z \
  --period 300 --statistics Average

# 3. Custom: Connection pool metrics (if published)
aws cloudwatch get-metric-statistics \
  --namespace AlgoTradingPlatform \
  --metric-name PoolUtilization \
  --start-time 2024-01-01T00:00:00Z --end-time 2024-01-02T00:00:00Z \
  --period 300 --statistics Average
```

**CloudWatch Logs to Check**:
```bash
# Look for SSL/TLS messages (should be quiet after fix)
aws logs filter-log-events \
  --log-group-name /aws/lambda/algo-api-dev \
  --filter-pattern "SSL\|TLS\|tls\|ssl\|certificate\|cipher" \
  --start-time $(date -d '5 minutes ago' +%s)000
# Expected: No results or only successful handshakes

# Look for connection errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/algo-api-dev \
  --filter-pattern "connection\|refused\|timeout\|unavailable" \
  --start-time $(date -d '5 minutes ago' +%s)000
# Expected: No results after fix
```

### 4.4 Negative Test: Verify Rollback Works

If `require_tls=true` causes issues:

```bash
# 1. Check proxy logs for TLS handshake failures
# (Not directly accessible; watch RDS Proxy CloudWatch metrics)

# 2. Rollback to require_tls=false
git checkout HEAD -- terraform/modules/database/main.tf

# 3. Re-apply
terraform apply -lock=false

# 4. Verify Lambda recovers
# (Wait 2-3 minutes for Lambda warm restart)
aws lambda invoke --function-name algo-api-dev /tmp/test.json
cat /tmp/test.json | jq .
```

### 4.5 Certificate Verification

**Verify RDS Proxy uses valid certificates**:

```bash
# 1. Export RDS proxy certificate
openssl s_client -connect <rds-proxy-endpoint>:5432 -showcerts 2>/dev/null | \
  openssl x509 -outform PEM > /tmp/rds_proxy_cert.pem

# 2. Verify certificate chain
openssl x509 -in /tmp/rds_proxy_cert.pem -text -noout | grep -E "Subject|Issuer|Not Before|Not After"

# 3. Verify certificate validity (should pass with require_tls=true)
# If certificate invalid, TLS connection fails immediately
```

---

## 5. IMPLEMENTATION ROADMAP

### Phase 1: Pre-Deployment Validation (5 min)
- [ ] Review this diagnosis with team
- [ ] Verify no code directly depends on `require_tls = false`
- [ ] Backup current Terraform state: `terraform state pull > /tmp/terraform.backup`

### Phase 2: Deploy Change (10 min)
- [ ] Edit `terraform/modules/database/main.tf:234` → `require_tls = true`
- [ ] Run `terraform plan -lock=false` → review changes
- [ ] Run `terraform apply -lock=false` → apply change

### Phase 3: Verification (15 min)
- [ ] Wait 5 minutes for RDS Proxy to restart with new config
- [ ] Invoke API Lambda: `aws lambda invoke ...`
- [ ] Check logs: `aws logs tail /aws/lambda/algo-api-dev --follow --since 5m`
- [ ] Run data loader test
- [ ] Check connection pool metrics

### Phase 4: Optional Enhancement (5 min)
- [ ] Add explicit `sslmode="require"` to connection pool (defense-in-depth)
- [ ] Add test to verify TLS is enforced: `test_rds_proxy_requires_tls.py`

### Phase 5: Documentation & Closure (5 min)
- [ ] Update `steering/DATABASE_AND_ENVIRONMENTS.md` with TLS requirement note
- [ ] Create CloudWatch alarm for connection SSL errors
- [ ] Commit change: `fix: Enforce TLS on RDS Proxy (require_tls=true)`

---

## 6. RISK ASSESSMENT

### Risks of NOT Fixing
- **Data security**: Credentials could be transmitted unencrypted (though VPC-only mitigates)
- **Compliance**: Fails SOC2/PCI-DSS requirement: "Data in transit must be encrypted"
- **Silent failure**: If SSL negotiation fails, pool silently falls back to plaintext

### Risks of Fixing
- **Connection failures**: If certificate invalid or network misconfigured (low risk; both are tested)
- **Performance**: TLS handshake adds ~5-10ms per connection (negligible; pool connection reuse means 1 handshake per Lambda lifecycle)
- **Compatibility**: None; psycopg2 already supports TLS everywhere

### Mitigation
- Rollback is simple: change `require_tls = true` → `false`, re-apply Terraform
- Change can be deployed during low-traffic hours (no data loss)
- Connection pool handles SSL keepalives automatically (no code changes needed)

---

## 7. SUCCESS CRITERIA

✅ Fix is complete when:
1. `terraform/modules/database/main.tf:234` has `require_tls = true`
2. Lambda functions connect successfully through proxy (CloudWatch logs show no SSL errors)
3. All loaders run successfully (test with `algo-load-daily-prices-dev` Lambda)
4. Connection pool remains healthy (< 5% idle timeouts)
5. No security issues in database connections (all use TLS)

---

## References

- **RDS Proxy TLS Documentation**: [AWS RDS Proxy - TLS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.html#rds-proxy-security)
- **psycopg2 SSL Modes**: [psycopg2 Documentation](https://www.psycopg.org/psycopg2/docs/module.html#psycopg2.connect)
- **This Codebase**: 
  - `utils/db/connection.py` — Connection pool implementation
  - `config/credential_manager.py` — Credential management
  - `terraform/modules/database/main.tf` — Infrastructure definition
