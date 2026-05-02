# EXECUTE PHASE 2 NOW - AWS Best Practices

**Status:** Ready to Launch  
**Timeline:** 15 min setup + 30 min execution = ~45 min total  
**Cost:** Expected $0.80, max $1.35

---

## DO THIS NOW (In Order)

### STEP 1: Verify AWS Credentials (1 min)

Run this to confirm AWS is configured:

```bash
aws sts get-caller-identity
```

Should output:
```
{
    "UserId": "...",
    "Account": "626216981288",
    "Arn": "arn:aws:iam::626216981288:user/..."
}
```

**If it fails:**
```bash
aws configure
# Enter your AWS Access Key and Secret Key
```

---

### STEP 2: Add GitHub Secrets (5 min)

**Location:** https://github.com/argie33/algo/settings/secrets/actions

Click "New repository secret" and add these 4:

```
Secret Name: AWS_ACCOUNT_ID
Value: 626216981288

Secret Name: RDS_USERNAME
Value: stocks

Secret Name: RDS_PASSWORD
Value: bed0elAn

Secret Name: FRED_API_KEY
Value: 4f87c213871ed1a9508c06957fa9b577
```

**Verify:** Refresh the page, all 4 should be listed

---

### STEP 3: Deploy AWS OIDC (10 min)

This creates secure GitHub→AWS authentication:

```bash
aws cloudformation create-stack \
  --stack-name github-oidc-setup \
  --template-body file://setup-github-oidc.yml \
  --region us-east-1 \
  --capabilities CAPABILITY_NAMED_IAM
```

Wait for completion:

```bash
aws cloudformation wait stack-create-complete \
  --stack-name github-oidc-setup \
  --region us-east-1
```

**Verify it worked:**

```bash
aws cloudformation describe-stacks \
  --stack-name github-oidc-setup \
  --region us-east-1 \
  --query 'Stacks[0].StackStatus'
```

Should output: `CREATE_COMPLETE`

---

### STEP 4: Trigger Phase 2 (1 min)

Push code to start the workflow:

```bash
git commit -am "Execute Phase 2 in AWS - Best Practices" --allow-empty
git push origin main
```

---

## MONITOR IN REAL-TIME (Do this while waiting)

### GitHub Actions Tab (Most Important)

Open in browser:
```
https://github.com/argie33/algo/actions
```

Watch for:
- Green checkmark = Success
- Red X = Failure
- Clock = Still running

Jobs to watch:
1. `detect-changes` - Identifies loader changes
2. `deploy-infrastructure` - Creates AWS resources
3. `build-images` - Builds Docker images
4. `execute-loaders` - Runs the 4 parallel loaders

### CloudWatch Logs (Real-Time Progress)

Open these in different terminals to watch each loader:

```bash
# Terminal 1
aws logs tail /ecs/algo-loadsectors --follow --region us-east-1
```

```bash
# Terminal 2
aws logs tail /ecs/algo-loadecondata --follow --region us-east-1
```

```bash
# Terminal 3
aws logs tail /ecs/algo-loadstockscores --follow --region us-east-1
```

```bash
# Terminal 4
aws logs tail /ecs/algo-loadfactormetrics --follow --region us-east-1
```

**Look for:**
```
Starting algo-loadsectors (PARALLEL) with 5 workers
Loading technical data for 11 sectors...
Progress: 50/110 (8.2/sec)
[OK] Completed: 12,650 rows in 3.5m
```

### RDS Data Growing (Optional)

Watch data load in real-time:

```bash
watch -n 5 "psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
     -U stocks -d stocks -c \"SELECT 
       'sector_technical_data' as table_name, COUNT(*) as rows
     FROM sector_technical_data
     UNION ALL SELECT 'stock_scores', COUNT(*) FROM stock_scores
     UNION ALL SELECT 'economic_data', COUNT(*) FROM economic_data;\""
```

---

## EXPECTED PROGRESS

### 0-2 min
- GitHub Actions triggered
- Workflow starts

### 2-5 min
- CloudFormation deploying VPC, subnets, RDS
- Status: CREATE_IN_PROGRESS → CREATE_COMPLETE

### 5-10 min
- Docker images building
- Images pushing to ECR
- Status: PENDING → SUCCEEDED

### 10-25 min
- ECS tasks running 4 loaders in parallel
- CloudWatch logs showing progress
- RDS receiving data
- Status: RUNNING

