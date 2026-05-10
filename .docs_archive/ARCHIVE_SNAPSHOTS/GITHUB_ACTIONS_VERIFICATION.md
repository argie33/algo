# GitHub Actions Execution Verification

## How GitHub Actions Works When You Push

```
YOUR PUSH TO MAIN
    ↓
GitHub detects file changes
    ↓
Workflow: "Data Loaders Pipeline" triggers
    ↓
Jobs execute in sequence/parallel
    ↓
CloudFormation deploys phases
    ↓
Loaders execute in AWS
    ↓
Results in database
```

---

## TRIGGER CONDITIONS

The workflow triggers when you push these files to main:
```
- load*.py          (any loader file)
- Dockerfile.*      (Docker images)
- template-app-ecs-tasks.yml
- .github/workflows/deploy-app-stocks.yml
```

**IMPORTANT**: You must push one of these files OR manually trigger workflow

---

## What Each Job Does

### 1. detect-changes
- **What**: Analyzes what changed in the push
- **Output**: List of loaders to run
- **Time**: 1-2 minutes

### 2. deploy-infrastructure
- **What**: Ensures core infrastructure exists (S3, IAM, networks)
- **Output**: CloudFormation stack status
- **Time**: 5-10 minutes

### 3. execute-loaders (Phase A)
- **What**: Runs ECS loaders with S3 staging (bulk COPY optimization)
- **Loaders**: All 39 official loaders detected in changes
- **Output**: Data loaded into database
- **Time**: 10-45 minutes (depends on loaders)

### 4. execute-phase-c-lambda-orchestrator
- **What**: Runs buyselldaily via 100 Lambda workers
- **Trigger**: Only if loadbuyselldaily.py changed
- **Output**: Buy/sell signals in database
- **Time**: 7 minutes
- **Cost**: $0.10 vs $5 ECS

### 5. deploy-phase-e-infrastructure
- **What**: Deploys DynamoDB caching
- **Output**: Ready for incremental loading
- **Time**: 3 minutes

### 6. deploy-phase-d-step-functions
- **What**: Deploys Step Functions DAG orchestration
- **Output**: State machine ready for scheduling
- **Time**: 3 minutes

### 7. deployment-summary
- **What**: Final report and metrics
- **Output**: Success/failure summary
- **Time**: 1 minute

---

## Verifying Workflow Execution

### Method 1: GitHub UI (Real-time)

```
1. Go to your GitHub repository
2. Click "Actions" tab
3. Look for "Data Loaders Pipeline"
4. Watch jobs execute in real-time
```

Status indicators:
- ✓ Yellow circle = In progress
- ✓ Green check = Completed successfully
- ✓ Red X = Failed

### Method 2: AWS Verification

```bash
# Check what's actually running in AWS
bash CHECK_AWS_STATUS.sh
```

This shows:
- ECS tasks currently running
- Lambda executions (last 24h)
- Step Functions executions
- Database updates (actual data)
- CloudWatch errors
- Cost today

---

## Ensuring Workflow Actually Runs

### Check 1: Workflow Syntax is Valid

```bash
# Verify workflow YAML is correct
cat .github/workflows/deploy-app-stocks.yml | grep -E "^on:|^jobs:" -A 5
```

Expected output:
```
on:
  push:
    paths:
      - 'load*.py'
      - 'Dockerfile.*'
```

### Check 2: Files Changed Trigger It

When you push, GitHub compares against previous commit.

If you modify ANY of these → workflow triggers:
```
- loadbuyselldaily.py
- Dockerfile.loadpricedaily
- template-app-ecs-tasks.yml
- .github/workflows/deploy-app-stocks.yml
```

If you only modify OTHER files → workflow doesn't trigger

**Fix**: Touch a loader file when pushing:
```bash
git add .
git commit -m "Deploy: all optimizations"
touch loadbuyselldaily.py  # Ensures workflow triggers
git add loadbuyselldaily.py
git commit --amend --no-edit
git push origin main
```

### Check 3: Secrets Are Configured

Workflow needs GitHub secrets to authenticate to AWS.

```bash
# Check if secrets are set (from GitHub CLI if installed)
gh secret list
```

Required secrets:
- AWS_ACCOUNT_ID
- RDS_USERNAME
- RDS_PASSWORD

If missing → workflow fails at "Configure AWS credentials" step

### Check 4: IAM Role Has Permissions

