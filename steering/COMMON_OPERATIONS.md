# Common Operations Runbook

**Quick reference for everyday tasks. All procedures are tested and verified.**

---

## Problem: Dashboard Shows "Data Not Available"

**Symptom:** Dashboard displays "data not available" on all panels.

**Cause:** Dashboard not connecting to API correctly. Usually:
- Missing `--local` flag (tries to connect to AWS instead of localhost)
- API dev server not running
- Lambda returning 503 errors in AWS

**Quick Fix (Local Development):**
```bash
# Terminal 1: Start API dev server
python3 lambda/api/dev_server.py

# Terminal 2: Start dashboard WITH --local flag (REQUIRED)
python3 -m dashboard --local -w 30

# Verify: Dashboard should show portfolio, positions, trades with real data
```

**If still showing errors:**
1. Check dev server is running: `curl http://localhost:3001/api/health`
2. Check for API errors: `curl http://localhost:3001/api/algo/portfolio`
3. Review dev server logs for errors
4. Run diagnostics: `python3 scripts/diagnose_system.py`

**If using AWS (not local):**
- See [AWS_LAMBDA_503_FIX.md](AWS_LAMBDA_503_FIX.md) for Lambda 503 troubleshooting
- Run: `bash scripts/fix-lambda-vpc.sh`
- Redeploy: `gh workflow run deploy-api-lambda.yml`

---

## Problem: Data Not Appearing in Dashboard

**Symptom:** Made changes to database, but dashboard shows old data.

**Solution:**

1. Verify which database you're on:
```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/c/Users/arger/code/algo')
from utils.db.context import DatabaseContext
with DatabaseContext("read") as cur:
    cur.execute("SELECT inet_server_addr(), current_database()")
    host, db = cur.fetchone()
    print(f"{host}:{db}")
    if '::1' in str(host): print("LOCAL - changes won't reach users")
    else: print("AWS - changes are live")
EOF
```

2. If LOCAL, changes don't affect users. Connect to AWS:
   - See [DATABASE_AND_ENVIRONMENTS.md](DATABASE_AND_ENVIRONMENTS.md) for AWS endpoint

3. If AWS, clear dashboard cache:
```bash
pkill -9 python
sleep 2
python -m dashboard -w
```

4. Verify with API:
```bash
curl "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores?limit=5" | jq '.data[0]'
```

---

## Problem: Scores Show "--" for Many Stocks

**Symptom:** Factor scores display `--` (missing data) for quality_score, growth_score, etc.

**This is EXPECTED** for:
- ~13% of stocks lack SEC filing data (quality_score missing)
- ~18% of stocks lack SEC filing data (growth_score missing)
- Foreign stocks, smaller caps, ADRs often lack data

**But check if genuine data issue:**

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/c/Users/arger/code/algo')
from utils.db.context import DatabaseContext

with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT COUNT(*) as total, 
               SUM(CASE WHEN quality_score IS NULL THEN 1 ELSE 0 END) as missing_qual,
               SUM(CASE WHEN growth_score IS NULL THEN 1 ELSE 0 END) as missing_growth
        FROM stock_scores WHERE composite_score > 0
    """)
    total, missing_q, missing_g = cur.fetchone()
    q_pct = 100 * missing_q / total
    g_pct = 100 * missing_g / total
    print(f"Quality missing: {q_pct:.1f}% ({missing_q}/{total})")
    print(f"Growth missing: {g_pct:.1f}% ({missing_g}/{total})")
    if q_pct > 20 or g_pct > 20:
        print("WARNING: More than 20% missing - check metric loaders")
    else:
        print("OK: Within normal range")
EOF
```

**If too many missing:**
- Check metric loaders ran: `SELECT last_updated FROM data_loader_status`
- Rerun loader: `python3 loaders/load_quality_metrics.py`
- See [DATA_LOADERS.md](DATA_LOADERS.md) for troubleshooting

---

## Problem: Dashboard Won't Start

**Symptom:** `python -m dashboard -w` hangs or crashes.

**Solution:**

1. Kill any stuck processes:
```bash
pkill -9 python
pkill -9 node
```

2. Check API is accessible:
```bash
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores?limit=1
```

3. Check database connection:
```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/c/Users/arger/code/algo')
from utils.db.context import DatabaseContext
try:
    with DatabaseContext("read") as cur:
        cur.execute("SELECT 1")
    print("Database connected OK")
except Exception as e:
    print(f"Database error: {e}")
EOF
```

4. Start dashboard in foreground to see errors:
```bash
cd /c/Users/arger/code/algo
python -m dashboard
```

---

## Problem: AWS Lambda Not Updated After Deployment

**Symptom:** Changed code, deployed via GitHub Actions, but Lambda still uses old code.

**Solution:**

1. Verify deployment completed:
```bash
gh run list -w deploy-api-lambda.yml | head -1
gh run view <run-id> --log | tail -20
```

2. Check Lambda was actually updated:
```bash
aws lambda get-function --function-name algo-api-dev \
  --query 'Configuration.LastModified' --region us-east-1
```

3. If old, redeploy:
```bash
gh workflow run deploy-api-lambda.yml -f force_redeploy=true
```

4. Wait 30 seconds for cache expiration, then test API

---

## Problem: "Connection refused" When Querying Database

**Symptom:** `psycopg2.OperationalError: could not connect to server`

**Solution:**

1. Verify you're not connecting to wrong host:
```bash
echo $AWS_RDS_HOST
echo $AWS_RDS_PORT
# Should show algo-db.xxxxx.us-east-1.rds.amazonaws.com:5432
# NOT localhost or ::1
```

2. If not set, refresh AWS credentials:
```bash
pwsh scripts/refresh-aws-credentials.ps1
```

3. Check AWS RDS is running:
```bash
aws rds describe-db-instances --db-instance-identifier algo-db \
  --query 'DBInstances[0].DBInstanceStatus' --region us-east-1
```

4. Check security group allows inbound 5432:
```bash
aws ec2 describe-security-groups --group-ids sg-xxxxx \
  --query 'SecurityGroups[0].IpPermissions' --region us-east-1
```

---

## Problem: Loaders Timing Out

**Symptom:** Loaders take >30 min, timeout during execution.

**Solution:**

1. Check which loader is slow:
```bash
# Run with verbose output
python3 loaders/load_quality_metrics.py 2>&1 | tail -50
```

2. Check parallelism setting (may be too high):
```bash
python3 loaders/load_quality_metrics.py --parallelism 2
```

3. Check upstream data availability:
```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/c/Users/arger/code/algo')
from utils.db.context import DatabaseContext
with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT table_name, completion_pct, last_updated
        FROM data_loader_status ORDER BY last_updated DESC LIMIT 5
    """)
    for row in cur.fetchall():
        print(row)