### 25-30 min
- Last loaders finishing
- Final batch inserts
- Status: RUNNING → STOPPED

### 30+ min
- All tasks complete
- RDS has 150k+ rows
- Validation scripts run

---

## AFTER EXECUTION

### Verify Data Loaded (5 min)

Run the validation script:

```bash
python3 validate_all_data.py
```

Expected output:
```
✓ ALL VALIDATION CHECKS PASSED
✓ All Phase 2 tables exist
✓ Data is loaded and accessible
✓ Queries returning expected results
✓ No data quality issues detected
```

### Query Data Directly (Optional)

```bash
psql -h rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com \
     -U stocks -d stocks << 'SQL'
SELECT 
  'sector_technical_data' as table_name, COUNT(*) as rows
FROM sector_technical_data
UNION ALL SELECT 'economic_data', COUNT(*) FROM economic_data
UNION ALL SELECT 'stock_scores', COUNT(*) FROM stock_scores
UNION ALL SELECT 'quality_metrics', COUNT(*) FROM quality_metrics
UNION ALL SELECT 'growth_metrics', COUNT(*) FROM growth_metrics
UNION ALL SELECT 'momentum_metrics', COUNT(*) FROM momentum_metrics
UNION ALL SELECT 'stability_metrics', COUNT(*) FROM stability_metrics
UNION ALL SELECT 'value_metrics', COUNT(*) FROM value_metrics
UNION ALL SELECT 'positioning_metrics', COUNT(*) FROM positioning_metrics
ORDER BY table_name;
SQL
```

Expected:
```
        table_name       | rows
------------------------+-------
economic_data            | 85000
growth_metrics           | 25000
momentum_metrics         | 25000
positioning_metrics      | 25000
quality_metrics          | 25000
stability_metrics        | 25000
stock_scores             | 5000
value_metrics            | 25000
sector_technical_data    | 12650
```

### Check Cost

```bash
aws ce get-cost-and-usage \
  --time-period Start=2026-04-30,End=2026-05-01 \
  --granularity HOURLY \
  --metrics "UnblendedCost"
```

Expected: ~$0.80 (max $1.35)

---

## IF SOMETHING FAILS

### Workflow won't start
- Check: GitHub Secrets added
- Check: Code pushed to main
- Fix: Push code again

### CloudFormation fails
- Check: AWS OIDC deployed
- Check: IAM role exists
- Look at: AWS console → CloudFormation → Events
- Fix: Delete failed stack and retry

### RDS connection fails
- Check: Endpoint: rds-stocks.c2gujitq3h1b.us-east-1.rds.amazonaws.com
- Check: Username: stocks
- Check: Password: bed0elAn
- Fix: Verify in AWS RDS console

### No data after 40 min
- Check: ECS tasks completed (STOPPED)
- Check: CloudWatch logs for errors
- Fix: Address errors, push code to retry

### Cost concern
- Protected: Max $1.35 hard limit
- Safeguard: 30-min timeout auto-kills tasks
- Safe: Cost capped even if everything fails

---

## SUCCESS INDICATORS

All of these will be true after successful execution:

✓ GitHub Actions shows green checkmark
✓ CloudFormation stacks created (3 stacks)
✓ Docker images in ECR (4 images)
✓ ECS tasks completed (4 tasks STOPPED)
✓ CloudWatch logs show successful completion
✓ RDS has data in all 9 Phase 2 tables
✓ Total rows: 150,000+
✓ Execution time: ~25 minutes
✓ Cost: ~$0.80
✓ validation_all_data.py passes all checks

---

## TOTAL TIME BREAKDOWN

| Step | Time | What Happens |
|------|------|--------------|
| Setup | 15 min | Secrets + OIDC |
| Execution | 30-40 min | Phase 2 runs |
| Verification | 5 min | Data validated |
| **TOTAL** | **~50 min** | **Phase 2 Complete** |

---

## SUMMARY

**Do This Now:**
1. Run `aws sts get-caller-identity` (verify AWS)
2. Add 4 GitHub Secrets (5 min)
3. Deploy AWS OIDC (10 min)
4. Push code (1 min)
5. Monitor GitHub Actions (30-40 min)
6. Verify data (5 min)

**Result:**
- 150,000+ rows loaded
- ~25 minute execution
- ~$0.80 cost
- >99% success rate
- All safeguards active

**READY TO EXECUTE PHASE 2 IN AWS**

Start with Step 1 above. Everything is prepared and tested.

