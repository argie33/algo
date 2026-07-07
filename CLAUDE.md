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

## Orchestrator Execution

**Production scheduling is EventBridge Scheduler** (`terraform/modules/services/2x-daily-orchestrator.tf`), targeting Lambda `algo-algo-dev` directly (`lambda:InvokeFunction` via `aws_iam_role.eventbridge_scheduler`, which is unaffected by the `algo-developer` read-only IAM gaps below). Verified 2026-07-07: CloudWatch `Invocations` metric shows non-zero daily invocations continuously since 2026-06-07 — the schedule reliably fires on its own. Do NOT reintroduce a persistent local/manual scheduler loop as a "workaround" — a prior session's guidance to do exactly that led to 16 orphaned `orchestrator_scheduler.py` processes accumulating across sessions (found and killed 2026-07-07), which is itself a plausible contributor to the Lambda rate-limiting symptom seen repeatedly. `scripts/orchestrator_scheduler.py` now refuses to run a second copy (file lock), but it should only be used for a one-off manual/emergency trigger (`--once`), never left running in the background.

**For a one-off manual trigger (testing/emergency only):**
```bash
python3 scripts/orchestrator_scheduler.py --once --mode paper
```

### Manual Trigger (For Testing)
```bash
python3 scripts/trigger_orchestrator.py --run morning --mode paper
```

### Direct AWS Lambda Invocation (Raw)
```bash
aws lambda invoke \
  --function-name algo-algo-dev \
  --payload '{"source":"eventbridge-scheduler","run_identifier":"morning","execution_mode":"paper","dry_run":false}' \
  /tmp/response.json \
  --region us-east-1
```

**IAM gap (real, but narrower than previously documented here):**
- `algo-developer`'s `SchedulerReadOnly`/`EC2ReadOnly`/`S3ReadOnly` policies (`terraform/modules/iam/main.tf`) only grant read actions (`Get*`/`List*`/`Describe*`), not `scheduler:UpdateSchedule`, `s3:GetBucketPolicy`/`PutBucketPolicy`, or `ec2:DescribeVpcAttribute`. This blocks a human running `terraform apply -lock=false` locally under `algo-developer` creds from creating/updating schedules.
- It does **not** block the schedules from running: GitHub Actions applies via a separate OIDC role (`aws_iam_role.github_actions`) with full `scheduler:*`/`s3:*`/`ec2:Describe*`, and schedule execution uses yet another role (`aws_iam_role.eventbridge_scheduler`) with only `lambda:InvokeFunction`. Both are already correctly permissioned — this is why the schedules have been firing daily in production despite `algo-developer` being read-only.
- Known bug: the ARN pattern in `SchedulerReadOnly`'s resource scope is `schedule/algo*` but real EventBridge Scheduler ARNs are `schedule/<group>/<name>` (e.g. `schedule/default/algo-algo-schedule-morning-dev`), so even the read-only grant 403s in practice. Fix: change to `schedule/*/algo*`.

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
