# Clean Architecture - The Right Way (100% Only)

**Philosophy:** Single source of truth, no duplication, clear ownership, proper IaC, everything deployable via GitHub Actions.

---

## CORE STACKS (Essential - Always Deployed)

### 1. OIDC Bootstrap (One-Time)
- **Workflow:** `bootstrap-oidc.yml`
- **Template:** `template-bootstrap.yml`
- **Creates:** GitHub OIDC provider, IAM role for GitHub Actions
- **Trigger:** Manual (run once at start)
- **Status:** ✅ Keep as-is

### 2. Core Infrastructure
- **Workflow:** `deploy-core.yml`
- **Template:** `template-core.yml`
- **Creates:** VPC, subnets, Internet Gateway, Bastion, Lambda execution role
- **Trigger:** Auto on push to template-core.yml
- **Dependencies:** None
- **Status:** ✅ Keep as-is

### 3. Application Infrastructure
- **Workflow:** `deploy-infrastructure.yml` (RENAME to `deploy-app-infrastructure.yml`)
- **Template:** `template-app-stocks.yml`
- **Creates:** 
  - RDS database instance
  - Database credentials secret (`stocks-db-secrets-...`)
  - ECS cluster (base infrastructure, not tasks)
  - ECS task execution role
  - Email config secret
  - Algo secrets (Alpaca creds)
- **Exports:** 
  - `StocksApp-SecretArn` (database credentials)
  - `StocksApp-DBEndpoint`, etc.
- **Trigger:** Auto on push to template-app-stocks.yml
- **Dependencies:** deploy-core.yml (needs VPC)
- **Status:** ✅ Keep as-is (rename workflow)

---

## APPLICATION STACKS (Independently Deployable)

### 4. Algo Orchestrator (The Algo Engine)
- **Workflow:** `deploy-algo-orchestrator.yml`
- **Template:** `template-algo-orchestrator.yml`
- **Creates:**
  - Lambda: algo-orchestrator (main execution engine)
  - EventBridge: AlgoScheduleRule (5:30pm ET daily trigger)
  - SNS: AlgoAlertTopic (algo execution alerts)
  - CloudWatch: Logs + alarms
- **References:** Database secret ARN from app-infrastructure
- **Trigger:** Auto on push to algo_*.py or template-algo-orchestrator.yml
- **Dependencies:** deploy-app-infrastructure.yml (needs database secret)
- **Status:** ✅ Keep as-is (just deployed)

### 5. Webapp (Frontend API + Auth)
- **Workflow:** `deploy-webapp.yml`
- **Template:** `template-webapp-lambda.yml`
- **Creates:**
  - Lambda: API functions (Node.js 20)
  - Cognito: User pool + client
  - CloudFront: CDN
  - S3: Frontend hosting
- **References:** Database secret ARN from app-infrastructure
- **Trigger:** Auto on push to webapp/
- **Dependencies:** deploy-app-infrastructure.yml (needs database)
- **Status:** ✅ Keep as-is

### 6. Data Loader Tasks (ECS)
- **Workflow:** `deploy-app-stocks.yml` (should deploy BOTH app-infrastructure AND task definitions)
- **Templates:** 
  - `template-app-stocks.yml` (cluster + base)
  - `template-app-ecs-tasks.yml` (task definitions + services)
- **Creates:** ECS task definitions + services for all 39 loaders
- **References:** Database secret, ECS cluster from app-infrastructure
- **Trigger:** Auto on push to load*.py or Dockerfile.*
- **Dependencies:** deploy-app-infrastructure.yml (needs cluster + secrets)
- **Status:** ⚠️ CURRENTLY ORPHANED - Need to wire this up
- **Action:** Integrate into deploy-app-stocks.yml workflow

---

## SCHEDULED EXECUTION

**What We Have:**
- Algo runs daily at 5:30pm ET (via EventBridge in template-algo-orchestrator.yml) ✅

