# PHASE 2 EXECUTION PLAN - Complete & Actionable

**Status:** Ready to execute - 2 blockers to remove, then launch

**Timeline:** 25 minutes total (15 min setup + 10 min for GitHub to detect changes)

---

## CURRENT STATE

✓ Code ready: 5 Phase 2 loaders parallelized (ThreadPoolExecutor + batch inserts)
✓ Infrastructure templates: CloudFormation for VPC, RDS, ECS, ECR
✓ GitHub workflow: Configured to detect changes and trigger Phase 2
✓ Verification tools: SQL + Python scripts ready to validate data

✗ BLOCKING: GitHub Secrets not configured
✗ BLOCKING: AWS OIDC provider not deployed

---

## STEP 1: ADD GITHUB SECRETS (5 MIN)

**Location:** https://github.com/argie33/algo/settings/secrets/actions

**Action:** Click "New repository secret" and add these 4 secrets:

| Secret Name | Value |
|-------------|-------|
| `AWS_ACCOUNT_ID` | `626216981288` |
| `RDS_USERNAME` | `stocks` |
| `RDS_PASSWORD` | `bed0elAn` |
| `FRED_API_KEY` | `4f87c213871ed1a9508c06957fa9b577` |

**Process for each secret:**
1. Go to https://github.com/argie33/algo/settings/secrets/actions
2. Click "New repository secret" (green button)
3. Enter Secret name (e.g., `AWS_ACCOUNT_ID`)
4. Paste Value
5. Click "Add secret"
6. Repeat for all 4 secrets

**Verification:** All 4 should appear in the secrets list on that page.

---

## STEP 2: DEPLOY AWS OIDC PROVIDER (10 MIN)

**Prerequisite:** AWS CLI configured with credentials

**Command:**
```bash
aws cloudformation create-stack \
  --stack-name github-oidc-setup \
  --template-body file://setup-github-oidc.yml \
  --region us-east-1 \
  --capabilities CAPABILITY_NAMED_IAM
```

**What it does:**
- Creates OIDC Identity Provider for GitHub
- Creates IAM role `GitHubActionsDeployRole`
- Grants permissions: CloudFormation, RDS, ECS, EC2, IAM, S3, ECR, Secrets Manager, CloudWatch Logs

**Wait for completion:**
```bash
aws cloudformation wait stack-create-complete \
  --stack-name github-oidc-setup \
  --region us-east-1
```

**Or check status manually:**
```bash
aws cloudformation describe-stacks \
  --stack-name github-oidc-setup \
  --region us-east-1 \
  --query 'Stacks[0].StackStatus'
```

**Expected output:** `CREATE_COMPLETE`

---

## STEP 3: TRIGGER PHASE 2 WORKFLOW (1 MIN)

**Action:** Push a commit to main branch

```bash
git commit -am "Trigger Phase 2 execution" --allow-empty
git push origin main
```

**What happens:**
1. GitHub detects push to main
2. Workflow starts: `.github/workflows/deploy-app-stocks.yml`
3. Detects changed loaders (load*.py files)
4. Builds and deploys Phase 2

---

## STEP 4: MONITOR EXECUTION (30-40 MIN)

### GitHub Actions (Real-time)
**URL:** https://github.com/argie33/algo/actions

**Watch for:**
- Green checkmark = Success
- Red X = Failure
- Clock = Still running

**Expected timeline:**
- 0-2 min: Detect changes
- 2-5 min: Deploy CloudFormation stacks
- 5-10 min: Build Docker images
- 10-40 min: Run 4 parallel loaders

### CloudWatch Logs (Live output)
**URL:** https://console.aws.amazon.com/logs/home

**Log Groups to watch:**
- `/ecs/algo-loadsectors`
- `/ecs/algo-loadecondata`
- `/ecs/algo-loadstockscores`
- `/ecs/algo-loadfactormetrics`

**Command line:**
```bash
aws logs tail /ecs/algo-loadsectors --follow --region us-east-1
```

**What to look for:**
```
2026-04-29 XX:XX:XX - Starting algo-loadsectors (PARALLEL) with 5 workers
2026-04-29 XX:XX:XX - Loading technical data for 11 sectors...
2026-04-29 XX:XX:XX - Progress: 100/110 (8.2/sec)
2026-04-29 XX:XX:XX - [OK] Completed: 12,650 rows in 3.5m
```

