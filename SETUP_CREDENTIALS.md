# Complete Credential Setup - Executable Guide

**Status:** Local ✅ | GitHub ⏳ | AWS ⏳ | End-to-End ⏳

This guide walks you through executing the complete credential setup. All three layers must be configured for end-to-end functionality.

---

## Layer 1: Local Development (ALREADY DONE ✅)

Your PowerShell profile is configured with:
- DB_HOST, DB_PASSWORD, ALPACA credentials

**Verify:**
```bash
python3 test_credentials_pipeline.py
```

**Status:** ✅ WORKING

---

## Layer 2: GitHub Secrets (YOUR ACTION - 5 MIN)

### Option A: Interactive Setup (Recommended)

```bash
# On macOS/Linux:
bash scripts/setup-github-secrets.sh

# On Windows (WSL or Git Bash):
bash scripts/setup-github-secrets.sh
```

The script will prompt you for:
1. AWS_ACCOUNT_ID (12-digit number)
2. API_GATEWAY_URL (https://...)
3. DB_SECRET_ARN (get from Step 3 below)
4. COGNITO_USER_POOL_ID (us-east-1_...)
5. COGNITO_CLIENT_ID (alphanumeric)

### Option B: Manual Setup

Go to: https://github.com/argie33/algo/settings/secrets/actions

Create these 5 secrets (values TBD in Step 3):
- `AWS_ACCOUNT_ID`
- `API_GATEWAY_URL`
- `DB_SECRET_ARN`
- `COGNITO_USER_POOL_ID`
- `COGNITO_CLIENT_ID`

### Verify:
```bash
gh secret list
```

Should show all 5 secrets ✓

---

## Layer 3: AWS Secrets Manager (YOUR ACTION - 5 MIN)

### Create RDS Secret

```bash
# On macOS/Linux or WSL:
bash scripts/setup-aws-secrets.sh

# On Windows PowerShell:
bash scripts/setup-aws-secrets.sh
```

The script will:
1. Ask for RDS endpoint, port, username, password, database
2. Create secret in AWS Secrets Manager
3. Output the SECRET ARN

**Copy this ARN and paste it into GitHub Secret `DB_SECRET_ARN`**

### Manual Alternative:

```bash
aws secretsmanager create-secret \
  --name algo/db/postgres \
  --secret-string '{
    "host":"your-rds-endpoint.rds.amazonaws.com",
    "port":5432,
    "username":"stocks",
    "password":"your_password",
    "dbname":"stocks"
  }'

# Get ARN:
aws secretsmanager describe-secret --secret-id algo/db/postgres | jq '.ARN'
```

### Verify:
```bash
aws secretsmanager get-secret-value --secret-id algo/db/postgres | jq '.SecretString'
```

Should show JSON with host, port, username, password, dbname ✓

---

## Layer 4: Verify Complete Pipeline

Run the verification script to check all three layers:

```bash
# On macOS/Linux or WSL:
bash scripts/verify-complete-pipeline.sh

# On Windows PowerShell (requires bash available):
bash scripts/verify-complete-pipeline.sh
```

This checks:
1. ✓ PowerShell environment variables
2. ✓ Python credential manager
3. ✓ GitHub Secrets configured
4. ✓ AWS Secrets Manager accessible
5. ✓ Lambda environment variables

**Expected Result:**
```
[OK] CREDENTIAL PIPELINE VERIFIED
Passed: 10+
Failed: 0
```

---

## Layer 5: Deploy to Production

Once all layers are verified:

```bash
git push origin main
```

GitHub Actions will automatically:
1. Assume OIDC role using AWS_ACCOUNT_ID
2. Deploy Terraform with all secrets
3. Update Lambda functions
4. Set environment variables in Lambda
5. Initialize database

**Watch the deployment:**
https://github.com/argie33/algo/actions

---

## Execution Sequence

**Step 1 (5 min):**
```bash
bash scripts/setup-github-secrets.sh
# Enter: AWS_ACCOUNT_ID, API_GATEWAY_URL, COGNITO IDs
# DB_SECRET_ARN: leave blank for now
```

**Step 2 (5 min):**
```bash
bash scripts/setup-aws-secrets.sh
# This creates the RDS secret and outputs ARN
# Copy the ARN
```

**Step 3 (1 min):**
```bash
# Go to GitHub Secrets and add DB_SECRET_ARN
# Or re-run setup-github-secrets.sh with the ARN
gh secret set DB_SECRET_ARN --body "arn:aws:secretsmanager:..."
```

**Step 4 (1 min):**
```bash
bash scripts/verify-complete-pipeline.sh
# Verify all checks pass
```

**Step 5 (automatic):**
```bash
git push origin main
# GitHub Actions handles the rest
```

---

## Troubleshooting

### "gh CLI not found"
Install: https://github.com/cli/cli#installation

### "AWS CLI not found"
Install: https://aws.amazon.com/cli/

### "AWS credentials not configured"
Run: `aws configure` or set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`

### "Secret already exists"
The setup-aws-secrets.sh script will update it automatically

### "gh CLI not authenticated"
Run: `gh auth login`

### Verification fails
Check each layer individually:
```bash
python3 test_credentials_pipeline.py        # Local
gh secret list                              # GitHub
aws secretsmanager get-secret-value ...     # AWS
```

---

## Complete Checklist

- [ ] Step 1: bash scripts/setup-github-secrets.sh
- [ ] Step 2: bash scripts/setup-aws-secrets.sh
- [ ] Step 3: gh secret set DB_SECRET_ARN with ARN from Step 2
- [ ] Step 4: bash scripts/verify-complete-pipeline.sh
- [ ] Step 5: git push origin main
- [ ] Verify: Watch deployment at GitHub Actions
- [ ] Done: All three layers wired and working

---

## What Gets Wired Up

### Local → Python
```
PowerShell Profile ($env:DB_HOST, $env:DB_PASSWORD)
         ↓
config.credential_manager.get_db_credentials()
         ↓
Database connection
```
**Status:** ✅ Tested working

### GitHub → Lambda
```
GitHub Secrets (AWS_ACCOUNT_ID, DB_SECRET_ARN, etc.)
         ↓
GitHub Actions OIDC Role Assumption
         ↓
Terraform Deployment
         ↓
Lambda Environment Variables
```
**Status:** ⏳ Ready after Step 1-3

### Lambda → AWS Services
```
Lambda Environment (DB_SECRET_ARN, COGNITO_USER_POOL_ID)
         ↓
AWS Secrets Manager (for DB password)
         ↓
AWS Cognito (for JWT validation)
         ↓
RDS Database (for data)
```
**Status:** ⏳ Ready after Step 1-3

---

## Scripts Reference

| Script | Purpose | Time |
|--------|---------|------|
| setup-github-secrets.sh | Configure GitHub Secrets | 5 min |
| setup-aws-secrets.sh | Create AWS Secrets Manager secret | 5 min |
| verify-complete-pipeline.sh | Check all three layers | 1 min |
| test_credentials_pipeline.py | Verify local layer | 1 min |

All scripts are in `scripts/` directory.

