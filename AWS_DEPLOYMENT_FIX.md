# AWS Deployment Fix - Path A

**Problem Identified:** CloudFormation export mismatch

---

## The Root Cause

**Stack Dependency Chain:**
```
1. template-app-stocks.yml (CORE - creates StocksApp-ClusterArn EXPORT)
                    ↓
2. template-app-ecs-tasks.yml (DEPENDS ON - imports StocksApp-ClusterArn)
                    ↓
3. GitHub Actions execute-loaders (DEPENDS ON - needs task definitions)
```

**What's Broken:**
- Step 1 (template-app-stocks.yml) either:
  - Never deployed successfully
  - OR deployed but in ROLLBACK state
  - OR partially deployed without exports

- Step 2 tries to import `StocksApp-ClusterArn` but can't find it
- Step 3 adds `&& false` workaround to skip failing infrastructure job

---

## Solution: Deploy CloudFormation Properly

### Option A: Manual AWS Console Deployment (15-30 min)

1. **Check if stacks exist:**
   ```bash
   aws cloudformation describe-stacks --region us-east-1 --query 'Stacks[].StackName'
   ```

2. **Check stack status:**
   ```bash
   aws cloudformation describe-stacks \
     --stack-name stocks-app-stack \
     --region us-east-1 \
     --query 'Stacks[0].StackStatus'
   ```

3. **If stack is in ROLLBACK or failed:**
   ```bash
   aws cloudformation delete-stack \
     --stack-name stocks-app-stack \
     --region us-east-1
   ```

4. **Deploy fresh:**
   ```bash
   aws cloudformation create-stack \
     --stack-name stocks-app-stack \
     --template-body file://template-app-stocks.yml \
     --region us-east-1 \
     --parameters \
       ParameterKey=RDSUsername,ParameterValue=stocks \
       ParameterKey=RDSPassword,ParameterValue=<your_rds_password> \
       ParameterKey=FREDApiKey,ParameterValue=$FRED_API_KEY \
     --capabilities CAPABILITY_IAM
   ```

5. **Wait for completion:**
   ```bash
   aws cloudformation wait stack-create-complete \
     --stack-name stocks-app-stack \
     --region us-east-1
   ```

6. **Verify exports exist:**
   ```bash
   aws cloudformation list-exports --region us-east-1 \
     --query 'Exports[?Name==`StocksApp-ClusterArn`]'
   ```

### Option B: Fix GitHub Actions to Deploy Properly (15 min)

1. **Update deploy-infrastructure job** (in `.github/workflows/deploy-app-stocks.yml`):
   - Currently hardcoded to template-app-stocks.yml
   - Add better error handling
   - Add stack status checking
   - Retry on transient failures

2. **Re-enable the job** (remove `&& false`):
   - Change line 283 from:
     ```yaml
     if: ${{ needs.detect-changes.outputs.infrastructure-changed == 'true' && false }}
     ```
   - To:
     ```yaml
     if: ${{ needs.detect-changes.outputs.infrastructure-changed == 'true' }}
     ```

3. **Next GitHub Actions run will:**
   - Deploy template-app-stocks.yml
   - Create StocksApp-ClusterArn export
   - Then template-app-ecs-tasks.yml can import it
   - Then loaders can run

---

## Prerequisites Checklist

Before we deploy:

```
[ ] AWS Account ID configured in GitHub Secrets: AWS_ACCOUNT_ID
[ ] AWS IAM credentials in GitHub Secrets:
    - AWS_ACCESS_KEY_ID
    - AWS_SECRET_ACCESS_KEY
[ ] GitHub OIDC provider configured (bootstrap workflow does this)
[ ] RDS database exists and is accessible
[ ] RDS password is known (will need for CloudFormation)
[ ] API keys configured:
    - FRED_API_KEY
    - APCA_API_KEY_ID
    - APCA_API_SECRET_KEY
```

---

## Recommended Path Forward

**Step 1: Verify Current AWS State (5 min)**
```bash
# Check what stacks exist
aws cloudformation describe-stacks --region us-east-1 \
  --query 'Stacks[].{Name:StackName,Status:StackStatus}' \
  --output table

# Check if StocksApp-ClusterArn export exists
aws cloudformation list-exports --region us-east-1 \
  --query 'Exports[?Name==`StocksApp-ClusterArn`]'
```

**Step 2: If Stack Doesn't Exist or Is Failed**
- Delete failed stack (if any)
- Deploy fresh with AWS CLI or GitHub Actions

**Step 3: Verify Exports**
- Confirm `StocksApp-ClusterArn` exists
- Confirm other required exports exist

**Step 4: Re-enable GitHub Actions**
- Remove `&& false` from line 283
- Push code to trigger deployment
- Monitor Actions workflow

**Step 5: Test Loader Execution**
- Manually trigger a loader via GitHub Actions
- Verify ECS task runs
- Check data in RDS

---

## What to Do Next

**You need to tell me:**

1. **Can you access AWS console?** (to check stack status)
   - OR I can write commands for you to run

2. **Do you have RDS password?** (needed for CloudFormation parameters)
   - It's currently in .env.local as DB_PASSWORD

3. **GitHub Secrets - are they all configured?**
   - Check repo Settings → Secrets and variables → Actions

Once we know these, I can:
- Either guide you through manual AWS deployment
- OR fix GitHub Actions to deploy it automatically

Which would you prefer?
