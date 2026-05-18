# Data Loading Guide - Complete the AWS Setup

Now that API and frontend are live, load data into the system to see it working end-to-end.

## Current Status

| Component | Status |
|-----------|--------|
| API | ✅ Live at https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com |
| Frontend | ✅ Live at https://d5j1h4wzrkvw7.cloudfront.net |
| Database | ✅ Ready (empty) |
| Data | ⏳ Need to load |

## Option 1: Automatic Loading (Recommended)

Data loaders are scheduled via **EventBridge → ECS Fargate**:
- **Tier 0 (symbols):** Runs first, foundation data
- **Tier 1-2:** Prices and financials run after symbols loaded
- **Tier 3-4:** Signals and metrics run after prices loaded
- **Tier 5:** Advanced metrics run last

**Status:** These run automatically on schedule. If you've just deployed, they'll start on their next scheduled time (check EventBridge rules).

---

## Option 2: Manual Trigger via AWS Console (Fastest for Testing)

### 2A. Trigger via ECS Console

1. **Go to AWS ECS Console**
   - Region: us-east-1
   - Cluster: `algo-cluster`

2. **Run Task Definition**
   - Task Definition: `algo-loaders-stocksymbols-dev` (start with this - foundation data)
   - Launch Type: Fargate
   - Platform Version: LATEST
   - Cluster: algo-cluster
   - Task Count: 1

3. **Network Configuration**
   - VPC: (select algo VPC)
   - Subnets: (private subnets for loaders)
   - Security Groups: (loader security group)
   - Assign public IP: DISABLED

4. **Click "Run Task"**

5. **Repeat for other loaders** (in order):
   - `algo-loaders-loadpricedaily-dev`
   - `algo-loaders-load_price_aggregate-dev`
   - `algo-loaders-loadbuyselldaily-dev`
   - ...etc

**Estimated time:** 30 minutes for Tier 0-1 loaders

### 2B. Trigger via AWS CLI

```bash
# Make sure AWS CLI is configured with credentials
aws configure

# Run stock symbols loader (foundation)
aws ecs run-task \
  --cluster algo-cluster \
  --task-definition algo-loaders-stocksymbols-dev \
  --launch-type FARGATE \
  --network-configuration \
    "awsvpcConfiguration={subnets=[subnet-xxxxx,subnet-xxxxx],securityGroups=[sg-xxxxx],assignPublicIp=DISABLED}" \
  --region us-east-1

# Check task status
aws ecs list-tasks --cluster algo-cluster --region us-east-1
aws ecs describe-tasks --cluster algo-cluster --tasks <task-id> --region us-east-1
```

---

## Option 3: Trigger via Step Functions (Production)

13 critical loaders use **Step Functions** for coordinated execution:
- Avoids rate limiting
- Respects data dependencies
- Automatic retry on failure

To trigger:
1. Go to **AWS Step Functions Console**
2. Find state machine: `algo-data-pipeline-dev`
3. Click **"Start execution"**
4. Optional: Add execution parameters for date range
5. **Confirm**

This orchestrates the full pipeline in dependency order.

---

## Option 4: Local Execution (If Possible)

```bash
# Requires:
# - Python 3.11+
# - PostgreSQL client (or RDS connection)
# - Alpaca API key, FRED API key
# - AWS credentials for RDS connection

# Set environment variables
export DB_HOST=algo-db.cxxx.us-east-1.rds.amazonaws.com
export DB_PORT=5432
export DB_NAME=stocks
export DB_USER=stocks
export DB_PASSWORD=<from-secrets-manager>
export ALPACA_KEY_ID=<your-key>
export ALPACA_SECRET_KEY=<your-secret>

# From project root
cd /path/to/algo
python3 run-all-loaders.py
```

**Note:** Requires networking setup to reach RDS from local machine (VPN or Security Group changes).

---

## Monitoring Data Load Progress

