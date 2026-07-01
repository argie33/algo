# Database & Environment Configuration

**Single source of truth for database setup, AWS credentials, and environment selection.**

**Rule:** When debugging data issues or applying fixes, VERIFY which database you're connected to first. Local fixes don't reach production users.

---

## Project Endpoints (This Project)

### AWS Production Environment
- **RDS Identifier:** `algo-db` (Terraform resource)
- **RDS Host:** `algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com` ← **ACTUAL ENDPOINT**
- **RDS Port:** 5432
- **Database Name:** `stocks`
- **Master User:** From Terraform variable (usually `postgres`)
- **Credentials Secret:** `algo-rds-credentials` (AWS Secrets Manager)
- **API Gateway:** `https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com`
- **Lambda Functions:**
  - API: `algo-api-dev`
  - Orchestrator: `algo-orchestrator`
  - Loaders: ECS tasks (not Lambda)
- **Region:** `us-east-1`
- **Dashboard:** `python -m dashboard` (connects to API Gateway endpoint)

**Getting actual RDS endpoint:**
```bash
# From Terraform (in terraform/ directory)
terraform output rds_address -raw

# From AWS CLI
aws rds describe-db-instances --db-instance-identifier algo-db \
  --query 'DBInstances[0].Endpoint.Address' --region us-east-1
```

### Local Development Environment
- **Database Host:** `localhost:5432` (PostgreSQL)
- **Database Name:** `stocks`
- **User:** Local PostgreSQL user (`postgres` or current user)
- **API:** None (local dev uses direct database connections)
- **Purpose:** Testing, experimentation, CI/CD (local tests)

---

## AWS Production Data Fixes (Critical)

### Issue: Dashboard showing stale/incorrect scores (OPI, ETFs, missing data)

**Fix:** Run these SQL commands against `algo-db` in AWS:

```sql
-- 1. Remove scores for stocks without positioning data (incomplete scoring)
DELETE FROM stock_scores
WHERE symbol IN (
    SELECT s.symbol FROM stock_scores s
    WHERE s.positioning_score IS NULL
);

-- 2. Remove ETF-marked stocks that got scored
DELETE FROM stock_scores  
WHERE symbol IN (SELECT symbol FROM stock_symbols WHERE etf = 'Y');

-- 3. Verify cleanup
SELECT COUNT(*) as total_valid_scores FROM stock_scores WHERE composite_score > 0;

-- 4. Disable caching for scores endpoint in Lambda
-- (This is code change, not SQL - done via GitHub deployment)

-- 5. Restart dashboard to pick up fresh data
-- pkill -9 python; python -m dashboard -w
```

**After running SQL:**
1. Verify scores count is ~5119
2. Restart dashboard: `pkill -9 python && python -m dashboard -w`
3. Check dashboard: should show no OPI, XHS, WCEO and complete factor data

**Connect to AWS RDS to run SQL:**
```bash
# Using psql (if installed)
psql -h algo-db.xxxxx.us-east-1.rds.amazonaws.com \
     -U postgres \
     -d stocks

# Or via AWS RDS Query Editor (AWS Console)
# Or use your favorite SQL client
```

---

## Verify Which Database You're Connected To

**Run this immediately when debugging:**

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/c/Users/arger/code/algo')
from utils.db.context import DatabaseContext

with DatabaseContext("read") as cur:
    cur.execute("SELECT inet_server_addr() as host, current_database() as db, current_user as usr")
    host, db, usr = cur.fetchone()
    print(f"Connected to: {host}")
    print(f"Database: {db}, User: {usr}")
    if '::1' in str(host) or '127.0.0.1' in str(host):
        print("\n>>> LOCAL DEVELOPMENT <<<")
        print("Changes here DO NOT reach production users")
    elif 'rds.amazonaws.com' in str(host):
        print("\n>>> AWS PRODUCTION <<<") 
        print("Changes here ARE LIVE for all users")
    else:
        print(f"\n>>> UNKNOWN: {host} <<<")
