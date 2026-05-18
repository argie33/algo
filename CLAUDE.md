# Stock Analytics Platform

Push to `main` → auto-deploys via GitHub Actions. Watch: https://github.com/argie33/algo/actions

## Rules

1. **One loader per data source**, integrated into `run-all-loaders.py` — else delete
2. **No one-time scripts** — delete backfills, diagnostics, utilities immediately
3. **No unintegrated code** — if not in main orchestration, it doesn't exist
4. **Dependencies used or deleted** — show WHERE and WHY before adding
5. **Test expiration dates** — `@pytest.mark.skip(reason="... (2026-06-15)")` or delete when expired
6. **No mock endpoints** — real data or delete completely
7. **No .env files, hardcoded secrets, or .env.local** — use AWS Secrets Manager (see LOCAL_CRED_SETUP.md)

## Local Dev (4 Steps)

1. PostgreSQL on localhost:5432
2. Set env vars: database host/port/user/pass, Alpaca API key/secret (see credential_helper.py)
3. `python3 init_database.py`
4. `python3 run-all-loaders.py`

Test: `python3 algo/algo_orchestrator.py --mode paper --dry-run`
