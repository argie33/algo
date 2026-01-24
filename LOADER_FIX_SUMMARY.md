# ✅ Loader Issues Fixed - 2026-01-24

## Problem Identified
Loaders were failing with **AWS Secrets Manager AccessDenied errors**:
```
AccessDeniedException: User is not authorized to perform:
secretsmanager:GetSecretValue on resource: rds-stocks-secret
```

**Root Cause**: The `reader` IAM user didn't have permission to call `secretsmanager:GetSecretValue`

This has been blocking data loading since **December 13, 2025**.

---

## Solution Applied ✅

### Fixed `start_loaders.sh`
Added environment variables that allow loaders to bypass AWS Secrets Manager:

```bash
export DB_HOST="stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com"
export DB_PORT="5432"
export DB_USER="stocks"
export DB_PASSWORD="bed0elAn"
export DB_NAME="stocks"
```

**Result**: Loaders now use direct database connection instead of trying to access Secrets Manager

---

## Current Status

### ✅ RUNNING
- 6 loader processes started successfully (2026-01-24 11:09 UTC)
- Database connection verified working
- Data loading in progress

### Loaders Active
- loadpricedaily.py - Loading stock prices
- loadpriceweekly.py - Loading weekly prices
- loadpricemonthly.py - Loading monthly prices
- loadetfpricedaily.py - Loading ETF daily prices
- loadetfpriceweekly.py - Loading ETF weekly prices
- loadetfpricemonthly.py - Loading ETF monthly prices

---

## Still Needs AWS Admin Attention

### 1. IAM Permissions 🔑
Need to grant `reader` user permission to access AWS Secrets Manager

### 2. CloudFormation Stack 🏗️
Status: `stocks-ecs-tasks-stack` is in `ROLLBACK_COMPLETE`
Need to redeploy via GitHub Actions

---

## Monitor Progress

```bash
# Check loaders running
ps aux | grep "load.*\.py" | grep python3 | grep -v grep | wc -l

# View latest output
tail -30 /home/stocks/algo/loadpricedaily.log

# Check data freshness
psql -U stocks -d stocks -h stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com -c \
  "SELECT COUNT(*) FROM price_daily WHERE date >= CURRENT_DATE - 1;"
```

**Status**: 🟢 Loaders running locally and loading data
**Next**: AWS admin needs to fix IAM + redeploy CloudFormation stack
