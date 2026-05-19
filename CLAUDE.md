# Stock Analytics Platform

**Env vars:** `DB_HOST=localhost DB_PORT=5432 DB_NAME=stocks DB_USER=stocks DB_PASSWORD=stocks`  
**Add:** `APCA_API_KEY_ID APCA_API_SECRET_KEY FRED_API_KEY` (all optional, env or GitHub Secrets)

**Run:** `python3 init_database.py && python3 run-all-loaders.py && python3 algo/algo_orchestrator.py --dry-run`

**Test:** `python3 -m pytest tests/ -v`  
**Verify creds:** `python3 config/credential_validator.py`

**GitHub Secrets:** APCA_API_KEY_ID, APCA_API_SECRET_KEY, AWS_ACCOUNT_ID, AWS_ROLE_TO_ASSUME, AWS_REGION, FRED_API_KEY  
**AWS Secrets Manager:** algo/alpaca, algo/database, algo/fred (JSON format)
