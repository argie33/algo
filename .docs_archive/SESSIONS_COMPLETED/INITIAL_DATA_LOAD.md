# Initial Data Load - Verify Everything Works in AWS

**Goal**: Get all data loaded via GitHub Actions once, verify it works, then setup scheduling later.

---

## The Plan

```
STEP 1: Setup AWS infrastructure (one time)
    ↓
STEP 2: Configure GitHub secrets (one time)
    ↓
STEP 3: Push to main (triggers GitHub Actions)
    ↓
STEP 4: Watch deployment in real-time
    ↓
STEP 5: Verify all data loaded in AWS
    ↓
STEP 6: Check performance metrics
    ↓
LATER: Setup EventBridge for scheduled runs
```

---

## STEP 1: Setup AWS Infrastructure (5 minutes)

Run this once to configure everything:

```bash
bash SETUP_EVERYTHING.sh
```

This creates:
- ✓ S3 bucket for CloudFormation templates
- ✓ Core infrastructure stack
- ✓ IAM role for GitHub Actions
- ✓ Verifies database access

**Save the output**: Your AWS Account ID (you'll need it for secrets)

---

## STEP 2: Configure GitHub Secrets (3 minutes)

Add credentials to GitHub so workflow can deploy to AWS:

```bash
python3 setup_github_secrets.py
```

You'll be prompted for:
1. GitHub Personal Access Token (create at https://github.com/settings/tokens/new)
   - Scopes: repo (full control)
2. AWS Account ID (from Step 1)
3. RDS Username (stocks)
4. RDS Password (your database password)

**Or manually**:
GitHub → Settings → Secrets and Variables → Actions → Add:
- AWS_ACCOUNT_ID
- RDS_USERNAME
- RDS_PASSWORD

---

## STEP 3: Push to Main (Triggers Everything)

```bash
git add .
git commit -m "Initial setup: ready for first data load via GitHub Actions"
git push origin main
```

**This is the key moment.** GitHub Actions will automatically:

```
→ Detect your push
→ Trigger "Data Loaders Pipeline" workflow
→ Deploy Phase A (ECS with S3 staging)
→ Deploy Phase C (Lambda orchestrator)
→ Deploy Phase E (DynamoDB caching)
→ Deploy Phase D (Step Functions)
→ Execute all 39 loaders
→ Load data into database
```

---

## STEP 4: Watch Deployment in Real-Time

Go to your GitHub repo:

```
GitHub → Actions → "Data Loaders Pipeline"
```

Watch jobs execute:

| Job | Time | Status |
|-----|------|--------|
| detect-changes | 1 min | ⏳ Running |
| deploy-infrastructure | 10 min | ⏳ Running |
| execute-loaders (Phase A) | 30 min | ⏳ Running |
| execute-phase-c-lambda | 7 min | ⏳ Running |
| deploy-phase-e | 3 min | ⏳ Running |
| deploy-phase-d | 3 min | ⏳ Running |
| deployment-summary | 1 min | ⏳ Running |

**Total time: 50-60 minutes**

Green checkmarks = Success ✓
Red X = Error (check logs)

---

## STEP 5: Verify All Data Loaded in AWS

After workflow completes, run this to verify:

```bash
bash CHECK_AWS_STATUS.sh
```

This shows:
```
1. ECS Loader Executions
   ✓ Recently executed tasks
   
2. Lambda Executions
   ✓ buyselldaily orchestrator running
   
3. Step Functions
   ✓ State machine deployed
   ✓ Latest execution status
   
4. Database Updates
   ✓ Latest price_daily date
   ✓ Latest buy_sell_daily date
   ✓ Total record counts
   
5. CloudWatch Logs
   ✓ 0 errors (if setup correctly)
   
6. Cost Today
   ✓ Actual spend (should be <$10)
```

**Expected output:**
```
✓ Phase A: ECS S3 Staging (LIVE)
✓ Phase C: Lambda 100 Workers (READY)
✓ Phase D: Step Functions DAG (READY)
✓ Phase E: Smart Incremental + Caching (READY)

SUMMARY: SYSTEM OPERATIONAL
```

---

## STEP 6: Verify Data in Database

Check what actually loaded:

```bash
# Connect to your database
psql -h $DB_HOST -U stocks -d stocks

# Check price data
SELECT MAX(date), COUNT(*) FROM price_daily;

# Check signals
SELECT MAX(date), COUNT(*) FROM buy_sell_daily;

# Check scores
SELECT MAX(date), COUNT(*) FROM stock_scores;

# Check technicals
SELECT MAX(date), COUNT(*) FROM technical_data_daily;
```

**Expected results:**
```
price_daily:        today's date, 5000+ records
buy_sell_daily:     today's date, 5000+ records
stock_scores:       today's date, 5000+ records
technical_data_daily: today's date, 5000+ records
```

---

## STEP 7: Performance Verification

After first load, you should see:

### Speed
```
Phase A (ECS loaders):    30 minutes (vs 45-100 min baseline)
Phase C (Lambda):         7 minutes (vs 3-4 hours buyselldaily baseline)
Total first load:         50-60 minutes
```

### Cost
```
First load:        ~$15 (all phases + all loaders)
Expected monthly:  ~$225 (vs $1,200 baseline)
Savings:           -81%
```

### Data Quality
```
✓ All 39 loaders executed successfully
✓ No missing data
✓ All tables populated
✓ 0 CloudWatch errors
```

---

## When All Data Is Loaded

You'll have:

```
Database Tables:
  ✓ price_daily (today's prices)
  ✓ price_weekly
  ✓ price_monthly
  ✓ buy_sell_daily (today's signals)
  ✓ buy_sell_weekly
  ✓ buy_sell_monthly
  ✓ stock_scores (today's scores)
  ✓ technical_data_daily (today's technicals)
  ✓ earnings_history
  ✓ financial statements (quarterly + annual)
  ✓ 30+ other data tables

AWS Infrastructure:
  ✓ Phase A: ECS with S3 staging
  ✓ Phase C: Lambda orchestrator + 100 workers
  ✓ Phase D: Step Functions DAG
  ✓ Phase E: DynamoDB caching
  ✓ EventBridge: Ready for scheduling

Frontend:
  ✓ API endpoints working with real data
  ✓ Charts populated
  ✓ All features enabled
```

---

## Troubleshooting Initial Load

### Workflow Failed in GitHub Actions

Check the logs:
```
GitHub → Actions → Data Loaders Pipeline → Failed Job → Logs
```

Common issues:
- AWS credentials wrong (check secrets)
- Database password wrong (check .env.local)
- IAM role missing (run SETUP_EVERYTHING.sh again)

### Workflow Succeeded but No Data in Database

Check database connection:
```bash
psql -h $DB_HOST -U stocks -d stocks -c "SELECT 1"
```

Check CloudWatch logs:
```bash
aws logs tail /stepfunctions/data-loading-pipeline --follow
```

### Partial Data Loaded

Check which loaders failed:
```bash
bash CHECK_AWS_STATUS.sh
# Look at error count
```

Some loaders may fail due to:
- API rate limits
- Missing credentials
- Data not available

Re-run workflow to retry:
```
GitHub → Actions → Data Loaders Pipeline → Run workflow
```

---

## Next Steps (After Initial Load)

Once you verify all data loaded successfully:

1. **Test the frontend** with real data
   - All charts should work
   - All features should be enabled
   
2. **Document what worked**
   - Save CHECK_AWS_STATUS.sh output
   - Note actual costs
   - Record load times
   
3. **Setup scheduled runs** (later, when ready)
   - EventBridge every 4 hours (Tier 1)
   - Daily at 2 AM (all tiers)
   - Or market-hours only
   
4. **Configure alerts** (optional)
   - CloudWatch alarms for failures
   - SNS notifications
   - Email on errors

---

## Summary

```
GOAL:     Get all data loaded in AWS to verify everything works
METHOD:   GitHub Actions (push to main)
TIME:     50-60 minutes for initial load
RESULT:   All 39 loaders executed, all data tables populated
NEXT:     Setup EventBridge for recurring scheduled runs

COMMANDS:
  bash SETUP_EVERYTHING.sh          # Setup AWS (one time)
  python3 setup_github_secrets.py   # Add secrets (one time)
  git push origin main              # Trigger first load
  bash CHECK_AWS_STATUS.sh          # Verify it worked
```

**Push and let GitHub Actions load all your data.**
