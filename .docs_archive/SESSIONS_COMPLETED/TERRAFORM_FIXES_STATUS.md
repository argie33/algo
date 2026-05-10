# Terraform Fixes - Current Status Report

**Date:** 2026-05-09  
**Total Issues Audited:** 23  
**Fixed So Far:** 5 issues  
**Remaining:** 18 issues  

---

## ✅ FIXED (5 Issues)

### CRITICAL - All 4 Fixed ✅
1. ✅ **S3 force_destroy = true** - Changed to false on all 6 buckets
2. ✅ **RDS Encryption** - Enable customer-managed KMS with validation for prod
3. ✅ **RDS Multi-AZ** - Default true, validation for prod
4. ✅ **RDS Final Snapshot Logic** - Clarified and made conditional

### HIGH - 1 of 6 Fixed ✅  
5. ✅ **S3 Data Loading Bucket Versioning** - Added versioning to data_loading and log_archive

---

## 🚨 REMAINING HIGH SEVERITY (5 Issues)

### Issue #6: Bastion Lambda Overpermissive IAM
**File:** `terraform/modules/compute/main.tf:308-340`
**Issue:** Lambda can describe ANY ASG/instance (`Resource: "*"`)
**Fix:** Scope to bastion-specific ASG ARN
**Complexity:** Medium
**Priority:** HIGH

### Issue #7: Batch ECR Pull Wildcard  
**File:** `terraform/modules/batch/main.tf:118-129`
**Issue:** Batch can pull ANY ECR image (`Resource: "*"`)
**Fix:** Add source ARN condition to specific ECR repo
**Complexity:** Medium
**Priority:** HIGH

### Issue #8: ECS Task Execution KMS Decrypt Too Broad
**File:** `terraform/modules/iam/main.tf:649-700`
**Issue:** Tasks can decrypt ANY KMS secret (`Resource: "*"`)
**Fix:** Restrict to project-specific KMS keys
**Complexity:** High
**Priority:** HIGH

### Issue #9: Batch EC2 Secrets Manager Too Broad
**File:** `terraform/modules/batch/main.tf:113-119`
**Issue:** EC2 instances access ANY secret (`secret:*`)
**Fix:** Scope to `${var.project_name}-*` pattern
**Complexity:** Medium
**Priority:** HIGH

### Issue #10: Lambda Using ECS Security Group
**File:** `terraform/modules/services/main.tf:63-66, 449-451`
**Issue:** API & Algo Lambda tied to ECS SG
**Fix:** Create dedicated Lambda security groups with explicit rules
**Complexity:** High
**Priority:** HIGH

---

## 📋 REMAINING MEDIUM SEVERITY (6 Issues)

| # | Issue | File | Priority |
|---|-------|------|----------|
| 11 | Missing Batch variable descriptions | `variables.tf` | MEDIUM |
| 12 | Lambda code embedded as string | `compute/main.tf:359-368` | MEDIUM |
| 13 | RDS TimescaleDB no validation | `database/main.tf:90-141` | MEDIUM |
| 14 | Loaders module missing validation | `loaders/outputs.tf` | MEDIUM |
| 15 | API CORS includes localhost for prod | `services/variables.tf` | MEDIUM |
| 16 | Cognito password policy weak default | `services/main.tf:326-332` | MEDIUM |

---

## 📝 REMAINING LOW SEVERITY (4 Issues)

| # | Issue | File |
|---|-------|------|
| 17 | EventBridge role output missing | `services/outputs.tf` |
| 18 | Monitoring module undefined variables | `monitoring/main.tf` |
| 19 | Unused VPC variables | `vpc/variables.tf` |
| 20 | Bastion instance profile naming | `compute/variables.tf` |

---

## 📊 Commits So Far

1. `864f988f5` - 40 loaders infrastructure
2. `faf4aa90d` - 8 critical Terraform issues (loaders module)
3. `775a1f50a` - Blocker documentation (Docker image missing)
4. **`f13da8ac3`** - ✅ 4 CRITICAL security fixes (force_destroy, encryption, Multi-AZ, snapshots)
5. **`dce5ffff5`** - ✅ HIGH fix (S3 versioning)

---

## 🎯 Recommended Next Steps

### Immediate (Should do now):
- [ ] Fix remaining 5 HIGH severity IAM issues (#6-#10)
- [ ] These are security/least-privilege issues
- [ ] Est. time: 2-3 hours

### Soon (Before production):
- [ ] Fix MEDIUM severity issues (#11-#16)
- [ ] Est. time: 2 hours

### Later (Polish):
- [ ] Fix LOW severity issues (#17-#20)
- [ ] Est. time: 1 hour

---

## 🔥 What's Still Required for Deployment

**Blocker:** Container image missing (separate from this audit)
- Need Dockerfile.loaders
- Need docker-entrypoint.sh
- Need build GitHub workflow

**Security:** 5 HIGH IAM issues remaining
- Must fix before production deployment
- Could deploy to dev/staging with current state

**Quality:** 6 MEDIUM + 4 LOW issues remaining
- Don't block deployment
- Should fix in next release

---

## Summary

**Status:** 21% complete (5 of 23 issues fixed)

**Critical security fixes:** ✅ DONE (S3, RDS, encryption)  
**High-priority fixes:** ⏳ IN PROGRESS (5 of 6 completed, 5 HIGH remaining)  
**Medium/Low issues:** ⏱️ TODO (10 issues)

**Estimated total time to fix all issues:** 5-6 hours  
**Estimated time to fix HIGH+CRITICAL:** 2-3 hours  

---

**Current branch:** main  
**Commits ready to push:** Yes  
**Ready for deployment:** No (container image still missing, 5 HIGH IAM issues)
