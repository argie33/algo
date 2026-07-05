# Dashboard Fix Guide - AWS RDS Configuration

## Problem
Dashboard panels show "no data available" because the AWS RDS `algo_config` table is missing critical configuration values required by the API.

**Missing fields:**
- `min_signal_quality_score`
- `min_swing_score`
- `min_completeness_score`
- `min_volume_ma_50d`
- `min_avg_daily_dollar_volume`
- `earnings_blackout_days_before`
- `earnings_blackout_days_after`

## Solution

### Option 1: Deploy & Invoke Lambda Fix (Recommended)

This is the fastest way to fix the issue in AWS.

#### Step 1: Deploy the Lambda Function

```bash
# From repository root
cd lambda/fix-dashboard-config

# Create deployment package
zip -r lambda_function.zip lambda_function.py

# Deploy to AWS (requires Lambda deployment permissions)
aws lambda create-function \
  --function-name fix-dashboard-config \
  --runtime python3.11 \
  --role arn:aws:iam::626216981288:role/algo-lambda-execution-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda_function.zip \
  --region us-east-1
```

#### Step 2: Invoke the Lambda

```bash
aws lambda invoke \
  --function-name fix-dashboard-config \
  --region us-east-1 \
  --cli-binary-format raw-in-base64-out \
  response.json

# Check result
cat response.json
```

#### Step 3: Restart API Lambda

The API Lambda needs to restart to reload the config:

```bash
# Option A: Wait for next cold start (next invocation after ~15 min idle)
# Option B: Manually restart
aws lambda update-function-code \
  --function-name algo-api-dev \
  --zip-file fileb://lambda_api_code.zip \
  --region us-east-1
```

---

### Option 2: Direct AWS RDS Access (If you have RDS endpoint)

If you have access to the RDS endpoint directly:

```bash
# Run the Python fix script with RDS credentials
python scripts/fix_aws_rds_config.py \
  --host <rds-endpoint>.rds.amazonaws.com \
  --user postgres \
  --password '<password>' \
  --database algo
```

---

### Option 3: Terraform/Infrastructure Code

Add to `terraform/rds.tf` or run manually:

```bash
cd terraform
terraform apply -target=aws_db_instance.algo_rds
```

---

## Verification

After applying the fix:

### 1. Verify Config in Database

```bash
# Query RDS directly or via Lambda
SELECT key, value FROM algo_config 
WHERE key IN ('min_signal_quality_score', 'min_swing_score', 'min_completeness_score',
              'min_volume_ma_50d', 'min_avg_daily_dollar_volume',
              'earnings_blackout_days_before', 'earnings_blackout_days_after');
```

Expected output:
```
min_signal_quality_score  | 60
min_swing_score           | 55.0
min_completeness_score    | 70
min_volume_ma_50d         | 300000
min_avg_daily_dollar_volume | 500000
earnings_blackout_days_before | 7
earnings_blackout_days_after | 3
```

### 2. Test Dashboard

```bash
# Run diagnostics
python -m dashboard.diagnose_dashboard

# Or start dashboard
python -m dashboard

# Check for config errors in the output
```

---

## What Was Wrong

The API Lambda reads from `algo_config` table in RDS. When the dashboard fetches config via `/api/algo/config`, the API validates the response and requires these 7 fields. If they're missing:

1. API returns partial/empty response
2. Dashboard validator raises `ResponseValidationError`
3. Circuit breaker opens after repeated failures
4. All dependent endpoints fail (markets, positions, etc.)
5. Dashboard shows "no data available" for everything

---

## Prevention

To prevent this in the future:

1. **Run migrations on RDS setup**: All config values should be seeded by Alembic migrations
2. **Add pre-deployment checks**: Verify config table has required keys before deploying
3. **Monitor**: Set up CloudWatch alarms for missing config keys

---

## Contact

If the fix doesn't work:
1. Check CloudWatch logs: `/aws/lambda/algo-api-dev`
2. Verify RDS is running and has data
3. Ensure database migrations have run (`alembic upgrade head`)
