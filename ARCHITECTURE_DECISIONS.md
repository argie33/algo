# Stock Analytics Platform - Architecture Decisions & Design

**Last Updated:** May 4, 2026

## The Big Picture

This document explains the infrastructure architecture decisions and why they were made. It's not just what we have, but **why we have it this way**.

---

## 1. Deployment Architecture: 6 Workflows by Responsibility

### Why Not Consolidate Everything?

We have **6 separate GitHub Actions workflows**, one per CloudFormation template. This could be consolidated to 2-4 super-workflows, but our 6-workflow design is intentional.

**Our Structure:**
```
bootstrap-oidc.yml      → template-bootstrap.yml       (OIDC provider, run once)
deploy-core.yml         → template-core.yml             (VPC infrastructure)
deploy-app-infrastructure.yml → template-app-stocks.yml (RDS, ECS, Secrets)
deploy-app-stocks.yml   → template-app-ecs-tasks.yml   (39 loader tasks)
deploy-webapp.yml       → template-webapp-lambda.yml    (Frontend API)
deploy-algo-orchestrator.yml → template-algo-orchestrator.yml (Algo engine)
```

### The Trade-off Decision

| Factor | 6 Workflows | Consolidated (2-4) |
|--------|-------------|-------------------|
| **Deployment Speed** | ✅ Each workflow deploys independently | ❌ All must deploy together |
| **Change Frequency** | ✅ Bootstrap rarely, core rarely, infra occasional, apps frequent | ❌ Bootstrap forced to deploy with apps |
| **Developer Experience** | ✅ Clear which workflow to run | ⚠️ Must know the structure |
| **Safety** | ⚠️ Requires discipline on ordering | ✅ Enforced by dependencies |
| **Maintenance** | ⚠️ 6 files to understand | ✅ Fewer files |

**Decision: Keep 6 workflows.** Our use case has drastically different change frequencies (VPC changes monthly, loader code changes daily). Consolidating would waste compute and increase risk.

---

## 2. Credential Flow: CloudFormation Exports via ImportValue

### The Right Pattern for This Architecture

**Rule:** All cross-stack values go through CloudFormation exports, imported via `!ImportValue` in templates.

```
template-app-stocks.yml (creates RDS, ECS, Secrets)
  ↓ Exports:
    - StocksApp-SecretArn                (DB credentials)
    - StocksApp-AlgoSecretsSecretArn     (Alpaca API keys)
    - StocksApp-DBEndpoint               (RDS hostname)
    - StocksApp-DBPort                   (RDS port)
    - StocksApp-DBName                   (Database name)
    - StocksApp-ClusterArn               (ECS cluster)
    - StocksApp-EcsTaskExecutionRoleArn  (ECS permissions)

template-app-ecs-tasks.yml, template-algo-orchestrator.yml, template-webapp-lambda.yml
  ↓ Import via:
    DATABASE_SECRET_ARN: !ImportValue StocksApp-SecretArn
    ALPACA_API_KEY_SECRET_ARN: !ImportValue StocksApp-AlgoSecretsSecretArn
```

### Why This Is Better Than Workflow-Level Queries

**Before (❌ Anti-pattern):**
```bash
# In deploy-webapp.yml workflow:
SECRET_ARN=$(aws cloudformation list-exports --query "Exports[?Name=='StocksApp-SecretArn'].Value")
aws cloudformation deploy ... --parameter-overrides DatabaseSecretArn=$SECRET_ARN
```

**After (✅ Correct pattern):**
```yaml
# In template-webapp-lambda.yml:
Resources:
  MyFunction:
    Environment:
      Variables:
        DATABASE_SECRET_ARN: !ImportValue StocksApp-SecretArn
```

**Benefits of ImportValue:**
1. **CloudFormation knows the dependency** — If StocksApp-SecretArn doesn't exist, deployment fails immediately
2. **No workflow complexity** — Workflows don't need business logic
3. **Single source of truth** — The template declares what it needs
4. **Automatic syncing** — If export value changes, template gets new value
5. **Type-safe** — CloudFormation validates the export exists

---

## 3. Trigger Patterns: Manual for Infrastructure, Auto for Applications

### Rule by Category

| Category | Trigger | Frequency | Risk | Reasoning |
|----------|---------|-----------|------|-----------|
| **bootstrap-oidc.yml** | Manual (`workflow_dispatch`) | Once at start | Low | One-time setup, no need to re-run |
| **deploy-core.yml** | Manual (`workflow_dispatch`) | ~monthly | High | VPC changes affect everything |
| **deploy-app-infrastructure.yml** | Auto on `template-app-stocks.yml` change | Occasional | Medium | RDS/ECS changes are infrastructure |
| **deploy-app-stocks.yml** | Auto on loader code change | Daily | Low | Loaders are isolated changes |
| **deploy-webapp.yml** | Auto on `webapp/` or template change | Daily | Low | Frontend is isolated |
| **deploy-algo-orchestrator.yml** | Auto on `algo_*.py` or template change | Weekly | Low | Algo is isolated |

### The Philosophy

- **Manual triggers** for infrastructure decisions (setup, VPC, database, cluster)
- **Auto triggers** for application changes (code, config, templates for apps)
- **Main branch only** for auto-deploys (feature branches can trigger manually)

