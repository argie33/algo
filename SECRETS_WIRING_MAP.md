# Complete Secrets Wiring Map - All Configuration Places

**Status:** ✅ ALL 7 GITHUB SECRETS SET  
**Date:** 2026-05-18  
**Configuration:** Complete and ready to deploy

---

## 📍 PLACE #1: GitHub Actions Secrets

**Location:** https://github.com/argie33/algo/settings/secrets/actions

**Status:** ✅ All 7 secrets configured (2026-05-18 02:19 UTC)

- AWS_ACCOUNT_ID
- RDS_PASSWORD
- ALPACA_API_KEY_ID
- ALPACA_API_SECRET_KEY
- FRED_API_KEY
- JWT_SECRET
- ALERT_EMAIL_ADDRESS

---

## 📍 PLACE #2: GitHub Workflow

**File:** `.github/workflows/deploy-all-infrastructure.yml`

Converts GitHub secrets to Terraform variables:
```yaml
env:
  TF_VAR_rds_password: ${{ secrets.RDS_PASSWORD }}
  TF_VAR_alpaca_api_key_id: ${{ secrets.ALPACA_API_KEY_ID }}
  TF_VAR_alpaca_api_secret_key: ${{ secrets.ALPACA_API_SECRET_KEY }}
  TF_VAR_jwt_secret: ${{ secrets.JWT_SECRET }}
  TF_VAR_fred_api_key: ${{ secrets.FRED_API_KEY }}
```

---

## 📍 PLACE #3: Terraform Variables

**Files:**
- `terraform/variables.tf` - Defines variables
- `terraform/modules/secrets/main.tf` - Creates secrets
- `terraform/modules/database/main.tf` - RDS configuration
- `terraform/modules/compute/main.tf` - Lambda configuration
- `terraform/modules/loaders/main.tf` - ECS configuration

**What happens:**
1. Receives TF_VAR_* from GitHub Actions
2. Creates AWS Secrets Manager entries
3. Passes ARNs to Lambda and ECS

---

## 📍 PLACE #4: AWS Secrets Manager

**Location:** AWS Console → Secrets Manager → us-east-1

**What's created:**
- `rds/password` - RDS database password
- `stocks-algo-secrets` - Contains 4 keys:
  - alpaca_api_key_id
  - alpaca_api_secret_key
  - fred_api_key
  - jwt_secret

**When:** Created during `terraform apply`

---

## 📍 PLACE #5: Lambda Functions

**Functions:**
- `stocks-api-dev` (API handler)
- `stocks-algo-dev` (Orchestrator)

**Environment Variables:**
- `DB_SECRET_ARN` - Points to rds/password secret
- `ALGO_SECRETS_ARN` - Points to stocks-algo-secrets

**At runtime:** Lambda reads Secrets Manager using these ARNs

---

## 📍 PLACE #6: ECS Task Definitions

**Tasks:**
- algo-loader-symbols
- algo-loader-prices
- algo-loader-financial
- algo-loader-signals
- algo-continuous-monitor

**Injected Secrets:**
- DB_PASSWORD (from Secrets Manager)
- APCA_API_KEY_ID (from Secrets Manager)
- APCA_API_SECRET_KEY (from Secrets Manager)

---

## 📍 PLACE #7: Local Development (Optional)

**File:** `terraform/terraform.tfvars.local` (gitignored)

Contains RDS password for local Terraform operations.

**Or via environment:**
```bash
export TF_VAR_rds_password="<password>"
export ALPACA_API_KEY="<key>"
export FRED_API_KEY="<key>"
python3 run-all-loaders.py
```

---

## 🔄 Complete Data Flow

```
GitHub Secrets (7 values)
    ↓
GitHub Actions reads secrets
    ↓ (converts to TF_VAR_*)
Terraform receives variables
    ↓ (creates resources)
AWS Secrets Manager ← stores secrets
    ↓
Lambda Functions ← gets ARNs
ECS Tasks ← gets secrets injected
RDS ← gets password
```

---

## ✅ Deployment Status

| Component | Status |
|-----------|--------|
| GitHub Secrets | ✅ SET |
| GitHub Workflow | ✅ Ready |
| Terraform Code | ✅ Ready |
| AWS Account | ✅ Ready |
| Local Config | ✅ Ready |

---

## 🚀 Next Step

```bash
git push origin main
```

GitHub Actions will automatically:
1. Read all 7 GitHub secrets
2. Run Terraform with TF_VAR_* environment variables
3. Create AWS resources with proper secret wiring
4. Auto-populate data via EventBridge

**Monitor:** https://github.com/argie33/algo/actions

---

**Status:** ✅ ALL WIRED UP - READY TO DEPLOY
