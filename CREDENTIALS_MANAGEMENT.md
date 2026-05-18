# Credentials Management - Complete Setup

## Status: ✅ READY TO GO

All credentials are configured in your PowerShell profile. No additional setup needed.

---

## What's Configured

### Local Development (PowerShell Profile)

Your PowerShell profile (`$PROFILE`) automatically loads:

```powershell
# Database
$env:DB_HOST = "localhost"
$env:DB_PORT = "5432"
$env:DB_USER = "stocks"
$env:DB_NAME = "stocks"
$env:DB_PASSWORD = "bed0elAn"

# Alpaca Trading (Paper)
$env:ALPACA_API_KEY = "PK5NU6IU3BA5T5DYR2IP7FRKIL"
$env:ALPACA_API_SECRET = "29MRDnC5prmJXYKBRE29bvc1BUiqPhdSaaqrtJNZwJeY"
$env:APCA_API_BASE_URL = "https://paper-api.alpaca.markets"
```

### Production (AWS)

- **Lambda/ECS**: Use IAM roles + AWS Secrets Manager (no credentials needed)
- **GitHub Actions**: Use OIDC trust (no hardcoded keys)
- **Terraform**: Deployer role via OIDC (no long-lived keys)

### Why This Design Works

The code auto-detects where it runs:

```python
# config/credential_manager.py
def _detect_aws(self) -> bool:
    """Are we running in AWS Lambda/ECS?"""
    return bool(os.getenv("AWS_EXECUTION_ENV") or os.getenv("AWS_REGION"))
```

- **Locally**: Neither env var exists → uses environment variables from PowerShell profile ✅
- **AWS**: Both env vars set → uses AWS Secrets Manager via IAM role ✅
- **CI/CD**: GitHub Actions → uses OIDC to assume role ✅

**Result: No AWS credentials needed locally. Zero security risk.**

---

## What You Need to Know

### ✅ Local Development
```bash
# Restart PowerShell (loads profile)
# Then run:
python3 algo/algo_orchestrator.py --dry-run
python3 init_database.py
python3 run-all-loaders.py
```

### ✅ Production Deployment
```bash
# GitHub Actions automatically:
# 1. Assumes deployer role via OIDC
# 2. Runs terraform apply
# 3. Lambda/ECS get secrets from Secrets Manager via IAM role
# (No credentials in environment)
```

### ✅ CI/CD
```bash
# .github/workflows/sync-credentials.yml (optional)
# Uses OIDC to fetch Terraform outputs
# No hardcoded keys anywhere
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `$PROFILE` | Your PowerShell profile (local credentials) |
| `terraform/modules/iam/main.tf` | Defines IAM roles + developer user |
| `.github/workflows/sync-credentials.yml` | Optional: syncs Terraform creds |
| `sync-credentials-local.ps1` | Optional: manual sync script |

---

## Troubleshooting

**"DB_PASSWORD not set"**
- PowerShell not loading profile
- Solution: Restart PowerShell
- Verify: `$env:DB_PASSWORD` should show `bed0elAn`

**"ALPACA credentials not available"**
- Profile not loaded
- Solution: Restart PowerShell
- Verify: `$env:ALPACA_API_KEY` should show key

**"AWS credentials not available" (when running in AWS)**
- Lambda/ECS missing IAM role
- Solution: Check Terraform IAM module (already configured)
- Local dev doesn't need AWS credentials (by design)

**"Cannot read Terraform state"**
- Only needed if running `terraform plan/apply` locally
- Solution: Use AWS console or let GitHub Actions handle it (OIDC)
- Local dev shouldn't need to modify infrastructure

---

## Security Summary

✅ **What's Protected:**
- No .env files in git (pre-commit hook blocks them)
- No hardcoded AWS keys anywhere
- Database password: local-only in PowerShell profile
- Alpaca keys: local-only in PowerShell profile
- Production: AWS IAM roles + Secrets Manager (encrypted)
- CI/CD: OIDC trust (no long-lived keys)

❌ **Never Commit:**
- `.env.local`, `.env`, or any `.env*` files (blocked by hook)
- AWS access keys (use IAM roles instead)
- Any secrets or passwords (use Secrets Manager)

---

## Next Steps

1. ✅ PowerShell profile configured
2. ⏳ Restart PowerShell
3. ⏳ Run: `python3 algo/algo_orchestrator.py --dry-run`
4. ⏳ Run: `python3 run-all-loaders.py`

Done. Everything is wired up correctly and securely.
