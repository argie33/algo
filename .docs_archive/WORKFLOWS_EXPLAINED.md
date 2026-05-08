# GitHub Actions Workflows — What Each One Actually Does

**Problem:** 13 workflows, many overlapping or unclear. Let's map out the reality.

---

## WORKFLOWS GROUPED BY PURPOSE

### 🔴 PRIMARY CONCERN: DATA LOADERS (3 overlapping workflows!)

| Workflow | Purpose | Triggers | Status | Problem |
|----------|---------|----------|--------|---------|
| **deploy-app-stocks.yml** (1787 lines) | Build Docker images for loaders, deploy to ECS via CloudFormation | On `load*.py` push OR manual dispatch | ❓ UNCLEAR | Most complex, uses Phase C/D/E templates, unclear if actually works |
| **manual-reload-data.yml** (123 lines) | Manually trigger ECS tasks for price/signal loaders | Manual dispatch only | ⚠️ BRITTLE | Hardcoded subnet/security group IDs, only runs 2 loaders |
| **optimize-data-loading.yml** (134 lines) | Run optimization features (TimescaleDB, multi-source fallback) | Manual dispatch only | ⚠️ INCOMPLETE | Says it will run features but doesn't actually execute loaders |

**THE MESS:** All three claim to do similar things, but none are clearly running loaders on a schedule. Data is stale since 2026-05-01.

---

### 🔵 INFRASTRUCTURE / DEPLOYMENT (5 workflows)

| Workflow | Purpose | Triggers | Status |
|----------|---------|----------|--------|
| **deploy-infrastructure.yml** | Deploy RDS + base infra via CloudFormation | On `template-app-stocks.yml` change | ✅ Working |
| **deploy-webapp.yml** | Deploy Lambda API + React frontend | On `webapp/**` changes | ✅ Working |
| **deploy-core.yml** | Deploy core AWS setup | Manual dispatch | ✅ Working |
| **deploy-tier1-optimizations.yml** | Deploy cost/perf optimizations (VPC endpoints, HTTP API, etc) | Manual dispatch | ✅ Working |
| **bootstrap-oidc.yml** | One-time GitHub OIDC setup | On `setup-github-oidc.yml` change | ✅ Done once |

**Assessment:** These work, but `deploy-app-stocks.yml` stands out as trying to do too much.

---

### 🟡 VERIFICATION / TESTING (4 workflows)

| Workflow | Purpose | Triggers | Status | Problem |
|----------|---------|----------|--------|---------|
| **algo-verify.yml** (128 lines) | Verify algo components + data integrity | On `algo_*.py`, `load*.py`, webapp changes | ✅ Running | But loaders aren't running so patrol likely fails |
| **test-automation.yml** (566 lines) | Comprehensive test suite (unit, integration, e2e, etc) | On `loaddata`/`develop` branches | ⚠️ INACTIVE | Triggers on branches that don't exist — never runs |
| **pr-testing.yml** (437 lines) | PR-specific testing | On PR to main | ✅ Runs | Minimal, mostly placeholders |
| **gemini-code-review.yml** (45 lines) | AI code review | On PR | ⚠️ MINIMAL | Just comments, unclear if useful |

**Assessment:** `test-automation.yml` is dead code (triggers on non-existent branches). Others are minimal/placeholders.

---

### 🟢 UTILITY / ONE-OFFS (3 workflows)

| Workflow | Purpose | Triggers | Status |
|----------|---------|----------|--------|
| **deploy-billing.yml** | Billing alerts | On push | ⚠️ Not clear if active |
| **algo-verify.yml** | (Also does data patrol) | On push | See above |

---

## THE CORE PROBLEM

### We Have THREE Conflicting Approaches to Running Loaders:

**Approach 1: `deploy-app-stocks.yml` (Auto-build on code change)**
```
Code change → Detect changed loaders → Build Docker → Push to ECR → 
  Deploy CloudFormation with Phase C/D/E templates → ??? 
```
- **Complexity:** 1787 lines, tries to detect, build, deploy
- **Status:** ❓ UNCLEAR — doesn't appear to be running (data is stale)
- **Problem:** Uses Phase C/D/E templates which are experimental

**Approach 2: `manual-reload-data.yml` (Manual trigger)**
```
User triggers → Run existing ECS tasks directly
```
- **Complexity:** 123 lines, simple
- **Status:** ⚠️ BRITTLE — hardcoded IDs (subnet-0142dc004c9fc3e0c, sg-0519c564d78cca3de)
- **Problem:** Only runs 2 loaders, not all 41

**Approach 3: `optimize-data-loading.yml` (Features, not execution)**
```
User triggers → Enable TimescaleDB / multi-source fallback
```
- **Complexity:** 134 lines
- **Status:** ⚠️ INCOMPLETE — says what it'll do but doesn't actually run loaders
- **Problem:** No actual loader execution

### What We DON'T Have:
- ❌ Scheduled execution (EventBridge not deployed)
- ❌ Clear understanding of which approach is "correct"
- ❌ Evidence that loaders are actually running in AWS
- ❌ A simple, single source of truth for "how do I run a loader?"

---

## ROOT CAUSE

Looking at commit history:
```
c7eaa2e3a (2026-05-04 08:43) Trigger GitHub Actions loader deployment workflow
  → Modified loadpricedaily.py
  → Expected to trigger "detect-changes-build-deploy-ecs-loaders" workflow
  → That workflow DOESN'T EXIST (I was creating it, user said it was wrong)
```

So someone/something was trying to trigger a loader deployment workflow that wasn't deployed. The system is confused.

---

## WHAT SHOULD HAPPEN

Per LOADER_SCHEDULE.md and CLAUDE.md, loaders should run:
```
Intraday (90min):  loadlatestpricedaily
EOD (5:30pm ET):   All Phase 2-5 daily loaders
Weekly (Sat 8am):  Phase 2-5 weekly + scoring
Monthly (1st Sat): Phase 2-5 monthly + factor metrics
Quarterly:         Fundamentals + earnings
```

**Currently:** None of this is happening.

---

## RECOMMENDED CLEANUP

### 🗑️ Delete (Dead Code)
- `test-automation.yml` — triggers on non-existent branches (loaddata, develop)
- `manual-reload-data.yml` — hardcoded IDs, only 2 loaders, fragile

### 🔄 Consolidate
- Combine `deploy-app-stocks.yml` (build/deploy) + what works from `manual-reload-data.yml` → one clean loader workflow

### 🚀 Create
- Proper EventBridge scheduling (deploy template-eventbridge-scheduling.yml)
- OR simple Lambda-based scheduler
- Single, clear "run a loader" mechanism

### 📋 Clarify
- What are Phase C/D/E templates for? (Keep or delete?)
- Why does `optimize-data-loading.yml` not actually execute loaders?
- What is `algo-verify.yml` doing (it seems to run on every push)?

---

## BOTTOM LINE

**We have too many, half-working workflows trying to do the same thing, and NOTHING is actually running loaders on a schedule.**

That's why data is 3 days stale.
