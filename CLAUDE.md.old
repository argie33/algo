# Stock Analytics Platform — Live Paper Trading Ready

## Credentials (All Rotated 2026-05-19)
**GitHub Secrets** (CI/CD): `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`, `FRED_API_KEY`, AWS keys, DB creds
**AWS Secrets Manager** (Lambda): `algo/alpaca`, `algo/fred`, `algo/database` (JSON format)
**Local dev**: Set via PowerShell profile: `$env:DB_HOST=localhost; $env:DB_PASSWORD=stocks`

## Deployment to AWS
1. `.\sync-secrets-to-aws.ps1` (one-time: copy GitHub Secrets → AWS)
2. `git push origin main` (triggers CI/CD deployment)
3. Monitor `.github/workflows/deploy-code.yml` for completion

## Run Locally
**Setup:** `python3 init_database.py && python3 run-all-loaders.py`
**Dry run:** `python3 algo/algo_orchestrator.py --dry-run`
**Live trading:** `ORCHESTRATOR_DRY_RUN=false python3 algo/algo_orchestrator.py`

## Test
`python3 -m pytest tests/ -v` (282 passing)
`python3 config/credential_validator.py`

See `LIVE_TRADING_CHECKLIST.md` for full pre-market deployment steps.
