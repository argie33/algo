# AWS Deployment Setup Checklist

## Step 1: Prepare AWS Account & Credentials

### Create IAM User for GitHub Actions

1. **Go to AWS Console** → IAM → Users → Create User
   - Username: `algo-github-deployer`
   - Access type: Programmatic access (Access key ID + Secret access key)

2. **Attach Permissions Policy:**
   - Use inline policy or managed policies:
     - `AdministratorAccess` (easiest for testing)
     - OR custom policy with: EC2, RDS, Lambda, IAM, S3, ECR, EventBridge, CloudWatch, SNS, SES

3. **Save Credentials:**
   - Access Key ID: `AKIA...`
   - Secret Access Key: `wJalr...`
   - (You'll use these for GitHub secrets)

4. **Create RDS Master Password:**
   - Example: `StocksTradingDB2024!` (alphanumeric, 8+ chars)
   - (Don't use special chars at start/end if using Terraform)
   - Actually use: `StocksTradingDB2024` (safer)

---

## Step 2: Configure GitHub Secrets

### Go to GitHub Repository Settings

1. **Navigate to:** https://github.com/argie33/algo/settings/secrets/actions

2. **Add These Secrets** (click "New repository secret" for each):

| Secret Name | Value | Notes |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | `AKIA...` from IAM user | From Step 1 |
| `AWS_SECRET_ACCESS_KEY` | `wJalr...` from IAM user | From Step 1 |
| `RDS_PASSWORD` | `StocksTradingDB2024` | Min 8 chars, alphanumeric |
| `ALPACA_API_KEY_ID` | Your Alpaca key | From https://app.alpaca.markets/paper/settings/api |
| `ALPACA_API_SECRET_KEY` | Your Alpaca secret | From Alpaca settings |
| `ALERT_EMAIL_ADDRESS` | `your-email@example.com` | For CloudWatch alarms (optional) |
| `JWT_SECRET` | `generate-random-string` | For API authentication |
| `FRED_API_KEY` | Your FRED API key | From https://fred.stlouisfed.org/docs/api/api_key.html (optional) |
| `EXECUTION_MODE` | `paper` | paper or live |
| `ORCHESTRATOR_DRY_RUN` | `false` | false to actually execute |
| `ORCHESTRATOR_LOG_LEVEL` | `INFO` | INFO, DEBUG, WARNING |
| `DATA_PATROL_ENABLED` | `true` | Enable data validation |
| `DATA_PATROL_TIMEOUT_MS` | `30000` | Timeout in milliseconds |

### Verify All Secrets Are Set

```bash
# You can't view values, but you can see which ones exist
# Go to Settings > Secrets and Variables > Actions
# You should see all 13 secrets listed
```

---

## Step 3: Verify Terraform Configuration

```bash
cd terraform

# Validate syntax
terraform validate
# Expected: Success! Valid configuration

# Format check
terraform fmt -check
# If it says files need formatting:
terraform fmt -recursive

# Show variables
terraform variables | head -20
```

---

## Step 4: Trigger Deployment Workflow

### Option A: Automatic (Recommended)

Just push any change to main:
```bash
# From Windows PowerShell or WSL
git log --oneline -1
# You should see recent commits

# If there are no new commits, make a trivial change
echo "# Deployment ready" >> DEPLOYMENT_NOTES.md
git add DEPLOYMENT_NOTES.md
git commit -m "chore: Ready for AWS deployment"
git push origin main
```

Then watch GitHub Actions:
1. Go to https://github.com/argie33/algo/actions
2. You should see "Deploy All Infrastructure" workflow running
3. Click on it to watch progress

### Option B: Manual Trigger

1. Go to https://github.com/argie33/algo/actions
2. Find "Deploy All Infrastructure" workflow on the left
3. Click "Run workflow" button
4. Keep defaults, click "Run workflow"

---

## Step 5: Monitor Deployment

### Watch Workflow Progress

1. **GitHub Actions:**
   - Go to Actions tab → Deploy All Infrastructure
   - Watch the job progress (terraform, docker, lambda)
   - Each step should take 2-5 minutes

2. **Terraform Output:**
   - Look for "Terraform Apply Complete" in summary
   - Should list ECR repo, Lambda functions, RDS endpoint
   - Example:
     ```
     - **ecr_repository_url**: 123456789.dkr.ecr.us-east-1.amazonaws.com/algo
     - **api_lambda_function_name**: stocks-api-dev
     - **algo_lambda_function_name**: stocks-algo-dev
     - **rds_db_endpoint**: algo-db-dev.xxx.us-east-1.rds.amazonaws.com
     ```

3. **If Workflow Fails:**
   - Click on failed job to see logs
   - Common issues:
     - Secret not set (check GitHub secrets)
     - Invalid RDS password (must be 8+ alphanumeric)
     - AWS credentials don't have permissions

---

## Step 6: Verify AWS Infrastructure

### Check RDS Database

```bash
# Via AWS CLI
aws rds describe-db-instances \
  --region us-east-1 \
  --query 'DBInstances[0].[DBInstanceIdentifier,DBInstanceStatus,Engine,DBInstanceClass]' \
  --output table

# Expected output:
# | algo-db-dev | available | postgres | db.t3.micro |
```

### Check Lambda Functions

```bash
aws lambda list-functions \
  --region us-east-1 \
  --query 'Functions[*].[FunctionName,Runtime,LastModified]' \
  --output table

# Should see: stocks-api-dev, stocks-algo-dev, stocks-db-init-dev
```

### Check EventBridge Schedule

```bash
aws events describe-rule \
  --name algo-orchestrator-schedule \
  --region us-east-1 \
  --query '[Name,ScheduleExpression,State]'

# Expected: algo-orchestrator-schedule | cron(30 17 ? * MON-FRI *) | ENABLED
# = 5:30pm ET Monday-Friday
```

---

## Step 7: Test Orchestrator Lambda

### Invoke Function via AWS CLI

```bash
# Prepare test event
cat > test_event.json << 'EOF'
{
  "action": "run_orchestrator",
  "date": "2026-05-08"
}
EOF

# Invoke function
aws lambda invoke \
  --function-name stocks-algo-dev \
  --payload file://test_event.json \
  --region us-east-1 \
  response.json

# Check response
cat response.json
```

### Check CloudWatch Logs

```bash
# View recent logs
aws logs tail /aws/lambda/stocks-algo-dev \
  --follow \
  --region us-east-1 \
  --since 10m

# You should see orchestrator execution logs
```

---

## Step 8: Verify Database Schema

### Connect to RDS and Check Tables

```bash
# Get RDS endpoint from Terraform output
RDS_ENDPOINT="algo-db-dev.xxx.us-east-1.rds.amazonaws.com"

# Connect (requires RDS proxy or public access)
psql -h $RDS_ENDPOINT \
  -U stocks \
  -d stocks \
  -c "\dt"  # List tables

# Or via AWS RDS Auth Token (IAM auth):
RDSTOKEN=$(aws rds generate-db-auth-token \
  --hostname $RDS_ENDPOINT \
  --port 5432 \
  --region us-east-1 \
  --username stocks)

# Connect with token (requires SSL)
psql -h $RDS_ENDPOINT \
  -U stocks \
  -d stocks \
  --sslmode=require \
  -c "\dt"
```

---

## Step 9: Local Development with AWS

### Keep Docker Running Locally

```bash
# Terminal 1: Local Docker for development/testing
docker-compose up -d

# Test locally
python3 test_orchestrator_direct.py

# When satisfied, push changes
git add .
git commit -m "feat: New feature"
git push origin main
# → Automatically triggers AWS deployment
```

### Use AWS for Production/Scheduled Runs

```bash
# Check Lambda logs in AWS
aws logs tail /aws/lambda/stocks-algo-dev --follow

# The orchestrator runs automatically at 5:30pm ET weekdays
# No manual triggering needed after deployment
```

---

## Troubleshooting

### Workflow Fails at "Terraform Apply"

**Problem:** `Error: Invalid or missing value for rds_password`

**Solution:**
1. Go to GitHub Settings → Secrets
2. Check `RDS_PASSWORD` exists
3. Verify it's 8+ characters, alphanumeric only
4. Re-run workflow

---

### Workflow Fails at "Lambda Deploy"

**Problem:** `Error: psycopg2 not found`

**Solution:**
1. Check Docker image build succeeded
2. Verify ECR repository exists
3. Check Lambda layer has psycopg2
4. Re-trigger workflow

---

### RDS Connection Times Out

**Problem:** `FATAL: pg_hba.conf rejects connection`

**Solution:**
1. Check security group allows Lambda → RDS (port 5432)
2. Verify RDS is running: `aws rds describe-db-instances`
3. Check credentials are correct
4. Verify database name is "stocks"

---

### EventBridge Schedule Doesn't Fire

**Problem:** Lambda not running at 5:30pm ET

**Solution:**
1. Check rule exists: `aws events list-rules --name-prefix algo`
2. Verify target is set: `aws events list-targets-by-rule --rule algo-orchestrator-schedule`
3. Check CloudWatch Events logs
4. Manually invoke to test: `aws lambda invoke ... response.json`

---

## Success Criteria

✅ All 13 GitHub secrets configured
✅ Workflow completes without errors
✅ RDS instance is "available" status
✅ 3 Lambda functions created
✅ EventBridge rule is "ENABLED"
✅ Lambda logs show orchestrator execution
✅ Database schema initialized

When all are ✅, your system is ready:
- **Local:** `docker-compose` + `python3 test_orchestrator_direct.py`
- **AWS:** EventBridge triggers orchestrator daily at 5:30pm ET
- **Monitoring:** CloudWatch logs, alarms, SNS notifications

---

## Next Steps

1. ✅ Complete Step 1-2 above (AWS account & GitHub secrets)
2. ✅ Run Step 3-4 (validate Terraform, trigger deployment)
3. ✅ Monitor Step 5 (watch workflow)
4. ✅ Verify Step 6-8 (check infrastructure)
5. ✅ Test Step 9 (local + AWS)

Estimated time: 30 minutes setup + 10 minutes deployment + 5 minutes verification = 45 minutes total

**Total cost:** ~$25-35/month for dev environment
