# Algo Orchestrator Deployment

## Overview

The algo orchestrator runs **daily at 5:30pm ET** (market close) via **AWS Lambda + EventBridge**. It executes the complete end-of-day workflow:

1. **Pre-flight checks** — Verify algo components are loaded
2. **Pre-load patrol** — Validate existing data health
3. **Load EOD data** — Run loaders (price, signals, metrics)
4. **Post-load patrol** — Validate new data
5. **Auto-remediation** — Fix any data issues
6. **Execute algo** — Trade if all checks passed

---

## Architecture

```
EventBridge Rule (cron(0 21 * * ? *))
    ↓ Daily at 5:30pm ET
AWS Lambda Function (algo-orchestrator)
    ├─ Pre-flight checks
    ├─ algo_data_patrol.py
    ├─ run_eod_loaders.sh (loads price, signals, metrics)
    ├─ algo_data_patrol.py (validate)
    ├─ algo_data_remediation.py (fix issues)
    ├─ algo_orchestrator.py (execute trades)
    ├─ SNS alert (success/failure)
    └─ CloudWatch logs
```

---

## Files

### GitHub Actions
- **`.github/workflows/deploy-algo-orchestrator.yml`** (230 lines)
  - Triggers: algo_*.py changes or manual dispatch
  - Jobs: Validate → Install deps → Package → Deploy Lambda → Deploy EventBridge

### Lambda
- **`lambda/algo_orchestrator/lambda_function.py`** (280 lines)
  - Handler: `lambda_function.lambda_handler`
  - Runs the full EOD flow
  - Fetches secrets from AWS Secrets Manager
  - Logs to CloudWatch
  - Sends SNS alerts

- **`lambda/algo_orchestrator/__init__.py`**
  - Makes it a Python package

### Infrastructure
- **`template-algo-orchestrator.yml`** (260 lines)
  - CloudFormation template
  - Lambda function (512MB, 15 min timeout)
  - EventBridge rule (5:30pm ET daily)
  - IAM role with permissions
  - SNS topic for alerts
  - CloudWatch alarms and logs

---

## Deployment Process

### Prerequisites

**AWS Secrets (must exist):**
```bash
# Database credentials
aws secretsmanager create-secret \
  --name stocks-db-credentials \
  --secret-string '{
    "host": "rds-endpoint.rds.amazonaws.com",
    "port": 5432,
    "username": "postgres",
    "password": "...",
    "dbname": "stocks"
  }'

# Alpaca API keys
aws secretsmanager create-secret \
  --name alpaca-api-keys \
  --secret-string '{
    "api_key": "...",
    "api_secret": "..."
  }'
```

**S3 Bucket for Lambda artifacts:**
```bash
aws s3 mb s3://your-lambda-artifacts-bucket
```

**GitHub Secrets:**
- `AWS_ACCOUNT_ID` — Your AWS account number
- `LAMBDA_ARTIFACTS_BUCKET` — S3 bucket name

### Deploy

**Option 1: Push to main (automatic)**
```bash
git add .github/workflows/deploy-algo-orchestrator.yml \
        lambda/algo_orchestrator/ \
        template-algo-orchestrator.yml
git commit -m "Deploy algo orchestrator to Lambda"
git push origin main
```

**Option 2: Manual trigger (for testing)**
```bash
# In GitHub UI:
# Actions → Deploy Algo Orchestrator → Run workflow
# Set: environment=dev, dry_run=true
```

---

## How It Works

### Daily Execution (5:30pm ET)

1. **EventBridge rule fires** (cron(0 21 * * ? *))
2. **Lambda starts** with environment variables set
3. **Fetches database credentials** from AWS Secrets Manager
4. **Runs each step in sequence:**
   - Verifies algo components load correctly
   - Runs patrol checks (stop on critical issues)
   - Loads fresh EOD data
   - Validates new data
   - Auto-fixes issues
   - Executes algo if patrol passed
5. **Logs everything** to CloudWatch
6. **Sends alert** via SNS (success/failure)

### Manual Testing

