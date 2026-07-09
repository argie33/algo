# Production Readiness Action Plan

**Target State:** Full end-to-end trading system operational via Alpaca paper trading  
**Current State:** Code is production-ready; infrastructure needs loader pipeline fix  
**Estimated Time to Resolution:** 30-60 minutes

---

## Critical Issue Summary

**Problem:** Metric loaders (quality, growth, value, positioning, stability, stock_scores) are 29+ hours stale. Without fresh metrics, the system cannot generate valid trading signals.

**Root Cause:** EventBridge EOD loader pipeline (scheduled for 4:05 PM ET) is not executing.

**Impact:** 
- Dashboard shows stale data
- Orchestrator runs but has no fresh metrics to work with
- Trading signals are yesterday's signals, not today's

---

## PHASE 1: Quick Diagnosis (5 minutes)

Run this to understand the current state:

```bash
cd /c/Users/arger/code/algo

# Get system diagnostic
python3 scripts/diagnose_and_fix_loaders.py

# Check specific loader status
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from utils.db.context import DatabaseContext
from datetime import datetime, timezone

with DatabaseContext("read") as cur:
    cur.execute("""
        SELECT table_name, last_updated, status
        FROM data_loader_status
        WHERE table_name IN ('stock_scores', 'quality_metrics', 'buy_sell_daily')
        ORDER BY last_updated DESC
    """)
    for table, last_run, status in cur.fetchall():
        age_h = (datetime.now(timezone.utc) - last_run.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        print(f"{table:25} {age_h:6.1f}h old | {status}")
EOF
```

---

## PHASE 2: Fix Loaders (Pick ONE approach)

### Approach A: Manual Trigger (Recommended - Fastest)

**1. Deploy fresh loaders via GitHub Actions:**

```bash
# Deploy all stale metric loaders in parallel
gh workflow run run-loader.yml -f loader_name=load_quality_metrics -f parallelism=2
gh workflow run run-loader.yml -f loader_name=load_growth_metrics -f parallelism=2
gh workflow run run-loader.yml -f loader_name=load_value_metrics -f parallelism=2
gh workflow run run-loader.yml -f loader_name=load_positioning_metrics -f parallelism=2
gh workflow run run-loader.yml -f loader_name=load_stability_metrics -f parallelism=2

# Wait ~15 minutes for metric loaders to complete

# Then compute stock scores
gh workflow run run-loader.yml -f loader_name=load_stock_scores

# Then generate signals
gh workflow run run-loader.yml -f loader_name=load_buy_sell_daily
```

**2. Verify completion:**

```bash
# Poll for completion
watch -n 30 'python3 scripts/diagnose_and_fix_loaders.py'

# Or manually check
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from utils.db.context import DatabaseContext
with DatabaseContext("read") as cur:
    cur.execute("SELECT table_name, status FROM data_loader_status WHERE table_name IN ('stock_scores', 'buy_sell_daily')")
    for table, status in cur.fetchall():
        print(f"{table}: {status}")
EOF
```

### Approach B: Infrastructure Investigation (Root Cause)

**If Approach A doesn't work or you want to fix the automation:**

```bash
# 1. Check EventBridge rule exists and is ENABLED
aws events describe-rule \
  --name algo-stock_scores-schedule \
  --region us-east-1

# Expected output: "State": "ENABLED"
# If not: aws events enable-rule --name algo-stock_scores-schedule

# 2. Check ECS cluster capacity
aws ecs describe-clusters \
  --clusters algo-cluster-dev \
  --region us-east-1 | jq '.clusters[0] | {name, status, registeredContainerInstancesCount}'

# Expected: registeredContainerInstancesCount > 0

# 3. Check for stuck loader locks
aws dynamodb get-item \
  --table-name algo-loader-locks-dev \
  --key '{"lock_key": {"S": "load_stock_scores"}}' \
  --region us-east-1

# If lock is stuck (old timestamp): Delete it
aws dynamodb delete-item \
  --table-name algo-loader-locks-dev \
  --key '{"lock_key": {"S": "load_stock_scores"}}' \
  --region us-east-1

# 4. Check CloudWatch logs
aws logs tail /ecs/algo-cluster --since 2h --follow | grep -i "error\|fail\|timeout"
```

