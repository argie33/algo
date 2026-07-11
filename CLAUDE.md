# Project Quick Reference

**Status:** ✅ Production Ready (Session 67 - Complete orchestration consolidation)

## Start Here

1. **Local dev setup?** → `QUICKSTART_LOCAL.md`
2. **Architecture & rules?** → `steering/GOVERNANCE.md`
3. **AWS/deployment?** → `steering/OPERATIONS.md`
4. **Data loading system?** → `steering/DATA_LOADERS.md`
5. **Lambda 503 errors?** → `steering/AWS_LAMBDA_503_FIX.md`
6. **AWS billing emails & cost controls?** → `BILLING_QUICK_REFERENCE.md` (or `steering/AWS_BILLING_AND_COST_CONTROLS.md`)
7. **Troubleshooting?** → `steering/COMMON_OPERATIONS.md`

## Quick Setup

```bash
# Verify system ready
python3 scripts/diagnose_system.py

# Terminal 1: API server
python3 api-pkg/dev_server.py

# Terminal 2: Dashboard (local mode, no AWS creds needed)
python3 -m dashboard --local -w 30
```

## System Status

- **Database:** PostgreSQL, 8.5M+ prices, 4.7k scores, 10,601 watermarks
- **Last critical fixes (Session 67):** Phase 3 complete - orchestration consolidated to Step Functions (single source of truth)
- **Production:** Step Functions runs orchestrator 2x daily (morning 2:15 AM ET, evening 4:00 PM ET)

## Running Orchestrator

**Local/test:**
```bash
python3 scripts/trigger_orchestrator.py --run morning --mode paper
```

**Production:** Configured in `terraform/modules/services/2x-daily-orchestrator.tf`, runs via Step Functions (primary) + optional weekly enrichment via EventBridge.

**Check status:**
```sql
SELECT COUNT(*) as runs_last_hour, MAX(started_at) as latest
FROM algo_orchestrator_runs
WHERE started_at > NOW() - INTERVAL '1 hour';
```

## Common Fixes

| Issue | Fix |
|-------|-----|
| Dashboard "data not available" (local) | Use `python3 -m dashboard --local` - MUST use --local flag |
| Dashboard "API Errors" panel (AWS) | Check `steering/AWS_LAMBDA_503_FIX.md` - likely VPC misconfiguration |
| Dev server "connection refused" | Run both: Terminal 1: `python3 api-pkg/dev_server.py` + Terminal 2: `python3 -m dashboard --local` |
| PostgreSQL connection refused | Check DB: `python3 -c "import psycopg2; psycopg2.connect('dbname=stocks user=stocks host=localhost')"` |
| Lambda 503 errors (AWS) | Run: `bash scripts/fix-lambda-vpc.sh` then redeploy: `gh workflow run deploy-api-lambda.yml` |
| Code fails pre-commit | Run: `make format && make type-check` |
| Orchestrator not running | Check AWS Step Functions: `aws stepfunctions describe-state-machine --state-machine-arn arn:aws:states:...` or AWS EventBridge Scheduler |
| Stale data (> 4 hours) | Loaders not running - check EventBridge Scheduler + ECS logs |

## Non-Negotiable Rules

- **Type safety:** `mypy strict` enforced (pre-commit blocks all type errors)
- **Code cleanliness:** No `.env`, `pdb`, or `print()` in library code
- **Data integrity:** Explicit `data_unavailable` flags (no silent fallbacks)
- **Safety:** Circuit breakers enforce risk limits

See steering docs for architecture, policy details, and deployment procedures.
