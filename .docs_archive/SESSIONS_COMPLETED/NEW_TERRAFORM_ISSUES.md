# Additional Terraform Issues Found - Round 2

**Date:** 2026-05-09  
**Status:** 6 NEW issues identified  
**Priority:** HIGH and MEDIUM

---

## 🔴 HIGH SEVERITY ISSUES

### Issue #21: Alpaca Paper Trading Type Mismatch
**File:** `terraform/modules/database/variables.tf:178-182`  
**Severity:** HIGH  
**Issue:** 
```terraform
variable "alpaca_paper_trading" {
  description = "Enable Alpaca paper trading mode"
  type        = string        # WRONG: Should be bool
  default     = "true"        # WRONG: String instead of boolean
}
```
Terraform will treat `"true"` as a string, which may cause logic errors when used in conditional statements.

**Fix:** Change to boolean type and value
```terraform
variable "alpaca_paper_trading" {
  description = "Enable Alpaca paper trading mode"
  type        = bool
  default     = true
}
```

---

### Issue #22: S3 Server-Side Encryption Using Deprecated `rule` Syntax
**File:** `terraform/modules/storage/main.tf` (multiple locations)  
**Severity:** HIGH  
**Issue:** Using deprecated `rule` block instead of `rules` in `aws_s3_bucket_server_side_encryption_configuration`
- Lines 29, 101, 140, 203, 270, 365 - all use deprecated `rule` syntax
- AWS Terraform provider deprecated this syntax in v4.8+
- Will cause errors in future provider versions

**Affected Resources:**
- aws_s3_bucket_server_side_encryption_configuration.code
- aws_s3_bucket_server_side_encryption_configuration.cf_templates
- aws_s3_bucket_server_side_encryption_configuration.lambda_artifacts
- aws_s3_bucket_server_side_encryption_configuration.data_loading
- aws_s3_bucket_server_side_encryption_configuration.log_archive
- aws_s3_bucket_server_side_encryption_configuration.frontend

**Fix:** Change `rule` to `rules` (plural) with proper nesting
```terraform
rules {
  apply_server_side_encryption_by_default {
    sse_algorithm = "AES256"
  }
}
```

---

### Issue #25: RDS KMS Key Referenced But Not Created
**File:** `terraform/main.tf:65`  
**Severity:** HIGH  
**Issue:** 
```terraform
enable_rds_kms_encryption = var.environment == "prod"
rds_kms_key_id           = var.environment == "prod" ? "alias/${var.project_name}-rds" : null
```
The KMS key is never created in Terraform. When `enable_rds_kms_encryption=true` for production, the code tries to use a KMS key alias that doesn't exist, causing deployment failure.

**Fix:** Create the KMS key and grant RDS access
- Add aws_kms_key resource in IAM or database module
- Add aws_kms_alias resource
- Add aws_kms_grant for RDS service

---

## 📋 MEDIUM SEVERITY ISSUES

### Issue #23: Hardcoded Email in Root Variables
**File:** `terraform/variables.tf:58`  
**Severity:** MEDIUM  
**Issue:**
```terraform
variable "notification_email" {
  description = "Email address for CloudWatch alarms and SNS notifications"
  type        = string
  default     = "argeropolos@gmail.com"  # WRONG: Hardcoded personal email
}
```
Personal email should not be in code defaults. Should require explicit input for each environment.

**Fix:** 
```terraform
default = ""  # No default, require explicit input
# OR: 
default = var.environment == "prod" ? "" : ""  # Force explicit input
```

---

### Issue #24: GitHub Actions IAM Policy EC2 Actions Overpermissive
**File:** `terraform/modules/iam/main.tf:95-96`  
**Severity:** MEDIUM  
**Issue:**
```terraform
resources = ["*"]  # Overpermissive for all EC2 actions
```
GitHub Actions can describe ANY EC2 resource in the entire account. Should split into:
- `Describe*` actions → `resources = ["*"]` (AWS requirement)
- Modification actions → Scoped ARNs only

**Fix:** Split EC2 policy into two statements
1. Describe-only: `resources = ["*"]`
2. Modifications: `resources = [specific ARNs]`

---

### Issue #26: Bastion Spot Instance Using One-Time Instead of Persistent
**File:** `terraform/modules/compute/main.tf:173`  
**Severity:** MEDIUM  
**Issue:**
```terraform
spot_options {
  spot_instance_type = "one-time"  # Wrong for bastion
}
```
"one-time" is for short-lived batch jobs. Bastion should use "persistent" so it survives Spot interruptions and automatically restarts.

**Fix:**
```terraform
spot_options {
  spot_instance_type = "persistent"
}
```

---

## SUMMARY TABLE

| Issue | Severity | Type | File | Status |
|-------|----------|------|------|--------|
| #21 | HIGH | Type mismatch | database/variables.tf | ❌ Not Fixed |
| #22 | HIGH | Deprecated syntax | storage/main.tf | ❌ Not Fixed |
| #23 | MEDIUM | Hardcoded value | variables.tf | ❌ Not Fixed |
| #24 | MEDIUM | Overpermissive IAM | iam/main.tf | ❌ Not Fixed |
| #25 | HIGH | Missing resource | main.tf | ❌ Not Fixed |
| #26 | MEDIUM | Configuration error | compute/main.tf | ❌ Not Fixed |

---

## BLOCKING ISSUES FOR PRODUCTION

- **Issue #21**: May cause configuration errors with paper trading flag
- **Issue #22**: Will fail in future Terraform versions
- **Issue #25**: Will fail immediately in production (KMS key doesn't exist)

**Recommendation:** Fix issues #21, #22, #25 before any production deployment.

---

**Next Steps:** Apply fixes systematically and validate with `terraform plan`
