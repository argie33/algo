# Credential Management Audit - 2026-05-09

## Summary
- **Total credential references**: 200+ across ~90 Python files
- **Primary issue**: Direct `os.getenv()` scattered everywhere + empty string defaults
- **Critical risk**: DB_PASSWORD defaults to empty string (allows connection bypass)

## Credentials Found

### 1. Database (DB_PASSWORD) - CRITICAL
- **Usage**: ~180 files reference DB_PASSWORD
- **Current pattern**: `os.getenv("DB_PASSWORD", "")` with empty string default
- **Risk**: Connection attempts with empty password succeeds if DB allows
- **Status**: Some places already use `DB_SECRET_ARN` (via Secrets Manager) — inconsistent

### 2. Alpaca Trading API (2 variants)
- **APCA_API_KEY_ID** + **APCA_API_SECRET_KEY** (preferred)
  - Used in: algo_config.py, algo_orchestrator.py, algo_trade_executor.py, ~20 others
  - No defaults (good)
- **ALPACA_API_KEY** + **ALPACA_SECRET_KEY** (legacy)
  - Used in: data_source_router.py, loadmultisource_ohlcv.py, loadalpacaportfolio.py
  - Falls back between variants with `or`

### 3. Email/SMS Alerts
- **ALERT_SMTP_PASSWORD** (algo_alerts.py:43) — default ""
- **SMTP_PASSWORD** (safeguard_alerts.py:161) — default ""
- **TWILIO_AUTH_TOKEN** (algo_alerts.py:53, safeguard_alerts.py:263) — default ""
- Risk: Low (only blocks alerts if missing, doesn't bypass anything)

### 4. AWS Secrets Manager (Good Practice - Already Exists)
- **DB_SECRET_ARN** (loadalpacaportfolio.py:48)
  - Used in lambda_function.py:28 to fetch DB credentials
  - Shows Lambda already knows the pattern
  - **Not used everywhere** — inconsistency between Lambda and ECS tasks

## Top Issues (Priority Order)

1. **DB_PASSWORD empty default** — Remove default entirely, fail fast if missing
2. **200+ scattered credential loads** — Create credential_manager.py singleton
3. **Inconsistent Secrets Manager usage** — Use DB_SECRET_ARN everywhere in AWS, env vars only for local
4. **Alpaca key variants** — Consolidate to APCA_API_* everywhere
5. **No credential rotation** — Will require Lambda + Secrets Manager rotation
6. **Credentials in error logs** — Need log filter to mask secrets

## Files Needing Changes

**High priority (infrastructure/config):**
- `algo_config.py` — centralized credential loading (update to use credential_manager)
- `optimal_loader.py` — bulk loaders, 150+ credential references
- `lambda_function.py` — already uses Secrets Manager, can be template

**All loader files** (~50 files):
- loadpricedaily.py, loadbuyselldaily.py, etc.
- Change from direct `os.getenv("DB_PASSWORD", "")` to credential manager

**Test/utility files** (~20):
- test_*.py, backfill_*.py, setup.py
- Migrate to credential manager or mark as test-only

## Secrets to Create in AWS Secrets Manager

```json
{
  "db/username": "stocks",
  "db/password": "*** (actual password)",
  "alpaca/key": "*** (actual key)",
  "alpaca/secret": "*** (actual secret)",
  "smtp/password": "*** (actual password)",
  "twilio/token": "*** (actual token)"
}
```

## Implementation Plan

1. **Create credential_manager.py** — Centralized fetcher
2. **Update lambda_function.py** → Already does this, use as template
3. **Update algo_config.py** → Call credential_manager instead of os.getenv
4. **Create logging_filters.py** → Mask credentials in logs
5. **Update all loaders** → Use credential_manager.get_password() instead of os.getenv
6. **Terraform changes** → Add Secrets Manager resources, update IAM roles
7. **Test locally** → .env.local still works, .env vars override for testing
8. **Deploy** → Rotate initial passwords, enable Secrets Manager rotation Lambda

## Timeline
- Critical: Credential manager + remove DB_PASSWORD defaults (today)
- Important: Secrets Manager integration + log masking (this week)
- Optional: Rotation Lambda (next iteration)
