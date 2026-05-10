# Comprehensive Terraform Audit - 23 Issues Found

**Date:** 2026-05-09  
**Total Issues:** 23 (4 CRITICAL, 6 HIGH, 6 MEDIUM, 4 LOW, 3 INFO)  
**Status:** 🚨 CRITICAL ISSUES REQUIRE IMMEDIATE FIXES

---

## CRITICAL ISSUES (Fix Before Any Deployment)

### 1. 🚨 S3 Buckets with `force_destroy = true` (Risk of Data Loss)
**File:** `terraform/modules/storage/main.tf` lines 11, 83, 122, 193, 252, 331  
**Severity:** CRITICAL  
**Issue:** All 6 S3 buckets configured with `force_destroy = true`
- Allows Terraform to DELETE non-empty buckets (data loss!)
- Affects: code, CF templates, data loading, lambda artifacts, logs, bucket backups
- Violates GDPR/data retention regulations

**Impact:** ONE `terraform destroy` command = PERMANENT DATA LOSS

**Fix:** Replace `force_destroy = true` with:
```terraform
force_destroy = var.environment != "prod" ? false : false  # Always false
# OR use conditional for dev-only:
force_destroy = var.environment == "dev" ? false : false
```

**Status:** [ ] Not Fixed

---

### 2. 🚨 RDS Database Encryption Using AWS-Managed Keys (Not Customer-Managed)
**File:** `terraform/modules/database/variables.tf:112-122`, `main.tf:53-54`  
**Severity:** CRITICAL  
**Issue:** `enable_rds_kms_encryption` defaults to `false`
- RDS uses AWS-managed keys, not customer-managed KMS
- Cannot audit/control encryption key rotation
- SOC2/PCI-DSS compliance requires customer-managed keys

**Impact:** Production database not meeting security compliance standards

**Fix:**
```terraform
variable "enable_rds_kms_encryption" {
  default = var.environment == "prod" ? true : false
  # Add validation:
  validation {
    condition = var.environment == "prod" ? var.enable_rds_kms_encryption == true : true
    error_message = "Production must use customer-managed KMS encryption"
  }
}
```

**Status:** [ ] Not Fixed

---

### 3. 🚨 RDS Not Multi-AZ (Single Point of Failure)
**File:** `terraform/modules/database/variables.tf:95-99`  
**Severity:** CRITICAL  
**Issue:** `db_multi_az` defaults to `false`
- NO failover during AZ failure or AWS maintenance
- Complete database downtime = algo cannot trade
- Any patch or AZ issue = full outage

**Impact:** Trading algorithm completely dependent on single AZ

**Fix:**
```terraform
variable "db_multi_az" {
  default = var.environment == "prod" ? true : false
  description = "Enable Multi-AZ for high availability"
}
```

**Status:** [ ] Not Fixed

---

### 4. 🚨 RDS Final Snapshot Logic Inverted (Data Loss Risk)
**File:** `terraform/modules/database/main.tf:40-44`  
**Severity:** CRITICAL  
**Issue:** `skip_final_snapshot = var.environment != "prod"`
- Logic may be backwards
- If DB deleted without final snapshot = UNRECOVERABLE

**Impact:** Production DB deletion without backup

**Fix:**
```terraform
skip_final_snapshot = false  # ALWAYS create final snapshot
final_snapshot_identifier = "${var.project_name}-final-snapshot-${formatdate("YYYY-MM-DD-hhmm", timestamp())}"
```

**Status:** [ ] Not Fixed

---

## HIGH SEVERITY ISSUES (Fix Before Production Deployment)

### 5. 🔴 S3 Data Loading Bucket Missing Versioning
**File:** `terraform/modules/storage/main.tf:191-245`  
**Issue:** `data_loading` and `log_archive` buckets don't have versioning
- Cannot detect accidental overwrites
- No version history for data recovery

**Fix:** Enable versioning on all data buckets

**Status:** [ ] Not Fixed

---

### 6. 🔴 Bastion Lambda with Overpermissive IAM (`resource = "*"`)
**File:** `terraform/modules/compute/main.tf:308-340`  
**Issue:** Lambda can describe ANY ASG/instance in account
- Should only manage bastion resources

**Fix:** Scope to specific bastion ASG ARN

**Status:** [ ] Not Fixed

---

### 7. 🔴 Batch ECR Pull with Wildcard Resources
**File:** `terraform/modules/batch/main.tf:118-129`  
**Issue:** Batch jobs can pull ANY ECR image from any repo

**Fix:** Add source ARN condition to ECR repo

**Status:** [ ] Not Fixed

---

### 8. 🔴 ECS Task Execution Role KMS Decrypt Too Broad
**File:** `terraform/modules/iam/main.tf:649-700`  
**Issue:** Tasks can decrypt ANY KMS-encrypted secret
- Should only decrypt project secrets

**Fix:** Restrict to project-specific KMS keys

**Status:** [ ] Not Fixed

---

