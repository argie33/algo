# Pending Work Summary (2026-06-04)

**Goal:** Complete pending fixes and cleanups from recent audits. All are verified, none are speculative.

---

## 🔴 CRITICAL PATH (Blocking Deploy)

### 1. RDS Proxy Configuration Resolution
**Status:** PARTIALLY DISABLED - aws_db_proxy exists but unconfigured  
**Effort:** 2-3 hours  
**Risk:** Medium - proxy endpoint unused, falls back to direct RDS

**What's broken:**
- `aws_db_proxy_default_target_group` (Terraform) is COMMENTED OUT with TODO
- `aws_db_proxy_target` (Terraform) is COMMENTED OUT
- Root cause: AWS provider version doesn't recognize connection pool arguments
- Impact: Proxy created ($0.015/hr cost) but non-functional, coalesce() falls back to RDS

**Options (pick one):**
1. **REMOVE ENTIRELY** (1 hour) - Delete aws_db_proxy resource, use native RDS connection pooling
   - File: `terraform/modules/database/main.tf` lines ~150-190
   - Remove: `aws_iam_role.rds_proxy`, `aws_db_proxy.main`, related policies
   - Pro: Simpler, RDS t4g.small has 100 connections (sufficient for 9 loaders)
   - Con: Lose automatic failover benefit

2. **UPGRADE PROVIDER** (2-3 hours) - Use new aws provider version with target_group support
   - Requires testing full Terraform apply workflow
   - Check compatibility with existing resources
   - Pro: Full proxy features, cost ~$11/month

3. **REIMPLEMENT WITH SECRETS** (3-4 hours) - Configure via aws_db_proxy_auth_token approach
   - Less common, requires research

**Recommendation:** Option 1 (remove) - simpler and cost savings. RDS at t4g.small is sufficient.

**Verification after fix:**
```bash
terraform plan  # Should have 0 changes
terraform apply # Should be fast
# Test: orchestrator should still connect to RDS directly
```

---

### 2. CloudFront Domain Hardcoding - Permanent Fix
**Status:** MITIGATED (daily verify workflow) → NEEDS PERMANENT SOLUTION  
**Effort:** 3-4 hours  
**Risk:** Low - workflow catches mismatches, manual redeploy works

**Current issue:**
- `d2u93283nn45h2.cloudfront.net` hardcoded in:
  - `terraform.tfvars` (lines 9, 19)
  - `terraform/modules/apigateway/main.tf` (CORS origin)
- Circular dependency prevents Terraform from auto-resolving
- Mitigation: Daily `verify-cloudfront.yml` workflow + manual instructions

**Recommended fix (Secrets Manager):**
1. Store CF domain in Secrets Manager
   ```bash
   aws secretsmanager create-secret \
     --name algo/cloudfront-domain \
     --secret-string 'd2u93283nn45h2.cloudfront.net'
   ```

2. Update `lambda/api/lambda_function.py`
   - Fetch domain from Secrets Manager on startup (cache for 24h)
   - Use for CORS headers instead of env var

3. Update API Gateway CORS config
   - Replace hardcoded `d2u93283nn45h2.cloudfront.net` with dynamic origin

4. Remove hardcoded from `terraform.tfvars`

5. Remove/simplify `verify-cloudfront.yml` workflow

**Files to modify:**
- `lambda/api/lambda_function.py` - Add Secrets Manager fetch + caching
- `terraform/terraform.tfvars` - Remove hardcoded lines 9, 19
- `terraform/modules/apigateway/main.tf` - Use dynamic origin
- `.github/workflows/verify-cloudfront.yml` - Simplify or remove

---

## 🟡 HIGH PRIORITY (Infrastructure Ready, Code Pending)

### 3. Secrets Manager Migration for Loader API Keys
**Status:** INFRASTRUCTURE READY (IAM permissions added 2dd0b6db)  
**Effort:** 2-3 hours  
**Risk:** Low - only affects local loader development

**What was done:**
- IAM permissions updated: ECS tasks can now read `algo-secrets`
  - File: `terraform/modules/iam/main.tf` (2dd0b6db commit)
  - Added: `algo-secrets*` to both ECS execution and task roles

**What's pending:**
- Loader code: Fetch Alpaca/FRED keys from Secrets Manager instead of env vars
- Update all files: `loaders/load_*.py` (37 loaders total)
- Add pattern: Each loader checks for Secrets Manager secret, falls back to env var

**Implementation template:**
```python
import json
import boto3

secretsmanager = boto3.client('secretsmanager', region_name='us-east-1')

def get_api_key(secret_name: str, env_var: str) -> str:
    """Get API key from Secrets Manager, fall back to env var."""
    try:
        response = secretsmanager.get_secret_value(SecretId=secret_name)
        return response['SecretString']
    except:
        return os.environ.get(env_var)

# Usage:
alpaca_key = get_api_key('algo-alpaca-key', 'ALPACA_API_KEY')
```

