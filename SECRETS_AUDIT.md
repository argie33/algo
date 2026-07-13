# Secrets Audit Report
**Date:** 2026-07-12  
**Status:** COMPREHENSIVE AUDIT

---

## Executive Summary

| Category | Total | Status |
|----------|-------|--------|
| **GitHub Secrets** | 7 required | ⚠️ See audit below |
| **AWS Secrets Manager** | 5 managed by Terraform | ✅ Created via IaC |
| **Environment Variables** | 9 required for operations | ✅ See config/environment_validation.py |

---

## Part 1: GitHub Secrets (in this repository)

These secrets are referenced in `.github/workflows/*.yml` files and are **required for CI/CD to work**.

### Required GitHub Secrets

| Secret Name | Purpose | Used In | Status | Set? |
|---|---|---|---|---|
| `AWS_ACCOUNT_ID` | AWS account number for IAM role assumption | All deploy workflows | **CRITICAL** | ❓ |
| `GITHUB_ACTIONS_ROLE_ARN` | OIDC role ARN for AWS credential exchange | deploy-orchestrator-lambda, deploy-api-lambda, apply-aws-migrations | Optional (fallback to role name) | ❓ |
| `GITHUB_ACTIONS_ROLE_NAME` | Fallback: IAM role name if ARN not provided | Deploy workflows | Optional | ❓ |
| `ALPACA_API_KEY_ID` | Alpaca API key for paper trading | deploy-all-infrastructure.yml (Terraform TF_VAR) | **CRITICAL** for live trading | ❓ |
| `ALPACA_API_SECRET_KEY` | Alpaca API secret for paper trading | deploy-all-infrastructure.yml (Terraform TF_VAR) | **CRITICAL** for live trading | ❓ |
| `FRED_API_KEY` | Federal Reserve Economic Data API key | deploy-all-infrastructure.yml (Terraform TF_VAR) | Optional | ❓ |
| `JWT_SECRET` | JWT signing secret | deploy-all-infrastructure.yml (Terraform TF_VAR) | **CRITICAL** | ❓ |
| `ALERT_SMTP_PASSWORD` | SMTP password for email alerts | deploy-all-infrastructure.yml (Terraform TF_VAR) | Optional | ❓ |
| `ALERT_EMAIL_ADDRESS` | Recipient email for alerts | deploy-all-infrastructure.yml (Terraform TF_VAR) | Optional | ❓ |
| `RDS_MASTER_PASSWORD` | RDS database master password | deploy-all-infrastructure.yml | Optional (can be auto-generated) | ❓ |
| `TF_STATE_BUCKET` | S3 bucket for Terraform state | deploy-all-infrastructure.yml | Optional (default: stocks-terraform-state) | ❓ |
| `TF_STATE_KEY` | Terraform state key path | deploy-all-infrastructure.yml | Optional (default: stocks/terraform.tfstate) | ❓ |

### GitHub Secrets Usage Pattern

```bash
# In workflows, accessed via:
${{ secrets.AWS_ACCOUNT_ID }}
${{ secrets.ALPACA_API_KEY_ID }}

# Passed to Terraform as environment variables:
TF_VAR_alpaca_api_key_id=${{ secrets.ALPACA_API_KEY_ID }}
TF_VAR_alpaca_api_secret_key=${{ secrets.ALPACA_API_SECRET_KEY }}
```

---

## Part 2: AWS Secrets Manager Secrets

These secrets are **created and managed by Terraform** in the `terraform/modules/secrets/main.tf` module.

### AWS Secrets (Terraform-Managed)

| Secret Name | Content | Source | Status | Used For |
|---|---|---|---|---|
| `algo/alpaca` | `{APCA_API_KEY_ID, APCA_API_SECRET_KEY}` | GitHub Secrets → Terraform → Secrets Manager | ✅ Auto-created by deploy | Paper/Live Trading via Alpaca API |
| `algo/fred` | `{api_key}` | GitHub Secrets → Terraform → Secrets Manager | ✅ Auto-created by deploy | Economic data loaders |
| `algo/database` | `{host, port, dbname, username, password}` | Terraform auto-generated or GitHub Secret | ✅ Auto-created by deploy | Lambda/ECS database connections |
| `algo/jwt` | `{jwt_secret}` | GitHub Secrets → Terraform | ✅ Auto-created by deploy | API token signing |
| `algo/orchestrator` | `{orchestrator_dry_run, halt_reason, ...}` | Terraform bootstrap | ✅ Auto-created | Circuit breaker halt state |

### Secrets Manager Access

```python
# In Python code (credential_manager.py):
from config.credential_manager import get_credential_manager

mgr = get_credential_manager()

# These load from AWS Secrets Manager (in AWS Lambda/ECS)
# OR from environment variables (in local dev)
alpaca_creds = mgr.get_alpaca_credentials()  # Fetches algo/alpaca
db_creds = mgr.get_db_credentials()          # Fetches algo/database
fred_key = mgr.get_secret("algo/fred")       # Fetches algo/fred
jwt = mgr.get_secret("algo/jwt")             # Fetches algo/jwt
```

