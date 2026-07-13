# Secrets Inventory - Current Status
**Generated:** 2026-07-12  
**Repository:** argie33/algo

---

## GitHub Secrets: WHAT YOU HAVE ✅

Total: **27 secrets currently configured**

### Critical Secrets (Trading & Infrastructure) ✅
| Secret | Last Updated | Status |
|--------|---|---|
| `ALPACA_API_KEY_ID` | 2026-07-08 | ✅ FRESH |
| `ALPACA_API_SECRET_KEY` | 2026-07-08 | ✅ FRESH |
| `ALPACA_API_KEY` | 2026-06-08 | ⚠️ OLD (duplicate?) |
| `ALPACA_SECRET_KEY` | 2026-06-08 | ⚠️ OLD (duplicate?) |
| `JWT_SECRET` | 2026-06-25 | ✅ Recent |
| `FRED_API_KEY` | 2026-06-25 | ✅ Recent |
| `AWS_ACCOUNT_ID` | 2026-05-29 | ✅ Present |
| `AWS_GITHUB_ACTIONS_ROLE_ARN` | 2026-05-29 | ✅ Present |
| `AWS_REGION` | 2026-05-01 | ✅ Present |

### Database Secrets ✅
| Secret | Last Updated | Status |
|--------|---|---|
| `DB_PASSWORD` | 2026-05-10 | ⚠️ STALE (2+ months) |
| `DB_NAME` | 2026-05-01 | ✅ Static (OK) |
| `DB_USER` | 2026-05-01 | ✅ Static (OK) |

### AWS Credentials ⚠️
| Secret | Last Updated | Status |
|--------|---|---|
| `AWS_ACCESS_KEY_ID` | 2026-05-17 | ⚠️ STALE (2 months) - **Should rotate** |
| `AWS_SECRET_ACCESS_KEY` | 2026-05-17 | ⚠️ STALE (2 months) - **Should rotate** |

### Alerts & Notifications ✅
| Secret | Last Updated | Status |
|--------|---|---|
| `ALERT_EMAIL_ADDRESS` | 2026-05-18 | ✅ Present |
| `NOTIFICATION_EMAIL` | 2026-05-06 | ✅ Present |
| `BILLING_EMAIL` | 2026-04-29 | ✅ Present |
| `BILLING_PHONE_NUMBER` | 2026-04-29 | ✅ Present |
| `BILLING_MONTHLY_LIMIT` | 2026-04-29 | ✅ Present |

### Configuration & URLs ✅
| Secret | Last Updated | Status |
|--------|---|---|
| `API_GATEWAY_URL` | 2026-05-09 | ✅ Present |
| `LAMBDA_ROLE_ARN` | 2026-04-29 | ✅ Present |
| `EXECUTION_MODE` | 2026-05-09 | ✅ Present |
| `ORCHESTRATOR_DRY_RUN` | 2026-05-09 | ✅ Present |
| `ORCHESTRATOR_LOG_LEVEL` | 2026-05-09 | ✅ Present |
| `DATA_PATROL_ENABLED` | 2026-05-09 | ✅ Present |
| `DATA_PATROL_TIMEOUT_MS` | 2026-05-09 | ✅ Present |
| `RDS_USERNAME` | 2026-05-03 | ✅ Present |

---

## Issues Found

### 🔴 CRITICAL SECURITY ISSUE
**AWS Credentials are 2 months old (2026-05-17)**
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

**Action:** These should be rotated immediately. In AWS:
```bash
# Check when they were last used
aws accessanalyzer validate-policy --policy-document file://policy.json

# Or in IAM console → Security credentials → Access keys
# Check "Last used" date

# Generate new keys if > 90 days old
```

### ⚠️ DUPLICATE SECRETS (should clean up)
- `ALPACA_API_KEY` (old, from 2026-06-08)
- `ALPACA_SECRET_KEY` (old, from 2026-06-08)
- → Prefer: `ALPACA_API_KEY_ID` + `ALPACA_API_SECRET_KEY` (fresh, 2026-07-08)

**Action:** Delete the old ones:
```bash
gh secret delete ALPACA_API_KEY --repo argie33/algo
gh secret delete ALPACA_SECRET_KEY --repo argie33/algo
```

### ⚠️ STALE DATABASE PASSWORD
- `DB_PASSWORD` last updated 2026-05-10 (2+ months old)

**Note:** This is stored in AWS Secrets Manager with auto-rotation. Check if rotation is working:
```bash
aws secretsmanager describe-secret \
  --secret-id algo/database \
  --region us-east-1 \
  --query 'RotationRules'
```

---

## What's Missing? ❌

### NOT in GitHub Secrets (but may not be needed)