EOF
```

**If metrics incomplete:**
- Rerun metric loaders with lower parallelism
- See [DATA_LOADERS.md](DATA_LOADERS.md#parallelism-tuning)

---

## Problem: Pre-commit Hook Fails

**Symptom:** `git commit` blocked by type errors, linting, or other checks.

**Solution:**

```bash
# See what failed
make ci-local

# Fix code
make format          # Auto-format
make type-check      # Check types
make lint            # Check linting

# Or fix specific issues
mypy <file>.py       # Type check one file
ruff check --fix <file>.py  # Auto-fix linting
```

**If you must skip (not recommended):**
```bash
git commit --no-verify
```

---

## Problem: Stock Score Calculation Failed

**Symptom:** Loader error: "Cannot compute score for AAPL"

**Solution:**

1. Check what metrics are available:
```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/c/Users/arger/code/algo')
from utils.db.context import DatabaseContext

symbol = "AAPL"
with DatabaseContext("read") as cur:
    for metric in ['quality', 'growth', 'value', 'positioning', 'stability', 'momentum']:
        cur.execute(f"SELECT COUNT(*) FROM {metric}_metrics WHERE symbol = %s", (symbol,))
        count = cur.fetchone()[0]
        print(f"{metric:15} {'✓' if count > 0 else '✗'}")
EOF
```

2. If metrics missing, rerun metric loaders for that symbol:
```bash
python3 loaders/load_quality_metrics.py --symbols AAPL
python3 loaders/load_positioning_metrics.py --symbols AAPL
```

3. Recompute stock score:
```bash
python3 loaders/load_stock_scores.py --symbols AAPL
```

---

## Problem: Need to Clear Cache Manually

**Symptom:** Dashboard is serving completely stale data.

**Solution:**

Clear both dashboard AND API caches:

```bash
# Kill dashboard (in-memory cache)
pkill -9 python

# Wait 30+ seconds for API cache to expire
sleep 35

# Restart dashboard
python -m dashboard -w
```

**Note:** `/api/scores` endpoint is never cached (by design to prevent stale trading data), but other endpoints cache for 30 min.

---

## Running Full Test Suite

**Verify everything works before deploying:**

```bash
make ci-local        # Full CI pipeline locally
```

Or individual checks:

```bash
make lint            # Linting
make type-check      # Type checking
make format          # Auto-format
make test            # Unit + integration tests
make coverage        # Coverage report
```

---

## Deploying Changes to Production

**Safe deployment checklist:**

1. ✓ All changes committed: `git status`
2. ✓ Tests pass locally: `make test`
3. ✓ Type checking passes: `make type-check`
4. ✓ Pre-commit passes: `git commit` (don't use `--no-verify`)
5. ✓ Push to main: `git push origin main`
6. ✓ GitHub Actions runs CI/CD automatically
7. ✓ Monitor Lambda: `aws lambda get-function --function-name algo-api-dev`
8. ✓ Test API: `curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores?limit=1`

See [OPERATIONS.md](OPERATIONS.md) for full deployment details.

---

## Getting Help

| Issue | Guide |
|-------|-------|
| Database/AWS setup | [DATABASE_AND_ENVIRONMENTS.md](DATABASE_AND_ENVIRONMENTS.md) |
| Data flow & loader issues | [DATA_LOADERS.md](DATA_LOADERS.md) |
| Code quality | [LINT_POLICY.md](LINT_POLICY.md) |
| Architecture questions | [GOVERNANCE.md](GOVERNANCE.md) |
| Configuration & monitoring | [OPERATIONS.md](OPERATIONS.md) |
| Deployment | [OPERATIONS.md](OPERATIONS.md) |

---