### 9. 🔴 Batch EC2 Secrets Manager Access Too Broad
**File:** `terraform/modules/batch/main.tf:113-119`  
**Issue:** Batch instances access ANY secret (`secret:*`)
- Can retrieve DB credentials, all project secrets

**Fix:** Scope to `${var.project_name}-*` pattern

**Status:** [ ] Not Fixed

---

### 10. 🔴 Lambda Functions Using ECS Security Group
**File:** `terraform/modules/services/main.tf:63-66, 449-451`  
**Issue:** API and Algo Lambdas use `ecs_tasks_security_group_id`
- Tight coupling between services
- Confuses security auditing

**Fix:** Create dedicated security groups for Lambda

**Status:** [ ] Not Fixed

---

## MEDIUM SEVERITY ISSUES (Fix in Next Release)

### 11. 📋 Missing Variable Descriptions - Batch Module
**File:** `terraform/modules/batch/variables.tf`  
**Issue:** Variables lack adequate descriptions

**Status:** [ ] Not Fixed

---

### 12. 📋 Lambda Bastion Code Embedded as String
**File:** `terraform/modules/compute/main.tf:359-368`  
**Issue:** Code embedded rather than read from file
- Difficult to test/version

**Status:** [ ] Not Fixed

---

### 13. 📋 RDS TimescaleDB Parameter Without Validation
**File:** `terraform/modules/database/main.tf:90-141`  
**Issue:** No validation that TimescaleDB extension exists

**Status:** [ ] Not Fixed

---

### 14. 📋 Loaders Module Missing Task Count Validation
**File:** `terraform/modules/loaders/outputs.tf`  
**Issue:** Cannot easily validate all expected loaders are scheduled

**Status:** [ ] Not Fixed

---

### 15. 📋 API Gateway CORS Includes Localhost in Production
**File:** `terraform/modules/services/variables.tf:177-181`  
**Issue:** Default CORS origins include localhost for all environments

**Fix:** Default empty for prod:
```terraform
default = var.environment == "prod" ? [] : [
  "http://localhost:5173",
  "http://localhost:3000"
]
```

**Status:** [ ] Not Fixed

---

### 16. 📋 Cognito Password Policy Minimum Not Enforced
**File:** `terraform/modules/services/main.tf:326-332`  
**Issue:** Password minimum length configurable, not enforced for prod

**Fix:** Add validation for prod minimum of 12

**Status:** [ ] Not Fixed

---

## LOW SEVERITY ISSUES (Consider Fixing)

### 17. 📝 EventBridge Scheduler Role Output Missing
**File:** `terraform/modules/services/outputs.tf`  
**Issue:** Role ARN not exported

**Status:** [ ] Not Fixed

---

### 18. 📝 Monitoring Module Undefined Variables
**File:** `terraform/modules/monitoring/main.tf:36-38, 83-84, 129-131`  
**Issue:** References variables not defined in monitoring/variables.tf
- Will cause Terraform errors

**Fix:** Add missing variables to monitoring/variables.tf

**Status:** [ ] Not Fixed

---

### 19. 📝 Unused Variables in VPC Module
**File:** `terraform/modules/vpc/variables.tf:86-96`  
**Issue:** `use_existing_vpc` and `existing_vpc_id` defined but never used

**Status:** [ ] Not Fixed

---

### 20. 📝 Bastion Instance Profile Naming Issue
**File:** `terraform/modules/compute/variables.tf:59-62`  
**Issue:** Odd coupling and naming convention

**Status:** [ ] Not Fixed

---

## INFORMATIONAL (Monitor/Plan)

### 21. CloudFront Without WAF
**Status:** Not currently critical, but WAF recommended for production

### 22. All Egress Rules Use 0.0.0.0/0
**Status:** Standard pattern, acceptable

### 23. No ALB Health Checks
**Status:** N/A currently, note for future

---

## ISSUE SUMMARY TABLE

| Severity | Count | Status |
|----------|-------|--------|
| 🚨 CRITICAL | 4 | **MUST FIX BEFORE DEPLOY** |
| 🔴 HIGH | 6 | Should fix for prod |
| 📋 MEDIUM | 6 | Fix in next release |
| 📝 LOW | 4 | Consider fixing |
| ℹ️ INFO | 3 | Monitor only |
| **TOTAL** | **23** | - |

---

## Fix Priority Order

**Phase 1 (CRITICAL - Do Now):**
1. Remove `force_destroy = true` from all S3 buckets
2. Enable RDS encryption with customer-managed KMS
3. Enable RDS Multi-AZ for prod
4. Fix RDS final snapshot logic

**Phase 2 (HIGH - Before Prod Deploy):**
5-10. Fix IAM overpermissiveness (6 issues)

**Phase 3 (MEDIUM - Next Release):**
11-16. Fix configurations and validations

**Phase 4 (LOW - Polish):**
17-20. Clean up outputs and variables

---

**Next Action:** Start fixing CRITICAL issues
