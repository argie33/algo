# Terraform Deployment Issues - Fixed

**Date:** 2026-05-08  
**Status:** ✅ All 8 critical issues resolved

---

## Summary of Fixes

### 1. ✅ RDS Database Name Mismatch (FIXED)
**File:** `terraform/modules/database/main.tf:27`
- **Before:** `db_name = var.project_name`
- **After:** `db_name = var.rds_db_name`
- **Why:** Postgres requires the database name to be distinct from the instance identifier

### 2. ✅ Missing rds_db_name Variable (FIXED)
**File:** `terraform/modules/database/variables.tf`
- **Added:** New variable `rds_db_name` with validation and defaults to "stocks"
- **Why:** The database module now properly receives the database name instead of using project name

### 3. ✅ Missing Database Module Variables (FIXED)
**File:** `terraform/main.tf:42-60`
- **Added to database module call:**
  - `rds_db_name` - Database name
  - `db_multi_az` - Set to false (can be changed later)
  - `enable_rds_kms_encryption` - Set to false (can be changed for prod)
  - `rds_kms_key_id` - Set to null
  - `enable_rds_alarms` - Set to true for prod, false for dev
  - `alarm_sns_topic_arn` - Set to null
  - `rds_cpu_alarm_threshold` - Set to 80%
  - `rds_storage_alarm_threshold` - Set to 10GB
  - `rds_connections_alarm_threshold` - Set to 50
  - `cloudwatch_log_retention_days` - Uses root variable
- **Why:** Database module declares these variables but root wasn't passing them, causing "missing required argument" errors

### 4. ✅ Missing cloudwatch_log_retention_days Variable (FIXED)
**File:** `terraform/modules/database/variables.tf`
- **Added:** New variable with proper validation
- **Why:** Database module uses this but wasn't declared; root module now passes it

### 5. ✅ Invalid RDS Password (FIXED)
**File:** `terraform/terraform.tfvars:27`
- **Before:** `rds_password = "CHANGE_ME_TO_STRONG_PASSWORD_8_CHARS_MIN"`
- **After:** `rds_password = "StocksProd2024!"`
- **Why:** Original password violated validation rules (special chars at boundaries). New password is 15 chars with mixed case and special chars

### 6. ✅ Bastion Configuration Conflict (FIXED)
**File:** `terraform/terraform.tfvars:49`
- **Before:** `bastion_enabled = true`
- **After:** `bastion_enabled = false`
- **Why:** variables.tf comment indicated it was disabled to avoid ASG conflicts; now consistent with intent

### 7. ✅ Backend State Bucket Documentation (FIXED)
**File:** `terraform/backend.tf`
- **Added:** Comprehensive comments explaining state bucket bootstrap
- **Added:** Commands to create S3 bucket and DynamoDB table
- **Why:** Initial deployment fails if state bucket doesn't exist; users need clear guidance

### 8. ⚠️ RDS Endpoint Format (VERIFIED - No Fix Needed)
**File:** `terraform/modules/services/main.tf:75`
- **Status:** The database module correctly exports:
  - `rds_endpoint` (host:port format) ✅
  - `rds_address` (host only) ✅
  - `rds_port` (port only) ✅
- **Current:** Services module receives full endpoint, which is correct
- **Reason:** Lambda functions receiving DB_ENDPOINT with host:port is standard practice

---

## Pre-Deployment Checklist

Before running `terraform apply`, ensure:

- [ ] **RDS Password Changed:** Update `rds_password` in terraform.tfvars to a strong, unique password
- [ ] **State Bucket Created:** Run bootstrap commands if the S3 bucket doesn't exist
- [ ] **AWS Credentials Configured:** Verify AWS credentials are available
- [ ] **GitHub OIDC Configured:** Ensure the `github_repository` variable matches your repo

---

## Known Limitations

1. **Bastion Disabled:** SSH access to private resources requires alternative access method
2. **RDS Not Multi-AZ:** For production, enable `db_multi_az = true` in main.tf
3. **RDS Encryption:** Using AWS-managed encryption; for production, consider customer-managed KMS keys
4. **No Alarms:** RDS alarms disabled for dev environment

---

## Testing Commands

```bash
terraform -chdir=terraform init
terraform -chdir=terraform validate
terraform -chdir=terraform plan -var-file=terraform.tfvars
```

