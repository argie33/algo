# Local Development Credential Setup

This guide explains how to set up credentials for running the system locally (loaders, orchestrator, tests) using PowerShell on Windows.

**📌 Important:** Always set credentials BEFORE running any code. Never use `.env` files — credentials must be environment variables.

## Prerequisites

- PostgreSQL running on `localhost:5432`
- Python 3.11+
- PowerShell (Windows) or Bash (macOS/Linux)
- Alpaca API account (optional - for paper trading)
- AWS account with Secrets Manager access (optional - for production config)

---

## Option 1: PowerShell Environment Variables (Simplest for Local Dev)

### Step 1: Open PowerShell as Administrator

```powershell
# Open Windows Terminal as Administrator
# Or: Right-click PowerShell → "Run as administrator"
```

### Step 2: Set Database Credentials (REQUIRED)

```powershell
# Database connection - REQUIRED, no defaults
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_NAME = "stocks"
$env:DB_PASSWORD = "your_postgres_password"  # ⚠️ REQUIRED - set your actual password
```

### Step 3: Set Alpaca API Credentials (OPTIONAL - for paper/live trading)

```powershell
# Paper trading mode (recommended for testing)
$env:APCA_API_KEY_ID = "your_alpaca_paper_key"
$env:APCA_API_SECRET_KEY = "your_alpaca_paper_secret"
$env:APCA_API_BASE_URL = "https://paper-api.alpaca.markets"

# Live trading mode (use only in production after thorough testing)
# $env:APCA_API_BASE_URL = "https://api.alpaca.markets"
```

### Step 4: (Optional) Set AWS Credentials for Secrets Manager

If you want to access AWS Secrets Manager from local dev:

```powershell
# Configure AWS CLI with your credentials
aws configure

# OR set environment variables directly
$env:AWS_ACCESS_KEY_ID = "your_aws_access_key"
$env:AWS_SECRET_ACCESS_KEY = "your_aws_secret_key"
$env:AWS_REGION = "us-east-1"
```

### Step 5: Verify Credentials Are Set

```powershell
# Check all required database credentials
Write-Host "DB_HOST: $env:DB_HOST"
Write-Host "DB_PORT: $env:DB_PORT"
Write-Host "DB_USER: $env:DB_USER"
Write-Host "DB_NAME: $env:DB_NAME"
Write-Host "DB_PASSWORD: $(if ($env:DB_PASSWORD) { '✓ SET' } else { '✗ NOT SET' })"

# Check optional Alpaca credentials
Write-Host "Alpaca Key: $(if ($env:APCA_API_KEY_ID) { '✓ SET' } else { '✗ NOT SET' })"
```

### Step 6: Run the Application

```powershell
# Initialize database (one time)
python3 init_database.py

# Run all loaders
python3 run-all-loaders.py

# Test the orchestrator (dry run - no trades)
python3 algo/algo_orchestrator.py --dry-run

# Paper trading mode
python3 algo/algo_orchestrator.py --mode paper
```

---

## Option 2: Persistent PowerShell Profile (Recommended)

To avoid re-entering credentials every time you open PowerShell:

### Step 1: Create PowerShell Profile Script

```powershell
# Find your profile location
$PROFILE

# Create or edit the profile file (e.g., C:\Users\YourName\Documents\PowerShell\profile.ps1)
notepad $PROFILE

# Or create it if it doesn't exist
if (!(Test-Path -Path $PROFILE)) { New-Item -ItemType File -Path $PROFILE -Force }
```

### Step 2: Add Credentials to Profile

Add this to your `$PROFILE` file:

```powershell
# ============================================================
# Development Credentials - Stock Analytics Platform
# ============================================================
# ⚠️ WARNING: This file contains credentials
# Ensure it has restricted permissions (owner read/write only)
# Never commit to git - add to .gitignore

# Database (REQUIRED)
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_NAME = "stocks"
$env:DB_PASSWORD = "your_postgres_password"  # ⚠️ REPLACE WITH YOUR PASSWORD

# Alpaca API (OPTIONAL - for trading)
$env:APCA_API_KEY_ID = "your_alpaca_key"
$env:APCA_API_SECRET_KEY = "your_alpaca_secret"
$env:APCA_API_BASE_URL = "https://paper-api.alpaca.markets"

# AWS (OPTIONAL - for accessing production Secrets Manager)
# Uncomment if using AWS Secrets Manager locally
# $env:AWS_ACCESS_KEY_ID = "your_key"
# $env:AWS_SECRET_ACCESS_KEY = "your_secret"
# $env:AWS_REGION = "us-east-1"

Write-Host "✓ Development credentials loaded" -ForegroundColor Green
```

### Step 3: Protect the Profile File (Windows)

```powershell
# Restrict profile to owner only (Windows NTFS ACL)
icacls $PROFILE /inheritance:r /grant:r "$env:username:(F)"
Write-Host "✓ Profile permissions set to owner-only"
```

### Step 4: Reload Profile

```powershell
# Restart PowerShell or reload profile
. $PROFILE
```