**Trigger manually (dry-run):**
```bash
aws lambda invoke \
  --function-name algo-orchestrator \
  --payload '{"dry_run": true}' \
  /tmp/response.json
```

**Check logs:**
```bash
aws logs tail /aws/lambda/algo-orchestrator --follow
```

---

## Configuration

### Environment Variables

Set via CloudFormation parameters:

| Variable | Default | Options |
|----------|---------|---------|
| `EXECUTION_MODE` | `paper` | `paper` \| `live` |
| `DRY_RUN_MODE` | `true` | `true` \| `false` |
| `ENVIRONMENT` | `dev` | `dev` \| `staging` \| `prod` |

### Safety Gates

✅ **Pre-flight checks** — Verify components load  
✅ **Pre-load patrol** — Stop if existing data is bad  
✅ **Post-load patrol** — Stop if new data is bad  
✅ **Auto-remediation** — Fix issues automatically  
✅ **Execution gate** — Skip trades if patrol failed  
✅ **Dry-run mode** — Preview trades, no execution  
✅ **Paper trading** — Default execution_mode (no live trades)  
✅ **SNS alerts** — Notified of every execution  
✅ **CloudWatch logs** — Full audit trail

---

## Monitoring

### CloudWatch Logs
```bash
# View logs in real-time
aws logs tail /aws/lambda/algo-orchestrator --follow

# View specific execution
aws logs filter-log-events \
  --log-group-name /aws/lambda/algo-orchestrator \
  --start-time $(date -d '1 hour ago' +%s)000
```

### CloudWatch Alarms
- **algo-orchestrator-errors-{env}** — Alert if Lambda errors > 0
- **algo-orchestrator-timeout-{env}** — Alert if duration > 850s (14.7 min)

### SNS Alerts
Subscribe to topic: `algo-orchestrator-alerts-{env}`
```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:ACCOUNT:algo-orchestrator-alerts-dev \
  --protocol email \
  --notification-endpoint your-email@example.com
```

---

## Troubleshooting

### Lambda fails at runtime

**Check logs:**
```bash
aws logs tail /aws/lambda/algo-orchestrator --follow
```

**Common issues:**
- Missing AWS Secrets → Verify secrets exist in Secrets Manager
- Missing database → Verify RDS endpoint is correct
- Python import errors → Verify dependencies are packaged in zip

### EventBridge rule not firing

**Check rule:**
```bash
aws events describe-rule --name algo-eod-orchestrator
aws events list-targets-by-rule --rule algo-eod-orchestrator
```

**Enable rule:**
```bash
aws events enable-rule --name algo-eod-orchestrator
```

### Dry-run shows errors but live trades execute anyway

**Check execution_mode:**
- Should be `paper` by default
- Only set to `live` if explicitly required

**Check DRY_RUN mode:**
- Set `DRY_RUN_MODE=true` to preview without executing

---

## Disabling/Re-enabling

### Disable scheduled execution
```bash
aws events disable-rule --name algo-eod-orchestrator
```

### Re-enable scheduled execution
```bash
aws events enable-rule --name algo-eod-orchestrator
```

### Delete and redeploy
```bash
aws cloudformation delete-stack --stack-name stocks-algo-orchestrator
# Wait for deletion to complete
git push origin main  # Or manually trigger workflow
```

---

## Cost

**Typical monthly costs:**
- Lambda: ~$0.50 (1 invocation/day × 30 days × execution time)
- SNS: ~$0.50 (alerts)
- CloudWatch: ~$1.00 (logs)
- **Total: ~$2/month**

---

## Next Steps

1. ✅ Create AWS Secrets (database + Alpaca)
2. ✅ Create S3 bucket for artifacts
3. ✅ Add GitHub Secrets (AWS_ACCOUNT_ID, LAMBDA_ARTIFACTS_BUCKET)
4. ✅ Deploy: `git push origin main`
5. ✅ Monitor: Check CloudWatch logs at 5:30pm ET
6. ✅ Verify: Check SNS alerts + database for trades