---

## 4. Workflow Trigger Fixes (Critical Bugs Fixed)

### Issue 1: bootstrap-oidc.yml Ran on Every Push ❌ → Fixed ✅

**Before:**
```yaml
on:
  push:
    branches: [ "**" ]  # Every branch, every push
```

**Why wrong:** Bootstrap runs once at infrastructure start. Running it on every push is:
- Wasteful (GitHub Actions minutes)
- Risky (could interfere with active deployments)
- Unnecessary (OIDC already created)

**After:**
```yaml
on:
  workflow_dispatch:  # Manual only
```

---

### Issue 2: deploy-app-infrastructure.yml Trigger Referenced Old Filename ❌ → Fixed ✅

**Before:**
```yaml
on:
  push:
    paths:
      - template-app-stocks.yml
      - .github/workflows/deploy-infrastructure.yml  # File doesn't exist! (renamed to deploy-app-infrastructure.yml)
```

**Why wrong:** Workflow was renamed but trigger references old filename. Result: **Changing the workflow file doesn't re-trigger itself.**

**After:**
```yaml
on:
  push:
    paths:
      - template-app-stocks.yml
      - .github/workflows/deploy-app-infrastructure.yml  # Correct name
```

---

### Issue 3: deploy-webapp.yml Ran on All Branches ❌ → Fixed ✅

**Before:**
```yaml
on:
  push:
    branches:
      - '*'  # ALL branches
```

**Why wrong:** Production deployments should only come from main. Feature branches shouldn't deploy infrastructure.

**After:**
```yaml
on:
  push:
    branches:
      - main  # Main only
```

---

### Issue 4: deploy-app-infrastructure.yml Had Unclear repository_dispatch ❌ → Fixed ✅

**Before:**
```yaml
on:
  push: ...
  workflow_dispatch: ...
  repository_dispatch:
    types: [deploy-infrastructure]  # Unused, unclear purpose
```

**Why wrong:** No part of the codebase triggers this. It's dead code that could confuse maintenance.

**After:**
```yaml
on:
  push: ...
  workflow_dispatch:  # Removed repository_dispatch
```

---

## 5. Dependency Chain (What Deploys in What Order)

```
1. bootstrap-oidc.yml (run once)
   ↓ Creates GitHub OIDC provider
   
2. deploy-core.yml (manual)
   ↓ Creates VPC, subnets, endpoints, exports VPC IDs
   
3. deploy-app-infrastructure.yml (manual or auto on template change)
   ↓ Creates RDS, ECS cluster, Secrets
   ↓ Imports VPC IDs from deploy-core
   ↓ Exports database/cluster ARNs
   
4. Deploy in parallel (can run together):
   ├─ deploy-app-stocks.yml
   │  ↓ Creates 39 ECS loader tasks
   │  ↓ Imports cluster ARN from step 3
   │
   ├─ deploy-webapp.yml
   │  ↓ Creates Lambda API + CloudFront
   │  ↓ Imports database secret from step 3
   │
   └─ deploy-algo-orchestrator.yml
      ↓ Creates Lambda + EventBridge scheduler
      ↓ Imports database secret + Alpaca keys from step 3
```

**Key Property:** Steps 4 depend on step 3, which depends on step 2, which depends on step 1. CloudFormation enforces this via ImportValue dependencies.

---

## 6. What We Avoided (And Why)

### ❌ Monolithic Single Workflow

```yaml
deploy-all.yml
  → template-bootstrap.yml (run once)
  → template-core.yml (run monthly)
  → template-app-stocks.yml (run occasionally)
  → template-app-ecs-tasks.yml (run daily)
  → template-webapp-lambda.yml (run daily)
  → template-algo-orchestrator.yml (run weekly)
```

**Problem:** If loader code changes, VPC and RDS redeploy too. Wasteful and risky.

### ❌ Consolidating to 2 Super-Workflows

```yaml
deploy-infrastructure.yml (bootstrap + core + RDS + ECS)
deploy-applications.yml (loaders + webapp + algo)
```

**Problem:** Can't update just VPC without also updating RDS. Less flexibility.

### ❌ Workflow-Level Export Queries

```bash
# In deploy-webapp.yml:
DB_SECRET_ARN=$(aws cloudformation list-exports --query "Exports[?Name=='StocksApp-SecretArn'].Value")
aws cloudformation deploy ... --parameter-overrides DatabaseSecretArn=$DB_SECRET_ARN
```

**Problems:**
- Workflow has business logic (should be in templates)
- CloudFormation doesn't know about the dependency
- If export name changes, workflows must change too
- Error is detected at runtime, not deployment time

---

## 7. The Architecture in One Sentence

**Infrastructure is set up once (VPC, RDS) via manual approval, then applications deploy automatically with proper dependency ordering via CloudFormation exports.**

---

## Summary: Why This Design

1. **6 workflows** — Match change frequency and responsibility
2. **ImportValue for credentials** — CloudFormation enforces dependencies
3. **Manual for infrastructure, auto for apps** — Balance safety and speed
4. **Trigger bug fixes** — Ensure deployment automation works correctly

This is not the "theoretically optimal" architecture for a startup with 10 engineers. It's the **right architecture for your system** where infrastructure changes rarely and application changes happen daily.

