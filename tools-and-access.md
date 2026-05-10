# Tools & Access Reference

## AWS CLI

### Installation & Verification
AWS CLI may not be in standard PATH. Search thoroughly:
```bash
# Search in common locations
find ~ -name "aws" -o -name "aws.exe" 2>/dev/null | head -20
find ~/AppData/Local/Programs/Python -name "aws*" 2>/dev/null
ls -la "/c/Program Files/Amazon/AWSCLI/bin/" 2>/dev/null

# If found, test:
aws --version
aws sts get-caller-identity --region us-east-1
```

### Authentication (Local)

Export credentials before running AWS CLI:
```bash
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_DEFAULT_REGION="us-east-1"

# Test
aws ec2 describe-vpcs --region us-east-1
```

**GitHub Workflows:** Credentials auto-configured via `configure-aws-credentials@v4` action

---

## AWS CLI Syntax Patterns

### Common Mistake: --filters vs --filter

❌ **WRONG** (won't work):
```bash
aws ec2 describe-nat-gateways --filters Name=vpc-id,Values=$VPC_ID Name=state,Values=available
```

✅ **CORRECT** (use --filter once per filter):
```bash
aws ec2 describe-nat-gateways --region us-east-1 \
  --filter "Name=vpc-id,Values=$VPC_ID" \
  --filter "Name=state,Values=available,pending"
```

### JMESPath Queries (--query parameter)

```bash
# Get all VPC IDs
aws ec2 describe-vpcs --query 'Vpcs[*].VpcId' --output text

# Get specific attributes
aws ec2 describe-instances --query 'Reservations[*].Instances[*].[InstanceId,State.Name]' --output table

# Conditional selection
aws rds describe-db-instances --query 'DBInstances[?Engine==`postgres`].DBInstanceIdentifier' --output text

# Count results
aws ec2 describe-vpcs --filters Name=isDefault,Values=false --query 'length(Vpcs)' --output text
```

### Error Handling in Bash Scripts

❌ **WRONG** (stops on error):
```bash
set -e
aws ec2 delete-vpc --vpc-id $VPC
```

✅ **CORRECT** (continue, check status):
```bash
aws ec2 delete-vpc --vpc-id $VPC 2>/dev/null || true

# Or with error handling:
if ! output=$(aws ec2 delete-vpc --vpc-id $VPC 2>&1); then
  echo "ERROR: $output"
  exit 1
fi
```

---

## Essential AWS CLI Commands (This Project)

### CloudFormation

```bash
# List stacks
aws cloudformation list-stacks --region us-east-1 \
  --query 'StackSummaries[?StackStatus!=`DELETE_COMPLETE`].StackName' \
  --output table

# Describe stack
aws cloudformation describe-stacks --stack-name stocks-core --region us-east-1

# Get outputs/exports
aws cloudformation describe-stacks --stack-name stocks-core \
  --query 'Stacks[0].Outputs' --region us-east-1

# Get stack events (for debugging)
aws cloudformation describe-stack-events --stack-name stocks-core \
  --region us-east-1 --query 'StackEvents[0:10]'
```

### RDS

```bash
# List databases
aws rds describe-db-instances --region us-east-1 \
  --query 'DBInstances[*].DBInstanceIdentifier' --output text

# Get endpoint
aws rds describe-db-instances --db-instance-identifier stocks-data-rds \
  --query 'DBInstances[0].Endpoint.Address' --region us-east-1

# Delete (skip final snapshot for dev)
aws rds delete-db-instance --db-instance-identifier stocks-data-rds \
  --skip-final-snapshot --region us-east-1
```

### Lambda

```bash
# List functions
aws lambda list-functions --region us-east-1 \
  --query 'Functions[?contains(FunctionName, `stocks`)].FunctionName' \
  --output text

# Invoke function
aws lambda invoke --function-name algo-orchestrator \
  --region us-east-1 /tmp/out.json && cat /tmp/out.json

# Get logs
aws logs tail /aws/lambda/algo-orchestrator --follow --region us-east-1
```

### ECS

```bash
# List clusters
aws ecs list-clusters --region us-east-1 \
  --query 'clusterArns[*]' --output text

# List services in cluster
aws ecs list-services --cluster stocks-data-cluster \
  --region us-east-1 --query 'serviceArns[*]' --output text

# List tasks
aws ecs list-tasks --cluster stocks-data-cluster \
  --region us-east-1 --query 'taskArns[*]' --output text

# Get task logs
aws logs tail /ecs/stocks-data-cluster --follow --region us-east-1
```

### Secrets Manager

```bash
# List secrets
aws secretsmanager list-secrets --region us-east-1 \
  --query 'SecretList[?contains(Name, `stocks`)].Name' --output text

# Get secret (plaintext)
aws secretsmanager get-secret-value --secret-id stocks-db-secrets \
  --region us-east-1 --query 'SecretString' --output text

# Parse JSON secret
aws secretsmanager get-secret-value --secret-id stocks-algo-secrets \
  --region us-east-1 --query 'SecretString' --output text | jq '.APCA_API_KEY_ID'
```

### EventBridge Scheduler

```bash
# List schedules
aws scheduler list-schedules --region us-east-1 \
  --query 'Schedules[?contains(Name, `stocks`)]' --output table

# Get schedule details
aws scheduler get-schedule --name algo-daily-5-30pm --region us-east-1

# Trigger manually
aws scheduler create-schedule-group --name test --region us-east-1 || true
aws scheduler start-schedule --name algo-daily-5-30pm --region us-east-1
```

---

## Accessing Bastion Host

Bastion for RDS access (SSH disabled, use Session Manager):

```bash
# List instances
aws ec2 describe-instances --region us-east-1 \
  --query 'Reservations[*].Instances[*].[InstanceId,Tags[?Key==`Name`].Value|[0]]' \
  --output table

# Start session
aws ssm start-session --target i-0123456789abcdef0 --region us-east-1

# Once in session, access RDS:
psql -h stocks-data-rds-endpoint.region.rds.amazonaws.com -U stocks -d stocks
```

---

## GitHub CLI (gh)

### Authentication
```bash
gh auth login  # Interactive, choose HTTPS + Personal Access Token
gh auth status  # Verify
```

### Workflows
```bash
# List workflows
gh workflow list

# Run workflow
gh workflow run deploy-all-infrastructure.yml --repo argie33/algo

# Check status
gh run list --workflow deploy-algo-orchestrator.yml

# View logs
gh run view <RUN_ID> --log
```

### PRs & Issues
```bash
# Create PR
gh pr create --title "Description" --body "Details"

# List PRs
gh pr list --state all

# View PR
gh pr view <PR_NUMBER>

# Merge PR
gh pr merge <PR_NUMBER> --merge
```

---

## Git Workflows

### Standard Flow
```bash
# Update main
git checkout main
git pull origin main

# Create feature branch
git checkout -b feature/my-change

# Make changes, test locally
python3 algo_run_daily.py

# Commit
git add .
git commit -m "Description"

# Push
git push origin feature/my-change

# Create PR (via GitHub or gh)
gh pr create --title "Description"

# Wait for tests to pass, then merge
gh pr merge --merge
```

### Emergency Hotfix
```bash
git checkout main
git pull origin main
git checkout -b hotfix/urgent-fix
# Make minimal fix only
git add <file>
git commit -m "Hotfix: description"
git push origin hotfix/urgent-fix
gh pr create --title "[HOTFIX] description" --body "Why needed"
# Merge immediately after tests pass
gh pr merge --merge
```

### Reverting Changes
```bash
# See recent commits
git log --oneline -10

# Revert a commit (creates new reverse commit)
git revert <COMMIT_SHA>
git push origin main

# Or reset if not pushed yet
git reset --soft HEAD~1  # Undo last commit, keep changes
```

---

## Environment Variables (For Local Development)

Create `.env.local`:
```bash
# Database (Docker Compose)
DB_HOST=localhost
DB_PORT=5432
DB_NAME=stocks
DB_USER=stocks
DB_PASSWORD=stocks_local_password

# Alpaca (Paper Trading)
APCA_API_KEY_ID=your_key
APCA_API_SECRET_KEY=your_secret
APCA_API_BASE_URL=https://paper-api.alpaca.markets
ALPACA_PAPER_TRADING=true

# LocalStack (optional, for S3 mocking)
LOCALSTACK_ENDPOINT_URL=http://localhost:4566
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
```

**IMPORTANT:** Never commit `.env.local` to git (already in .gitignore)

---

## Useful Aliases (Add to ~/.bash_profile or ~/.zshrc)

```bash
# AWS
alias aws-vpcs="aws ec2 describe-vpcs --region us-east-1 --query 'Vpcs[*].[VpcId,CidrBlock]' --output table"
alias aws-stacks="aws cloudformation list-stacks --region us-east-1 --query 'StackSummaries[?StackStatus!=\`DELETE_COMPLETE\`].StackName' --output text"
alias aws-logs-algo="aws logs tail /aws/lambda/algo-orchestrator --follow --region us-east-1"

# Git
alias gst="git status"
alias glog="git log --oneline -10"
alias gpush="git push origin main"

# Algo
alias algo-test="cd /mnt/c/Users/arger/code/algo && python3 algo_run_daily.py"
alias algo-db="psql -h localhost -U stocks -d stocks"
```

---

## Alert Configuration (Email/SMS/Slack)

Critical data issues trigger automated alerts. Configure once, then forget.

### Email Alerts (Gmail)

Add to `.env.local`:
```bash
ALERT_EMAIL_FROM=edgebrookecapital@gmail.com
ALERT_EMAIL_TO=argeropolos@gmail.com
ALERT_SMTP_HOST=smtp.gmail.com
ALERT_SMTP_PORT=587
ALERT_SMTP_USER=edgebrookecapital@gmail.com
ALERT_SMTP_PASSWORD=<app_password>
```

**Get Gmail app password:**
1. Go to https://myaccount.google.com/apppasswords
2. Select "Mail" + "Windows Computer"
3. Copy 16-char password to `ALERT_SMTP_PASSWORD`

### SMS Alerts (Twilio)

Free tier: 1000 SMS/month.

```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=+1-XXX-XXX-XXXX
ALERT_PHONE_NUMBERS=+1-312-307-8620
```

**Find in Twilio Console:**
- Account SID: top right of dashboard
- Auth Token: next to Account SID
- Twilio number: Phone Numbers → Manage Numbers → Active Numbers

### Slack Webhook (Optional)

```bash
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

**Get URL:**
1. Slack: Settings → Manage apps → Build → Create New App
2. Choose "From scratch", name it "Algo Alerts"
3. Enable Incoming Webhooks → Create New Webhook to Channel
4. Copy URL to `.env.local`

### Alert Levels

- **CRITICAL** → Email + SMS + Slack (OHLC corruption, stale orders)
- **ERROR** → Email + SMS + Slack (>2 errors)
- **WARN** → Email + Slack only (30%+ 1-day drop, missing data)

**Test:** `python3 algo_alerts.py`

---

## AWS Budget & Cost Controls

### Create $100/Month Budget (5 minutes)

**CLI method:**
```bash
aws budgets create-budget \
  --account-id ACCOUNT_ID \
  --budget file:///dev/stdin <<'EOF'
{
  "BudgetName": "StockLoaderMonthly",
  "BudgetLimit": {"Amount": "100", "Unit": "USD"},
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST"
}
EOF
```

**Or AWS Console:**
1. AWS Budgets → Create budget
2. Cost budget, name: `StockLoaderMonthly`
3. Monthly, limit: $100

### Set Alert Thresholds

```bash
# Alert at 80% ($80)
aws budgets create-notification \
  --account-id ACCOUNT_ID \
  --budget-name StockLoaderMonthly \
  --notification file:///dev/stdin <<'EOF'
{
  "NotificationType": "FORECASTED",
  "ComparisonOperator": "GREATER_THAN",
  "Threshold": 80,
  "ThresholdType": "PERCENTAGE"
}
EOF

# Alert at 95% ($95)
aws budgets create-notification \
  --account-id ACCOUNT_ID \
  --budget-name StockLoaderMonthly \
  --notification file:///dev/stdin <<'EOF'
{
  "NotificationType": "ACTUAL",
  "ComparisonOperator": "GREATER_THAN",
  "Threshold": 95,
  "ThresholdType": "PERCENTAGE"
}
EOF
```

### Cost Optimization Levers

| Optimization | Monthly Savings | How |
|---|---|---|
| **RDS auto-pause (20h/day)** | $16 | RDS → Modify → Aurora Serverless → Auto pause: 20 min |
| **Lambda reserved concurrency** | - | `aws lambda put-function-concurrency --function-name LoadPriceDailyWorker --reserved-concurrent-executions 5` |
| **CloudWatch logs retention** | $1-3 | `aws logs put-retention-policy --log-group-name /aws/lambda/LoadPriceDailyWorker --retention-in-days 7` |

### Current Cost Breakdown

| Service | Est. Monthly |
|---------|---|
| RDS (with auto-pause) | $14 |
| Lambda (5 daily + 1 weekly + 1 monthly) | $0.15 |
| CloudWatch Logs | $3 |
| NAT Gateway | $7 |
| Data Transfer | $1.50 |
| Other | $1 |
| **TOTAL** | **~$27** |

Buffer: $73 of $100 budget remaining (73% spare capacity).

### If You Hit $100

AWS doesn't auto-stop at budget limits. Manual emergency controls:

```bash
# Disable all loader schedules
aws events put-rule --name LoadPriceDailySchedule --state DISABLED
aws events put-rule --name LoadPriceWeeklySchedule --state DISABLED

# Pause RDS
aws rds stop-db-instance --db-instance-identifier stocks-db

# Check current spend
aws ce get-cost-and-usage \
  --time-period Start=2026-05-01,End=2026-05-31 \
  --granularity MONTHLY \
  --metrics UnblendedCost
```

---

**Last Updated:** 2026-05-10