### Approach C: Deploy Full Infrastructure (Nuclear Option)

If EventBridge rules are missing or misconfigured:

```bash
# Redeploy entire loader infrastructure via Terraform
cd terraform

# Validate
terraform validate

# Plan (see what will change)
terraform plan -out=tfplan

# Apply
terraform apply tfplan

# Verify EventBridge rules created
aws events list-rules --name-prefix algo --region us-east-1
```

---

## PHASE 3: Run Orchestrator with Fresh Data (5 minutes)

Once metric loaders complete:

```bash
# Trigger orchestrator immediately
python3 scripts/trigger_orchestrator.py --run morning --mode paper

# Or via GitHub Actions
gh workflow run trigger-orchestrator-scheduled.yml

# Watch execution
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from utils.db.context import DatabaseContext
from datetime import datetime, timezone

with DatabaseContext("read") as cur:
    # Poll for latest orchestrator run
    while True:
        cur.execute("""
            SELECT run_id, started_at, completed_at, success
            FROM algo_orchestrator_runs
            ORDER BY started_at DESC LIMIT 1
        """)
        run = cur.fetchone()
        if run:
            run_id, started, completed, success = run
            elapsed = (completed - started).total_seconds() / 60 if completed else "..."
            status = "✅ SUCCESS" if success else "❌ FAILED"
            print(f"{status} {run_id} ({elapsed}min)")
            if completed:
                break
        import time
        time.sleep(10)
EOF
```

---

## PHASE 4: Verify Dashboard (5 minutes)

```bash
cd /c/Users/arger/code/algo/webapp

# Start dev server
npm run dev &

# Open browser to http://localhost:5173

# Verify:
# ✅ Dashboard loads without errors
# ✅ Portfolio section shows current value
# ✅ Positions section shows open positions (if any)
# ✅ Scores section shows stock rankings
# ✅ Market section shows fresh market data (prices, VIX, market regime)
# ✅ Signals section shows today's BUY signals
# ✅ Data freshness indicators show "✅ FRESH" (< 2 hours old)

# Stop when verified
pkill -f "npm run dev"
```

---

## PHASE 5: Deploy to AWS (5 minutes)

Once everything verified locally:

```bash
# Push code changes
git push origin main

# GitHub Actions will automatically:
# 1. Run all tests (CI pipeline)
# 2. Build and push Docker images
# 3. Deploy Lambda functions
# 4. Update Terraform state

# Monitor deployment
gh run list -w deploy-all-infrastructure.yml --limit 1

# Watch for completion
gh run view <run-id> --log --follow

# Verify AWS infrastructure updated
aws lambda get-function --function-name algo-orchestrator-dev \
  --query 'Configuration.LastModified' \
  --region us-east-1

aws lambda get-function --function-name algo-api-dev \
  --query 'Configuration.LastModified' \
  --region us-east-1
```

---

## Troubleshooting Guide

### Symptom: Loaders still don't complete

```bash
# Check ECS task logs
TASK_ARN=$(aws ecs list-tasks --cluster algo-cluster-dev --family algo-metric-loader \
  --region us-east-1 --query 'taskArns[0]' --output text)

aws ecs describe-tasks --cluster algo-cluster-dev --tasks $TASK_ARN \
  --region us-east-1 --query 'tasks[0].[taskArn, lastStatus, exitCode]'

# Get full logs
CONTAINER_INSTANCE_ARN=$(aws ecs describe-tasks --cluster algo-cluster-dev \
  --tasks $TASK_ARN --region us-east-1 \
  --query 'tasks[0].containerInstanceArn' --output text)

# CloudWatch logs
aws logs tail /ecs/algo-cluster --since 30m --follow | grep -i "ERROR\|Exception"
```

