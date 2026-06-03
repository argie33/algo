# Full Orchestrator Test & Deployment Plan

**Status:** Ready for testing (post-fix 5f0948dd)  
**Goal:** Verify full orchestrator runs end-to-end with complete dataset, then deploy to prod  
**Expected Duration:** 30-45 minutes total

## Prerequisites Checklist

Before starting the test:

- [ ] AWS credentials refreshed: `scripts/refresh-aws-credentials.ps1`
- [ ] Latest code committed (commit 5f0948dd or later)
- [ ] Database is accessible from dev environment
- [ ] RDS performance insights enabled to monitor during run

## Test Procedure

### Step 1: Deploy Latest Code (5 minutes)

```powershell
# Verify working directory
cd C:\Users\arger\code\algo

# Show latest commits
git log --oneline -3

# Deploy infrastructure (ECS images, Lambda, migrations)
cd terraform
terraform apply -var-file="terraform.tfvars" -auto-approve

# Wait for ECS image build if triggered
# (Check GitHub Actions: build-push-ecr.yml)
```

### Step 2: Run Orchestrator Test (Manual Invocation)

Choose **ONE** testing approach:

#### Option A: Manual Lambda Invocation via Console (Easiest)

```powershell
# Via AWS CLI (substitute actual run date if needed)
aws lambda invoke \
  --function-name algo-algo-dev \
  --region us-east-1 \
  --payload '{"run_date":"2026-06-03","dry_run":false,"verbose":true}' \
  response.json

# Watch response
cat response.json | ConvertFrom-Json | ConvertTo-Json -Depth 10
```

#### Option B: Trigger via GitHub Actions Workflow

```
GitHub → Actions → "Manual Invoke Orchestrator" 
→ Run Workflow → date: 2026-06-03, dry_run: false
→ Wait for completion
```

#### Option C: Wait for Scheduled Run

Next scheduled orchestrator runs:
- 9:30 AM ET (market open) — LIVE RUN
- 1:00 PM ET (intraday) — LIVE RUN
- 3:00 PM ET (intraday) — LIVE RUN
- 5:30 PM ET (post-market) — LIVE RUN

### Step 3: Monitor Execution (Real-Time, ~5-10 minutes)

Open **2 parallel monitoring windows:**

**Window 1: Stream CloudWatch Logs**
```powershell
aws logs tail '/aws/lambda/algo-algo-dev' `
  --follow `
  --region us-east-1 `
  --log-stream-name-prefix "2026/06/03"
```

**Window 2: Check Metrics**
```powershell
# Every 30 seconds, check phase results
$pattern = "PHASE|Final Report|qualified|trades executed"
aws logs tail '/aws/lambda/algo-algo-dev' `
  --follow `
  --region us-east-1 `
  --filter-pattern $pattern
```

### Step 4: Verify Success Criteria

After orchestrator completes, check for:

#### Criterion 1: All Phases Completed

Log should contain:
```
PHASE 1: DATA FRESHNESS ... [OK]
PHASE 2: CIRCUIT BREAKERS ... [OK or HALT]
PHASE 3: POSITION MONITOR ... [OK]
PHASE 3B: EXPOSURE POLICY ... [OK]
PHASE 4: EXIT EXECUTION ... [OK]
PHASE 4B: PYRAMID ADDS ... [OK]
PHASE 5: SIGNAL GENERATION ... [OK]
PHASE 6: ENTRY EXECUTION ... [OK or SKIP if halted]
PHASE 7: RECONCILIATION ... [OK]
```

#### Criterion 2: Signals Generated

Look for output like:
```
[WATERFALL] Signal filtering on 2026-06-03:
  Total BUY signals:        324
  Stage 2 (pre-pipeline):   98
  Tier 1 rejected:          0
  ...
  Final qualified:          12
```

**Pass Condition:** `Final qualified >= 1`

#### Criterion 3: Trades Executed (if not halted)

Look for:
```
PHASE 6: ENTRY EXECUTION ... [OK]
  Executed 5 new trades (e.g., ON, MT, ODFL, COHU, RMBS)
```

**Pass Condition:** Trade count > 0 (or 0 if halted by Phase 2)

#### Criterion 4: Reconciliation Complete

Look for:
```
PHASE 7: RECONCILIATION ... [OK]
  Portfolio $... , X positions, unrealized P&L $...
```

**Pass Condition:** Reconciliation must complete (fail-open)

### Step 5: Data Verification (Optional, 5 minutes)

Connect to RDS and verify data consistency:

