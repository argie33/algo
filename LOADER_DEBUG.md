# Loader Debug Status

## Summary
Stock symbols loaded successfully (10,142 items), but price loaders are not loading data into the database despite multiple Tier 1 runs.

## Current State

### ✅ Working
- API deployed and responding to requests
- Frontend deployed on CloudFront
- Stock symbols successfully loaded (Tier 0) - 10,142 stocks
- Database connection works (proven by stock symbols loading)
- ECS tasks can execute Python code and HTTP requests

### ❌ Not Working
- Price loaders (Tier 1) - returning 0 data to API
- No error messages in GitHub Actions logs
- ECS task logs not visible in this environment

## Root Cause Hypothesis
The ECS task execution role likely lacks IAM permissions to read from AWS Secrets Manager. When the loader runs in ECS:

1. Task tries to load DB_PASSWORD from injected secrets
2. If Secrets Manager read fails, injection doesn't happen
3. Loader can't get database password and fails silently
4. Database connection fails, no data inserted
5. API returns 0 prices

## What to Check

### 1. CloudWatch Logs (User Access Required)
Check `/ecs/algo-stock_prices_daily-loader` log group for any error messages from the price loader tasks that ran at:
- First run: ~06:46 UTC (26031482744)
- Second run: ~12:20 UTC (26033070042)

Look for:
```
Database password not available
OperationalError: connection failed
Exception in OptimalLoader
```

### 2. IAM Permissions
Verify the ECS task execution role has permissions:
```
secretsmanager:GetSecretValue
secretsmanager:DescribeSecret
```
For the database credentials secret ARN.

### 3. Secrets Manager Verification
Confirm the database secret exists and contains:
- `username` 
- `password` 
- `host`
- `port`
- `dbname`

## How to Fix

### Option 1: Fix IAM Permissions (Recommended)
Add to the ECS task execution role policy:
```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:GetSecretValue",
    "secretsmanager:DescribeSecret"
  ],
  "Resource": ["arn:aws:secretsmanager:*:*:secret:algo*"]
}
```

Then re-trigger Tier 1 loaders.

### Option 2: Manual Data Load
If IAM fix doesn't work, manually load price data:
```bash
python3 loaders/loadpricedaily.py --symbols AAPL,MSFT
```
(Requires AWS RDS credentials set as environment variables)

### Option 3: Check Alternate Credential Path
Verify `credential_manager.py` can access Secrets Manager:
```bash
python3 -c "from config.credential_manager import get_credential_manager; cm=get_credential_manager(); print(cm.get_db_credentials())"
```

## Files Modified
- `terraform/modules/loaders/main.tf` - ECS task definition with Secrets Manager injection
- `config/credential_helper.py` - Credential fallback logic

## Next Steps
1. Check CloudWatch logs for actual error messages
2. Verify ECS task execution IAM role has Secrets Manager permissions
3. Re-trigger Tier 1 loaders after fixing IAM (if needed)
4. Verify API returns non-zero prices: `curl https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com/api/prices/history/AAPL`
