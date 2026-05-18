# Credential Audit: Immediate Action Items
**Status:** Audit Complete  
**Date:** 2026-05-17  
**Priority:** MEDIUM (setup before production)

---

## QUICK START: What to Do Now

### ✅ ALREADY CORRECT (No Action Needed)
- [x] No .env files in repo (using env vars only)
- [x] No hardcoded credentials found
- [x] Terraform creates Secrets Manager secrets
- [x] Lambda functions configured to read from Secrets Manager
- [x] Python credential_helper/credential_manager properly set up
- [x] IAM roles have Secrets Manager permissions
- [x] GitHub Actions uses OIDC (not long-lived keys)

---

## 🔴 CRITICAL: Must Do Before Production

### 1. Verify All GitHub Actions Secrets Exist
**Time: 5 minutes**

Go to: GitHub → Settings → Secrets and variables → Actions

**Verify these secrets are set:**
```
[ ] AWS_ACCOUNT_ID          → e.g., "123456789012"
[ ] RDS_PASSWORD            → Your database password
[ ] ALPACA_API_KEY_ID       → From Alpaca dashboard
[ ] ALPACA_API_SECRET_KEY   → From Alpaca dashboard
[ ] JWT_SECRET              → Any random 32-char string
[ ] FRED_API_KEY            → From Federal Reserve site
[ ] ALERT_EMAIL_ADDRESS     → Your email
```

**Optional but recommended:**
```
[ ] API_GATEWAY_URL         → Will be auto-populated after deploy
```

**Action:** If any are missing, click "New repository secret" and add them

---

### 2. Test Local Database Connection
**Time: 10 minutes**

```bash
# Step 1: Ensure PostgreSQL is running
psql -h localhost -U stocks -d stocks -c "SELECT 1"
# Should return: 1

# Step 2: Set environment variable
export DB_PASSWORD=your_postgres_password

# Step 3: Run verification
python3 config/credential_helper.py
# Should print: DB Config: localhost:5432/stocks

# Step 4: Test database
python3 -c "from utils.db_connection import get_db_connection; conn = get_db_connection(); print('✅ Connected')"
# Should print: ✅ Connected
```

**Action:** If this fails, check LOCAL_CRED_SETUP.md for detailed setup

---

### 3. Verify All Python Loaders Use Credential Helper
**Time: 5 minutes**

```bash
# Check that all loaders use proper credential functions
grep -l "get_db_connection\|get_db_config" loaders/*.py | wc -l
# Should show: ~40 (all loaders)

# Check for any hardcoded passwords
grep -n "password.*=.*['\"].*['\"]" loaders/*.py | grep -v "test\|example"
# Should return: (empty - no matches)
```

**Action:** If any loaders don't use credential_helper, they need to be fixed

---

### 4. Verify Terraform Outputs (After First Deployment)
**Time: 5 minutes**

```bash
cd terraform

# Initialize terraform
terraform init

# Check outputs
terraform output -json | jq '{
  rds_endpoint: .rds_endpoint.value,
  rds_credentials_arn: .rds_credentials_secret_arn.value,
  api_lambda_name: .api_lambda_function_name.value,
  algo_lambda_name: .algo_lambda_function_name.value
}'

# Should show valid ARNs and endpoints
```

**Action:** If outputs are empty, run `terraform apply` first

---

### 5. Verify Lambda Functions Have DB_SECRET_ARN
**Time: 5 minutes** (requires AWS access)

```bash
# Check API Lambda
aws lambda get-function-configuration \
  --function-name stocks-api-dev \
  --region us-east-1 | jq '.Environment.Variables | keys'

# Should include: ["DB_SECRET_ARN", "DB_ENDPOINT", ...]
```

**Action:** If DB_SECRET_ARN is missing, re-run `terraform apply`

---

## 🟡 IMPORTANT: Before Going Live

### 6. Set Up Credential Rotation Policy
**Time: 15 minutes**

Create a schedule to rotate credentials:

```markdown
- [ ] RDS Password: Rotate every 90 days
- [ ] Alpaca API Keys: Rotate annually or if leaked
- [ ] JWT Secret: Rotate with each production deployment
- [ ] FRED API Key: Keep on file, rotate if accessed

Add to calendar:
- 2026-08-17: RDS password rotation due
- 2027-05-17: Alpaca keys rotation due
```

**Action:** Add reminders to your calendar or project management system

---

### 7. Enable Secret Scanning in GitHub
**Time: 2 minutes**

Go to: GitHub → Settings → Security & analysis

