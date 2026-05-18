# System Verification Checklist - 2026-05-18

## Current Status Summary

### ✅ Working Components
- **Local PostgreSQL Database:** Connected, 1.5M+ price records, fully populated
- **Stock Symbol Loader:** `python3 loaders/loadstocksymbols.py` executes successfully
- **Frontend Application:** https://d5j1h4wzrkvw7.cloudfront.net returns 200 OK
- **API Lambda Health:** `/api/health` endpoint returns HTTP 200 OK
- **AWS Infrastructure:** Terraform deployment complete, all resources created

### ⚠️ Issues to Fix
- **Lambda → RDS Connection:** `/api/metrics` endpoint fails with "database connection failed"
  - **Root Cause:** Lambda function can't access RDS with current credentials
  - **Fix:** Verify GitHub Actions secrets and Lambda environment variables

---

## Action Items (In Order)

### 1. Verify GitHub Actions Secrets [CRITICAL]
**Time: 5 minutes**

Go to: https://github.com/argie33/algo/settings/secrets/actions

**Required secrets that must be set:**
```
☐ AWS_ACCOUNT_ID              (12-digit AWS account number)
☐ RDS_PASSWORD                (Your PostgreSQL password)
☐ ALPACA_API_KEY_ID           (From Alpaca dashboard)
☐ ALPACA_API_SECRET_KEY       (From Alpaca dashboard)
☐ JWT_SECRET                  (Any random 32-character string)
☐ FRED_API_KEY                (From Federal Reserve site)
```

**Action:** If any are missing, click "New repository secret" and add them.

---

### 2. Verify Lambda Environment Variables [CRITICAL]
**Time: 10 minutes** (requires AWS Console access)

Go to: https://console.aws.amazon.com/lambda/home?region=us-east-1#/functions

1. Click function: `stocks-api-dev`
2. Click "Configuration" tab
3. Click "Environment variables"

**Required variables that must exist:**
```
✓ DB_SECRET_ARN         (ARN of RDS credentials in Secrets Manager)
✓ DB_ENDPOINT          (RDS endpoint: algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com)
✓ DB_NAME              (Database: stocks)
✓ COGNITO_USER_POOL_ID (Cognito pool ID from Terraform output)
✓ COGNITO_CLIENT_ID    (Cognito client ID from Terraform output)
```

**How to fix if missing:**
```bash
# Check Terraform outputs for the values
cd terraform
terraform output -json | jq '{
  rds_endpoint: .rds_endpoint.value,
  rds_credentials_arn: .rds_credentials_secret_arn.value,
  cognito_user_pool: .cognito_user_pool_id.value,
  cognito_client: .cognito_client_id.value
}'

# Then update Lambda via console or:
aws lambda update-function-configuration \
  --function-name stocks-api-dev \
  --environment Variables={DB_SECRET_ARN=$SECRET_ARN,DB_ENDPOINT=$ENDPOINT,DB_NAME=stocks}
```

---

### 3. Verify Secrets Manager Has RDS Credentials
**Time: 5 minutes**

Go to: https://console.aws.amazon.com/secretsmanager/home?region=us-east-1

**Should see secrets like:**
- `stocks-algo-secrets-dev` (or similar)
- Contains: `username`, `password`, `engine`, `host`, `port`, `dbname`

**If missing:** Terraform should create this. Re-run:
```bash
cd terraform
terraform apply
```

---

### 4. Test Each Component Locally [RECOMMENDED]
**Time: 15 minutes**

```bash
# Test 1: Database connection
python3 -c "
import sys
sys.path.insert(0, '.')
from utils.db_connection import get_db_connection
conn = get_db_connection()
print('DB connection OK' if conn else 'DB connection FAILED')
"

# Test 2: Run a loader
timeout 30 python3 loaders/loadstocksymbols.py

# Test 3: Check frontend
curl https://d5j1h4wzrkvw7.cloudfront.net/api/health

# Test 4: Check API lambda
curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health
```

---

### 5. If Lambda Still Can't Connect to RDS
**Possible causes and fixes:**

**A. Security Group Issue**
```bash
# Check if RDS security group allows Lambda traffic
aws ec2 describe-security-groups \
  --group-ids sg-xxxxx \
  --query 'SecurityGroups[0].IpPermissions'
```

**B. Subnet Issue**
```bash
# Verify Lambda and RDS are in same VPC
aws lambda get-function-configuration \
  --function-name stocks-api-dev \
  --query 'VpcConfig'
```

**C. IAM Role Issue**
```bash
# Verify Lambda role can read Secrets Manager
aws iam get-role-policy \
  --role-name stocks-svc-api-dev \
  --policy-name lambda-secrets-access
```

---

## Quick Validation Commands

**After all above are fixed, run:**

```bash
# Test local database
python3 -c "
import sys
sys.path.insert(0, '.')
from utils.db_connection import get_db_connection
conn = get_db_connection()
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM stock_symbols, price_daily;')
print(cursor.fetchone())
"

# Test API endpoints
curl -s https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health | jq .
curl -s https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/metrics | jq .

# Test frontend loads with data
# Open: https://d5j1h4wzrkvw7.cloudfront.net
# Check browser console for errors
# Verify dashboard shows stock data
```

---

## When Everything Works

All these should return 200 OK with valid JSON:
1. ✅ Frontend: https://d5j1h4wzrkvw7.cloudfront.net
2. ✅ API Health: https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/health  
3. ✅ API Metrics: https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/metrics
4. ✅ Local DB: `python3 run-all-loaders.py` executes without errors
5. ✅ Loaders: Individual loader scripts execute and insert data

---

## Reference

- **Deployment Guide:** DEPLOYMENT_GUIDE.md
- **Local Setup:** LOCAL_CRED_SETUP.md
- **Troubleshooting:** troubleshooting-guide.md
- **Terraform Outputs:** `cd terraform && terraform output -json`
- **GitHub Actions:** https://github.com/argie33/algo/actions

---

**Status:** Ready for verification. Follow checklist items 1-2 to fix Lambda connectivity.
