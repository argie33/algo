# Deployment Checklist - Portfolio/Dashboard Data Unavailable

**Status:** CRITICAL - Portfolio snapshot stale (8491s old, max 360s allowed)

**Root Cause:** EventBridge schedules for orchestrator Lambda NOT deployed to AWS.

## What's Broken

1. ✗ **Portfolio Panel** — Returns "Data is stale" (8491s old)
2. ✗ **Orchestrator not running** — Phase 9 hasn't executed in 2+ hours
3. ✗ **EventBridge schedules missing** — Morning (9:30 AM) and Evening (5:30 PM) schedules not in AWS

## Fix: Deploy Infrastructure via GitHub Actions

### Step 1: Ensure code is pushed to main

```bash
git status  # Should show "nothing to commit"
git log -1  # Should show latest fixes
```

### Step 2: Manually trigger GitHub Actions deployment

**Option A: Using GitHub CLI (Recommended)**

```bash
gh workflow run deploy-all-infrastructure.yml \
  --ref main \
  -R argie33/algo
```

Then monitor:
```bash
gh run list -R argie33/algo --workflow deploy-all-infrastructure.yml
gh run view <RUN_ID> --log -R argie33/algo  # Stream logs
```

**Option B: Using GitHub Web UI**

1. Go to: https://github.com/argie33/algo/actions
2. Select workflow: "Deploy All Infrastructure (Terraform)"
3. Click "Run workflow" button
4. Leave inputs as default (skip_terraform=false, skip_code=false, skip_image=false)
5. Monitor the run

### Step 3: Verify deployment succeeded

Once workflow completes (takes ~15-20 min):

```bash
# Check if EventBridge scheduler created
aws scheduler list-schedules --region us-east-1 \
  --query "Schedules[?Name | contains('algo-schedule')].{Name:Name, State:State}" \
  --output table

# Expected output (2 schedules for 2x daily):
# - algo-schedule-morning-dev (ENABLED)
# - algo-schedule-dev (ENABLED, 5:30 PM evening)

# Verify Lambda function deployed
aws lambda get-function --function-name algo-orchestrator-dev \
  --region us-east-1 \
  --query 'Configuration.LastModified'
```

### Step 4: Trigger first run manually (optional, to test)

```bash
# Invoke orchestrator once to create portfolio snapshot
aws lambda invoke \
  --function-name algo-orchestrator-dev \
  --region us-east-1 \
  --payload '{"source":"manual-test"}' \
  /tmp/response.json

cat /tmp/response.json
```

### Step 5: Verify data is fresh

Wait 2-3 minutes, then:

```bash
python -m dashboard.diagnose_dashboard
```

Expected: Portfolio panel should show "SUCCESS" instead of "STALE"

## What the deployment does

1. **Terraform:** Creates EventBridge Scheduler rules
   - Morning: 9:30 AM ET (Monday-Friday) → `algo_orchestrator_morning`
   - Evening: 5:30 PM ET (Monday-Friday) → `algo_orchestrator` (at 5:30 PM per expression)

2. **IAM:** Grants EventBridge permission to invoke Lambda

3. **Lambda:** Deploys latest orchestrator code with all phases

4. **Result:** Orchestrator runs on schedule, Phase 9 creates fresh portfolio snapshots every run

## If deployment fails

### Check logs

```bash
gh run view <RUN_ID> --log -R argie33/algo 2>&1 | grep -i error
```

### Common issues

| Issue | Fix |
|-------|-----|
| `AccessDenied` from Lambda | Verify GitHub Actions IAM role in AWS account has permission: `iam:PassRole`, `lambda:CreateFunction`, `events:PutRule` |
| Terraform lock timeout | Run manually: `cd terraform && terraform apply -lock=false` |
| State corruption | Inspect: `terraform state list \| grep scheduler` |

## Manual Workaround (Temporary Only)

Until deployment succeeds, manually trigger orchestrator:

```bash
# Every 30 minutes during trading hours
aws lambda invoke \
  --function-name algo-orchestrator-dev \
  --region us-east-1 \
  --payload '{"source":"manual","execution_mode":"paper"}' \
  /tmp/run.json
```

But this is NOT a permanent solution. **EventBridge deployment is required.**

## Expected Timeline

- **Deploy workflow:** 15-20 minutes
- **Terraform apply:** 5-10 minutes
- **First orchestrator run:** 2-3 minutes (Lambda cold start)
- **Portfolio snapshot created:** 5-10 minutes after Phase 9 completes
- **Dashboard data refreshes:** Within 1 minute of snapshot creation

**Total:** ~25-35 minutes from workflow start to seeing fresh data in dashboard.

## Next Steps

1. ✅ Code fixes committed to main
2. ⏳ Deploy via GitHub Actions
3. ⏳ Verify EventBridge schedules created in AWS
4. ⏳ Verify orchestrator Lambda runs on schedule
5. ⏳ Verify Phase 9 creates portfolio snapshot
6. ⏳ Verify dashboard displays fresh data
