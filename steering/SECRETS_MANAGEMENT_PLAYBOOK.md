# Secrets Management Playbook
**Version:** 2.0  
**Last Updated:** 2026-07-12  
**Maintainer:** DevOps/Security Team

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture](#architecture)
3. [Credential Lifecycle](#credential-lifecycle)
4. [Rotation Procedures](#rotation-procedures)
5. [Best Practices](#best-practices)
6. [Troubleshooting](#troubleshooting)
7. [Monitoring & Alerts](#monitoring--alerts)

---

## Quick Start

### Check Secrets Status
```bash
# Full audit
python3 scripts/rotate_secrets_automated.py --audit

# Quick check
python3 scripts/rotate_secrets_automated.py --verify

# Pre-commit check (automatic on git commit)
python3 .pre-commit-scripts/check-secrets-freshness.py
```

### Rotate AWS Keys (When Needed)
```bash
# Print step-by-step guide
python3 scripts/rotate_secrets_automated.py --rotate-aws

# After manual steps in AWS Console, verify
python3 scripts/rotate_secrets_automated.py --verify
```

### Full Setup & Verification
```bash
python3 scripts/rotate_secrets_automated.py --full-setup
```

---

## Architecture

### Secret Sources (Priority Order)

```
┌─────────────────────────────────────────────────────────────────┐
│                     Credential Loading Priority                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  LOCAL DEVELOPMENT                AWS LAMBDA/ECS                │
│  ─────────────────────────────    ──────────────────────────   │
│  1. Environment variables          1. AWS Secrets Manager       │
│     (DB_HOST, DB_PASSWORD,            (algo/alpaca,             │
│      AWS_REGION, etc.)               algo/database,             │
│                                      algo/jwt,                   │
│  2. Error if missing                algo/fred)                  │
│     (fail-fast principle)                                        │
│                                    2. Fallback to env vars       │
│                                    3. Error if missing           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### GitHub Secrets Usage

**Purpose:** CI/CD pipeline credentials only  
**Flow:** GitHub Actions → OIDC → AWS IAM role → Deploy  
**Not used at runtime:** Credentials loaded from AWS Secrets Manager in Lambda/ECS

```
GitHub Secrets (25 total)
├─ ALPACA_API_KEY_ID → Terraform → algo/alpaca
├─ ALPACA_API_SECRET_KEY → Terraform → algo/alpaca
├─ JWT_SECRET → Terraform → algo/jwt
├─ FRED_API_KEY → Terraform → algo/fred
├─ DB_PASSWORD → Terraform → algo/database
├─ AWS_GITHUB_ACTIONS_ROLE_ARN → GitHub Actions OIDC
└─ [17 other operational config secrets]
```

### AWS Secrets Manager Secrets

**Purpose:** Runtime credentials for Lambda/ECS  
**Management:** Terraform creates & updates from GitHub Secrets  
**Rotation:** Automatic (every 30 days for database)

```
algo/alpaca
  ├─ APCA_API_KEY_ID
  └─ APCA_API_SECRET_KEY

algo/database
  ├─ host
  ├─ port
  ├─ username
  ├─ password
  └─ dbname

algo/fred
  └─ api_key

algo/jwt
  └─ jwt_secret

algo/orchestrator
  ├─ orchestrator_dry_run
  ├─ halt_reason
  └─ last_updated
```

---

## Credential Lifecycle

### Timeline

```
Day 0: Credential Created
  ├─ Initial value set in GitHub Secrets
  └─ Terraform deploys to AWS Secrets Manager

Days 1-30: Active Use
  ├─ Lambda/ECS loads from Secrets Manager
  ├─ Cache TTL = 5 minutes (auto-refresh)
  └─ No action needed

Days 31-60: Monitor
  ├─ Watch for "Credentials will expire soon" warnings
  └─ Plan rotation if > 90 days old

Day 90+: ROTATE (Best Practice)
  ├─ Generate new credentials
  ├─ Update GitHub Secrets
  ├─ Terraform deploys new value
  ├─ Secrets Manager updates (automatic)
  ├─ Test in staging first
  └─ Delete old credentials

Day 180+: CRITICAL
  ├─ Automatic rotation alerts trigger
  ├─ CI/CD may reject deploys with stale secrets
  └─ Must rotate immediately
```

### Credential Age Thresholds

| Age | Status | Action |
|-----|--------|--------|
| < 30 days | ✅ Fresh | None |
| 30-60 days | ⚠️ Monitor | Plan rotation |
| 60-90 days | ⚠️ Warning | Schedule rotation |
| > 90 days | 🔴 Critical | **ROTATE NOW** |

---

## Rotation Procedures

### AWS Access Key Rotation (Every 90 Days)

**When:** First weekday of quarter (Jan 1, Apr 1, Jul 1, Oct 1)  
**Duration:** ~20 minutes  
**Risk:** Low (OIDC is primary auth method)

#### Step 1: Generate New Key
```bash
# AWS Console
# Navigate to: IAM → Users → algo-developer → Security credentials
# Click: "Create access key"
# Select: "Other"
# SAVE the values (won't see secret again)
```

#### Step 2: Update GitHub Secrets
```bash
# Replace with your new values
gh secret set AWS_ACCESS_KEY_ID \
  --body "AKIAIOSFODNN7EXAMPLE" \
  --repo argie33/algo

gh secret set AWS_SECRET_ACCESS_KEY \
  --body "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" \
  --repo argie33/algo

# Verify
gh secret list --repo argie33/algo | grep AWS_ACCESS_KEY
```

#### Step 3: Test in GitHub Actions
```bash
# Go to GitHub → Actions
# Click any deploy workflow (e.g., "Deploy Orchestrator Lambda")
# Click "Run workflow" → "Run workflow"
# Wait 2-3 minutes for completion

# Success = ✅ (green checkmark)
# Failure = ❌ (red X) → New key needs more permissions
```

#### Step 4: Delete Old Key
```bash
# AWS Console
# Navigate to: IAM → Users → algo-developer → Security credentials
# Find the OLD key (created > 90 days ago)
# Click "Deactivate" first (safety measure)
# Wait 24 hours
# Then click "Delete" → Confirm
```

#### Step 5: Verify
```bash
python3 scripts/rotate_secrets_automated.py --verify
# All checks should pass ✓
```

---

### Database Password Rotation (Every 30 Days)

**When:** Automatic (Secrets Manager handles it)  
**Manual Setup:** First time only  
**Verification:** Monthly

#### First-Time Setup
```bash
# AWS Console
# Navigate to: Secrets Manager → algo/database
# Click "Edit rotation"
# Toggle: "Enable rotation" → ON
# Set interval: 30 days
# Click "Save"

# Verify
aws secretsmanager describe-secret \
  --secret-id algo/database \
  --region us-east-1 \
  --query 'RotationRules'

# Expected output:
# {"AutomaticallyAfterDays": 30}
```

#### Monthly Verification
```bash
# Check rotation happened
aws secretsmanager describe-secret \
  --secret-id algo/database \
  --region us-east-1 \
  --query '{LastRotatedDate:LastRotatedDate, RotationEnabled:RotationEnabled}'

# Expected:
# LastRotatedDate: (should be within last 30 days)
# RotationEnabled: true
```

#### If Rotation Fails
```bash
# Check CloudWatch logs
aws logs tail /aws/secretsmanager/algo/database \
  --region us-east-1 \
  --follow

# Manual rotation as fallback
# (Contact AWS admin for Lambda rotation function setup)
```

---

### FRED API Key Rotation (As Needed)

**When:** When FRED credentials change or compromised  
**Duration:** ~5 minutes

```bash
# 1. Get new key from Federal Reserve
# https://fredaccount.stlouisfed.org/login/secure/

# 2. Update GitHub Secret
gh secret set FRED_API_KEY \
  --body "YOUR_NEW_FRED_KEY" \
  --repo argie33/algo

# 3. Terraform will deploy automatically on next deployment
# (Or manually trigger deploy-all-infrastructure workflow)

# 4. Verify
python3 -c "
from config.credential_manager import get_credential_manager
mgr = get_credential_manager()
fred = mgr.get_secret('algo/fred')
print('✓ FRED key updated')
"
```

---

### Alpaca Credentials Rotation (As Needed)

**When:** Annual or if compromised  
**Duration:** ~10 minutes

```bash
# 1. Generate new API key in Alpaca Dashboard
# https://app.alpaca.markets → API Keys

# 2. Decide: Paper vs Live
#    - Paper: APCA_API_PAPER_KEY_ID (test trading)
#    - Live: APCA_API_KEY_ID (real money)

# 3. Update GitHub Secrets
gh secret set ALPACA_API_KEY_ID \
  --body "YOUR_NEW_KEY_ID" \
  --repo argie33/algo

gh secret set ALPACA_API_SECRET_KEY \
  --body "YOUR_NEW_SECRET" \
  --repo argie33/algo

# 4. Update Alpaca setting in terraform.tfvars
# alpaca_paper_trading = true    # For paper trading
# OR
# alpaca_paper_trading = false   # For live trading

# 5. Deploy
terraform apply -var-file=dev.tfvars

# 6. Test
python3 -c "
from config.credential_manager import get_credential_manager
mgr = get_credential_manager()
alpaca = mgr.get_alpaca_credentials()
print(f'✓ Alpaca key: {alpaca[\"key\"][:10]}...')
"
```

---

## Best Practices

### ✅ DO

1. **Rotate every 90 days**
   ```bash
   # Set calendar reminder
   # Run: python3 scripts/rotate_secrets_automated.py --audit
   # Rotate any keys > 90 days old
   ```

2. **Test after rotation**
   ```bash
   # Always run workflow test
   # Verify: python3 scripts/rotate_secrets_automated.py --verify
   ```

3. **Use Secrets Manager, not environment variables**
   - Lambda/ECS: Load from Secrets Manager (automatic)
   - Local dev: Use environment variables as fallback

4. **Enable auto-rotation where supported**
   - Database password: ✓ Auto-rotate (30 days)
   - Alpaca/FRED: ✓ Manual (annual)
   - AWS keys: ✓ Manual (quarterly)

5. **Document credential changes**
   - Add note in commit message
   - Update SECRETS_CHANGELOG.md

6. **Monitor credential age**
   - Pre-commit check warns if old
   - CI/CD validates on every push
   - Weekly email digest

7. **Fail-fast on missing credentials**
   - Never use empty string defaults
   - Never fall back silently
   - Always raise ValueError with context

### ❌ DON'T

1. **Hardcode credentials**
   ```python
   # ❌ WRONG
   API_KEY = "sk_live_abc123"
   
   # ✅ RIGHT
   from config.credential_manager import get_credential_manager
   mgr = get_credential_manager()
   api_key = mgr.get_secret("api/key")
   ```

2. **Commit secrets to git**
   - All secrets in GitHub Secrets or AWS Secrets Manager
   - .gitignore prevents accidental commits
   - Pre-commit hook blocks secrets in code

3. **Use old credentials "just a little longer"**
   - Rotation is mandatory at 90 days
   - CI/CD will block deployments with stale keys
   - No exceptions for testing or "temporary" use

4. **Rely on environment variables in production**
   - Lambda/ECS: Load from Secrets Manager
   - Env vars are fallback only
   - Never use env vars as primary source in cloud

5. **Skip rotation testing**
   - Always test new credentials before deleting old
   - Run GitHub Actions workflow
   - Verify staging environment first

6. **Store multiple versions of same credential**
   - One current + one previous only (during rotation)
   - Delete old immediately after verification
   - No "just in case" backups

7. **Ignore pre-commit warnings**
   ```
   [FAILED] Stale secrets found (not rotated in > 90 days)
   ```
   - Fix before committing
   - Don't use `git commit --no-verify`

---

## Troubleshooting

### Issue: Pre-commit Hook Blocks Commit

**Error:**
```
✗ FAILED: Stale secrets found (not rotated in > 90 days)
  - AWS_ACCESS_KEY_ID: 95 days old
```

**Solution:**
```bash
# Rotate AWS keys first
python3 scripts/rotate_secrets_automated.py --rotate-aws

# Then try committing again
git commit -m "..."
```

### Issue: GitHub Actions Fails After Key Rotation

**Error:**
```
AWS Error: AccessDenied - User is not authorized to assume role
```

**Solution:**
1. Check new key has right IAM permissions
2. Old key had which permissions?
3. Apply same permissions to new key
4. Test again

**Fallback:**
```bash
# Restore old key temporarily
gh secret set AWS_ACCESS_KEY_ID --body "OLD_KEY_ID" --repo argie33/algo
gh secret set AWS_SECRET_ACCESS_KEY --body "OLD_SECRET" --repo argie33/algo

# Debug IAM, then rotate properly
```

### Issue: Database Connection Fails After Rotation

**Error:**
```
psycopg2.OperationalError: FATAL: password authentication failed
```

**Solution:**
1. Check database rotation actually happened
   ```bash
   aws secretsmanager describe-secret --secret-id algo/database \
     --region us-east-1 --query 'LastRotatedDate'
   ```

2. Clear credential cache (forces refetch)
   ```python
   from config.credential_manager import clear_credential_cache
   clear_credential_cache()
   ```

3. Verify rotation is enabled
   ```bash
   aws secretsmanager describe-secret --secret-id algo/database \
     --region us-east-1 --query 'RotationRules'
   # Should show: {"AutomaticallyAfterDays": 30}
   ```

### Issue: Credential Manager Can't Load Secrets

**Error:**
```
ValueError: Secret 'algo/alpaca' not found.
```

**Debug:**
```bash
# Check environment
echo "AWS_REGION: $AWS_REGION"
echo "Running in AWS: $AWS_EXECUTION_ENV"

# Check Secrets Manager
aws secretsmanager describe-secret \
  --secret-id algo/alpaca \
  --region us-east-1

# Check IAM permissions
aws iam get-user

# Check local environment variables
env | grep -E "DB_|AWS_|ALPACA"
```

**Solutions:**
1. Local dev: Set environment variables
2. Lambda: Check IAM permissions on execution role
3. ECS: Check task role has Secrets Manager access

---

## Monitoring & Alerts

### Automated Checks

| Check | When | Result |
|-------|------|--------|
| Pre-commit hook | Every git commit | Blocks if secrets stale |
| CI/CD validation | Every push | Blocks if secrets missing |
| Daily schedule | 00:00 UTC daily | Email report if issues |
| Rotation reminder | Day 75 | Email reminder to rotate |

### Manual Monitoring

```bash
# Weekly audit
python3 scripts/rotate_secrets_automated.py --audit

# Check all credentials loadable
python3 config/credential_manager.py

# System diagnostic
python3 scripts/diagnose_system.py
```

### Alerts to Set Up

**CloudWatch Alarms:**
```bash
# Alert if secret accessed > 100x/day (possible breach)
aws cloudwatch put-metric-alarm \
  --alarm-name "algo-secrets-high-access" \
  --metric-name SecretAccessCount \
  --statistic Sum \
  --period 3600 \
  --threshold 100 \
  --comparison-operator GreaterThanThreshold

# Alert if rotation fails
aws cloudwatch put-metric-alarm \
  --alarm-name "algo-database-rotation-failed" \
  --metric-name RotationFailure \
  --statistic Sum \
  --threshold 1
```

**Email Notifications:**
```bash
# Set up SNS topic for alerts
aws sns create-topic --name algo-secrets-alerts
aws sns subscribe --topic-arn arn:aws:sns:... \
  --protocol email \
  --notification-endpoint your-email@example.com
```

---

## Related Documents

- **Quick Reference:** `EXECUTION_SUMMARY.md`
- **Cleanup & Audit:** `SECRETS_STATUS.md`
- **Automation:** `scripts/rotate_secrets_automated.py`
- **Pre-commit Checks:** `.pre-commit-scripts/check-secrets-freshness.py`
- **CI/CD Validation:** `.github/workflows/validate-secrets.yml`
- **Configuration:** `config/credential_manager.py`

---

## Maintenance Schedule

**Daily:**
- CI/CD automatic validation on every push

**Weekly:**
- Manual audit: `python3 scripts/rotate_secrets_automated.py --audit`
- Check credential freshness

**Monthly:**
- Database rotation verification
- Review CloudWatch alerts
- Email audit report

**Quarterly:**
- AWS key rotation (Jan 1, Apr 1, Jul 1, Oct 1)
- Review and update this playbook
- Security audit

**Annually:**
- Alpaca credentials review
- Complete secrets inventory audit
- Update rotation schedule

---

## Emergency Procedures

### If Secrets Leaked

1. **Immediate (< 5 min):**
   ```bash
   # Stop Lambda execution
   aws lambda update-function-configuration \
     --function-name algo-orchestrator-dev \
     --environment "Variables={ORCHESTRATOR_DRY_RUN=true}"
   ```

2. **Short-term (< 30 min):**
   - Rotate all potentially-affected credentials
   - Update GitHub Secrets
   - Redeploy Lambda

3. **Long-term (< 24 hours):**
   - Review CloudTrail for unauthorized access
   - Audit database logs for unauthorized queries
   - Document incident
   - Update security procedures

### If AWS Account Compromised

1. Contact AWS Support immediately
2. Enable CloudTrail across all regions
3. Rotate all credentials
4. Review IAM policy changes
5. Enable MFA on root account
6. Run full security audit

---

**Last Updated:** 2026-07-12  
**Next Review:** 2026-10-12  
**Owner:** Security & DevOps Team