**Verification:**
- Deploy one loader locally
- Confirm it fetches keys from Secrets Manager
- Confirm fallback works if secret doesn't exist

---

## 🟢 MEDIUM PRIORITY (Testing & Validation)

### 4. Test Infrastructure Auto-Discovery Scripts (COMPLETED)
**Status:** ✅ TESTED & WORKING  
**Files:**
- `scripts/get-terraform-outputs.ps1` (NEW) - Works, fetches all terraform outputs
- `scripts/terraform_helpers.py` (NEW) - Works, provides JSON output
- `scripts/setup-cognito-users.ps1` (UPDATED) - Fixed syntax error line 50
- `scripts/setup-frontend-dev-config.ps1` (UPDATED) - Now dynamic

**What was verified:**
- Python helper correctly fetches pool ID and resource names
- PowerShell helper loads environment variables
- Cognito scripts properly require ADMIN_EMAIL and TRADER_EMAIL env vars (no defaults)
- All scripts dynamic instead of hardcoded

**Next step:** Commit these with message "Infrastructure discovery scripts ready" (already done: ade06c1e)

---

### 5. Test Updated IAM Permissions
**Status:** READY FOR TESTING  
**Effort:** 30 minutes

**What changed:**
- ECS task execution role: can read `algo-db-credentials`, `algo/database`, `algo-secrets`
- ECS task role: can read `algo-db-credentials`, `algo/database`, `algo-secrets`
- Purpose: Support Secrets Manager migration for API keys

**Test procedure:**
1. Deploy a test ECS loader task
2. Verify it can list secrets: `aws secretsmanager list-secrets`
3. Verify it can read: `aws secretsmanager get-secret-value --secret-id algo-secrets`

---

## 🔵 LOWER PRIORITY (Optimization & Documentation)

### 6. AWS Credentials Rotation Schedule
**Status:** DUE NEXT QUARTER (2026-09-04)  
**Effort:** 10 minutes when due

**Schedule:** First Monday of each quarter
- Q2: 2026-06-04 ← CURRENT (if not done)
- Q3: 2026-09-04
- Q4: 2026-12-02
- Q1: 2027-03-01

**Process:**
```bash
# GitHub Actions handles via rotate-developer-credentials.yml
# Manual override if needed:
terraform apply -var-file=terraform.tfvars  # Re-runs rotation
```

---

## 📋 TESTING CHECKLIST

### Before Committing Any Changes
- [ ] Terraform plan shows 0 changes (after RDS Proxy fix)
- [ ] terraform apply succeeds
- [ ] All loaders start without errors
- [ ] Orchestrator runs successfully
- [ ] API Lambda responds to health check
- [ ] No stale AWS credentials warnings

### After Secrets Manager Migration
- [ ] Loader fetches API key from Secrets Manager
- [ ] Fallback to env var works if secret missing
- [ ] No loader errors related to auth

### After CloudFront Hardcoding Fix
- [ ] CloudFront domain NOT in terraform.tfvars
- [ ] API CORS headers accept CloudFront domain dynamically
- [ ] verify-cloudfront.yml workflow no longer needed (or greatly simplified)

---

## 📝 COMMIT STRATEGY

**Current state:** Main branch is DEPLOYABLE but has pending optimizations

**Commits needed:**
1. ✅ Infrastructure scripts + IAM updates (already done - 2dd0b6db, ade06c1e)
2. **RDS Proxy removal** - terraform/modules/database/main.tf
3. **CloudFront permanent fix** - lambda/api/, terraform/tfvars, apigateway/main.tf
4. **Loader Secrets Manager migration** - loaders/load_*.py (37 files)

**Each commit should:**
- Include terraform apply verification (mention in commit message)
- Update steering/algo.md if adding permanent procedure
- Have clear PR description showing what was tested

---

## 🎯 RECOMMENDED ORDER

1. **TODAY:** RDS Proxy removal (2h) → immediate cost savings, simplifies Terraform
2. **THIS WEEK:** CloudFront hardcoding fix (3h) → removes daily verify task
3. **NEXT WEEK:** Loader Secrets Manager migration (3h) → better security posture
4. **ONGOING:** Test each deployment in staging first

**Total effort:** 8-9 hours over 2-3 weeks

---

## 📚 References

- **Steering docs:** `steering/algo.md` (system map, known issues)
- **Terraform:** `terraform/` (current state: mostly working, RDS Proxy incomplete)
- **Recent commits:** Last 5 all focused on infrastructure cleanup
- **IAM:** `terraform/modules/iam/main.tf` (updated 2dd0b6db)
- **Database:** `terraform/modules/database/main.tf` (RDS Proxy section ~150-190)
- **Logs:** CloudWatch dashboard `algo-loader-monitoring-dev` shows health