EOF
```

**Result tells you:**
- `::1` or `127.0.0.1` = **LOCAL** (safe to experiment, won't affect users)
- `algo-db.xxxxx.rds.amazonaws.com` = **AWS PRODUCTION** (all changes live immediately)

---

## Database Configuration (How It Works)

### Connection Priority
1. **If `AWS_RDS_HOST` env var is set** → Connect to AWS RDS
2. **Else** → Connect to local PostgreSQL (default for development)

### Setting AWS Connection (Production)

**Option 1: Via Environment Variables (Best)**
```bash
export AWS_RDS_HOST="algo-db.xxxxx.us-east-1.rds.amazonaws.com"
export AWS_RDS_PORT="5432"
export AWS_RDS_USER="algo_user"
export AWS_RDS_PASS="<password>"
export AWS_RDS_DB="stocks"
```

**Option 2: Via AWS Secrets Manager (Automatic)**
1. Run credential refresh: `scripts/refresh-aws-credentials.ps1`
2. Credentials auto-load from `~/.aws/credentials`
3. Database config fetched from Secrets Manager during connection

**Option 3: Via PowerShell Profile**
Add to `$PROFILE`:
```powershell
$env:AWS_RDS_HOST = "algo-db.xxxxx.us-east-1.rds.amazonaws.com"
$env:AWS_RDS_USER = "algo_user"
```

### Finding Your AWS RDS Endpoint

```bash
# Method 1: AWS CLI
aws rds describe-db-instances --query 'DBInstances[*].[DBInstanceIdentifier,Endpoint.Address]'

# Method 2: Terraform outputs
cd terraform && terraform output rds_endpoint

# Method 3: AWS Console
# RDS → Databases → algo-db → Connectivity & security → Endpoint
```

---

## Common Mistakes & Fixes

| Problem | Cause | Fix |
|---------|-------|-----|
| Changes don't appear in dashboard | Connected to LOCAL db, not AWS | Set `AWS_RDS_HOST` env var |
| "::1:5432 connection" messages | Local PostgreSQL, not AWS | Confirm this is intentional or set AWS env vars |
| "No such table" errors | Wrong database selected | Check database name: `SELECT current_database()` |
| Permission denied on AWS | IAM credentials expired | Run `scripts/refresh-aws-credentials.ps1` |
| Secrets Manager not accessible | Missing IAM permissions | Contact AWS admin for `secretsmanager:GetSecretValue` |

---

## Testing & Verification

### Verify You're Connected to AWS
```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/c/Users/arger/code/algo')
from utils.db.context import DatabaseContext