```powershell
# Using psql or similar
# Check trade count
SELECT COUNT(*) as trade_count FROM algo_trades 
WHERE entry_date::date = '2026-06-03'

# Check position count
SELECT COUNT(*) as open_positions FROM algo_positions 
WHERE status = 'open' AND entry_date::date = '2026-06-03'

# Check latest orchestrator run record
SELECT run_id, run_date, success, phases FROM algo_orchestrator_runs 
ORDER BY created_at DESC LIMIT 1
```

## Success/Failure Paths

### ✅ SUCCESS: All phases pass, signals generated, trades executed

```
Action: Proceed to Deployment
- Create new commit with test results
- Push to main (triggers prod deploy)
- Monitor prod run at 9:30 AM ET tomorrow
```

### ⚠️ PARTIAL: All phases complete but NO signals generated

```
Likely cause: Swing scores stale or all candidates filtered
Action: 
1. Check Phase 1 log: is swing_trader_scores fresh?
2. Check Phase 5 [WATERFALL]: which tier rejects most signals?
3. Check algo_config: is min_percent_from_52w_low = 0.0?
   SELECT value FROM algo_config WHERE key = 'min_percent_from_52w_low'

Fix: Manually update config if needed:
   UPDATE algo_config SET value = '0.0' WHERE key = 'min_percent_from_52w_low'
   
Then retry test.
```

### ❌ FAILURE: Phase halts (Phase 1 or 2)

```
Likely cause: Data stale, circuit breaker triggered
Action:
1. Check Phase 1: which data is stale?
   SELECT table_name, latest_date, age_days FROM data_loader_status

2. If price_daily stale: manually trigger stock_prices_daily loader
   aws stepfunctions start-execution \
     --state-machine-arn arn:aws:stepfunctions:us-east-1:...:stateMachine:eod-pipeline \
     --name "manual-price-load-$(date +%s)"

3. If circuit breaker (Phase 2 halt):
   Check /tmp/orchestrator_halt in DynamoDB
   Manual clear: python scripts/check_halt_flag.py --clear

Then retry test.
```

### 🔴 CRITICAL: Lambda errors, DB unreachable

```
Action: Immediate diagnosis needed
1. Check CloudWatch logs for stack trace
2. Verify RDS is running: aws rds describe-db-instances --db-instance-identifier algo-db
3. Verify IAM permissions: aws iam list-role-policies --role-name algo-orchestrator-dev
4. Check VPC security groups: orchestrator -> RDS ingress on 5432

If credential/permission issue:
   scripts/refresh-aws-credentials.ps1
   Then retry

If RDS issue:
   Contact AWS support or check RDS console for maintenance windows
```

## Deployment to Production

### Prerequisites (Before Pushing to Main)

- [ ] Test run succeeded with at least 1 signal generated
- [ ] All 7 phases completed without errors
- [ ] No transaction abort or timeout errors in logs
- [ ] Test run date is recent (within last 3 trading days)

### Deploy Command

```powershell
# Verify no uncommitted changes
git status  # Should be clean

# Deploy to production (triggers GitHub Actions)
git push main

# Monitor deploy via GitHub
# GitHub -> Actions -> "Deploy All Infrastructure" -> Watch progress
```

### Post-Deployment Verification (Next Trading Day)

After deploy completes, monitor 9:30 AM ET production run:

```powershell
aws logs tail '/aws/lambda/algo-algo-prod' `
  --follow `
  --region us-east-1 `
  --filter-pattern "PHASE 5|PHASE 6|FINAL REPORT"
```

**Success Indicators:**
- Prod orchestrator runs at 9:30 AM ET without errors
- Trades execute in prod account (check Alpaca account)
- Daily report includes executed trades

## Rollback Plan (If Production Issues)

```powershell
# Immediate: Revert last commit
git revert HEAD
git push main

# This triggers automatic rollback deploy

# Optional: Manually disable trading
# Update algo_config: UPDATE algo_config SET value = 'dry' WHERE key = 'execution_mode'
```

## Monitoring Dashboard

After successful deployment, monitor via:

- **CloudWatch**: algo-loader-monitoring-dev (loader status)
- **RDS Performance Insights**: Check query durations
- **Alpaca Dashboard**: Verify trades executing in correct account
- **GitHub Actions**: Scheduled workflows running on time

## Troubleshooting Reference

See steering/algo.md sections:
- "Orchestrator Phases" — phase descriptions and fail-closed behavior
- "Performance Baseline" — expected timings
- "Troubleshooting" — common issues and fixes
