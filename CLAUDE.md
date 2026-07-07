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

## AWS Cost Optimizations

7-phase cost reduction complete: $209-211/month savings (73% reduction for dev).
- Phases 1-3: RDS Proxy, VPC Endpoints, Performance Insights (pre-existing)
- Phases 4-7: CloudWatch alarms, Lambda concurrency, data quality gates, CloudFront disable

Deploy: `cd terraform && terraform apply -lock=false`

## Orchestrator Execution

**Production:** EventBridge Scheduler runs 2x daily via `terraform/modules/services/2x-daily-orchestrator.tf`

**One-off trigger (testing/emergency only):**
```bash
python3 scripts/trigger_orchestrator.py --run morning --mode paper
```

**Check orchestrator status:**
```sql
SELECT COUNT(*) as runs_last_hour, MAX(started_at) as latest
FROM algo_orchestrator_runs
WHERE started_at > NOW() - INTERVAL '1 hour';

SELECT MAX(created_at) as latest_snapshot FROM algo_portfolio_snapshots;
```

See `steering/OPERATIONS.md` for IAM and scheduler details.

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

- Type safety: `mypy strict` enforced (pre-commit blocks all type errors)
- Code cleanliness: No `.env`, `pdb`, or `print()` in library code (pre-commit blocks)
- Data integrity: Explicit `data_unavailable` flags (no silent fallbacks)
- Safety: Circuit breakers enforce risk limits (see GOVERNANCE.md)

**All other rules, examples, and context:** See the steering docs above. This file stays thin.