with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT inet_server_addr() as host, 
               current_database() as db,
               current_user as usr
    """)
    host, db, usr = cur.fetchone()
    print(f"Connected to: {host}:{db} (user: {usr})")
    
    if 'rds.amazonaws.com' in str(host):
        print("✓ AWS PRODUCTION")
    elif '::1' in str(host) or '127.0.0.1' in str(host):
        print("✓ LOCAL DEVELOPMENT")
    else:
        print("? UNKNOWN")
EOF
```

### Check Data Freshness
```bash
# Stock scores last updated
psql -h $AWS_RDS_HOST -U $AWS_RDS_USER -d stocks -c \
  "SELECT COUNT(*), MAX(updated_at) FROM stock_scores"

# Upstream metrics coverage
psql -h $AWS_RDS_HOST -U $AWS_RDS_USER -d stocks -c \
  "SELECT table_name, completion_pct FROM data_loader_status"
```

---

## Production Deployment Checklist

**Before making changes to production data:**
1. ✓ Verify AWS connection: `SELECT inet_server_addr()`
2. ✓ Confirm environment: Production or Local?
3. ✓ Backup or snapshot (if destructive changes)
4. ✓ Test locally first, then apply to AWS
5. ✓ Verify Lambda will pick up new data (clear cache if needed)

**After changes:**
1. ✓ Verify data in AWS: `SELECT COUNT(*) FROM stock_scores`
2. ✓ Restart dashboard to clear cache: `pkill -9 python && python -m dashboard -w`
3. ✓ Test API endpoint: `curl https://api-endpoint/api/scores`
4. ✓ Monitor CloudWatch logs for errors

---

## Dashboard & Caching

### Important: Dashboard Caches Data
- **Scores endpoint (`/api/scores`):** NOT cached (disabled 2026-07-01 to prevent stale trading data)
- **Other endpoints:** Cached for 30 minutes to reduce API load
- **Cache location:** In-memory in dashboard process
- **Clear cache:** Kill and restart dashboard process

### Dashboard Connection
- **Default:** Connects to AWS production (requires `DASHBOARD_API_URL` env var)
- **Local mode:** `python -m dashboard --local` (uses localhost:3001)
- **Config:** Set `DASHBOARD_API_URL` to AWS API endpoint

```bash
# Verify dashboard is using correct API
python -m dashboard --local    # Use local dev API (localhost:3001)
python -m dashboard            # Use AWS production API (needs DASHBOARD_API_URL)
```

---

## Credential Management

### Refresh AWS Credentials
```powershell
# Windows PowerShell
.\scripts\refresh-aws-credentials.ps1

# Fetches from:
# 1. AWS Secrets Manager (algo-developer secrets)
# 2. Writes to ~/.aws/credentials
# 3. Auto-loads in next Python process
```

### Credential TTL & Rotation
- **TTL:** 5 minutes (cache duration)
- **Auto-refresh:** Called at Lambda invocation start
- **Manual refresh:** Run script above before long-running operations
- **On rotation:** Old credentials expire automatically after 5 min

---

## Loaders & Data Pipeline

### Which Loaders Use Which Database

**Local Development (default)**
```bash
python3 loaders/load_stock_scores.py          # Uses LOCAL db
python3 loaders/load_quality_metrics.py       # Uses LOCAL db
```

**AWS Production (via CI/CD)**
```bash
# GitHub Actions workflow
gh workflow run deploy-ecs-image.yml           # Builds + deploys ECS tasks
# ECS tasks run loaders connecting to AWS RDS via environment variables
```

### Loader Environment Configuration

**In ECS Task Definitions:**
```json
{
  "environment": [
    {"name": "AWS_RDS_HOST", "value": "algo-db.xxxxx.us-east-1.rds.amazonaws.com"},
    {"name": "AWS_RDS_USER", "value": "algo_prod"},
    {"name": "AWS_RDS_DB", "value": "stocks"}
  ]
}
```

**Secrets (in Secrets Manager):**
- `AWS_RDS_PASS` — RDS password (not in task definition for security)
- `algo-rds-credentials` — Full connection object with host/user/password/port

---

## Troubleshooting: Data Not Appearing

**Symptom:** Made changes to database, but dashboard still shows old data

**Checklist:**
1. Am I connected to AWS or LOCAL?
   ```bash
   python3 -c "import sys; sys.path.insert(0, '/c/Users/arger/code/algo'); from utils.db.context import DatabaseContext; cur = DatabaseContext('read').__enter__(); cur.execute('SELECT inet_server_addr()'); print(cur.fetchone())"
   ```
   - If `::1` → LOCAL (changes won't reach users)
   - If `rds.amazonaws.com` → AWS (correct)

2. Did the change actually persist in AWS?
   ```bash
   aws rds describe-db-instances --query 'DBInstances[0].Endpoint.Address'
   # Then query the database with that hostname
   ```

3. Is the dashboard cache stale?
   ```bash
   pkill -9 python
   sleep 2
   python -m dashboard -w
   ```

4. Did the Lambda/API pick up the new data?
   - Check Lambda CloudWatch logs
   - Wait 30s for API cache to expire (if cached)
   - Test API: `curl https://api-endpoint/api/scores`

---

## Related Documents

- **GOVERNANCE.md** — Architecture, data contracts, safety rules
- **OPERATIONS.md** — CI/CD, deployment workflows, monitoring
- **DATA_LOADERS.md** — Loader pipeline, parallelism tuning
- **AWS_INFRASTRUCTURE_FIX_STEPS.md** — AWS setup & infrastructure debugging

