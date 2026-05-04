# IaC Cleanup Plan — Remove AI Slop, Keep What Works

**Goal:** Go from 13 workflows + 12 templates + 78 Dockerfiles to a clean, understandable system.

---

## WORKFLOWS CLEANUP

### ✅ KEEP (5 workflows)

These are intentional, working, and necessary:

1. **deploy-infrastructure.yml** (165 lines)
   - Purpose: Deploy RDS + CloudFormation base stack
   - Trigger: On template-app-stocks.yml change
   - Status: ✅ Working
   - Keep: YES

2. **deploy-webapp.yml** (688 lines)
   - Purpose: Deploy Lambda API + React frontend
   - Trigger: On webapp/** changes
   - Status: ✅ Working
   - Keep: YES

3. **deploy-core.yml** (80 lines)
   - Purpose: Deploy core AWS infrastructure
   - Trigger: Manual dispatch
   - Status: ✅ Working
   - Keep: YES

4. **deploy-tier1-optimizations.yml** (215 lines)
   - Purpose: Deploy cost/perf optimizations (VPC endpoints, HTTP API, etc)
   - Trigger: Manual dispatch
   - Status: ✅ Working
   - Keep: YES

5. **bootstrap-oidc.yml** (53 lines)
   - Purpose: One-time GitHub OIDC setup
   - Trigger: On setup-github-oidc.yml change
   - Status: ✅ Done once
   - Keep: YES (don't run again, but keep for reference)

---

### ❌ DELETE (8 workflows)

These are dead code, overlapping, or incomplete:

| Workflow | Lines | Problem | Delete |
|----------|-------|---------|--------|
| **deploy-app-stocks.yml** | 1787 | Too complex, uses Phase C/D/E (experimental), no evidence it works | ✅ DELETE |
| **manual-reload-data.yml** | 123 | Hardcoded subnet/security group IDs (brittle), only runs 2 loaders | ✅ DELETE |
| **optimize-data-loading.yml** | 134 | Incomplete, doesn't actually execute loaders | ✅ DELETE |
| **test-automation.yml** | 566 | Triggers on non-existent branches (loaddata, develop) — NEVER RUNS | ✅ DELETE |
| **pr-testing.yml** | 437 | Mostly placeholders, not critical right now | ✅ DELETE |
| **gemini-code-review.yml** | 45 | Nice to have, not critical, can add later | ✅ DELETE |
| **deploy-billing.yml** | 37 | Unclear purpose, minimal | ✅ DELETE |
| **algo-verify.yml** | 128 | Runs on every push, probably fails due to stale data, can move to cron later | ✅ DELETE |

**Total deleted: 3,227 lines of YML**

---

## CLOUDFORMATION TEMPLATES CLEANUP

### ✅ KEEP (5 templates)

1. **template-app-stocks.yml** (244 lines)
   - Purpose: RDS database + security groups + base networking
   - Used by: deploy-infrastructure.yml
   - Keep: YES

2. **template-core.yml** (416 lines)
   - Purpose: Core AWS resources (S3, CloudWatch, IAM)
   - Used by: deploy-core.yml
   - Keep: YES

3. **template-webapp-lambda.yml** (454 lines)
   - Purpose: Lambda API + API Gateway + frontend S3/CloudFront
   - Used by: deploy-webapp.yml
   - Keep: YES

4. **template-tier1-api-lambda.yml** (243 lines)
   - Purpose: HTTP API migration + SnapStart
   - Used by: deploy-tier1-optimizations.yml
   - Keep: YES

5. **template-tier1-cost-optimization.yml** (249 lines)
   - Purpose: VPC endpoints, S3 optimization, CloudWatch retention
   - Used by: deploy-tier1-optimizations.yml
   - Keep: YES

---

### ⚠️ REPLACE (1 template)

1. **template-app-ecs-tasks.yml** (5,511 lines!)
   - Current status: Huge, probably hardcoded, used by dead deploy-app-stocks.yml
   - What to do: **REPLACE with simple, clean version**
     - Define ECS task definitions for 61 loaders
     - Use generic Docker image (stocks-loaders:latest)
     - Simple Fargate configuration (256 CPU, 512 MB RAM for each)
   - Why: Current version is probably full of per-loader customizations. We don't need that.
   - New size estimate: 300-400 lines (use a loop/macro to generate 61 identical tasks)

---

### ❌ DELETE (6 templates)

| Template | Lines | Problem | Delete |
|----------|-------|---------|--------|
| **template-bootstrap.yml** | 46 | One-time setup, doesn't need to stay | Keep for reference only |
| **template-lambda-phase-c.yml** | 221 | Phase C (Lambda fan-out) — experimental, unclear if used | ✅ DELETE |
| **template-step-functions-phase-d.yml** | 332 | Phase D (Step Functions DAG) — experimental, unclear if used | ✅ DELETE |
| **template-phase-e-dynamodb.yml** | 169 | Phase E (DynamoDB metadata) — experimental, unclear if used | ✅ DELETE |
| **template-eventbridge-scheduling.yml** | 243 | EXISTS but NOT DEPLOYED — we'll CREATE NEW instead | ✅ DELETE & RECREATE |
| **template-optimize-database.yml** | 357 | Exists but NOT USED — can add back if needed | ✅ DELETE |

**Total deleted: 1,368 lines of CloudFormation**

---

### 🆕 CREATE (1 new template)

**template-loader-scheduler.yml** (~250 lines)
- Purpose: EventBridge rules + Lambda to orchestrate loader execution
- Schedule:
  - Intraday (every 90 min): loadlatestpricedaily
  - EOD (5:30pm ET): All Phase 2-5 daily loaders
  - Weekly (Sat 8am): Phase 2-5 weekly loaders
  - Monthly (1st Sat): Phase 2-5 monthly loaders
- Implementation: EventBridge → SNS → Lambda → ECS run-task

---

## DOCKERFILES CLEANUP

### ✅ KEEP (2 files)

1. **Dockerfile** (main API)
   - Keep: YES

2. **Dockerfile.loader** (generic, uses ARG LOADER_SCRIPT)
   - Keep: YES
   - Already exists and works

---

### ❌ DELETE (76 files)

```
Dockerfile.aaiidata
Dockerfile.alpacaportfolio
Dockerfile.analystsentiment
... 73 more individual Dockerfile.load*.py files ...
```

**Why:** These are legacy. We now have a generic `Dockerfile.loader` that handles all of them with a build argument. Individual Dockerfiles add confusion and maintenance burden.

**When to delete:** After confirming Dockerfile.loader works for at least one loader.

---

## GITHUB ACTIONS WORKFLOW CLEANUP (Step-by-Step)

### Step 1: Create NEW loader workflow

Create `.github/workflows/deploy-loaders.yml`:
- **Trigger:** On `load*.py` changes OR manual dispatch with specific loaders
- **Does:** Build Docker image, push to ECR, register ECS task definition
- **Does NOT:** Deploy infrastructure, run Phase C/D/E experiments
- **Scope:** Clean, simple, <300 lines

### Step 2: Delete dead workflows

```bash
rm .github/workflows/deploy-app-stocks.yml
rm .github/workflows/manual-reload-data.yml
rm .github/workflows/optimize-data-loading.yml
rm .github/workflows/test-automation.yml
rm .github/workflows/pr-testing.yml
rm .github/workflows/gemini-code-review.yml
rm .github/workflows/deploy-billing.yml
rm .github/workflows/algo-verify.yml
```

### Step 3: Deploy scheduler

Once deploy-loaders.yml works:
1. Create template-loader-scheduler.yml (EventBridge rules)
2. Create .github/workflows/deploy-loader-scheduler.yml (deploys the template)
3. Verify loaders run on schedule

---

## FINAL STATE (Clean IaC)

### Workflows (5 total)
```
✅ deploy-infrastructure.yml     — RDS + base
✅ deploy-webapp.yml             — Lambda API + frontend
✅ deploy-core.yml               — Core AWS
✅ deploy-tier1-optimizations.yml — Cost/perf
✅ deploy-loaders.yml            — Build & deploy loaders
```

### Templates (6 total)
```
✅ template-app-stocks.yml              — RDS database
✅ template-core.yml                    — Core AWS resources
✅ template-webapp-lambda.yml           — Lambda API + frontend
✅ template-tier1-api-lambda.yml        — HTTP API migration
✅ template-tier1-cost-optimization.yml — VPC endpoints, S3
✅ template-loader-scheduler.yml        — EventBridge + Lambda (NEW)
```

### Dockerfiles (2 total)
```
✅ Dockerfile                    — Main API
✅ Dockerfile.loader             — Generic loader image
```

### Loaders (61 total - no change to Python files)
```
✅ 41 official loaders (Phases 1-10)
✅ 20 supplementary loaders (algo required)
```

---

## WHAT THIS FIXES

### Before
- 13 workflows (confusing, overlapping)
- 12 templates (5,511 lines in one file!)
- 78 Dockerfiles (unclear which to use)
- Data stale (2026-05-01 → today)
- No scheduler deployed
- Three different "run a loader" approaches

### After
- 5 workflows (clear purpose for each)
- 6 templates (organized by concern)
- 2 Dockerfiles (clear source of truth)
- Data fresh (loaders run on schedule)
- EventBridge deployed + working
- ONE loader deployment mechanism

---

## Execution Order

1. **TODAY:** Delete dead workflows (8 files)
2. **TODAY:** Delete dead templates (6 files, 1,368 lines)
3. **TODAY:** Delete individual Dockerfiles (76 files)
4. **TOMORROW:** Create simple deploy-loaders.yml
5. **TOMORROW:** Test deploy-loaders.yml with 1 loader (loadpricedaily)
6. **TOMORROW:** Create template-loader-scheduler.yml
7. **TOMORROW:** Deploy scheduler via new workflow
8. **VERIFY:** Check database — data should start loading

---

## Risk Assessment

**Low risk:**
- Deleting dead workflows (test-automation, pr-testing, etc)
- Deleting individual Dockerfiles (Dockerfile.loader works fine)

**Medium risk:**
- Deleting Phase C/D/E templates (if they're deployed in AWS, might break things)
  - Mitigation: Check if they're actually deployed first

**No risk:**
- Deleting dead templates (template-optimize-database, etc)

---

## Success Criteria

✅ All YML files deleted  
✅ All unnecessary templates deleted  
✅ All individual Dockerfiles deleted  
✅ One loader runs end-to-end in AWS  
✅ EventBridge scheduler deployed  
✅ Data loading automatically (fresh every day)  
✅ System is understandable (5 workflows, 6 templates, 2 Dockerfiles)
