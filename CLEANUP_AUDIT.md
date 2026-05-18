# Comprehensive Cleanup Audit - 2026-05-18

## Summary
Project has **infrastructure mess** (3 VPCs, misconfigured deployment) and **security violations** (.env files with hardcoded creds), but **code quality is good** (all 37 algo files are integrated, loaders are properly tiered).

**Total Issues: 16 | Critical: 5 | Medium: 6 | Minor: 5**

---

## 🔴 CRITICAL ISSUES (Block Deployment)

### 1. Security Violation: 3 .env Files with Hardcoded Credentials
**Severity:** 🔴 CRITICAL SECURITY  
**Files:**
- `./.env.local` → DB_PASSWORD=stocks
- `./webapp/.env.local` → DB_PASSWORD=stocks
- `./webapp/lambda/.env.local` → exists (same)

**Violates:** CLAUDE.md rule #7: "No .env files, hardcoded secrets, or .env.local"  
**Fix Effort:** 30 minutes  
**Action:**
1. Delete all 3 .env files
2. Create .env.example templates with placeholder values
3. Add `*.env.local` to `.gitignore`
4. Document AWS Secrets Manager credential flow in LOCAL_CRED_SETUP.md
5. Verify credential_helper.py loads from AWS Secrets Manager correctly

**Status:** 🔴 NEEDS FIX

---

### 2. Infrastructure Mess: 3 VPCs (Should Be 1)
**Severity:** 🔴 CRITICAL INFRASTRUCTURE  
**Evidence:**
- Git commits: "fix: use Terraform VPC", "debug: check for multiple algo-vpc VPCs"
- Multiple debug commits about VPC, subnet, NACL issues
- Suggests manual creation → Terraform takeover → orphaned resources

**Root Cause:** Infrastructure created ad-hoc, then Terraform tried to manage it  
**Fix Effort:** 3-4 hours (AWS cleanup)  
**Action:**
1. Audit AWS account: list all VPCs and find which is Terraform-managed
2. Delete orphaned VPCs and dependent resources (subnets, SGs, ENIs, NACLs, route tables)
3. Verify Terraform VPC is only one (check terraform/modules/vpc/main.tf)
4. Verify all resources (ECS tasks, RDS, Lambda) reference the right VPC
5. Add VPC tagging requirement: all resources must have `ManagedBy=Terraform`

**Status:** 🔴 NEEDS FIX

---

### 3. Orchestrator Cannot Run Without Manual DB Setup
**Severity:** 🔴 BLOCKS --DRY-RUN  
**Evidence:**
- AUDIT_BLOCKERS.md Blocker #5: orchestrator --dry-run fails with "Database password not available"
- Phase 7 crash if no credentials provided

**Root Cause:** Orchestrator assumes credentials available in environment; no graceful degradation  
**Fix Effort:** 2-3 hours  
**Action:**
1. Add Phase 0: Database health check (optional, fail-open)
2. Skip Phase 7 (reconciliation) if database is down
3. Add --init-only mode: run loaders without trading logic
4. Return meaningful error messages instead of crashes
5. Document when orchestrator can run vs when it needs data

**Status:** 🔴 NEEDS FIX

---

### 4. API Gateway Not Deployed to AWS
**Severity:** 🔴 BACKEND NOT ACCESSIBLE  
**Evidence:**
- AUDIT_BLOCKERS.md Blocker #3: 25+ endpoint handlers exist but API Gateway not deployed
- No Terraform resource for API Gateway integration

**Root Cause:** Lambda functions packaged but not exposed via API Gateway  
**Fix Effort:** 5-6 hours  
**Action:**
1. Check if terraform/modules/services/ has API Gateway definition
2. Create Terraform resource: `aws_apigateway_rest_api`
3. Create resources for: routes, integrations, Lambda permissions, CORS, auth
4. Deploy and verify `/api/health` returns 200
5. Document API endpoint URL in outputs.tf
6. Add integration tests for all 10+ endpoints

**Status:** 🔴 NEEDS FIX

---

### 5. Frontend API_BASE_URL Hardcoded to Localhost
**Severity:** 🔴 FRONTEND BROKEN IN AWS  
**Evidence:**
- `webapp/frontend/src/config/index.js`: `API_BASE_URL = 'http://localhost:3001'`
- No environment variable injection at deploy time

**Root Cause:** Frontend built locally with hardcoded values, not externalized for AWS  
**Fix Effort:** 3-4 hours  
**Action:**
1. Externalize API_BASE_URL via VITE_API_URL environment variable
2. Inject actual API endpoint URL in GitHub Actions during build
3. Create S3 + CloudFront deployment in Terraform
4. Remove hardcoded localhost fallback
5. Deploy frontend and verify API calls work

**Status:** 🔴 NEEDS FIX

---

## 🟠 MEDIUM ISSUES (Degrade Functionality)

### 6. Uncommitted Deletions (Test Cleanup Incomplete)
**Severity:** 🟠 CLEANUP  
**Files Deleted (Not Committed):**
- `tests/integration/test_loader_validation.py` (deleted)
- `utils/monitoring/loader_sla_tracker.py` (deleted)

**Root Cause:** Cleanup attempt left git state dirty  
**Fix Effort:** 5 minutes  
**Action:**
1. Commit deletions: `git add -A && git commit -m "cleanup: remove deprecated test and SLA tracker files"`
2. Verify no orphaned imports after deletion

**Status:** 🟠 NEEDS FIX

---

