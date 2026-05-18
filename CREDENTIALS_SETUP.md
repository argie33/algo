# Credentials Setup - Local Dev & Production

## Quick Start (Local Development)

```powershell
! powershell -ExecutionPolicy Bypass -File setup-secrets.ps1
```

This script will prompt you for:
- PostgreSQL password
- Alpaca API credentials (optional)
- Alert emails/SMS (optional)
- AWS credentials (optional, for production)

**Your credentials are stored in your PowerShell profile** (`$PROFILE`), which is:
- ✅ NOT in git (safe)
- ✅ Persistent across terminal sessions
- ✅ Local-only (never committed)

---

## Where Credentials Are Stored

### Local Development (This Machine)
- **PowerShell Profile:** `C:\Users\<your_user>\OneDrive\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1`
  - Environment variables for PostgreSQL, Alpaca, alerts
  - Loaded automatically when PowerShell starts
  - ✅ Safe—not in git

### Production (AWS)
- **GitHub Secrets:** Used in CI/CD workflows (GitHub Actions)
- **AWS Secrets Manager:** Used by running Lambda/ECS tasks
  - `algo/db/postgres` → PostgreSQL credentials
  - `algo/alpaca/paper` → Alpaca paper credentials
  - `algo/alpaca/live` → Alpaca live credentials (if used)

---

## Setup Instructions

### Option A: Local Development (Recommended for Local Dev)

1. **Run the setup script:**
   ```powershell
   ! powershell -ExecutionPolicy Bypass -File setup-secrets.ps1
   ```

2. **Close and reopen PowerShell** to load credentials

3. **Test:**
   ```bash
   python3 -c "from utils.db_connection import get_db_connection; get_db_connection(); print('✅ OK')"
   ```

### Option B: AWS Secrets Manager (Recommended for Prod)

**Prerequisites:**
- AWS CLI installed: `aws configure`
- AWS IAM user with SecretsManager permissions

**1. Create PostgreSQL Secret:**
```bash
aws secretsmanager create-secret \
  --name algo/db/postgres \
  --secret-string '{"host":"localhost","port":5432,"user":"stocks","password":"YOUR_PASSWORD","database":"stocks"}' \
  --region us-east-1
```

**2. Create Alpaca Secret (Paper):**
```bash
aws secretsmanager create-secret \
  --name algo/alpaca/paper \
  --secret-string '{"key":"YOUR_KEY","secret":"YOUR_SECRET"}' \
  --region us-east-1
```

**3. Wire GitHub Actions Secrets:**
Go to GitHub repo → Settings → Secrets and variables → Actions

Create these:
- `AWS_ACCESS_KEY_ID` → Your AWS access key
- `AWS_SECRET_ACCESS_KEY` → Your AWS secret
- `AWS_REGION` → `us-east-1`

Code automatically reads from AWS Secrets Manager when available.

---

## Credential Priority (What Gets Used)

The system checks credentials in this order:

1. **AWS Secrets Manager** (if configured)
2. **Environment variables** (from PowerShell profile or CI/CD)
3. **Local .env.local** (NOT RECOMMENDED—prevent git commits!)

Example for PostgreSQL:
```python
# Code tries these in order:
1. aws secretsmanager get_secret_value("algo/db/postgres")
2. os.environ.get("DB_PASSWORD")
3. Falls back to defaults if neither available
```

---

## Common Issues

### "Database password not available"
- PowerShell profile not loaded (restart terminal)
- AWS credentials incorrect (run `aws sts get-caller-identity`)
- PostgreSQL not running (check `localhost:5432`)

### "Alpaca credentials not available"
- Credentials not in PowerShell profile (run `setup-secrets.ps1`)
- AWS Secrets Manager not configured (use PowerShell profile for local dev)
- Paper trading: Use `ALPACA_API_KEY`, not `APCA_API_KEY_ID`

### ".env.local keeps sneaking into git"
- ✅ We don't use .env.local files anymore
- Use PowerShell profile (local) or AWS Secrets Manager (production)
- Pre-commit hooks prevent `.env` files from being committed

---

## For Team Members

**Local Setup (First Time):**
```powershell
cd C:\Users\<you>\code\algo
! powershell -ExecutionPolicy Bypass -File setup-secrets.ps1
# (restart PowerShell)
python3 init_database.py
python3 run-all-loaders.py
```

**Verify it works:**
```bash
python3 algo/algo_orchestrator.py --dry-run
```

**Credentials needed:**
- PostgreSQL password (ask project lead)
- Alpaca API key/secret (create account, optional)
- AWS credentials (if accessing production, ask lead)

---

## Files Reference

| File | Purpose |
|------|---------|
| `setup-secrets.ps1` | Interactive setup script—adds credentials to PowerShell profile |
| `.env.local.example` | Example .env.local (for reference only—don't use) |
| `LOCAL_CRED_SETUP.md` | Original setup guide (legacy, use CREDENTIALS_SETUP.md instead) |
| `config/env_loader.py` | Code that loads credentials (rejects .env.local, tries AWS then env vars) |
| `config/credential_manager.py` | Reads from AWS Secrets Manager or environment |

---

## Never Commit

These files are in `.gitignore` and should NEVER be committed:
- `.env.local` (local credentials)
- `.env` (any .env file)
- `~/.aws/credentials` (AWS credentials—use `aws configure` instead)
- PowerShell profile with secrets (personal—stays on your machine)

---

## Questions?

- **Setup not working?** Run `setup-secrets.ps1` again (it appends, so multiple runs are OK)
- **Forgotten password?** Reset PostgreSQL user password and run setup again
- **Production AWS setup?** See project lead—needs IAM permissions
