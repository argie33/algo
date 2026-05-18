# Credential Setup - Quick Start Guide

**TL;DR:** Set PowerShell environment variables → Verify with script → Deploy

---

## 🚀 Step 1: Local Development (5 minutes)

### Option A: Interactive Setup (Recommended)

```powershell
.\scripts\setup-powershell-env.ps1
# Enter your PostgreSQL password
# Script will verify and set everything
```

### Option B: Manual Setup

```powershell
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_NAME = "stocks"
$env:DB_PASSWORD = "your_postgres_password"
```

### Option C: Permanent Setup (Save to Profile)

```powershell
.\scripts\setup-powershell-env.ps1 -DBPassword "password" -Persistent
# Restart PowerShell
# Credentials will load automatically
```

---

## ✓ Step 2: Verify Setup (1 minute)

```bash
# Run credential audit
python3 scripts/verify-credentials.py

# Or use credential validator
python3 config/credential_validator.py

# Expected: [OK] All credentials valid
```

---

## 📋 Step 3: GitHub Secrets Setup (5 minutes)

Get these values:

| Value | How to Find |
|-------|------------|
| `AWS_ACCOUNT_ID` | Your AWS account (12 digits) |
| `API_GATEWAY_URL` | From your API Gateway in AWS Console |
| `DB_SECRET_ARN` | Create below ↓ |
| `COGNITO_USER_POOL_ID` | From AWS Cognito console |
| `COGNITO_CLIENT_ID` | From Cognito app client settings |

Set them here: https://github.com/argie33/algo/settings/secrets/actions

```bash
# Verify all are set
gh secret list
```

---

## 🔑 Step 4: AWS Secrets Manager (5 minutes)

### Create RDS Secret:

```bash
aws secretsmanager create-secret \
  --name algo/db/postgres \
  --secret-string '{
    "host":"your-rds.rds.amazonaws.com",
    "port":5432,
    "username":"stocks",
    "password":"your_password",
    "dbname":"stocks"
  }'
```

### Get Secret ARN:

```bash
aws secretsmanager describe-secret \
  --secret-id algo/db/postgres | jq '.ARN'

# Copy this ARN to GitHub Secret: DB_SECRET_ARN
```

---

## 🧪 Step 5: Test Everything (2 minutes)

### Local Test:

```bash
python3 init_database.py
python3 run-all-loaders.py
python3 algo/algo_orchestrator.py --dry-run
```

### GitHub Actions Test:

```bash
git push origin main
# Watch deploy at: https://github.com/argie33/algo/actions
```

---

## 🔧 Common Issues

| Issue | Solution |
|-------|----------|
| `DB_HOST not set` | Run: `$env:DB_HOST = "localhost"` |
| `DB_PASSWORD not available` | Run: `$env:DB_PASSWORD = "your_password"` |
| `GitHub Actions fails` | Check all 5 secrets are set: `gh secret list` |
| `Lambda errors` | Check: `aws lambda get-function-configuration --function-name algo-api-dev` |
| `Can't connect to database` | Verify PostgreSQL is running, DB_HOST is correct |

---

## 📚 Full Documentation

| Document | Use Case |
|----------|----------|
| `LOCAL_CRED_SETUP.md` | Detailed local PowerShell setup |
| `CREDENTIALS_SETUP.md` | Complete technical reference |
| `CREDENTIAL_IMPLEMENTATION_CHECKLIST.md` | Implementation checklist + troubleshooting |
| `scripts/verify-credentials.py` | Audit credentials setup |
| `config/credential_validator.py` | Validate credentials at startup |

---

## 🎯 Architecture Overview

```
PowerShell Environment Variables
         ↓
Credential Manager (Python) / apiKeyService (Node.js)
         ↓
Local Dev: Direct connection
AWS: AWS Secrets Manager → Database
Lambda: Environment vars → Services
         ↓
Database / Cognito / External APIs
```

---

## ⏭️ Next Steps

1. **NOW:** `.\scripts\setup-powershell-env.ps1`
2. **THEN:** `python3 scripts/verify-credentials.py`
3. **VERIFY:** `python3 init_database.py`
4. **DEPLOY:** Set GitHub Secrets + `git push origin main`

---

For detailed info, see: **`CREDENTIAL_IMPLEMENTATION_CHECKLIST.md`**

