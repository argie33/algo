# 🚀 SETUP PHASE 2 EXECUTION - Step by Step

**Goal:** Get Phase 2 running in AWS in 40 minutes

**Blockers to fix:**
1. GitHub Secrets not configured
2. AWS OIDC provider not configured
3. CloudFormation infrastructure
4. Database connectivity

---

## STEP 1: Add GitHub Secrets (5 minutes)

**URL:** https://github.com/argie33/algo/settings/secrets/actions

Add 4 new secrets:

| Secret Name | Value |
|-------------|-------|
| `AWS_ACCOUNT_ID` | `626216981288` |
| `RDS_USERNAME` | `stocks` |
| `RDS_PASSWORD` | `bed0elAn` |
| `FRED_API_KEY` | `4f87c213871ed1a9508c06957fa9b577` |

**How to add each:**
1. Click "New repository secret"
2. Enter Name (e.g., `AWS_ACCOUNT_ID`)
3. Paste Value
4. Click "Add secret"

**Verify:** You should see all 4 secrets listed

---

## STEP 2: Setup AWS OIDC Provider & IAM Role (15 minutes)

Two options: **Option A (Automated) or Option B (Manual)**

### Option A: Use CloudFormation (RECOMMENDED)

```bash
# Run this command:
aws cloudformation create-stack \
  --stack-name github-oidc-setup \
  --template-body file://setup-github-oidc.yml \
  --region us-east-1 \
  --capabilities CAPABILITY_NAMED_IAM
```

**Wait for:** Stack shows `CREATE_COMPLETE` in AWS Console

**Verify in AWS:**
1. Go to IAM → Roles
2. Find `GitHubActionsDeployRole`
3. Go to IAM → Identity Providers
4. Find `token.actions.githubusercontent.com`

### Option B: Manual Setup

Go to AWS Console → IAM

**Step 1: Create OIDC Provider**
1. IAM → Identity Providers
2. Click "Add provider"
3. Select OpenID Connect
4. Provider URL: `https://token.actions.githubusercontent.com`
5. Audience: `arn:aws:iam::626216981288:repo:argie33/algo:*`
6. Create provider

**Step 2: Create IAM Role**
1. IAM → Roles → Create role
2. Select "Custom trust policy"
3. Paste this policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::626216981288:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "arn:aws:iam::626216981288:repo:argie33/algo:*"
        }
      }
    }
  ]
}
```

4. Click Next
5. Role name: `GitHubActionsDeployRole`
6. Click Create

**Step 3: Attach Permissions**
1. Open the role just created
2. Click "Add permissions" → "Attach policies"
3. Search and add:
   - `AWSCloudFormationFullAccess`
   - `AmazonRDSFullAccess`
   - `AmazonECS_FullAccess`
   - `AmazonEC2FullAccess`
   - `IAMFullAccess`
   - `AmazonS3FullAccess`
   - `AmazonEC2ContainerRegistryFullAccess`
   - `SecretsManagerReadWrite`
   - `CloudWatchLogsFullAccess`

---

## STEP 3: Verify CloudFormation Infrastructure (5 minutes)

Go to AWS Console → CloudFormation → Stacks

Check these stacks exist and show `CREATE_COMPLETE`:
- [ ] `stocks-core-stack`
- [ ] `stocks-app-stack`
- [ ] `stocks-ecs-tasks-stack`

If any are `ROLLBACK_COMPLETE` or `FAILED`:
1. Click stack → Events tab
2. Look for error messages
3. Common issues:
   - S3 bucket doesn't exist
   - RDS storage misconfigured
   - Security group rules wrong

**If errors:** See CRITICAL_FIXES_REQUIRED.md Issue #3

---

## STEP 4: Verify RDS Connectivity (5 minutes)

Test database connection:

```bash
psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
     -U stocks \
     -d stocks \
     -c "SELECT 1"
