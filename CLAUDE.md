# Project Quick Reference

**Status:** ✅ Production Ready (Session 89 - Dashboard startup fixes, all systems operational)

## Start Here

1. **Dashboard "data not available"?** → `DASHBOARD_TROUBLESHOOTING.md` (MUST USE --local FLAG)
2. **Local dev setup?** → `QUICKSTART_LOCAL.md`
3. **Architecture & rules?** → `steering/GOVERNANCE.md`
4. **AWS/deployment?** → `steering/OPERATIONS.md`
5. **Data loading system?** → `steering/DATA_LOADERS.md`
6. **Lambda 503 errors?** → `steering/AWS_LAMBDA_503_FIX.md`
7. **AWS billing emails & cost controls?** → `BILLING_QUICK_REFERENCE.md` (or `steering/AWS_BILLING_AND_COST_CONTROLS.md`)
8. **Troubleshooting?** → `steering/COMMON_OPERATIONS.md`

## Quick Setup (LOCAL DEVELOPMENT)

**CRITICAL: Start dev_server FIRST, then dashboard. Do NOT run them in reverse order.**

```bash
# Verify system ready
python3 scripts/diagnose_system.py

# TERMINAL 1: Start API dev server
python3 api-pkg/dev_server.py
# Wait for: "[OK] DEV Server running on http://localhost:3001"

# TERMINAL 2: Start dashboard (ONLY after Terminal 1 is ready)
python3 -m dashboard --local -w 30
# Must use --local flag! Without it, dashboard tries AWS Lambda (requires Cognito auth)
```

**Why two terminals?**
- Terminal 1 keeps dev_server running
- Terminal 2 runs the dashboard and updates live
- If one crashes, you can restart it without losing the other

**Most Common Mistake:** Running dashboard without dev_server or without --local flag

## System Status

- **Database:** PostgreSQL, 8.6M+ prices, fresh data as of today
- **Dashboard:** All 26 fetchers working (100%), all 9 API endpoints responding
- **Circuit Breaker:** Improved to handle startup failures gracefully (threshold 5, not 3)
- **Dev Server:** Startup validation added - fails fast with clear instructions if not running
- **Production Orchestrator:** Step Functions runs 2x daily (morning 2:15 AM ET, evening 4:00 PM ET)

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