### Symptom: Orchestrator runs but generates 0 signals

```bash
# Check if stock_scores has data
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from utils.db.context import DatabaseContext
with DatabaseContext("read") as cur:
    cur.execute("SELECT COUNT(*) FROM stock_scores WHERE updated_at > NOW() - INTERVAL '1 hour'")
    count = cur.fetchone()[0]
    print(f"Fresh scores: {count}")

    cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE signal_date >= CURRENT_DATE AND signal_type = 'BUY'")
    signals = cur.fetchone()[0]
    print(f"Today's BUY signals: {signals}")
EOF

# If scores are missing: Re-run load_stock_scores
gh workflow run run-loader.yml -f loader_name=load_stock_scores

# If signals are 0: Re-run buy_sell_daily
gh workflow run run-loader.yml -f loader_name=load_buy_sell_daily
```

### Symptom: Dashboard still shows stale data

```bash
# Clear dashboard cache
pkill -9 python

# Kill any lingering processes
pkill -f "npm\|node"

# Restart dashboard fresh
cd webapp && npm run dev &

# Note: API cache is 30 min, but /api/scores is NOT cached
# Wait 30 seconds and refresh browser

# Or force API cache clear on AWS:
aws lambda invoke \
  --function-name algo-api-dev \
  --region us-east-1 \
  --payload '{"action": "clear_cache"}' \
  /tmp/response.json

cat /tmp/response.json
```

---

## Success Criteria

System is production-ready when:

- [ ] ✅ All loaders complete successfully (stock_scores, buy_sell_daily, etc.)
- [ ] ✅ Data is fresh (< 2 hours old for prices, < 1 day old for metrics)
- [ ] ✅ Orchestrator runs successfully (Phase 1-9 all pass)
- [ ] ✅ Dashboard shows fresh data with proper error handling
- [ ] ✅ Trading signals are generated (today's date, > 0 signals)
- [ ] ✅ Tests pass locally and on CI/CD
- [ ] ✅ AWS infrastructure deployed and operational
- [ ] ✅ EventBridge scheduler firing orchestrator Lambda at scheduled times

---

## Estimated Timeline

| Phase | Task | Time | Status |
|-------|------|------|--------|
| 1 | Run diagnostic | 5 min | Ready |
| 2 | Fix loaders (manual trigger) | 20 min | Ready |
| 3 | Run orchestrator | 5 min | Ready |
| 4 | Verify dashboard | 5 min | Ready |
| 5 | Deploy to AWS | 5 min | Ready |
| **Total** | | **40 min** | **Ready to Execute** |

---

## Commands Quick Reference

```bash
# Diagnostics
python3 scripts/diagnose_and_fix_loaders.py

# Trigger loaders
gh workflow run run-loader.yml -f loader_name=load_stock_scores

# Trigger orchestrator
python3 scripts/trigger_orchestrator.py --run morning --mode paper

# Start dashboard
cd webapp && npm run dev

# Deploy to AWS
git push origin main

# Monitor AWS deployment
gh run list -w deploy-all-infrastructure.yml

# Check AWS resources
aws rds describe-db-instances --db-instance-identifier algo-db --region us-east-1
aws lambda list-functions --region us-east-1 | grep algo
aws events list-rules --name-prefix algo --region us-east-1
```

---

## Support & Escalation

**If Approach A (manual trigger) works:**
- System is operational but EventBridge automation needs investigation
- Action: File bug on EventBridge/ECS infrastructure

**If Approach B (infrastructure investigation) finds issue:**
- Fix the infrastructure bug and redeploy
- Action: Detailed fix documented in CloudWatch logs

**If Approach C (nuclear option) needed:**
- Infrastructure was corrupt or missing
- Action: Terraform redeploy with monitoring

**Emergency Contact:** Check steering/OPERATIONS.md for on-call procedures

---

**Remember:** The code is production-ready. We just need to get fresh data flowing through the loaders. Once loaders complete, the system will work end-to-end.

Good luck! 🚀