### 7. Unintegrated Root-Level Test Scripts
**Severity:** 🟠 CODE CLEANUP  
**Files (Should Be Deleted Per CLAUDE.md #2):**
- `bulk_load_prices.py` - diagnostic price loader (use run-all-loaders.py instead)
- `run_full_load.py` - alternative orchestrator (duplicate of run-all-loaders.py)
- `test_loaders.py` - test utility script
- `test_yfinance_basic.py` - diagnostic script
- `validate_all_loaders.py` - validation script

**Rule Violated:** CLAUDE.md #2: "No one-time scripts — delete backfills, diagnostics, utilities immediately"  
**Fix Effort:** 30 minutes  
**Action:**
1. Delete all 5 root scripts (use run-all-loaders.py as single source of truth)
2. If any have unique validation logic, integrate into proper test suite
3. Move any legitimate tests to `tests/` directory

**Status:** 🟠 NEEDS FIX

---

### 8. Missing Integration Tests for API Contract Compliance
**Severity:** 🟠 RISK MISMATCH  
**Evidence:**
- API_CONTRACT.md defines 10+ endpoints
- No tests verify response schemas match contract

**Fix Effort:** 2 hours  
**Action:**
1. Create `tests/test_api_contract_compliance.py`
2. Test each endpoint returns correct columns and structure
3. Run in CI/CD before deployment

**Status:** 🟠 NEEDS FIX

---

### 9. No Terraform Configuration for Frontend Deployment
**Severity:** 🟠 INFRASTRUCTURE  
**Evidence:**
- `webapp/frontend/dist/` exists but no deployment target
- No S3/CloudFront resources defined

**Fix Effort:** 2-3 hours  
**Action:**
1. Create Terraform resources for S3 + CloudFront (or extend terraform/modules/storage)
2. Add deployment pipeline in GitHub Actions
3. Document frontend URL output

**Status:** 🟠 NEEDS FIX

---

### 10. RDS Proxy Configuration Incomplete
**Severity:** 🟠 CONNECTION POOLING  
**Evidence:**
- `terraform/modules/rds-proxy/` exists but unclear if integrated
- Multiple debugging commits about connection issues

**Fix Effort:** 1-2 hours  
**Action:**
1. Verify RDS Proxy is correctly defined and integrated
2. Update Lambda environment to use RDS Proxy endpoint instead of direct RDS
3. Test connection pooling works under load

**Status:** 🟠 NEEDS FIX

---

## 🟡 MINOR ISSUES (Technical Debt)

### 11. Orphaned Documentation Files
**Files:**
- `MONITORING_SETUP.md` - monitoring setup (is it implemented?)
- `RDS_PROXY_SETUP.md` - RDS proxy setup (is it implemented?)
- Multiple PRODUCTION_READY.md, etc.

**Action:** Clean up duplicate docs, consolidate into single architecture guide

---

### 12. Lambda Code Not Packaged with Latest Changes
**Evidence:**
- `terraform/lambda_api.zip` exists but may be stale
- Last modified 2026-05-17, code changed recently

**Action:** Regenerate Lambda zips as part of deployment pipeline

---

### 13. GitHub Actions Workflow Mess
**Files:**
- `manual-trigger-loaders.yml` - shows manual trigger setup
- Multiple workflows may be outdated

**Action:** Consolidate workflows, document deployment pipeline

---

### 14. Code Validator Configuration Unclear
**Evidence:**
- `utils/config_validator.py` modified recently
- Purpose not documented

**Action:** Document what validation is performed and when

---

### 15. Technical Indicators Module Not Integrated into Loaders
**Severity:** 🟡 UNUSED CODE  
**Evidence:**
- `loaders/technical_indicators.py` is new (untracked)
- Not referenced in run-all-loaders.py

**Action:** Verify if this should be:
1. Integrated into an existing loader
2. Added as a new loader to run-all-loaders.py
3. Used by algo/algo_signals.py or filters
4. Or deleted if unnecessary

---

## ✅ What's Actually Good

- **Algo code:** All 37 algo files are properly integrated and imported
- **Data pipeline:** run-all-loaders.py has well-structured 10-tier hierarchy with proper dependencies
- **Orchestrator:** 7-phase architecture is clean and well-documented
- **Test suite:** Comprehensive tests in place (integration, unit, performance, edge cases)
- **Database schema:** Properly designed with appropriate indexes
- **Loaders:** All loaders inherit from OptimalLoader correctly
- **Error handling:** Most modules handle failures gracefully

---

## 🎯 CRITICAL PATH TO WORKING SYSTEM

**Phase 1: Security & Cleanup (1 hour)**
1. ✗ Delete .env files + commit deletions
2. ✗ Delete root test scripts
3. ✗ Fix uncommitted git state

**Phase 2: Local Dev Works (2-3 hours)**
1. ✗ Implement orchestrator graceful DB degradation
2. ✗ Test orchestrator --dry-run works

**Phase 3: Infrastructure (6-8 hours)**
1. ✗ Audit and fix 3 VPCs (AWS cleanup)
2. ✗ Deploy API Gateway
3. ✗ Deploy frontend to S3/CloudFront

**Phase 4: Verification (2 hours)**
1. ✗ Test API endpoints
2. ✗ Test frontend → API communication
3. ✗ End-to-end test

**Total: ~11-15 hours for working deployment**

---

## 📋 Next Actions (Recommended Order)

1. **Start with Phase 1 (security/cleanup)** - 1 hour, unblocks everything
2. **Then Phase 2 (orchestrator fix)** - lets you test locally
3. **Parallel: Phase 3 (infrastructure)** - requires AWS access but independent
4. **Finally: Verification** - proves everything works