```

**Expected output:** `1`

**If failed:** Check:
- RDS endpoint is correct (AWS Console → RDS)
- Security group allows port 5432
- Username/password correct

---

## STEP 5: Trigger Phase 2 Workflow (1 minute)

Push a commit to trigger the workflow:

```bash
git commit -am "Trigger Phase 2 workflow execution" --allow-empty
git push origin main
```

Then check: https://github.com/argie33/algo/actions

**Watch for:**
1. Workflow starts (should see it in Actions tab)
2. Infrastructure deployment (CloudFormation)
3. Docker build (ECR push)
4. Phase 2 loader execution (ECS tasks)

---

## STEP 6: Monitor Execution (25 minutes)

### GitHub Actions
URL: https://github.com/argie33/algo/actions

Watch for green checkmarks (success) or red X (failure)

### CloudWatch Logs
AWS Console → CloudWatch → Logs → Log Groups

Look for:
- `/ecs/algo-loadsectors`
- `/ecs/algo-loadecondata`
- `/ecs/algo-loadstockscores`
- `/ecs/algo-loadfactormetrics`

Watch log messages for:
```
2026-04-29 XX:XX:XX - Starting algo-loadsectors (PARALLEL) with 5 workers
2026-04-29 XX:XX:XX - Progress: 100/5009 symbols
2026-04-29 XX:XX:XX - [OK] Completed: XXXX rows inserted in YY.Xm
```

### ECS Tasks
AWS Console → ECS → Clusters → stocks-cluster → Tasks

Watch task statuses:
- `RUNNING` = currently executing
- `STOPPED` = completed
- `FAILED` = error

---

## STEP 7: Verify Data Loaded (5 minutes)

Query RDS to confirm data was inserted:

```bash
psql -h <endpoint> -U stocks -d stocks << 'SQL'
SELECT 
  'sector_technical_data' as table_name, COUNT(*) as row_count
FROM sector_technical_data
UNION ALL
SELECT 'economic_data', COUNT(*) FROM economic_data
UNION ALL
SELECT 'stock_scores', COUNT(*) FROM stock_scores
UNION ALL
SELECT 'quality_metrics', COUNT(*) FROM quality_metrics;
SQL
```

**Expected output:**
```
      table_name       | row_count
-----------------------+----------
sector_technical_data  |     XXXX
economic_data          |     XXXX
stock_scores           |     XXXX
quality_metrics        |     XXXX
```

**If all zero:** Check CloudWatch logs for errors

---

## STEP 8: Check Performance Metrics

Extract execution time from CloudWatch logs:

Look for messages like:
```
[OK] Completed: 24950 rows in 15.2m
```

Calculate speedup:
- Baseline: 53 minutes
- Phase 2: ~25 minutes
- Speedup: 53 ÷ 25 = **2.1x**

---

## SUCCESS CRITERIA

✅ GitHub Actions workflow completed (green checkmark)
✅ All CloudFormation stacks show CREATE_COMPLETE
✅ ECS tasks show STOPPED (completed)
✅ CloudWatch logs show successful execution
✅ RDS database has new data
✅ Execution time ~25 minutes (was 53)

---

## IF SOMETHING FAILS

Check these in order:

1. **Workflow doesn't start**
   - GitHub Secrets not configured (STEP 1)
   - No push detected (try again)

2. **CloudFormation fails**
   - OIDC not configured (STEP 2)
   - IAM role permissions insufficient (STEP 2)
   - Infrastructure already exists (delete and retry)

3. **RDS connection fails**
   - Security group misconfigured (STEP 4)
   - Credentials wrong (STEP 4)

4. **ECS tasks fail**
   - Docker images not built (check GitHub Actions)
   - Network configuration wrong (check VPC/subnets)
   - RDS not reachable (check security groups)

5. **No data in database**
   - Check CloudWatch logs for actual errors
   - Verify RDS has correct data (STEP 7)

---

## COMMANDS TO MONITOR

```bash
# Watch GitHub Actions
gh run list --repo argie33/algo

# Watch CloudFormation
aws cloudformation list-stacks --region us-east-1

# Watch ECS tasks
aws ecs list-tasks --cluster stocks-cluster --region us-east-1

# Watch CloudWatch logs (requires AWS CLI)
aws logs tail /ecs/algo-loadsectors --follow --region us-east-1
```

---

## TOTAL TIME: ~40 minutes

| Step | Time | Task |
|------|------|------|
| 1 | 5m | Add GitHub Secrets |
| 2 | 15m | Setup AWS OIDC + IAM |
| 3 | 5m | Verify CloudFormation |
| 4 | 5m | Test RDS Connection |
| 5 | 1m | Trigger Workflow |
| 6 | 25m | Monitor Execution |
| 7 | 5m | Verify Data |
| **Total** | **~40m** | **Phase 2 Running** |

---

**After completing these steps, Phase 2 will be running in AWS and loading data!**

Next: Move to Phase 3 (S3 staging + Lambda parallelization) for additional speedups.