---

## Part 3: Environment Variables (Required)

These **environment variables** are validated by `algo/config/environment_validation.py` and are used:
- ✅ **In local development:** Set in your shell
- ✅ **In GitHub Actions:** Passed via workflow env or GitHub Secrets
- ✅ **In AWS Lambda:** Set in Lambda environment variables

### Required Environment Variables

| Variable | Default | Where Used | Can Load From Secrets Manager? | Status |
|---|---|---|---|---|
| `DB_HOST` | None | Database connections (local + Lambda) | Yes (DB_ENDPOINT fallback) | **CRITICAL** |
| `DB_PORT` | None | Database connections | No | **CRITICAL** |
| `DB_NAME` | None | Database connections | No | **CRITICAL** |
| `DB_USER` | None | Database connections | No | **CRITICAL** |
| `DB_PASSWORD` | None | Database connections | Yes (`algo/database` secret) | **CRITICAL** |
| `AWS_REGION` | None | AWS SDK access (Secrets Manager, CloudWatch) | No | **CRITICAL** |
| `ORCHESTRATOR_EXECUTION_MODE` | "paper" | Trading mode (paper vs live) | No | Optional |
| `ORCHESTRATOR_DRY_RUN` | "false" | Dry-run mode for testing | No | Optional |
| `APCA_API_KEY_ID` | None | Alpaca paper trading | Yes (`algo/alpaca` secret) | Optional for paper mode |
| `APCA_API_SECRET_KEY` | None | Alpaca paper trading | Yes (`algo/alpaca` secret) | Optional for paper mode |

### Local Development Setup

```bash
# Terminal 1: Start dev server with environment variables
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=stocks
export DB_USER=stocks
export DB_PASSWORD=your_local_password
export AWS_REGION=us-east-1
export ORCHESTRATOR_EXECUTION_MODE=paper

python3 api-pkg/dev_server.py
```

```bash
# Terminal 2: Run dashboard after dev_server is ready
python3 -m dashboard --local
```

---

## Part 4: Credential Loading Priority

### Local Development (Terminal 1)
```
1. Environment variables (DB_HOST, DB_PORT, etc.)
2. Credentials return as-is (no AWS access needed)
```

### AWS Lambda/ECS
```
1. AWS Secrets Manager (via get_secret_value API)
   - algo/alpaca (Alpaca credentials)
   - algo/database (RDS credentials)
   - algo/fred (FRED API key)
   - algo/jwt (JWT secret)
2. Fall back to environment variables if Secrets Manager unavailable
3. Raise ValueError if nothing found
```

---

## Part 5: Missing Secrets Checklist

### ✅ What's Definitely Set Up

- [x] AWS Secrets Manager infrastructure (created by Terraform)
- [x] Terraform automatically creates all 5 secrets from GitHub Secrets
- [x] Database credentials managed via `DB_SECRET_ARN` in Lambda
- [x] Credential manager with caching and TTL-based expiration (5 min)
- [x] Environment validation at Lambda startup (pre-commit checks in CI)

### ❌ What You Need to Verify/Set

**GitHub Secrets (required for CI/CD):**
1. [ ] `AWS_ACCOUNT_ID` — Get from `aws sts get-caller-identity`
2. [ ] `GITHUB_ACTIONS_ROLE_ARN` — OR `GITHUB_ACTIONS_ROLE_NAME`
3. [ ] `ALPACA_API_KEY_ID` — Get from Alpaca dashboard
4. [ ] `ALPACA_API_SECRET_KEY` — Get from Alpaca dashboard
5. [ ] `JWT_SECRET` — Can auto-generate via Terraform (optional)
6. [ ] `FRED_API_KEY` — Optional, get from Federal Reserve website
7. [ ] `ALERT_SMTP_PASSWORD` — Optional, for email alerts
8. [ ] `ALERT_EMAIL_ADDRESS` — Optional, for email alerts
9. [ ] `RDS_MASTER_PASSWORD` — Optional (Terraform generates if missing)

**Local Development (required to run):**
1. [ ] `DB_HOST` — localhost (if using local Postgres)
2. [ ] `DB_PORT` — 5432
3. [ ] `DB_NAME` — stocks
4. [ ] `DB_USER` — stocks
5. [ ] `DB_PASSWORD` — Local database password
6. [ ] `AWS_REGION` — us-east-1

