# QUICK START DIAGNOSTIC - Find Out What's Broken

**Goal:** In 5 minutes, identify which blocking issues are preventing your system from working.

**Prerequisites:** AWS credentials configured, PowerShell or bash

---

## DIAGNOSTIC CHECKLIST

### 1. Can You Access the Dashboard? (30 seconds)

```bash
# Try to access the frontend
curl https://d2u93...cloudfront.net/  # or your CloudFront URL
echo "If you got HTML back → Frontend is up"
echo "If you got 403/404 → CloudFront not working (BLOCK-011)"
```

**Result:**
- [ ] Frontend loads → Move to test 2
- [ ] Frontend fails → **BLOCK-011: CloudFront not serving**

---

### 2. Can You Call the API? (30 seconds)

```bash
# Test health endpoint (public, no auth needed)
curl https://<api-gateway-endpoint>/api/health | jq .

# Or via local proxy if deployed
python scripts/api-proxy-server.py &
curl http://localhost:3001/api/health | jq .
```

**Expected Response:**
```json
{
  "statusCode": 200,
  "status": "healthy | degraded | unhealthy",
  "rds_connection_pool": { ... },
  "freshness": { ... }
}
```

**Result:**
- [ ] Got 200 response → Move to test 3
- [ ] Got 502/503 → **BLOCK-001 or BLOCK-004: Lambda/Database issue**
- [ ] Got 404 → **BLOCK-007: Route import failed**
- [ ] Got timeout → **BLOCK-001: Database hang**

---

### 3. Is Database Connected? (1 minute)

```bash
# Set these from your environment
export DB_HOST="..."     # RDS Proxy endpoint, NOT direct RDS
export DB_USER="..."
export DB_PASSWORD="..."
export DB_NAME="..."

# Test direct connection
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1"
echo "Exit code 0? Connection works"
echo "Exit code non-zero? Connection failed"
```

**Result:**
- [ ] Connection successful → Move to test 4
- [ ] `FATAL: could not translate host name` → **BLOCK-001: RDS Proxy endpoint wrong**
- [ ] `FATAL: password authentication failed` → **BLOCK-001: Credentials wrong**
- [ ] `FATAL: remaining connection slots reserved` → **DB-005: Connection pool exhausted**

---

### 4. Are Database Tables Created? (1 minute)

```bash
# Check if critical tables exist
psql -h $DB_HOST -U $DB_USER -d $DB_NAME << 'EOF'
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('price_daily', 'algo_positions', 'stock_symbols', 'market_health_daily');
EOF

# Should see 4 rows
```

**Result:**
- [ ] See 4 table names → Move to test 5
- [ ] See fewer than 4 → **BLOCK-003: Schema not applied**
- [ ] See "FATAL: database does not exist" → **BLOCK-003: Database not initialized**

---

### 5. Do Loaders Have Data? (1 minute)

```bash
# Check if price_daily table has recent data
psql -h $DB_HOST -U $DB_USER -d $DB_NAME << 'EOF'
SELECT 
  MAX(date) as latest_price_date,
  COUNT(DISTINCT symbol) as num_symbols
FROM price_daily;
EOF

# Today's date? Many symbols (>5000)? Good.
# Old date or few symbols? Loaders not running.
```

**Result:**
- [ ] Latest date is today, symbols > 5000 → Move to test 6
- [ ] Latest date is old (>1 day ago) → **BLOCK-006: Loaders not running**
- [ ] No rows returned → **BLOCK-003: Schema not applied**

---

### 6. Can You Call a Protected Endpoint? (1 minute)

```bash
# Try to call a protected endpoint (requires auth)
curl https://<api-gateway-endpoint>/api/algo/trades \
  -H "Authorization: Bearer <your-token>"

# Or without token to see what happens
curl https://<api-gateway-endpoint>/api/algo/trades 2>&1 | jq .
```

**Expected:** 
- With valid token: 200 response with data
- Without token: 401 Unauthorized or 403 Forbidden
- With invalid token: 401 Unauthorized

**Result:**
- [ ] Got 200 with valid token → Move to test 7
- [ ] Got 403/401 error → Check error message:
  - "COGNITO_CLIENT_ID not configured" → **BLOCK-005: Cognito not configured**
  - "JWKS endpoint unreachable" → **BLOCK-005: Network issue**
  - "Invalid token" → **BLOCK-005: Token invalid**
- [ ] Got 500 error → **BLOCK-004: Lambda layer issue**

---

### 7. Are Feature Flags Accessible? (30 seconds)