```
[ ] Enable "Secret scanning"
[ ] Enable "Push protection"
[ ] Enable "Secret scanning validity checks"
```

**Action:** Click the toggle buttons to enable these

---

### 8. Set Up CloudTrail Logging
**Time: 10 minutes** (requires AWS access)

```bash
# Enable CloudTrail for Secrets Manager access
aws cloudtrail start-logging \
  --trail-name algo-trail \
  --region us-east-1

# Verify logging is enabled
aws cloudtrail get-trail-status \
  --trail-name algo-trail \
  --region us-east-1 | jq '.IsLogging'
# Should return: true
```

**Action:** Enable in AWS CloudTrail console if not already done

---

## 📋 REFERENCE DOCUMENTS

Created during this audit:

1. **CREDENTIAL_AUDIT_2026-05-17.md**
   - Complete credential flow documentation
   - Architecture diagrams
   - Compliance checklist

2. **CREDENTIAL_SETUP_CHECKLIST.md**
   - Step-by-step setup guide
   - Phase 1: Local development
   - Phase 2: GitHub Actions
   - Phase 3: AWS
   - Phase 4: Integration testing
   - Phase 5: Ongoing management
   - Troubleshooting guide

3. **LOCAL_CRED_SETUP.md** (existing)
   - Local development credential setup
   - Option 1: Environment variables
   - Option 2: AWS Secrets Manager

---

## ✅ VALIDATION CHECKLIST

Use this to confirm everything is working:

### Local Development (✅ Can test now)
```bash
[ ] python3 config/credential_helper.py          # Shows DB config
[ ] python3 config/credential_validator.py        # Shows all required creds
[ ] python3 -c "from utils.db_connection import get_db_connection; get_db_connection()"  # DB connects
[ ] python3 loaders/loadstocksymbols.py          # Loader runs (requires data)
[ ] python3 algo/algo_orchestrator.py --dry-run  # Orchestrator runs
```

### GitHub Actions (✅ Can test on next push)
```bash
[ ] Deploy workflow triggers on push to main
[ ] Terraform uses TF_VAR_rds_password secret
[ ] Secrets Manager secrets are created
[ ] Deployment succeeds with no credential errors
```

### AWS (✅ Can verify after deployment)
```bash
[ ] aws secretsmanager list-secrets shows 3+ secrets
[ ] aws secretsmanager get-secret-value returns valid JSON
[ ] aws lambda get-function-configuration shows DB_SECRET_ARN
[ ] API health check works: curl https://$API_URL/api/health
```

---

## 🚨 COMMON ISSUES & FIXES

### Problem: "DB_PASSWORD not available"
**Solution:**
```bash
export DB_PASSWORD=your_password
python3 config/credential_helper.py
```

### Problem: "Database password not set"
**Solution:**
- Check GitHub Actions secret `RDS_PASSWORD` is configured
- Run `terraform apply` to update Secrets Manager
- Check Lambda environment variable `DB_SECRET_ARN`

### Problem: "Lambda cannot access Secrets Manager"
**Solution:**
- Verify Lambda IAM role has `secretsmanager:GetSecretValue` permission
- Check secret ARN in environment variable
- Verify secret exists: `aws secretsmanager list-secrets`

### Problem: "Alpaca API returns 401"
**Solution:**
- Check GitHub Actions secret `ALPACA_API_KEY_ID` is set correctly
- Verify API keys at Alpaca dashboard (may have been revoked)
- Check Secrets Manager: `aws secretsmanager get-secret-value --secret-id stocks-algo-secrets-dev`

---

## 📞 NEXT STEPS

1. **Today:** Complete Section 🔴 (GitHub secrets + local testing)
2. **This Week:** Complete Section 🟡 (rotation policy + monitoring)
3. **Before Prod:** Run all validation checks
4. **Ongoing:** Monitor credentials monthly

---

## SIGN-OFF CHECKLIST

**When you can check all these boxes, credentials are fully secured:**

- [ ] All GitHub Actions secrets verified (Section 1)
- [ ] Local database connection tested (Section 2)
- [ ] All loaders use credential_helper (Section 3)
- [ ] Terraform outputs verified (Section 4)
- [ ] Lambda DB_SECRET_ARN confirmed (Section 5)
- [ ] Credential rotation policy created (Section 6)
- [ ] Secret scanning enabled in GitHub (Section 7)
- [ ] CloudTrail logging enabled (Section 8)
- [ ] All validation checks pass (see ✅ VALIDATION CHECKLIST)
- [ ] Common issues resolved if applicable

**Last Updated:** 2026-05-17  
**Next Review:** 2026-08-17 (90 days)
