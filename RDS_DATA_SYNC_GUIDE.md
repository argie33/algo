# AWS RDS Data Synchronization Guide

## Goal
Populate AWS RDS with stock market data from local PostgreSQL database so the frontend displays real data.

## Current State
- ✅ Local PostgreSQL: 10,142 stocks + 171,169 prices loaded
- ✅ AWS RDS: Provisioned, accessible, but EMPTY
- ✅ API endpoints: Responding, ready for data
- ✅ Frontend: Serving, waiting for real data

## Quick Start (3 minutes)

### Step 1: Get RDS Endpoint
```bash
# Option A: From AWS Console
# 1. Go to AWS RDS Dashboard
# 2. Find "algo-db" instance
# 3. Copy the "Endpoint" (format: algo-db-xxx.us-east-1.rds.amazonaws.com)

# Option B: From Terraform (requires AWS credentials)
cd terraform
terraform output rds_address
```

### Step 2: Run Loaders Against RDS
```bash
# Set environment variables with RDS credentials
export DB_HOST=<RDS-endpoint-from-above>
export DB_PORT=5432
export DB_USER=stocks        # Same as local
export DB_PASSWORD=<RDS-password>  # From GitHub Secrets or terraform.tfvars
export DB_NAME=stocks

# Run all loaders
python3 run-all-loaders.py

# Expected: 181,687+ records loaded into RDS
# Time: 20-30 minutes
```

### Step 3: Verify Data in RDS
```bash
# Test that data is in RDS
python3 << 'EOF'
import psycopg2
import os

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT', 5432),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)

cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM price_daily")
print(f"Prices in RDS: {cur.fetchone()[0]:,}")
cur.close()
conn.close()
EOF
```

### Step 4: Verify Frontend Shows Real Data
```bash
# Visit the frontend (CloudFront)
open https://d5j1h4wzrkvw7.cloudfront.net

# Or test via API
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/prices/history/AAPL?limit=1
# Should now return actual price data
```

---

## Getting RDS Credentials

### From GitHub Secrets
1. Go to: https://github.com/argie33/algo/settings/secrets/actions
2. Look for `RDS_PASSWORD`
3. That's your RDS master password

### From terraform.tfvars (if stored locally)
```bash
grep rds_password terraform/terraform.tfvars
```

### From AWS Secrets Manager (if you have credentials)
```bash
aws secretsmanager get-secret-value \
  --secret-id algo/rds/master \
  --region us-east-1 \
  --query SecretString --output text | jq .password
```

---

## Alternative: Trigger GitHub Actions

If you prefer AWS to run the loaders:

```bash
# 1. Make a commit to trigger deployment
git add .
git commit -m "trigger: Populate RDS with loaders"
git push origin main

# 2. Wait for deployment to complete
# Watch: https://github.com/argie33/algo/actions

# 3. Auto-populate workflow will trigger
# The 'auto-populate-on-first-deploy' workflow will:
#    - Trigger the algo-eod-pipeline state machine
#    - Run loaders in AWS
#    - Populate RDS (takes 30-45 minutes)
```

---

## Troubleshooting

### "Connection refused" error
- Verify RDS_HOST is correct (format: `algo-db-xxx.us-east-1.rds.amazonaws.com`)
- Verify Security Group allows inbound on port 5432
- Verify DB_USER and DB_PASSWORD are correct

### "Database does not exist" error
- Verify DB_NAME=stocks (must match terraform variable)
- RDS should have "stocks" database created by Terraform

### Loaders slow or timing out
- This is normal, loaders take 20-30 minutes
- Check CloudWatch logs: https://console.aws.amazon.com/cloudwatch

### RDS still empty after loaders complete
- Verify loaders completed without errors
- Check `SELECT COUNT(*) FROM stock_symbols` — should have 10,142+ rows
- Check `SELECT COUNT(*) FROM price_daily` — should have 171,169+ rows

---

## What Gets Synced

When you run the loaders against RDS, these tables get populated:

| Table | Records | Purpose |
|-------|---------|---------|
| stock_symbols | 10,142 | Ticker symbols and names |
| price_daily | 171,169 | OHLCV price history |
| company_profile | 378 | Company fundamentals |
| technical_indicators | ~50K | RSI, MACD, SMA, etc |
| key_metrics | ~5K | Market cap, ratios, etc |
| ... | ... | Other trading data |

**Total: ~181,687+ records**

---

## Next: Run Orchestrator with Real Data

Once RDS is populated with real data:

```bash
# The orchestrator will connect to RDS and execute trades
export DB_HOST=<RDS-endpoint>
export DB_USER=stocks
export DB_PASSWORD=<RDS-password>
export DB_NAME=stocks
export ALPACA_API_KEY=<your-key>
export ALPACA_SECRET_KEY=<your-secret>

# Test with paper trading (no real money at risk)
python3 algo/algo_orchestrator.py --dry-run

# Run live paper trading
python3 algo/algo_orchestrator.py
```

---

## Done!

After following these steps:
- ✅ Frontend will display real stock data
- ✅ APIs will return actual price histories
- ✅ Orchestrator can execute real trades
- ✅ System is fully operational for trading

Questions? Check STATUS.md or DEPLOYMENT_GUIDE.md for more context.