```bash
# Check feature flag configuration
psql -h $DB_HOST -U $DB_USER -d $DB_NAME << 'EOF'
SELECT * FROM algo_config LIMIT 5;
EOF
```

**Result:**
- [ ] See configuration rows → Feature flags working
- [ ] See no rows or error → **BLOCK-003: Schema not applied**

---

### 8. Is Orchestrator Running? (1 minute)

```bash
# Check if orchestrator processes exist and recent runs
psql -h $DB_HOST -U $DB_USER -d $DB_NAME << 'EOF'
SELECT 
  MAX(run_date) as last_run,
  COUNT(*) as total_runs
FROM orchestrator_execution_log;
EOF

# Should show recent date (today or yesterday)
```

**Result:**
- [ ] Recent run date → Orchestrator working
- [ ] No rows or old date (>2 days ago) → **BLOCK-006: Orchestrator not running**

---

### 9. Are Circuit Breakers Computed? (30 seconds)

```bash
# Check circuit breaker status
psql -h $DB_HOST -U $DB_USER -d $DB_NAME << 'EOF'
SELECT MAX(check_date), COUNT(*) FROM circuit_breaker_status;
EOF

# Should show today's date with 1 row
```

**Result:**
- [ ] Today's date, 1 row → Circuit breakers working
- [ ] No data or old date → **BLOCK-006: Loaders not running**

---

### 10. Is Frontened Error Logging Working? (1 minute)

```bash
# Check if CloudWatch log group exists
aws logs describe-log-groups --log-group-name-prefix /aws/frontend

# Should see /aws/frontend/algo-trading-dashboard
```

**Result:**
- [ ] Log group exists → Frontend logging configured
- [ ] No log groups → **MAJOR-006: Frontend logging not wired**

---

## DIAGNOSIS SUMMARY

Based on the tests above, here's what's broken:

**If Test 1 Failed:**
- [ ] BLOCK-011: CloudFront distribution not working
- **Fix:** Redeploy frontend: `npm run build && aws s3 sync dist s3://...`

**If Test 2 Failed:**
- [ ] BLOCK-004: Lambda layer missing or API import failed
- [ ] BLOCK-001: Database connection problem
- **Next:** Check Lambda logs: `aws logs tail /aws/lambda/algo-api-dev`

**If Test 3 Failed:**
- [ ] BLOCK-001: RDS Proxy misconfigured
- [ ] BLOCK-008: Secrets Manager access failing
- **Fix:** Verify RDS Proxy endpoint in `terraform.tfvars`

**If Test 4 Failed:**
- [ ] BLOCK-003: Database schema not applied
- **Fix:** Run: `psql -h $DB_HOST -f lambda/db-init/schema.sql`

**If Test 5 Failed:**
- [ ] BLOCK-006: Data loaders not running
- **Fix:** Check: `aws stepfunctions list-state-machines | grep algo-eod`

**If Test 6 Failed:**
- [ ] BLOCK-005: Cognito configuration incomplete
- **Fix:** Check Lambda env: `aws lambda get-function-configuration --function-name algo-api-dev`

**If Test 7 Failed:**
- System basically working, just configuration issues

**If Test 8 Failed:**
- [ ] BLOCK-006: Orchestrator not running
- **Fix:** Check EventBridge: `aws events list-rules --state ENABLED | grep algo`

**If Test 9 Failed:**
- [ ] BLOCK-006: Circuit breaker loaders not running
- **Fix:** Manually trigger: `aws ecs run-task --cluster algo-cluster-dev --task-definition algo-compute_circuit_breakers-loader`

**If Test 10 Failed:**
- [ ] MAJOR-006: Frontend error logging not configured
- **Fix:** Verify `/api/logs` endpoint exists and is registered

---

## NEXT STEPS BASED ON DIAGNOSIS

### If Everything Passed Tests 1-10:
**Congratulations!** The system is basically working. Now:
1. Look at COMPREHENSIVE_ISSUES_LIST.md
2. Focus on MAJOR issues (data validation, error handling)
3. Then fix ARCH, PERF, SECURITY issues

### If Tests 1-3 Failed:
**Critical blocking issues.** In order:
1. Fix database connection (BLOCK-001)
2. Fix Lambda layer (BLOCK-004)
3. Fix terraform state (BLOCK-002)

### If Tests 4-6 Failed:
**Data pipeline broken.** In order:
1. Apply schema (BLOCK-003)
2. Get loaders running (BLOCK-006)
3. Fix Cognito (BLOCK-005)

