# AWS Data Loader & Schema Deployment Guide

**Goal:** Deploy fixed code to AWS, apply migrations, and populate database with real data.

**Status:** Code ✅, Schema prepared ✅, Data 🟡 (needs population on AWS)

---

## Step 1: Deploy Code to AWS Lambda

The code has been fixed (circuit breaker columns, contracts, migrations). Deploy it:

```bash
# Option A: Via GitHub Actions (Recommended)
gh workflow run deploy-api-lambda.yml
gh workflow run deploy-orchestrator-lambda.yml

# Monitor:
gh run list --workflow deploy-api-lambda.yml
```

Or manually via AWS Console: Lambda → algo-api-dev & algo-orchestrator → Update code.

---

## Step 2: Apply Database Migrations on AWS RDS

**Via AWS CloudShell (Recommended):**

```bash
# 1. Clone repo
git clone https://github.com/argeropolos/algo.git
cd algo

# 2. Set AWS RDS credentials
export DB_HOST="algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com"
export DB_PORT="5432"
export DB_USER="postgres"
export DB_NAME="algo"

# Fetch password from Secrets Manager:
export DB_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id algo-rds-credentials \
  --query SecretString --output text | jq -r '.password')

# 3. Run migrations (applies 80+ pending migrations)
python3 migrations/run.py apply --all

# 4. Check status
python3 migrations/run.py status
```

**Expected output:** All pending migrations applied, schema ready for data.

---

## Step 3: Populate Database with Data (Critical for Scores Display)

Run data loaders on AWS Lambda or ECS. **These require network access to AWS APIs:**

### Option A: Trigger Orchestrator (Runs All Loaders in Sequence)

```bash
# Manually trigger Phase 1-9 orchestrator run
aws lambda invoke \
  --function-name algo-orchestrator \
  --payload '{}' \
  --region us-east-1 \
  response.json

# Monitor progress
tail -f response.json
```

### Option B: Run Specific Loaders (Faster, Parallel)

```bash
# In AWS CloudShell, run critical loaders in parallel:

# Load prices (most important for scoring)
python3 -m loaders.load_prices --backfill-days 30 &

# Load market health (SPY, VIX, breadth)
python3 -m loaders.load_market_health_daily &

# Load market sentiment
python3 -m loaders.load_aaii_sentiment &

# Load stock scores (requires prices + metrics)
python3 -m loaders.load_stock_scores --backfill-days 30 &

# Wait for all to complete
wait

echo "All loaders complete - dashboard should show scores now"
```

---

## Step 4: Verify Data & Endpoints

```bash
# Check data freshness
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/algo/markets

# Expected response:
# {
#   "spy_close": 744.78,
#   "vix_level": 16.15,
#   "regime": "uptrend",
#   ...
# }

# Check scores are loading
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/scores

# Expected: statusCode 200 with stock scores
```

---

## Key Tables Populated After Step 3

| Table | Records | Use |
|-------|---------|-----|
| `price_daily` | 8.5M+ | Prices for technical indicators |
| `stock_scores` | 3,973 | Composite scores (displayed on dashboard) |
| `market_sentiment` | 250+ | Fear/greed, sentiment for portfolio sizing |
| `orchestrator_execution_log` | N+ | Run history and status |
| `algo_signals` | 50K+ | Trading signals |

---

## Troubleshooting

**Q: Migrations fail with "UndefinedTable" or "UndefinedColumn"**
- A: Some migrations may have conflicts with views (e.g., sector_allocation_summary). Check migration logs and skip the problematic migration. Critical migrations (052, 066, 056) are safe.

**Q: Loaders fail with "breadth data missing"**
- A: Market breadth data may not be available from external sources. This is expected—data quality degrades gracefully. API returns 503 for missing market data, not an error.

**Q: Dashboard still shows "stale data"**
- A: Loaders must complete and write to database. Check:
  ```bash
  # View loader status
  aws logs tail /aws/ecs/algo-loaders --follow
  
  # Check last data write
  psql -h algo-db.xxx.rds.amazonaws.com -U postgres -d algo \
    -c "SELECT COUNT(*), MAX(created_at) FROM price_daily"
  ```

---

## What Happens Next (Automated on Schedule)

Once deployed:
1. **EventBridge** triggers orchestrator every 5 min during market hours (1-8 PM EST, Mon-Fri)
2. **Phase 1-9 run:** Loads data, computes scores, updates positions
3. **Dashboard auto-updates:** Shows fresh scores, portfolio, signals
4. **Alerts:** Triggered if circuit breakers activate

---

## Related Docs
- `steering/OPERATIONS.md` — CI/CD and deployment workflows
- `steering/GOVERNANCE.md` — Data quality rules (fail-fast, data_unavailable)
- `steering/DATABASE_AND_ENVIRONMENTS.md` — Database config, credentials