**AWS Secrets Manager (auto-created by Terraform from GitHub Secrets):**
1. ✅ `algo/alpaca` — Created from ALPACA_API_KEY_ID + ALPACA_API_SECRET_KEY
2. ✅ `algo/database` — Created from RDS credentials
3. ✅ `algo/fred` — Created from FRED_API_KEY
4. ✅ `algo/jwt` — Created from JWT_SECRET
5. ✅ `algo/orchestrator` — Created by Terraform bootstrap

---

## Part 6: How to Set GitHub Secrets

### Get Your AWS Account ID
```bash
aws sts get-caller-identity
# Output: Account ID is the 12-digit number
```

### Get Your Alpaca Credentials
1. Go to https://alpaca.markets
2. Dashboard → API Keys
3. Copy Key ID and Secret Key

### Set GitHub Secrets
```bash
# Via GitHub CLI
gh secret set AWS_ACCOUNT_ID --body "123456789012"
gh secret set ALPACA_API_KEY_ID --body "your-key-id"
gh secret set ALPACA_API_SECRET_KEY --body "your-secret-key"
gh secret set GITHUB_ACTIONS_ROLE_ARN --body "arn:aws:iam::123456789012:role/algo-svc-github-actions-dev"
gh secret set JWT_SECRET --body "$(openssl rand -base64 32)"
```

Or via GitHub Web UI:
- https://github.com/YOUR_ORG/YOUR_REPO/settings/secrets/actions
- Click "New repository secret"
- Add each secret name and value

---

## Part 7: Verification Checklist

### Pre-Deployment
```bash
# Check environment variables (local dev)
python3 -c "from algo.config.environment_validation import EnvironmentValidator; print(EnvironmentValidator.get_status())"
# Should show: required_ok=True, missing_required=[]

# Check credential manager can load secrets
python3 config/credential_manager.py
# Should show: [OK] DB credentials loaded, [OK] Alpaca credentials loaded (or OK if not live trading)
```

### Post-Deployment
```bash
# Check AWS Secrets Manager
aws secretsmanager list-secrets --region us-east-1 --query 'SecretList[*].[Name,LastAccessedDate]'
# Should list: algo/alpaca, algo/database, algo/fred, algo/jwt, algo/orchestrator

# Check Lambda environment variables
aws lambda get-function-configuration --function-name algo-orchestrator-dev \
  --query 'Environment.Variables' | head -20
# Should show: DB_HOST, DB_PORT, DB_NAME, DB_USER, AWS_REGION, etc.
```

---

## Part 8: Security Best Practices

1. **Never commit secrets** — All secrets loaded from:
   - GitHub Secrets (CI/CD only)
   - AWS Secrets Manager (Lambda/ECS runtime)
   - Environment variables (local dev only)

2. **Rotate secrets regularly** — Secrets Manager TTL is 5 minutes:
   ```python
   CREDENTIAL_CACHE_TTL_SECONDS = 300  # Credentials re-fetched every 5 min
   ```

3. **Use IAM roles, not keys** — Lambda uses OIDC to assume roles (no long-lived keys)

4. **Monitor credential usage** — CloudWatch metrics:
   - `AlpacaCredentialsInvalidated` — When Alpaca returns 401
   - Check `CloudWatch → Logs → /aws/lambda/` for credential errors

5. **Database security**:
   - RDS password rotated by Secrets Manager (7-day recovery window)
   - Lambda uses RDS Proxy for connection pooling
   - Database SSL mode: `require` (production)

---

## FAQ

**Q: Do I need to manually create AWS Secrets Manager secrets?**  
A: No. Terraform creates all 5 secrets automatically when you deploy. They're created from GitHub Secrets → Terraform variables → Secrets Manager.

**Q: What if I want to use Alpaca live trading credentials?**  
A: Set `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY` GitHub Secrets with live credentials, then set `alpaca_paper_trading=false` in `terraform/dev.tfvars`.

**Q: Can I run locally without AWS?**  
A: Yes. Set environment variables locally (DB_HOST, DB_PORT, etc.) and the credential manager will use those instead of AWS Secrets Manager.

**Q: What if a secret gets leaked?**  
A: 
1. Immediately rotate the secret in Secrets Manager (7-day recovery window)
2. Update GitHub Secret with new value
3. Wait 5 minutes for Lambda to re-fetch (TTL expiration)
4. Check CloudWatch logs for any unauthorized access

**Q: How do I test if secrets are loaded correctly?**  
A: Run the diagnostic script:
   ```bash
   python3 scripts/diagnose_system.py
   ```
   It will check DB connection, Alpaca credentials, FRED API, etc.

---

## Related Documentation

- **Credential Manager:** `config/credential_manager.py`
- **Environment Validation:** `algo/config/environment_validation.py`
- **Secrets Terraform Module:** `terraform/modules/secrets/main.tf`
- **GitHub Workflows:** `.github/workflows/deploy-all-infrastructure.yml`
- **AWS Deployment:** `steering/OPERATIONS.md`
- **Quick Reference:** `CLAUDE.md` (project instructions)