### If Tests 7-10 Failed:
**Orchestration broken.** In order:
1. Fix EventBridge rules (BLOCK-006)
2. Fix circuit breaker loaders (BLOCK-006)
3. Fix orchestrator config (check algo_config table)

---

## DETAILED FAILURE DIAGNOSTICS

### If You See "FATAL: password authentication failed"

```bash
# 1. Verify credentials in Secrets Manager
aws secretsmanager get-secret-value --secret-id algo/database | jq .SecretString

# 2. Verify RDS Proxy endpoint accepts connections
# (RDS Proxy uses same credentials as RDS)

# 3. Verify security group allows access
aws ec2 describe-security-groups --group-ids sg-xxx | jq '.SecurityGroups[0].IpPermissions'

# Should see rule allowing PostgreSQL (5432) from Lambda SG
```

### If You See "FATAL: could not translate host name"

```bash
# 1. Check RDS Proxy exists
aws rds-proxy describe-db-proxies | grep DBProxyName

# 2. Get correct endpoint
aws rds-proxy describe-db-proxies | jq '.DBProxies[0].Endpoint'

# 3. Update environment variable
export DB_HOST="<correct-endpoint>"
```

### If You See "remaining connection slots reserved"

```bash
# 1. Check active connections
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT COUNT(*) FROM pg_stat_activity"

# 2. Kill idle connections (DANGEROUS - backup first!)
# psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "
# SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
# WHERE state='idle' AND pid <> pg_backend_pid()"

# 3. Increase connection limits in RDS Proxy
# Edit terraform.tfvars: increase max_connections
```

### If You See "CRITICAL_ROUTE_IMPORT_FAILURE"

```bash
# 1. Check which routes failed
aws logs tail /aws/lambda/algo-api-dev --follow | grep CRITICAL

# 2. Look for ImportError or ModuleNotFoundError
aws logs tail /aws/lambda/algo-api-dev --follow | grep -E "ImportError|ModuleNotFoundError"

# 3. Rebuild Lambda layer
cd terraform && bash build-layer.sh
# Then redeploy: git push main
```

### If You See "Cannot import psycopg2"

```bash
# 1. Verify Lambda layer attached
aws lambda get-function --function-name algo-api-dev | jq '.Configuration.Layers'

# 2. If missing, rebuild and attach
cd terraform && bash build-layer.sh
terraform apply

# 3. If psycopg2 exists but wrong version
# Check Lambda runtime: should be Python 3.12
# Layer must be compiled for 3.12 (not 3.11)
```

---

## QUICK REFERENCE: ERROR MESSAGE → ROOT CAUSE

| Error Message | Root Cause | BLOCK Issue |
|---|---|---|
| `FATAL: password authentication failed` | Wrong credentials in env vars | BLOCK-001 |
| `FATAL: could not translate host name` | RDS Proxy endpoint wrong | BLOCK-001 |
| `remaining connection slots reserved` | Connection pool exhausted | DB-005 |
| `CRITICAL_ROUTE_IMPORT_FAILURE` | Lambda layer missing or broken imports | BLOCK-004 |
| `Cannot import psycopg2` | psycopg2 not in Lambda layer | BLOCK-004 |
| `COGNITO_CLIENT_ID not configured` | Env var missing | BLOCK-005 |
| `JWKS endpoint unreachable` | Network isolation | BLOCK-009 |
| `relation "price_daily" does not exist` | Schema not applied | BLOCK-003 |
| `Phase 1 HALTED: data too stale` | Loaders not running | BLOCK-006 |
| `Invalid token` | JWT signature or audience mismatch | BLOCK-005 |
| `502 Bad Gateway` | VPC cold-start timeout | BLOCK-009 |
| `503 Service Unavailable` | All replicas down or db error | Database issue |
| `504 Gateway Timeout` | Query exceeded 15s statement_timeout | DB-004 |
| `Empty response []` or `{}` | Recent code change removed fallback | MAJOR-001 |

---

## CRITICAL: After Fixing Any Issue

**ALWAYS verify the fix:**

1. Run the corresponding test again
2. Check logs for new errors
3. If multiple issues, fix them in order (blocking issues first)
4. Retest entire system (run all 10 tests)

---

## GETTING HELP

If stuck:
1. Check ISSUES_ROOT_CAUSE_ANALYSIS.md for detailed fix procedures
2. Check COMPREHENSIVE_ISSUES_LIST.md for complete issue descriptions
3. Check logs: `aws logs tail /aws/lambda/algo-api-dev --follow`
4. Check database connectivity: `psql ... -c "SELECT 1"`
5. Ask: What error did you see? Which test failed?

