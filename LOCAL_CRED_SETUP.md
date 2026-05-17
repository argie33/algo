# Local Development Credentials Setup

**RULE: NO .env.local files. Period.**

Use AWS Secrets Manager locally — it's the same system production uses.

---

## Why AWS Secrets Manager Locally?

- ✅ Same as production (no surprises)
- ✅ No files to accidentally commit
- ✅ Credentials stored securely (not in git)
- ✅ Set once, works forever (no per-session setup)
- ✅ One command to add/update credentials

---

## Setup (One-Time, 5 minutes)

### Step 1: Store credentials in AWS Secrets Manager

```bash
# Database credentials
aws secretsmanager create-secret \
  --name db/password \
  --secret-string "your_postgres_password"

aws secretsmanager create-secret \
  --name db/host \
  --secret-string "localhost"

aws secretsmanager create-secret \
  --name db/port \
  --secret-string "5432"

aws secretsmanager create-secret \
  --name db/user \
  --secret-string "stocks"

aws secretsmanager create-secret \
  --name db/name \
  --secret-string "stocks"

# Alpaca credentials (if using live API)
aws secretsmanager create-secret \
  --name alpaca/api-key \
  --secret-string "your_alpaca_api_key"

aws secretsmanager create-secret \
  --name alpaca/secret-key \
  --secret-string "your_alpaca_secret_key"
```

### Step 2: Verify credentials are stored

```bash
aws secretsmanager get-secret-value --secret-id db/password
```

---

## How It Works

When you run a loader or orchestrator:

1. `credential_helper.py` calls `credential_manager.get_db_credentials()`
2. `credential_manager` tries:
   - AWS Secrets Manager (✅ finds your credentials here)
   - Environment variables (fallback, not used locally)
   - Raises error if not found
3. Code runs with credentials from Secrets Manager

**No environment variables. No .env files. Just works.**

---

## For CI/GitHub Actions

Use GitHub Secrets for environment variables — production uses AWS Secrets Manager (same code path).

---

## If credentials leak

You can rotate them in AWS Secrets Manager in seconds — no code changes needed.

---

## Verify it works

```bash
python3 -c "from config.credential_helper import get_db_config; print(get_db_config())"
```

Should print your actual database config without asking for anything.