### ECS Tasks (Execution status)
**URL:** AWS Console → ECS → Clusters → stocks-cluster → Tasks

**Status meanings:**
- `RUNNING` = Currently executing
- `STOPPED` = Completed successfully
- `FAILED` = Error occurred

---

## STEP 5: VERIFY DATA LOADED (5 MIN)

**Command:**
```bash
psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
     -U stocks \
     -d stocks << 'SQL'
SELECT 
  'sector_technical_data' as table_name, COUNT(*) as rows
FROM sector_technical_data
UNION ALL
SELECT 'economic_data', COUNT(*) FROM economic_data
UNION ALL
SELECT 'stock_scores', COUNT(*) FROM stock_scores
UNION ALL
SELECT 'quality_metrics', COUNT(*) FROM quality_metrics
UNION ALL
SELECT 'growth_metrics', COUNT(*) FROM growth_metrics
UNION ALL
SELECT 'momentum_metrics', COUNT(*) FROM momentum_metrics
UNION ALL
SELECT 'stability_metrics', COUNT(*) FROM stability_metrics
UNION ALL
SELECT 'value_metrics', COUNT(*) FROM value_metrics
UNION ALL
SELECT 'positioning_metrics', COUNT(*) FROM positioning_metrics;
SQL
```

**Expected output:**
```
         table_name      | rows
------------------------+-------
sector_technical_data    | 12650
economic_data            | 85000
stock_scores             | 4969
quality_metrics          | 24950
growth_metrics           | 24950
momentum_metrics         | 24950
stability_metrics        | 24950
value_metrics            | 24950
positioning_metrics      | 24950
```

**If all rows > 0:** Phase 2 SUCCESSFUL!

---

## STEP 6: RUN VALIDATION SCRIPTS (5 MIN)

**Option A: Python validation**
```bash
python3 validate_all_data.py
```

**Option B: SQL validation**
```bash
psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
     -U stocks \
     -d stocks \
     -f verify_data_loaded.sql
```

**Option C: Python monitoring**
```bash
python3 monitor_phase2_execution.py
```

---

## TROUBLESHOOTING

### Workflow doesn't start
- Check: GitHub Secrets configured at `/settings/secrets/actions`
- Check: Push detected (look at Actions tab)
- Fix: Try pushing again

### CloudFormation fails to deploy
- Check: AWS OIDC provider deployed (run stack creation command)
- Check: IAM permissions sufficient
- Look at: AWS CloudFormation console → Events tab for error details

### ECS tasks fail
- Check: CloudFormation stacks created successfully
- Check: Security groups allow RDS access
- Look at: CloudWatch logs for error messages

### No data in database
- Check: ECS tasks completed (status = STOPPED)
- Check: CloudWatch logs for actual errors
- Verify: RDS endpoint correct and accessible

---

## SUCCESS CRITERIA

✓ GitHub Secrets configured  
✓ AWS OIDC provider deployed  
✓ Workflow triggered and completed  
✓ CloudWatch logs show successful execution  
✓ RDS has data (all 9 Phase 2 tables populated)  
✓ Total rows: ~150,000+  

---

## NEXT PHASE (After Phase 2 Complete)

Once Phase 2 data loads successfully:

**Phase 3A: S3 Staging** (10x speedup on bulk inserts)
- Apply to: Price/technical data loaders
- Expected: 1.25M rows in 30 sec (was 5+ min)

**Phase 3B: Lambda Parallelization** (100x speedup on API calls)
- Apply to: FRED API, yfinance, sentiment data
- Expected: 5000 symbols in 5 sec (was 500 sec)

---

## ESTIMATED PHASE 2 METRICS

| Metric | Expected |
|--------|----------|
| Total execution time | ~25 minutes |
| Total data rows | ~150,000+ |
| Parallelization speedup | 4-5x per loader |
| Wall-clock speedup | 2.1x (53 min → 25 min) |
| Cost | ~$2-4 (one-time, measured) |

---

**Status: READY TO EXECUTE**

Complete Steps 1-2, then trigger Phase 2!