**What We Need:**
- Loaders scheduled on their own schedule (via loaders' internal scheduling, not EventBridge)
- OR: Create a separate workflow for loader scheduling (if needed)

**Current Status:**
- ❌ `template-eventbridge-scheduling.yml` - ORPHANED, DELETE IT
  - Its functionality either belongs in template-algo-orchestrator.yml or loader scheduling
  - No workflow deploys it, so it's dead code

---

## OPTIMIZATION STACKS (Optional, Tier 1+)

### Tier 1 Optimizations (Optional)
- **Workflow:** `deploy-tier1-optimizations.yml`
- **Templates:**
  - `template-tier1-api-lambda.yml` (HTTP API migration)
  - `template-tier1-cost-optimization.yml` (S3 tiering, CloudWatch sampling, VPC endpoints)
- **Status:** ⚠️ Optional enhancement
- **Decision Needed:** Keep or remove?

---

## WHAT TO DELETE

**Delete These - They're Dead Code:**
1. ❌ `template-eventbridge-scheduling.yml` - Orphaned, duplicates algo orchestrator scheduling
2. ❌ `template-lambda-phase-c.yml` - Phase C experiment, incomplete
3. ❌ `template-step-functions-phase-d.yml` - Phase D experiment, incomplete
4. ❌ `template-phase-e-dynamodb.yml` - Phase E experiment, incomplete
5. ❌ `template-optimize-database.yml` - Optimization experiment, orphaned

**Workflows to Delete or Consolidate:**
1. ❌ No dedicated `optimize-data-loading.yml` workflow (unclear purpose, incomplete)
2. ❌ No `test-automation.yml`, `deploy-billing.yml`, `manual-reload-data.yml`, `pr-testing.yml`, `gemini-code-review.yml` (out of scope)
3. ❌ Fix `algo-verify.yml` (currently broken - tries to test DB in CI without database)

---

## CLEAN WORKFLOW MATRIX

| Workflow | Template | Purpose | Trigger | Status |
|----------|----------|---------|---------|--------|
| bootstrap-oidc.yml | template-bootstrap.yml | GitHub OIDC setup | Manual (once) | ✅ Keep |
| deploy-core.yml | template-core.yml | VPC/networking | Auto | ✅ Keep |
| deploy-app-infrastructure.yml | template-app-stocks.yml | RDS/ECS base/secrets | Auto | ✅ Keep (rename) |
| deploy-app-stocks.yml | + template-app-ecs-tasks.yml | Data loader tasks | Auto | ⚠️ FIX (add tasks) |
| deploy-webapp.yml | template-webapp-lambda.yml | Frontend API | Auto | ✅ Keep |
| deploy-algo-orchestrator.yml | template-algo-orchestrator.yml | Algo engine | Auto | ✅ Keep |
| deploy-tier1-optimizations.yml | tier1 templates | Cost/perf optimizations | Manual | ? (keep or delete) |

**Total After Cleanup:** 6-7 workflows, 7-8 templates (from current 9 workflows, 14 templates)

---

## CONSOLIDATION DECISIONS NEEDED

1. **Should we keep Tier 1 optimizations?**
   - If yes: Finalize and integrate
   - If no: Delete entirely

2. **How do loaders get scheduled?**
   - Option A: Each loader has its own cron (local scheduling in load*.py)
   - Option B: EventBridge with one central rule (would need scheduler template)
   - Option C: Manual trigger via GitHub Actions

3. **One SNS topic or per-service?**
   - Option A: One unified `alerts` topic for all notifications
   - Option B: Keep separate (algo, loaders, webapp, etc.)
   - Recommendation: **One unified topic** (cleaner, easier to subscribe to)

4. **Verification workflow (algo-verify.yml)?**
   - Option A: Delete (unnecessary duplication)
   - Option B: Fix with PostgreSQL service container in CI
   - Recommendation: **Delete** (deployment itself is the verification)

---

## IMPLEMENTATION ORDER

1. **Delete all Phase C/D/E templates and orphaned files**
   - `template-eventbridge-scheduling.yml`
   - `template-lambda-phase-c.yml`
   - `template-step-functions-phase-d.yml`
   - `template-phase-e-dynamodb.yml`
   - `template-optimize-database.yml`

2. **Consolidate ECS task definitions**
   - Integrate `template-app-ecs-tasks.yml` into `deploy-app-stocks.yml` workflow
   - OR keep separate if intentional (which is OK)

3. **Rename for clarity**
   - `deploy-infrastructure.yml` → `deploy-app-infrastructure.yml`

4. **Simplify verification**
   - Delete `algo-verify.yml` (deployment is the test)

5. **Unify alerts** (if needed)
   - Decide: one SNS topic or multiple?

6. **Test the clean setup**
   - Verify all 6-7 workflows work correctly

---

## FINAL STATE (Right Way, 100% Only)

```
✅ Essential Core (3):
   - bootstrap-oidc.yml
   - deploy-core.yml
   - deploy-app-infrastructure.yml

✅ Applications (3):
   - deploy-app-stocks.yml (with integrated ECS tasks)
   - deploy-webapp.yml
   - deploy-algo-orchestrator.yml

? Optional (1):
   - deploy-tier1-optimizations.yml (keep or delete?)

❌ Deleted (11 files):
   - 5 orphaned templates (Phase C/D/E, eventbridge, optimize-db)
   - 6+ unwanted workflows (billing, gemini, pr-testing, etc.)
```

**Result:** Clean, organized, purposeful, NO SLOP.
