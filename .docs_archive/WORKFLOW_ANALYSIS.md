# Workflow Analysis: Are We Over-Complicated?

**Purpose:** Analyze if we have the right workflows or if we went down a weird path

---

## CURRENT WORKFLOWS (6 total)

### 1. bootstrap-oidc.yml
**Trigger:** `push` on any branch
**Deploys:** template-bootstrap.yml
**Purpose:** Set up GitHub OIDC provider for authentication

**Issues:**
- ❌ Runs on ANY branch push (should be manual only)
- ❌ Runs every time anything is pushed (wasteful)
- ❌ bootstrap only needs to run once at the start
- ❌ Should be workflow_dispatch only

**Verdict:** WRONG. Should be manual trigger only.

---

### 2. deploy-core.yml
**Trigger:** workflow_dispatch (manual only, auto-trigger commented out)
**Deploys:** template-core.yml (VPC)
**Purpose:** Deploy core VPC infrastructure

**Configuration:**
```yaml
on:
  # Disabled to prevent unnecessary runs - enable manually when needed
  # push:
  #   branches: [ "**" ]
  #   paths:
  #     - 'template-core.yml'
  workflow_dispatch:
```

**Analysis:**
- ✅ Manual trigger is correct (VPC changes are risky, rare)
- ✅ Auto-trigger deliberately disabled with comment
- ✅ This is intentional and right

**Verdict:** CORRECT. Manual-only is right for infrastructure.

---

### 3. deploy-app-infrastructure.yml
**Trigger:** `push` on template-app-stocks.yml changes + manual
**Deploys:** template-app-stocks.yml (RDS, ECS cluster, Secrets)
**Purpose:** Deploy shared application infrastructure

**Configuration:**
```yaml
on:
  push:
    branches: [main]
    paths:
      - template-app-stocks.yml
      - .github/workflows/deploy-infrastructure.yml
  workflow_dispatch:
  repository_dispatch:
    types: [deploy-infrastructure]
```

**Issues:**
- ✅ Triggers on template changes (correct)
- ✅ Also manual trigger available (correct)
- ⚠️ Has `repository_dispatch` trigger (unclear purpose, not in paths)
- ⚠️ Trigger references `.github/workflows/deploy-infrastructure.yml` but file is named `deploy-app-infrastructure.yml`

**Verdict:** MOSTLY RIGHT, but has stale references and unclear dispatch trigger.

---

### 4. deploy-app-stocks.yml
**Trigger:** `push` on loader changes + manual
**Deploys:** template-app-ecs-tasks.yml (39 loader ECS tasks)
**Purpose:** Deploy loader infrastructure (very complex workflow)

**Configuration:**
```yaml
on:
  push:
    paths:
      - 'load*.py'
      - 'Dockerfile.*'
      - 'template-app-ecs-tasks.yml'
      - '.github/workflows/deploy-app-stocks.yml'
    branches: [main]
  workflow_dispatch:
    inputs:
      loaders:
        description: 'Comma-separated list of loaders to run (max 5 per batch - NEVER run all 45!)'
```

**Issues:**
- ✅ Triggers on loader changes (correct)
- ✅ Manual trigger with batch controls (correct)
- ⚠️ Very complex workflow (120+ jobs for matrix execution)
- ⚠️ Has internal coordination logic (which loaders to run, batching)
- ⚠️ Depends on deploy-app-infrastructure but doesn't explicitly state it

**Verdict:** COMPLEX but FUNCTIONAL. Could be simplified.

---

### 5. deploy-webapp.yml
**Trigger:** `push` on webapp/ changes + manual
**Deploys:** template-webapp-lambda.yml (API Gateway, Lambda, Cognito)
**Purpose:** Deploy frontend API

**Configuration:**
```yaml
on:  
  push:
    branches: ['*']  # ALL branches, not just main
    paths:
      - 'webapp/**'
      - 'template-webapp-lambda.yml'
      - '.github/workflows/deploy-webapp.yml'
  workflow_dispatch:
```

**Issues:**
- ⚠️ Triggers on ALL branches (not just main)
- ⚠️ This might be intentional (feature branch testing) but unusual
- ✅ Has manual trigger (correct)

**Verdict:** WORKS but UNUSUAL (all branches).

---

### 6. deploy-algo-orchestrator.yml
**Trigger:** `push` on algo_*.py and template changes + manual
**Deploys:** template-algo-orchestrator.yml (Lambda + EventBridge)
**Purpose:** Deploy algo execution engine