| Item | Where Used | Why Missing | Workaround |
|---|---|---|---|
| `ALERT_SMTP_PASSWORD` | SMTP email alerts (optional) | Not configured for email alerts | Set in terraform.tfvars if needed |
| `ALERT_SMTP_HOST` | SMTP email alerts (optional) | Not configured for email alerts | Set in terraform.tfvars if needed |
| `ALERT_SMTP_PORT` | SMTP email alerts (optional) | Not configured for email alerts | Set in terraform.tfvars if needed |
| `ALERT_SMTP_USER` | SMTP email alerts (optional) | Not configured for email alerts | Set in terraform.tfvars if needed |
| `RDS_MASTER_PASSWORD` | Terraform only (auto-generated) | Terraform generates this | No action needed |
| `TF_STATE_BUCKET` | Terraform state (has default) | Using default: `stocks-terraform-state` | No action needed |
| `TF_STATE_KEY` | Terraform state (has default) | Using default: `stocks/terraform.tfstate` | No action needed |

---

## AWS Secrets Manager

**Status:** Cannot verify due to IAM access restrictions, but based on GitHub Secrets, Terraform should have created:

```
✅ algo/alpaca              (from ALPACA_API_KEY_ID + ALPACA_API_SECRET_KEY)
✅ algo/fred                (from FRED_API_KEY)
✅ algo/database            (from DB_PASSWORD, DB_USER, DB_NAME)
✅ algo/jwt                 (from JWT_SECRET)
✅ algo/orchestrator        (Terraform bootstrap)
```

**To verify:**
```bash
# Try to list (you may get access denied)
aws secretsmanager list-secrets --region us-east-1

# Or check a specific secret
aws secretsmanager get-secret-value --secret-id algo/alpaca --region us-east-1
```

---

## Quick Status Summary

| Category | Count | Status |
|----------|-------|--------|
| **Total Secrets** | 27 | ✅ Complete |
| **Critical Secrets** | 9 | ✅ 9/9 Present |
| **All Secrets Fresh** | - | ⚠️ AWS keys are 2 months old |
| **Duplicates** | 2 | ⚠️ Need cleanup |
| **Missing Optional** | 4 | ℹ️ Optional (email alerts) |

---

## Recommended Actions (Priority Order)

### 🔴 URGENT (Security)
1. **Rotate AWS credentials**
   ```bash
   # In AWS IAM console or CLI
   aws iam create-access-key --user-name algo-developer
   # Delete old keys after testing new ones
   ```
   - Add new keys to GitHub Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
   - Delete old keys from IAM (after 24-hour test period)

### 🟡 SOON (Cleanup)
2. **Delete duplicate Alpaca secrets**
   ```bash
   gh secret delete ALPACA_API_KEY --repo argie33/algo
   gh secret delete ALPACA_SECRET_KEY --repo argie33/algo
   ```
   - Update any workflows referencing the old names to use the new ones

3. **Verify database password rotation**
   ```bash
   aws secretsmanager describe-secret --secret-id algo/database --region us-east-1
   ```
   - Confirm `RotationEnabled=true` and check last rotation date

### 🟢 OPTIONAL (Enhancement)
4. **Add SMTP secrets if you want email alerts**
   - `ALERT_SMTP_HOST`: smtp.gmail.com (or your provider)
   - `ALERT_SMTP_PORT`: 587
   - `ALERT_SMTP_USER`: your-email@gmail.com
   - `ALERT_SMTP_PASSWORD`: app-specific password
   - Then set `enable_smtp_alerts=true` in terraform.tfvars

---

## Verification Checklist

### ✅ Before Next Deployment
- [ ] Rotate AWS access keys (if > 90 days old)
- [ ] Delete duplicate ALPACA_API_KEY secrets
- [ ] Verify DB password auto-rotation is enabled
- [ ] Run CI/CD pipeline to test with current secrets

### ✅ Ongoing
- [ ] Check GitHub Secrets → Security → "Last used" dates monthly
- [ ] AWS credentials: rotate every 90 days
- [ ] Database password: Secrets Manager auto-rotates (no action)
- [ ] Alpaca keys: rotate if compromised or after major version changes

---

## Need to Fix?

**To rotate AWS keys:**
```bash
# 1. Create new access key
aws iam create-access-key --user-name algo-developer
# Copy NEW_KEY_ID and NEW_SECRET

# 2. Update GitHub Secrets
gh secret set AWS_ACCESS_KEY_ID --body "NEW_KEY_ID" --repo argie33/algo
gh secret set AWS_SECRET_ACCESS_KEY --body "NEW_SECRET" --repo argie33/algo

# 3. Test in GitHub Actions (run any workflow)
# (Wait 1-2 minutes for secrets to propagate)

# 4. After successful test, delete old key
aws iam delete-access-key --access-key-id OLD_KEY_ID --user-name algo-developer
```

**To clean up duplicate secrets:**
```bash
gh secret delete ALPACA_API_KEY --repo argie33/algo
gh secret delete ALPACA_SECRET_KEY --repo argie33/algo
```
