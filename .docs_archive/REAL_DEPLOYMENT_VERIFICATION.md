# Real Deployment Verification Checklist

**Purpose:** Actually verify workflows are running and infrastructure is deployed

---

## Where to Check

### 1. GitHub Actions (Recent Workflow Runs)

**URL:** https://github.com/argie33/algo/actions

**Check:**
- [ ] Go to "Actions" tab
- [ ] Look for recent runs of these workflows:
  - `bootstrap-oidc.yml`
  - `deploy-core.yml`
  - `deploy-app-infrastructure.yml`
  - `deploy-app-stocks.yml`
  - `deploy-webapp.yml`
  - `deploy-algo-orchestrator.yml`

**What to look for:**
- ✅ Green checkmark = workflow succeeded
- ❌ Red X = workflow failed
- ⏳ Yellow circle = workflow in progress

**For each failed workflow:**
1. Click on it
2. Click on the failing job
3. Scroll through logs to find error
4. Check "Deploy CloudFormation stack" step for errors

---

### 2. AWS CloudFormation Console

**URL:** https://console.aws.amazon.com/cloudformation/home?region=us-east-1

**Check:**
- [ ] Look for these stacks in the list:
  - `stocks-oidc-bootstrap` — Status should be `CREATE_COMPLETE` or `UPDATE_COMPLETE`
  - `stocks-core-vpc` (or similar) — Status should be `CREATE_COMPLETE` or `UPDATE_COMPLETE`
  - `stocks-app-stack` — Status should be `CREATE_COMPLETE` or `UPDATE_COMPLETE`
  - `stocks-app-ecs-tasks` — Status should be `CREATE_COMPLETE` or `UPDATE_COMPLETE`
  - `stocks-webapp-dev` — Status should be `CREATE_COMPLETE` or `UPDATE_COMPLETE`
  - `stocks-algo-orchestrator` — Status should be `CREATE_COMPLETE` or `UPDATE_COMPLETE`

**For each stack:**
1. Click on the stack name
2. Check "Stack Info" tab → Status field
3. If status is ROLLBACK_COMPLETE or CREATE_FAILED, click "Events" tab to see what went wrong

---

### 3. AWS Lambda Console

**URL:** https://console.aws.amazon.com/lambda/home?region=us-east-1

**Check:**
- [ ] Search for `algo-orchestrator`
  - ✅ Function should exist
  - ✅ Runtime: Python 3.11
  - ✅ Code should be from S3
  - ✅ Environment variables set (DATABASE_SECRET_ARN, ALPACA_API_KEY_SECRET_ARN, etc.)

- [ ] Search for webapp Lambda function
  - ✅ Function should exist
  - ✅ Runtime: Node.js 20.x
  - ✅ Environment variables set (DB_SECRET_ARN, DB_ENDPOINT, etc.)

**For each function:**
1. Click on function name
2. Check "Code" tab → Should not be empty
3. Check "Configuration" tab → Environment variables should be populated

---

### 4. AWS EventBridge Console

**URL:** https://console.aws.amazon.com/events/home?region=us-east-1

**Check:**
- [ ] Look for rule named `algo-eod-orchestrator`
  - ✅ State should be `ENABLED`
  - ✅ Schedule expression: `cron(0 21 * * ? *)`
  - ✅ Target should be Lambda function `algo-orchestrator`

**For the rule:**
1. Click on rule name
2. Check "Details" tab
3. Verify schedule and target are correct

---

### 5. AWS RDS Console

**URL:** https://console.aws.amazon.com/rds/home?region=us-east-1

**Check:**
- [ ] Look for database instance named `stocks`
  - ✅ Status should be `available`
  - ✅ Engine: PostgreSQL
  - ✅ Multi-AZ: Yes (or No if single-AZ is acceptable)

---

### 6. AWS ECS Console

**URL:** https://console.aws.amazon.com/ecs/home?region=us-east-1

**Check:**
- [ ] Look for cluster named `stocks-cluster` (or similar)
  - ✅ Status should show task definitions registered
  - ✅ Number of running tasks (should be 0 unless loaders are running)

**Check task definitions:**
1. Click "Task Definitions"
2. Look for tasks starting with `stocks-`
3. Should see 39 loader task definitions

---

### 7. AWS Secrets Manager Console

**URL:** https://console.aws.amazon.com/secretsmanager/home?region=us-east-1

**Check:**
- [ ] Look for secret named `stocks-db-credentials`
  - ✅ Status: Not deleted
  - ✅ Contains: DB username and password

- [ ] Look for secret named `alpaca-api-key` (or similar)
  - ✅ Status: Not deleted
  - ✅ Contains: Alpaca API keys

---

### 8. CloudWatch Logs

**URL:** https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:logs-insights

**Check:**
- [ ] Look for log group `/aws/lambda/algo-orchestrator`
  - ✅ Should have recent log streams (if algo executed)
  - ✅ No errors in recent logs

- [ ] Look for log group `/ecs/loader-*`
  - ✅ Should have recent entries (if loaders are running)