---

## Option 3: AWS Secrets Manager (Recommended for Teams/Production Simulation)

If you want to test production credential flow locally:

### Step 1: Create Secret in AWS Secrets Manager

```powershell
# One-time setup - creates the secret
aws secretsmanager create-secret `
  --name algo/db/postgres `
  --secret-string '{
    "host":"localhost",
    "port":5432,
    "username":"stocks",
    "password":"your_postgres_password",
    "dbname":"stocks"
  }' `
  --region us-east-1
```

### Step 2: Set AWS Credentials Locally

```powershell
# Configure AWS CLI with your credentials
aws configure

# Enter your AWS access key ID, secret access key, default region, and output format
```

### Step 3: Run Code

The system will automatically fetch credentials from AWS Secrets Manager:

```powershell
# If AWS_REGION is set, credential_manager.py will fetch from Secrets Manager
$env:AWS_REGION = "us-east-1"

# Run any script - credentials will be fetched automatically
python3 run-all-loaders.py

# Verify it's using Secrets Manager by checking logs
# Should show: "Credentials loaded from AWS Secrets Manager"
```

---

## Testing Credentials

### Test Database Connection

```powershell
python3 config/credential_manager.py
```

Expected output:
```
[OK] DB credentials loaded
[OK] Alpaca credentials loaded (or [WARN] not configured)
```

Or test directly:

```powershell
python3 -c "
from config.credential_manager import get_db_credentials
creds = get_db_credentials()
print(f'Database: {creds[\"host\"]}:{creds[\"port\"]}/{creds[\"database\"]}')
print(f'User: {creds[\"user\"]}')
print('✓ Connection successful')
"
```

### Test One Loader

```powershell
# Run a simple loader to verify database connectivity
python3 loaders/load_stock_symbols.py

# Should complete without errors
```

### Test Orchestrator (Dry Run)

```powershell
# Test the trading algorithm in dry-run mode (no real trades)
python3 algo/algo_orchestrator.py --dry-run

# Or paper trading mode (simulated trades, no money)
python3 algo/algo_orchestrator.py --mode paper
```

---

## Troubleshooting

### "Database password not available"

```powershell
# Check if DB_PASSWORD is set
if ($env:DB_PASSWORD) {
    Write-Host "✓ DB_PASSWORD is set"
} else {
    Write-Host "✗ DB_PASSWORD is NOT set - set it with:"
    Write-Host '$env:DB_PASSWORD = "your_password"'
}

# Verify with credential manager
python3 -c "from config.credential_manager import get_db_credentials; print(get_db_credentials())"
```

### "Connection refused" to Database

```powershell
# Check if PostgreSQL is running
Get-Service | Where-Object { $_.Name -like "*postgres*" }

# If not running, start it:
# On Windows: Start PostgreSQL service in Services.msc

# Verify connection parameters
Write-Host "DB_HOST: $env:DB_HOST"
Write-Host "DB_PORT: $env:DB_PORT"
Write-Host "DB_USER: $env:DB_USER"

# Test connection with psql
psql -h $env:DB_HOST -U $env:DB_USER -d $env:DB_NAME
```

### "Alpaca API credentials not configured"

```powershell
# This is OK for paper trading with mock data
# But if you want to use Alpaca, set:
$env:APCA_API_KEY_ID = "your_key"
$env:APCA_API_SECRET_KEY = "your_secret"

# Verify
python3 -c "from config.credential_manager import get_alpaca_credentials; print(get_alpaca_credentials())"
```

### "Could not fetch from Secrets Manager"

```powershell
# This is OK if you're not using AWS locally
# If you want to test AWS Secrets Manager:

# 1. Configure AWS
aws configure

# 2. Create the secret
aws secretsmanager create-secret --name algo/db/postgres --secret-string '...'

# 3. Test access
aws secretsmanager get-secret-value --secret-id algo/db/postgres
```

---

## Security Best Practices

✅ **DO:**
- Use environment variables for credentials
- Store passwords in AWS Secrets Manager (production)
- Use separate credentials for dev/test/prod
- Regularly rotate database passwords
- Keep PowerShell profile permissions restricted (`icacls ...`)

❌ **DON'T:**
- Commit credentials to git
- Use `.env` files (not supported)
- Hardcode passwords in code
- Share AWS access keys
- Use the same password for dev and production

---

## Next Steps

1. **Set database credentials** using one of the options above
2. **Initialize the database:** `python3 init_database.py`
3. **Load initial data:** `python3 run-all-loaders.py`
4. **Test the system:** `python3 algo/algo_orchestrator.py --dry-run`
5. **For production:** See `CREDENTIALS_SETUP.md` for GitHub Secrets & AWS setup

---

## Additional Resources

- **Comprehensive guide:** See `CREDENTIALS_SETUP.md` for complete pipeline docs
- **Credential manager code:** `config/credential_manager.py`
- **Validation script:** `config/credential_validator.py`
- **Troubleshooting guide:** See `troubleshooting-guide.md`