**Configuration:**
```yaml
on:
  push:
    paths:
      - 'algo_*.py'
      - 'run_eod_loaders.sh'
      - 'lambda/algo_orchestrator/**'
      - 'template-algo-orchestrator.yml'
      - '.github/workflows/deploy-algo-orchestrator.yml'
    branches: [main]
  workflow_dispatch:
    inputs:
      environment:
        description: 'Deployment environment'
      dry_run:
        description: 'Deploy with --dry-run'
```

**Issues:**
- ✅ Triggers on algo changes (correct)
- ✅ Triggers on algo template changes (correct)
- ✅ Manual trigger with environment control (correct)

**Verdict:** CORRECT.

---

## SUMMARY: Do We Have Extra Workflows?

### What We Have (6)
1. bootstrap-oidc ← OIDC setup
2. deploy-core ← VPC infrastructure
3. deploy-app-infrastructure ← RDS + ECS cluster + Secrets
4. deploy-app-stocks ← Loader tasks
5. deploy-webapp ← Frontend API
6. deploy-algo-orchestrator ← Algo engine

### Do We Need All 6?
**Yes.** Each template has a corresponding workflow because each template:
- Deploys independently
- Has different trigger paths
- Has different deployment logic

### Issues Found

1. **bootstrap-oidc.yml runs on every push** ❌
   - Should be `workflow_dispatch` only (set up once)
   - Current: triggers on `push` to any branch
   - Fix: Change trigger to manual only

2. **deploy-app-infrastructure.yml has stale reference** ⚠️
   - Trigger references `.github/workflows/deploy-infrastructure.yml`
   - File is actually named `deploy-app-infrastructure.yml`
   - Fix: Update trigger path reference

3. **deploy-webapp.yml runs on ALL branches** ⚠️
   - Current: `branches: ['*']` (all branches)
   - Expected: `branches: [main]` (main only)
   - Purpose: Deploy only from main branch
   - Fix: Change to main only (unless feature branches intentional)

4. **Credential Flow (Already identified)** ❌
   - deploy-algo-orchestrator.yml queries exports (should use ImportValue)
   - deploy-webapp.yml queries exports (should use ImportValue)
   - Fix: Use ImportValue in templates instead of parameters

---

## WHAT WENT WEIRD

Looking at the git history, it seems:
1. Initial setup had all workflows
2. Some auto-triggers got commented out (deploy-core)
3. Some workflows got renamed (deploy-infrastructure → deploy-app-infrastructure)
4. Trigger paths didn't get fully updated
5. Webapp trigger was set to all branches (maybe for testing feature branches?)

This explains the "weird path" — **incomplete migration/refactoring**.

---

## RECOMMENDATIONS TO CLEAN UP

### Priority 1 (Critical)
1. **Fix bootstrap-oidc.yml trigger**
   - Change from `push` to `workflow_dispatch`
   - Reason: Should only run once, not on every push

2. **Fix deploy-app-infrastructure.yml trigger path**
   - Update `.github/workflows/deploy-infrastructure.yml` → `.github/workflows/deploy-app-infrastructure.yml`
   - Reason: File was renamed, trigger wasn't updated

### Priority 2 (Good to Have)
3. **Fix deploy-webapp.yml branch trigger**
   - Change from `branches: ['*']` to `branches: [main]`
   - Reason: Production deploy should only run from main
   - Alternative: If feature branch testing is desired, document it

### Priority 3 (Long-term)
4. **Fix credential flow (ImportValue)**
   - Change template-algo-orchestrator to use ImportValue
   - Change template-webapp-lambda to use ImportValue
   - Simplify workflows (remove export queries)

---

## FINAL ASSESSMENT

### Do We Have Too Many Workflows?
**No.** We have the right number (6).

### Do We Have Issues?
**Yes, 4 issues:**
1. bootstrap-oidc runs too often (should be manual)
2. deploy-app-infrastructure has stale path reference
3. deploy-webapp runs on all branches (should be main only)
4. Credential flow is inconsistent (parameters vs ImportValue)

### Are These Easy to Fix?
**Yes.** All fixable in ~30 minutes.

### Are These Blocking?
**No.** Everything works, but it's suboptimal.

---

## CONCLUSION

**We didn't end up with "extra" workflows, we ended up with incomplete cleanup/renaming.**

The issue isn't too many files. The issue is:
- ✅ 6 templates, 6 workflows (right number)
- ❌ Some triggers not updated after renaming
- ❌ Some triggers set to run too often
- ❌ Credential flow uses wrong pattern
- ❌ Some trigger logic is stale

**This is what "weird path" means — incomplete refactoring.**
