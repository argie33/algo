# Core Workflows — What Actually Matters

---

## THE 5 REAL WORKFLOWS (Everything else should be IN these)

### 1. bootstrap-oidc.yml (53 lines)
**Purpose:** One-time GitHub OIDC setup  
**Trigger:** On setup-github-oidc.yml change  
**Status:** ✅ DONE, keep for reference only  
**Change needed:** None

---

### 2. deploy-infrastructure.yml (165 lines)
**Purpose:** Deploy base infrastructure (RDS, networking, core AWS)  
**Trigger:** On template-app-stocks.yml change  
**Current scope:** RDS database  
**What SHOULD be here:**
- ✅ RDS database
- ✅ CloudFormation base stack
- ⚠️ SHOULD ADD: VPC Endpoints (currently in deploy-tier1-optimizations.yml)
- ⚠️ SHOULD ADD: CloudWatch retention (currently in deploy-tier1-optimizations.yml)

**Why separate?** Makes no sense. These ARE infrastructure.

---

### 3. deploy-core.yml (80 lines)
**Purpose:** Deploy core AWS resources  
**Trigger:** Manual dispatch  
**Current scope:** S3, CloudWatch, IAM basics  
**Status:** ✅ Works, keep as-is

---

### 4. deploy-webapp.yml (688 lines)
**Purpose:** Deploy Lambda API + React frontend  
**Trigger:** On webapp/** changes  
**Current scope:** Lambda + S3 + CloudFront + Cognito  
**What SHOULD be here:**
- ✅ Lambda API
- ✅ S3 + CloudFront frontend
- ⚠️ SHOULD ADD: HTTP API migration (currently in deploy-tier1-optimizations.yml)
- ⚠️ SHOULD ADD: SnapStart (currently in deploy-tier1-optimizations.yml)

**Why separate?** Makes no sense. These ARE webapp optimizations.

---

### 5. deploy-loaders.yml (DOESN'T EXIST YET - SHOULD EXIST)
**Purpose:** Deploy data loaders to AWS  
**Trigger:** On load*.py change OR manual dispatch  
**What SHOULD be here:**
- Build Docker image (using Dockerfile.loader)
- Push to ECR
- Register ECS task definition
- ✅ SHOULD ADD: TimescaleDB (currently in optimize-data-loading.yml)
- ✅ SHOULD ADD: Multi-source fallback (currently in optimize-data-loading.yml)

**Why missing?** Because deploy-app-stocks.yml is broken, so nobody created a replacement.

---

## CURRENT GARBAGE (Why they exist)

| Workflow | Lines | Should Be In | Status |
|----------|-------|--------------|--------|
| deploy-tier1-optimizations.yml | 215 | deploy-infrastructure.yml + deploy-webapp.yml | ❌ FRAGMENTATION |
| optimize-data-loading.yml | 134 | deploy-loaders.yml | ❌ FRAGMENTATION |
| deploy-app-stocks.yml | 1,787 | REPLACE with deploy-loaders.yml | ❌ BROKEN |
| algo-verify.yml | 128 | Delete or move to cron | ⚠️ UNNECESSARY |

---

## THE SOLUTION

### Consolidate into 5 core workflows:

**deploy-infrastructure.yml (165 → 250 lines)**
- RDS database ✅
- CloudFormation base ✅
- **ADD:** VPC Endpoints (from tier1)
- **ADD:** CloudWatch retention (from tier1)
- **ADD:** S3 Lifecycle (from tier1)

**deploy-webapp.yml (688 → 800 lines)**
- Lambda API ✅
- S3 + CloudFront frontend ✅
- **ADD:** HTTP API migration (from tier1)
- **ADD:** SnapStart (from tier1)

**deploy-loaders.yml (NEW, ~300 lines)**
- Detect changed loaders
- Build Docker (Dockerfile.loader)
- Push to ECR
- Register ECS tasks
- **ADD:** TimescaleDB (from optimize-data-loading)
- **ADD:** Multi-source fallback (from optimize-data-loading)

**deploy-core.yml** (80 lines)
- Keep as-is ✅

**bootstrap-oidc.yml** (53 lines)
- Keep as reference only ✅

---

## FILES TO DELETE

```
❌ deploy-tier1-optimizations.yml    → Consolidate into deploy-infrastructure.yml + deploy-webapp.yml
❌ optimize-data-loading.yml         → Consolidate into deploy-loaders.yml
❌ deploy-app-stocks.yml             → REPLACE with clean deploy-loaders.yml
❌ algo-verify.yml                   → Delete (runs every push, probably fails)
```

---

## TOTAL REDUCTION

| Metric | Current | After | Saved |
|--------|---------|-------|-------|
| Workflows | 8 | 5 | 3 |
| Lines of YML | ~2,500 | ~2,000 | 500 |
| Separate manual triggers | 2 (tier1, optimize) | 0 | Clear flow |
| Confusion | Maximum | Minimal | ✅ |

---

## Why This Happened (The Real Problem)

Someone created **new YML files instead of extending existing ones**:

1. Wanted to optimize infrastructure → Created `deploy-tier1-optimizations.yml` instead of extending `deploy-infrastructure.yml`
2. Wanted to optimize data loading → Created `optimize-data-loading.yml` instead of creating/extending `deploy-loaders.yml`
3. Wanted to deploy loaders → Created `deploy-app-stocks.yml` (broken) instead of fixing it or creating clean replacement

**Result:** Workflows are scattered, confusing, and don't work.

**The fix:** Consolidate into 5 core workflows, each with ONE clear purpose.

