# Project Quick Reference

**Status:** ✅ Production Ready for Integration Testing (Session 9 Complete - 26 Fixes)

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

## Running Dashboard (Session 59)

**Local Development Mode** (Recommended - No AWS credentials needed)
```bash
# Terminal 1: Start API dev server
python3 api-pkg/dev_server.py

# Terminal 2: Start dashboard in local mode
python3 -m dashboard --local -w 30
```

See `QUICKSTART_LOCAL.md` for complete setup, troubleshooting, and examples.

**AWS Production Mode**  
Requires Cognito credentials configured. See `steering/OPERATIONS.md` for setup.

## System Verification (Session 59)

**Before running locally:**
```bash
# Diagnose system state
python3 scripts/diagnose_system.py

# Expected output: All checks PASS
# - Environment configured
# - Database has data
# - Dev server can start
# - Dashboard fetchers load
```

**To run the system:**
```bash
# Terminal 1: API dev server
python3 api-pkg/dev_server.py

# Terminal 2: Dashboard
python3 -m dashboard --local -w 30
```

See `QUICKSTART_LOCAL.md` for complete instructions.

## Instant Fixes

| Problem | Fix |
|---------|-----|
| Dashboard shows "data not available" | Use `python3 -m dashboard --local` (need --local flag for dev) |
| Can't connect to dev server | Check `python3 api-pkg/dev_server.py` is running in another terminal |
| Database connection refused | Check PostgreSQL is running (`psql -U stocks stocks -c "SELECT 1"`) |
| Verify system is working | `python3 scripts/diagnose_system.py` |
| Code fails pre-commit | `make format && make type-check` |
| AWS credential error | Requires COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID set (see OPERATIONS.md) |
| Orchestrator not running in AWS | Check EventBridge Scheduler is enabled: `aws events describe-rule --name algo-orchestrator-2x-daily` |
| Positions/portfolio count mismatch | Refresh view: `REFRESH MATERIALIZED VIEW algo_positions_with_risk` |

## Non-Negotiable Rules

- Type safety: `mypy strict` enforced (pre-commit blocks all type errors)
- Code cleanliness: No `.env`, `pdb`, or `print()` in library code (pre-commit blocks)
- Data integrity: Explicit `data_unavailable` flags (no silent fallbacks)
- Safety: Circuit breakers enforce risk limits (see GOVERNANCE.md)

**All other rules, examples, and context:** See the steering docs above. This file stays thin.
