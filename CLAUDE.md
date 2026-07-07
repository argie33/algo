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

**STATUS**: Lambda deployed and callable, but EventBridge schedules not triggering (last automatic run: Jul 6 17:46 UTC).

**IMMEDIATE FIX**: 
Use GitHub Actions to enable EventBridge schedules OR manually trigger the orchestrator:
```bash
python3 scripts/trigger_orchestrator.py --run morning --mode paper
```

**ROOT CAUSE**: EventBridge Scheduler Lambda invocations are disabled/misconfigured. Terraform apply can't complete due to IAM permission constraints on S3 bucket policies.

**PERMANENT FIX**: 
1. Grant algo-developer IAM user: `s3:GetBucketPolicy`, `s3:PutBucketPolicy`, `ec2:DescribeVpcAttribute`
2. Run: `cd terraform && terraform apply -lock=false`
3. Verify: `aws scheduler list-schedules --region us-east-1 | grep algo` — check State is ENABLED

**VERIFICATION**:
- Check database: `SELECT COUNT(*) FROM algo_orchestrator_runs WHERE started_at > NOW() - INTERVAL '1 hour'`
- Check Lambda logs: `/aws/lambda/algo-algo-dev` — should show recent executions
- Check dashboard: should show fresh portfolio snapshots and scores

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
