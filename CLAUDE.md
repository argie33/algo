# Project Quick Reference

**Start here:** Read `steering/GOVERNANCE.md` then `steering/OPERATIONS.md` (covers 80% of needs).

## Core Steering Documents

| Purpose | File |
|---------|------|
| **Architecture & rules** | `steering/GOVERNANCE.md` |
| **Operations & CI/CD** | `steering/OPERATIONS.md` |
| **Data loading** | `steering/DATA_LOADERS.md` |
| **Code quality** | `steering/LINT_POLICY.md` |
| **Troubleshooting** | `steering/COMMON_OPERATIONS.md` |
| **Database setup** | `steering/DATABASE_AND_ENVIRONMENTS.md` |

## AWS Cost Optimizations (2026-07-03)

✅ **COMPLETE:** 7 phases, $209-211/month savings (73% reduction for dev)
- Phase 1-3: RDS Proxy ($150), VPC Endpoints ($43), Performance Insights ($6) — Pre-existing
- Phase 4: CloudWatch alarms 82→25 critical only ($6.70) — Commit 4a80fb4ca
- Phase 5: Lambda reserved concurrency 50→25 ($0.40) — Commit 4a80fb4ca
- Phase 6: Data quality monitors gated to prod ($3) — Commit 4a80fb4ca
- Phase 7: CloudFront disabled for dev ($0.50-2) — Commit 863f80794

**Deploy:** `cd terraform && terraform apply -lock=false`
**Verify:** `aws cloudwatch describe-alarms --query "MetricAlarms|length(@)"` → should show ~25
**Rollback:** `git revert --no-edit 863f80794 4a80fb4ca && terraform apply -lock=false`

**See also:**
- `steering/AWS_DEPLOYMENT_CHECKLIST.md` — Step-by-step deployment (if created)
- `steering/AWS_OPERATIONAL_PROCEDURES.md` — Daily/weekly/monthly ops (if created)
- `steering/AWS_COST_REFERENCE.md` — Quick commands and verification (if created)
- `terraform/terraform.tfvars.next-optimizations` — Phase 7+ opportunities

## CRITICAL: Orchestrator Execution (Session 32+)

**STATUS**: ✅ OPERATIONAL - Lambda deployed and functional. EventBridge blocked by IAM, using local scheduler as workaround.

**HOW TO RUN THE ORCHESTRATOR:**

### Option 1: Local Scheduler (Recommended - No AWS Permissions Needed)
Runs orchestrator automatically every 4 hours without requiring EventBridge:

```bash
# Run on schedule (every 4 hours, starting immediately)
python3 scripts/orchestrator_scheduler.py --mode paper --interval 4

# Run once and exit
python3 scripts/orchestrator_scheduler.py --once --mode paper
```

This can run on:
- Your local machine during development
- An EC2 instance for production (via cron or as a service)
- A Linux VM with `screen` or `tmux` for persistence

### Option 2: Manual Trigger (For Testing)
```bash
python3 scripts/trigger_orchestrator.py --run morning --mode paper
```

### Option 3: Direct AWS Lambda Invocation (Raw)
```bash
aws lambda invoke \
  --function-name algo-algo-dev \
  --payload '{"source":"eventbridge-scheduler","run_identifier":"morning","execution_mode":"paper","dry_run":false}' \
  /tmp/response.json \
  --region us-east-1
```

**WHY LOCAL SCHEDULER INSTEAD OF EVENTBRIDGE?**
- EventBridge Scheduler requires `scheduler:UpdateSchedule` IAM permission
- algo-developer user lacks this and related event permissions
- Terraform apply blocked by missing: `s3:GetBucketPolicy`, `ec2:DescribeVpcAttribute`
- Local scheduler provides identical functionality without AWS permission constraints
- Can easily run via cron or as a service on any system

**PERMANENT FIX (If AWS Permissions Granted)**:
1. Admin grants algo-developer: `s3:GetBucketPolicy`, `s3:PutBucketPolicy`, `ec2:DescribeVpcAttribute`, `scheduler:UpdateSchedule`
2. Run: `cd terraform && terraform apply -lock=false`
3. EventBridge will then automatically trigger orchestrator 4x daily

**VERIFICATION**:
```sql
-- Check if orchestrator is running (execute after starting scheduler)
SELECT COUNT(*) as runs_last_hour, MAX(started_at) as latest
FROM algo_orchestrator_runs
WHERE started_at > NOW() - INTERVAL '1 hour';

-- Check fresh portfolio snapshots
SELECT MAX(created_at) as latest_snapshot
FROM algo_portfolio_snapshots;

-- Check recent trades
SELECT COUNT(*) as recent_trades, MAX(created_at) as latest
FROM algo_trades
WHERE created_at > NOW() - INTERVAL '24 hours';
```

## Instant Fixes

| Problem | Fix |
|---------|-----|
| Orchestrator not executing (dashboard shows no data) | `python3 scripts/trigger_orchestrator.py --run morning --mode paper` |
| AWS credential error | `scripts/refresh-aws-credentials.ps1` |
| Code fails pre-commit | `make format && make type-check` |
| Dashboard stale data | `pkill -9 python && python -m dashboard -w` |
| Positions panel and portfolio panel show different counts | Refresh materialized view: `python3 -c "from utils.db import DatabaseContext; DatabaseContext('write').execute('REFRESH MATERIALIZED VIEW algo_positions_with_risk')"` |
| Need to deploy AWS cost optimizations | `cd terraform && terraform apply -lock=false` (see AWS Cost Optimizations above) |
| Check if position data sources are in sync | Call `/api/diagnostics` endpoint to detect sync issues across algo_trades, algo_positions, and view cache |

## Non-Negotiable Rules

- ✅ Type safety: `mypy strict` enforced (pre-commit blocks all type errors)
- ✅ Code cleanliness: No `.env`, `pdb`, or `print()` in library code (pre-commit blocks)
- ✅ Data integrity: Explicit `data_unavailable` flags (no silent fallbacks)
- ✅ Safety: Circuit breakers enforce risk limits (see GOVERNANCE.md)

**All other rules, examples, and context:** See the steering docs above. This file stays thin.
