# Project Quick Reference

**Status:** ✅ Production Ready (Session 59 - Watermark Pipeline Fixed)

## Start Here

1. **Local dev setup?** → `QUICKSTART_LOCAL.md`
2. **Architecture & rules?** → `steering/GOVERNANCE.md`
3. **AWS/deployment?** → `steering/OPERATIONS.md`
4. **Data loading system?** → `steering/DATA_LOADERS.md`
5. **Troubleshooting?** → `steering/COMMON_OPERATIONS.md`

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
- **Last critical fixes (Session 59):** Watermark pipeline rebuilt, OptimalLoader corrected, price loader batch fixed
- **Production:** EventBridge Scheduler runs orchestrator 2x daily

## Running Orchestrator

**Local/test:**
```bash
python3 scripts/trigger_orchestrator.py --run morning --mode paper
```

**Production:** Configured in `terraform/modules/services/2x-daily-orchestrator.tf`, runs via EventBridge Scheduler.

**Check status:**
```sql
SELECT COUNT(*) as runs_last_hour, MAX(started_at) as latest
FROM algo_orchestrator_runs
WHERE started_at > NOW() - INTERVAL '1 hour';
```

## Common Fixes

| Issue | Fix |
|-------|-----|
| Dashboard shows "data not available" | Use `python3 -m dashboard --local` (need `--local` flag) |
| Dev server connection refused | Run `python3 api-pkg/dev_server.py` in another terminal |
| PostgreSQL connection refused | Check DB running: `psql -U stocks stocks -c "SELECT 1"` |
| Code fails pre-commit | Run `make format && make type-check` |
| AWS credential error | Set `COGNITO_USER_POOL_ID` and `COGNITO_CLIENT_ID` (see `steering/OPERATIONS.md`) |
| Orchestrator not running in AWS | Check scheduler: `aws events describe-rule --name algo-orchestrator-2x-daily` |
| Positions/portfolio mismatch | Refresh: `REFRESH MATERIALIZED VIEW algo_positions_with_risk` |

## Non-Negotiable Rules

- **Type safety:** `mypy strict` enforced (pre-commit blocks all type errors)
- **Code cleanliness:** No `.env`, `pdb`, or `print()` in library code
- **Data integrity:** Explicit `data_unavailable` flags (no silent fallbacks)
- **Safety:** Circuit breakers enforce risk limits

See steering docs for architecture, policy details, and deployment procedures.