Workflow assumes this role to deploy:
```
arn:aws:iam::{AWS_ACCOUNT_ID}:role/GitHubActionsDeployRole
```

If role doesn't exist or lacks permissions → workflow fails

---

## Complete Workflow: From Push to Data in Database

```
STEP 1: You push to main
  $ git push origin main

STEP 2: GitHub detects changes
  → Checks if any trigger files changed
  → Triggers "Data Loaders Pipeline" workflow

STEP 3: Workflow runs jobs
  detect-changes         (1-2 min)
     ↓
  deploy-infrastructure  (5-10 min, if needed)
     ↓
  execute-loaders        (10-45 min) ← Phase A (S3 staging)
     ↓
  execute-phase-c-lambda (7 min)     ← Phase C (Lambda workers)
     ↓
  deploy-phase-e         (3 min)     ← Phase E (DynamoDB cache)
     ↓
  deploy-phase-d         (3 min)     ← Phase D (Step Functions)
     ↓
  deployment-summary     (1 min)

STEP 4: AWS executes
  → CloudFormation creates/updates stacks
  → ECS tasks run loaders
  → Lambda functions execute
  → Data is inserted into RDS

STEP 5: Verify in AWS
  $ bash CHECK_AWS_STATUS.sh
  
  Shows:
  ✓ ECS tasks completed
  ✓ Lambda invocations
  ✓ Step Functions executions
  ✓ Latest data in database
  ✓ Errors (if any)

STEP 6: Total time
  GitHub Actions: 30-70 minutes
  Data available: Immediately after executor completes
```

---

## ENSURE IT WORKS EVERY TIME

### Before Each Push

```bash
# 1. Check workflow syntax
cat .github/workflows/deploy-app-stocks.yml | head -20

# 2. Verify you're modifying a trigger file
git diff --name-only HEAD~1

# 3. Ensure secrets are configured (in GitHub)
# Go to: Settings → Secrets and Variables → Actions
# Check: AWS_ACCOUNT_ID, RDS_USERNAME, RDS_PASSWORD exist

# 4. Verify IAM role exists in AWS
aws iam get-role --role-name GitHubActionsDeployRole
```

### When You Push

```bash
git add .
git commit -m "Update: [description]"
git push origin main
```

### After You Push

```bash
# 1. Check workflow in GitHub (real-time)
# Go to: GitHub → Actions → Data Loaders Pipeline

# 2. Check AWS status (shows actual execution)
bash CHECK_AWS_STATUS.sh

# 3. Verify data loaded in database
psql -h $DB_HOST -U stocks -d stocks -c "SELECT COUNT(*) FROM price_daily"
```

---

## Troubleshoot: Workflow Didn't Run

### Cause 1: Files don't trigger workflow
**Symptom**: You pushed but no workflow appears in Actions tab

**Fix**:
```bash
# Touch a trigger file
touch loadbuyselldaily.py
git add loadbuyselldaily.py
git commit -m "Trigger workflow"
git push origin main
```

### Cause 2: Secrets missing
**Symptom**: Workflow starts but fails at "Configure AWS credentials"

**Fix**:
```
GitHub → Settings → Secrets → Add:
  AWS_ACCOUNT_ID = your-account-id
  RDS_USERNAME = stocks
  RDS_PASSWORD = your-password
```

### Cause 3: IAM role missing
**Symptom**: Workflow fails with permission error

**Fix**:
```bash
aws iam get-role --role-name GitHubActionsDeployRole
# If not found, create it (run SETUP_EVERYTHING.sh again)
```

### Cause 4: Secrets syntax wrong
**Symptom**: Workflow runs but AWS API calls fail

**Check**: Ensure secrets have correct values (no extra spaces)

---

## Expected Results After Successful Deployment

```
In GitHub Actions:
  ✓ All jobs green checkmarks
  ✓ No red X marks
  ✓ deployment-summary shows success

In AWS:
  ✓ ECS tasks completed in CloudWatch
  ✓ Lambda invocations recorded
  ✓ Step Functions state machine updated
  ✓ No errors in /stepfunctions/data-loading-pipeline logs

In Database:
  ✓ New rows in price_daily
  ✓ New rows in buy_sell_daily
  ✓ Latest timestamp matches today
```

---

## One-Line Status Check

```bash
bash CHECK_AWS_STATUS.sh && echo "✓ All systems operational"
```

This tells you:
- What's running in AWS
- What's deployed
- What's still needed
- Latest execution status
- Cost today