### 1. Watch ECS Tasks
```bash
aws ecs list-tasks --cluster algo-cluster
aws ecs describe-tasks --cluster algo-cluster --tasks <task-id>
```

### 2. Check CloudWatch Logs
- Log Group: `/aws/ecs/algo-loaders`
- Stream: `algo-loaders-{loader-name}/{container-id}`

Example:
```bash
aws logs tail /aws/ecs/algo-loaders --follow
```

### 3. Query Database (once data loads)
```bash
# Via AWS RDS Console or psql:
SELECT COUNT(*) FROM stock_symbols;      -- Should be 2000+
SELECT COUNT(*) FROM price_daily;         -- Should be 100000+
SELECT MAX(date) FROM price_daily;        -- Should be recent date
```

### 4. Check API Responses
```bash
# Should return data instead of empty arrays
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/stocks?symbol=AAPL
```

---

## Data Load Timeline

| Tier | Loaders | Est. Time | Dependencies |
|------|---------|-----------|--------------|
| 0 | Stock symbols | 2-5 min | None (foundation) |
| 1 | Daily prices | 15-30 min | Tier 0 |
| 1b | Price aggregates | 5 min | Tier 1 |
| 1c | Technical indicators | 5-10 min | Tier 1 |
| 2 | Reference data | 20-40 min | Tier 0 |
| 2b | Computed metrics | 10-15 min | Tier 2 |
| 2d | Stock scores | 20-30 min | Tier 2b |
| 3 | Trading signals | 15-20 min | Tier 1 |
| 3b | Signal aggregates | 5 min | Tier 3 |
| 4 | Algo metrics | 5 min | Tier 3 |
| **Total** | **37 loaders** | **~2 hours** | Parallel tiers |

---

## Verifying System Works End-to-End

### 1. Load Data
Choose one of the options above. Start with Tier 0 (symbols).

### 2. Check Frontend Displays Data
Open https://d5j1h4wzrkvw7.cloudfront.net:
- **Market Health** should show indices and charts
- **Top Movers** should show top gainers/losers
- **All dashboards** should show data, no errors

### 3. Test API Endpoints
```bash
# After symbols loaded
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/stocks?symbol=AAPL

# After prices loaded  
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/market/top-movers

# After signals loaded
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/signals/buysell
```

### 4. Check Logs for Errors
```bash
aws logs tail /aws/lambda/algo-api-dev --follow
aws logs tail /aws/ecs/algo-loaders --follow
```

No "ERROR" or "psycopg2" messages = healthy system ✅

---

## Troubleshooting

### API Returns Empty Data
- **Check:** Are loaders running? Check CloudWatch Logs
- **Fix:** Verify database has tables: `aws rds-data execute-statement`
- **Wait:** Data takes time to load (15+ minutes for initial load)

### Frontend Shows "No Data"
- **Check:** API responding? Test endpoint in curl
- **Wait:** Frontend caches data, try browser hard refresh (Ctrl+Shift+R)
- **Check:** Console for JavaScript errors

### Loader Task Fails
- **Check logs:** `aws logs tail /aws/ecs/algo-loaders`
- **Common:** Rate limiting from Alpaca API (normal, auto-retries)
- **Check:** Security group allows RDS access
- **Verify:** Environment variables passed to task

### Rate Limiting Issues
- **Price loaders:** 2 workers (not 4) to avoid rate limits
- **Loaders wait and retry:** Expected behavior
- **Don't force stop:** Let them complete naturally

---

## Next: Full Automation

Once you verify data loads and system works:

1. **Set EventBridge schedules** to auto-run loaders daily
2. **Set algo orchestrator** to run trading logic automatically
3. **Configure alerts** in CloudWatch for failures
4. **Monitor costs** in AWS Billing dashboard

---

## Questions?

Check:
- CloudWatch Logs for detailed error messages
- AWS ECS Cluster status page
- GitHub Actions deployment logs (past runs)
- CLAUDE.md for system architecture

**System is ready!** 🚀 Just needs data.