**For Lambda logs:**
1. Click on log group `/aws/lambda/algo-orchestrator`
2. Click on most recent log stream
3. Scroll through and look for error patterns
4. Should see execution details (start, end, duration)

---

## Real Verification Steps (What to Do Right Now)

### Step 1: Check GitHub Actions (5 minutes)
```
1. Go to https://github.com/argie33/algo/actions
2. Look for any recent runs
3. If no recent runs, we haven't pushed changes yet
4. Click on latest run for each workflow
5. Check if green ✅ or red ❌
```

**Expected:**
- All recent runs should be green (or some might not have run yet if no changes)
- If any are red, click into them to see the error

---

### Step 2: Check CloudFormation Stacks (10 minutes)
```
1. Go to https://console.aws.amazon.com/cloudformation
2. Look for the 6 stacks (see list above)
3. Note the Status of each
4. If any are ROLLBACK_COMPLETE or CREATE_FAILED, click Events tab
```

**Expected:**
- All stacks should show CREATE_COMPLETE or UPDATE_COMPLETE
- If any are missing, that workflow hasn't run yet
- If any are ROLLBACK_COMPLETE, there was an error (check Events tab)

---

### Step 3: Check Lambda Functions (5 minutes)
```
1. Go to https://console.aws.amazon.com/lambda
2. Search for "algo-orchestrator"
3. Click on it
4. Check Configuration → Environment variables
```

**Expected:**
- Function should exist
- Should have DATABASE_SECRET_ARN and ALPACA_API_KEY_SECRET_ARN set
- Values should be valid ARNs (like arn:aws:secretsmanager:...)

---

### Step 4: Check EventBridge Rule (5 minutes)
```
1. Go to https://console.aws.amazon.com/events
2. Look for "algo-eod-orchestrator" rule
3. Check it's ENABLED
4. Check schedule is "cron(0 21 * * ? *)"
```

**Expected:**
- Rule should exist
- State should be ENABLED
- Target should be algo-orchestrator Lambda function

---

### Step 5: Trigger a Test Workflow (Optional)

If you want to test that workflows actually work:

**Option A: Push a code change**
```bash
# Make a trivial change to trigger a workflow
echo "# test" >> README.md
git add README.md
git commit -m "test: trigger workflows"
git push origin main
```

Then go to GitHub Actions and watch the workflows run.

**Option B: Manually trigger a workflow**
```
1. Go to https://github.com/argie33/algo/actions
2. Click "deploy-algo-orchestrator"
3. Click "Run workflow" button
4. Click the green "Run workflow" button
5. Watch the run in real-time
```

---

## Verification Report Template

Use this to document what you find:

```
DEPLOYMENT VERIFICATION REPORT
Date: ___________
Verified by: ___________

GITHUB ACTIONS
  bootstrap-oidc.yml: ✅ ❌ ⏳ (latest run: __________)
  deploy-core.yml: ✅ ❌ ⏳ (latest run: __________)
  deploy-app-infrastructure.yml: ✅ ❌ ⏳ (latest run: __________)
  deploy-app-stocks.yml: ✅ ❌ ⏳ (latest run: __________)
  deploy-webapp.yml: ✅ ❌ ⏳ (latest run: __________)
  deploy-algo-orchestrator.yml: ✅ ❌ ⏳ (latest run: __________)

CLOUDFORMATION STACKS
  stocks-oidc-bootstrap: ✅ ❌ (status: ____________)
  stocks-core-vpc: ✅ ❌ (status: ____________)
  stocks-app-stack: ✅ ❌ (status: ____________)
  stocks-app-ecs-tasks: ✅ ❌ (status: ____________)
  stocks-webapp-dev: ✅ ❌ (status: ____________)
  stocks-algo-orchestrator: ✅ ❌ (status: ____________)

LAMBDA FUNCTIONS
  algo-orchestrator: ✅ ❌ (exists, env vars set)
  webapp function: ✅ ❌ (exists, env vars set)

EVENTBRIDGE RULES
  algo-eod-orchestrator: ✅ ❌ (enabled, correct schedule)

SECRETS
  stocks-db-credentials: ✅ ❌ (exists, accessible)
  alpaca-api-key: ✅ ❌ (exists, accessible)

OVERALL STATUS
All green: ✅ Infrastructure is properly deployed
Some issues: ⚠️ Need to fix the following:
  - ________________________________________
  - ________________________________________
```

---

## What This Verification Proves

✅ **All workflows ran successfully** = Infrastructure is being deployed automatically
✅ **All CloudFormation stacks exist** = AWS resources are created and configured
✅ **Lambda functions have env vars set correctly** = Credentials are flowing from CloudFormation exports
✅ **EventBridge rule is enabled** = Algo will run automatically at 5:30pm ET
✅ **Secrets exist and are accessible** = Applications can access credentials

---

## Timeline

**Today:**
- Right now: Do the 5 verification steps above
- 5:30pm ET: Algo will automatically execute (if EventBridge rule exists and is enabled)
- 5:35pm ET: Check CloudWatch logs to see execution results
- 5:40pm ET: Run monitor script to see new rows in algo tables

**This proves everything works end-to-end.**

