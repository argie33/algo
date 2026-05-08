# AWS Deployment Issues & Fixes - Complete Audit

**Date:** 2026-05-05  
**Review Period:** Today's workflow runs (6am-12:30pm ET)  
**Status:** 3 critical, 5 major, 2 deferred

---

## CRITICAL ISSUES (Block All Deployments)

### ❌ C1: Webapp Deployment - CloudFormation Early Validation Failure
**Severity:** CRITICAL | **Status:** BLOCKING  
**First Failure:** 2026-05-05 11:54:59 UTC (deploy-webapp run)  
**Error:**
```
Error: Failed to create changeset for the stack: stocks-webapp-dev
Reason: The following hook(s)/validation failed: [AWS::EarlyValidation::ResourceExistenceCheck]
```
**Root Cause:** SAM template references non-existent CloudFormation exports or parameters. Template is trying to create resources that reference stacks that don't exist or in wrong order.

**Impact:** Cannot deploy webapp Lambda at all. Stack stays in REVIEW_IN_PROGRESS state.

**Required Fixes:**
- [ ] Review `template-webapp-lambda.yml` for all `!ImportValue` statements
- [ ] Verify those exports exist in deployed stacks (deploy-core, deploy-app-infrastructure)
- [ ] Check for hardcoded parameter references that should be outputs
- [ ] Ensure `deploy-app-infrastructure` runs BEFORE `deploy-webapp` (dependency chain)
- [ ] Add explicit stack dependency checks in `deploy-webapp.yml` workflow

**Files to Audit:**
- `template-webapp-lambda.yml` - check all imports
- `.github/workflows/deploy-webapp.yml` - add stack validation step
- `template-core.yml` - export all needed outputs

---

### ❌ C2: Data Loaders - Missing Module `optimal_loader`
**Severity:** CRITICAL | **Status:** BLOCKING ALL LOADERS  
**First Failure:** 2026-05-05 06:35:41 UTC (stocksymbols loader)  
**Error:**
```
ModuleNotFoundError: No module named 'optimal_loader'
File "/app/loadpricedaily.py", line 28, in <module>
    from optimal_loader import OptimalLoader
```
**Root Cause:** Dockerfile copies `*.py` from repo root, but ECR image built does NOT include all necessary shared modules. The `COPY *.py ./` in main Dockerfile is working, but the Dockerfile.* files for individual loaders may be outdated.

**Impact:** Every data loader fails immediately. No data gets loaded into RDS.

**Required Fixes:**
- [ ] Verify `optimal_loader.py` exists at repo root and is being copied
- [ ] Check if individual Dockerfile.* files are still being used (they shouldn't be)
- [ ] Audit all Dockerfile.* entries - consolidate into single Dockerfile
- [ ] Rebuild all ECR images with new unified Dockerfile
- [ ] Test stocksymbols loader in isolation before full pipeline

**Files to Check:**
- `optimal_loader.py` - must exist at repo root
- All `Dockerfile.*` files - should be removed, use single `Dockerfile`
- `Dockerfile` - verify `COPY *.py ./` line is correct
- `requirements.txt` - all deps included

---

### ❌ C3: CloudFormation Stack Ordering Dependency Chain Undefined
**Severity:** CRITICAL | **Status:** IMPLICIT ORDERING ONLY  
**Problem:** Workflows depend on specific stacks existing but don't explicitly enforce order:
- `deploy-loaders-lambda.yml` checks for `stocks-app-stack` (line 42-51)
- `deploy-webapp.yml` imports from core stack (implicit)
- `deploy-app-stocks.yml` depends on bootstrap stack outputs
- **But:** No workflow enforces sequential execution. Parallel triggers can cause cascade failures.

**Impact:** Stack creation race conditions. Outputs may not exist when downstream templates try to import them.

**Required Fixes:**
- [ ] Add explicit dependency workflow ordering in GitHub Actions
- [ ] Create `deploy-stack-chain.yml` that runs workflows sequentially
- [ ] Add pre-flight checks in each workflow to verify dependency stacks
- [ ] Document exact stack creation order in CLAUDE.md

---

## MAJOR ISSUES (Fix Soon)

### 🟠 M1: Workflow File Duplication & Confusion
**Severity:** MAJOR | **Status:** DOCUMENTATION ISSUE  
**Problem:** 
- 6 main workflows but unclear which deploy what
- `deploy-app-stocks.yml` runs loaders AND infrastructure
- `deploy-app-infrastructure.yml` also deploys infrastructure
- Two similar names for related but different work

**Files:**
- `.github/workflows/deploy-app-stocks.yml` - runs ECS loaders
- `.github/workflows/deploy-app-infrastructure.yml` - deploys RDS/ECS/Secrets infrastructure
- **Confusion:** Which runs first? What's the dependency?

**Impact:** Team confusion on what triggers what. Developers accidentally trigger wrong workflow.

**Required Fixes:**
- [ ] Rename for clarity: `deploy-app-infrastructure.yml` → `deploy-database-and-infrastructure.yml`
- [ ] Rename for clarity: `deploy-app-stocks.yml` → `deploy-data-loaders-pipeline.yml`
- [ ] Document in CLAUDE.md: "Infrastructure must deploy before loaders"
- [ ] Create clear workflow dependency diagram in README

---

### 🟠 M2: Hardcoded Stack Names vs Dynamic
**Severity:** MAJOR | **Status:** PARTIALLY FIXED  
**Problem:** Mix of hardcoded and dynamic stack names:
- `stocks-app-stack` - hardcoded in multiple workflows
- `stocks-cluster` - hardcoded ECS cluster name
- `stocks-app-registry` - hardcoded ECR repo name
- But some use `${ENVIRONMENT_NAME}` variables

**Impact:** Can't deploy to different environments (staging/prod) easily. Stack names collide.

**Required Fixes:**
- [ ] Audit all CloudFormation templates for hardcoded names
- [ ] Make all stack names environment-aware: `stocks-{component}-{env}`
- [ ] Update workflows to pass `ENVIRONMENT_NAME` consistently
- [ ] Test with dev/staging/prod environment variables

---

### 🟠 M3: Missing Stack Cleanup Logic in Failed Deployments
**Severity:** MAJOR | **Status:** PARTIALLY IMPLEMENTED  
**Problem:** 
- `deploy-webapp.yml` has cleanup for ROLLBACK_COMPLETE state
- Other workflows do NOT have cleanup steps
- Failed stacks get stuck in `CREATE_FAILED` or `UPDATE_ROLLBACK_FAILED`
- Next deploy attempt fails because stack exists in bad state

**Impact:** Manual AWS console cleanup required. Blocks CI/CD pipeline recovery.

**Required Fixes:**
- [ ] Add cleanup step to ALL workflows (not just deploy-webapp)
- [ ] Check for ROLLBACK_COMPLETE, CREATE_FAILED, UPDATE_ROLLBACK_FAILED states
- [ ] Delete bad stacks before retrying deployment
- [ ] Use `aws cloudformation wait stack-create-complete` with timeout handling

---

### 🟠 M4: No Pre-Deployment Validation of AWS Limits
**Severity:** MAJOR | **Status:** MISSING  
**Problem:**
- No check for AWS account limits (VPCs, security groups, NAT gateways)
- No check for IAM role existence before deployment
- No check for required secrets before running
- Early validation catches some issues but not all

**Impact:** Deployments fail mid-way with cryptic AWS errors instead of upfront errors.

**Required Fixes:**
- [ ] Add pre-flight check job to all workflows
- [ ] Verify AWS_ACCOUNT_ID secret exists
- [ ] Verify required API keys (FRED_API_KEY, APCA keys) exist
- [ ] Check IAM role exists: `GitHubActionsDeployRole`
- [ ] Verify ECR repository can be created/accessed
- [ ] Test RDS security group creation won't hit limit

---

### 🟠 M5: Node.js 20 Deprecation Warning
**Severity:** MAJOR | **Status:** ACTION ITEM JUNE 2026  
**Problem:** All workflows use Node 20 actions but GitHub is deprecating them June 2, 2026.
```
Node.js 20 actions are deprecated and will be removed September 16th, 2026.
```
**Impact:** By June 2026, workflows will fail. Need to update to Node 24.

**Required Fixes:**
- [ ] Update `aws-actions/configure-aws-credentials@v4` → v5 or later
- [ ] Update `aws-actions/setup-sam@v2` → v4 or later
- [ ] Update `actions/checkout@v3` → v4
- [ ] Update `.github/workflows/*.yml` files to use new versions

---

## DEFERRED ISSUES (Intentional Dev Choices)

### ⏸️ D1: Network Security - Open RDS to World
**Status:** DEFERRED - Fix before prod cutover  
**Current State:**
- RDS `PubliclyAccessible: true`
- Security group allows `0.0.0.0/0` on port 5432
- **Reason:** Would require Lambdas in VPC + NAT or VPC endpoints

**What Needs Doing:**
- [ ] Move Lambdas (webapp, algo orchestrator) into VPC
- [ ] Create NAT gateway or use VPC endpoints
- [ ] Restrict RDS to private subnet only
- [ ] Test outbound connectivity from VPC-based Lambdas

---

### ⏸️ D2: Loader Network Connectivity
**Status:** DEFERRED - Works now, prod needs improvement  
**Current State:**
- ECS loaders run in public subnets with public IPs
- Can reach external APIs (yfinance, Alpaca, FRED)
- **Reason:** Private subnets would need NAT for outbound HTTPS

**What Needs Doing:**
- [ ] Create NAT gateway in public subnet
- [ ] Move loaders to private subnet
- [ ] Route outbound through NAT
- [ ] Cost: ~$32/month for NAT gateway + data charges

---

## ARCHITECTURE REVIEW - YML STRATEGY

### Current State (6 Templates, 6 Workflows)

**Templates:**
1. `template-bootstrap.yml` - OIDC role for GitHub Actions
2. `template-core.yml` - VPC, bastion, IAM roles, S3 buckets
3. `template-app-stocks.yml` - RDS, ECS cluster, secrets
4. `template-app-ecs-tasks.yml` - ECS task definitions for loaders
5. `template-webapp-lambda.yml` - Webapp Lambda, API Gateway, CloudFront
6. `template-algo-orchestrator.yml` - Algo Lambda + EventBridge scheduler

**Workflows:**
1. `bootstrap-oidc.yml` - One-time setup (GitHub OIDC provider)
2. `deploy-core.yml` - VPC + base infrastructure
3. `deploy-app-infrastructure.yml` - RDS + ECS cluster setup
4. `deploy-app-stocks.yml` - Loader task definitions + executes loaders
5. `deploy-webapp.yml` - Webapp Lambda deployment
6. `deploy-algo-orchestrator.yml` - Algo Lambda deployment

### Issues with Current Strategy

**Problem 1: Implicit Dependencies**
- Workflows should run in order: bootstrap → core → app-infrastructure → (webapp/algo/loaders)
- Currently no GitHub Actions workflow orchestration
- Team doesn't know the correct sequence

**Problem 2: Naming Confusion**
- `deploy-app-stocks` vs `deploy-app-infrastructure` - which does what?
- Both touch ECS but for different purposes

**Problem 3: No Central Deployment Orchestrator**
- Teams manually trigger workflows in correct order
- Risk of wrong order causing cascade failures

**Problem 4: Incomplete Documentation**
- No CLAUDE.md section explaining YML strategy
- No dependency diagram
- No runbook for fresh AWS account setup

### Recommended YML Strategy

#### Phase 0: Clear Documentation (Do First)
Create `AWS_DEPLOYMENT_STRATEGY.md`:
```markdown
## Stack Deployment Order (MUST FOLLOW THIS)

1. **bootstrap-oidc.yml** - One-time setup
   - Creates GitHub OIDC provider in AWS
   - Creates GitHubActionsDeployRole IAM role
   - Prerequisites: None
   
2. **deploy-core.yml** - Foundation
   - Creates VPC, subnets, bastion
   - Creates base IAM roles and policies
   - Creates S3 bucket for CloudFormation templates
   - Prerequisites: bootstrap stack complete
   - Output exports: Core-VpcId, Core-PrivateSubnetIds, etc.
   
3. **deploy-app-infrastructure.yml** - Data Layer
   - Creates RDS PostgreSQL database
   - Creates ECS cluster for loaders
   - Creates Secrets Manager entries
   - Prerequisites: core stack complete
   - Output exports: AppStocks-DbEndpoint, AppStocks-SecretArn, etc.
   
4. **deploy-app-stocks.yml** - Loader Task Definitions
   - Creates ECS task definitions (not tasks - just definitions)
   - Optionally executes loaders on schedule or manual trigger
   - Prerequisites: app-infrastructure stack complete
   
5. **deploy-webapp.yml** - Frontend/API
   - Creates Lambda function for webapp
   - Creates API Gateway
   - Creates CloudFront distribution
   - Prerequisites: core stack complete
   
6. **deploy-algo-orchestrator.yml** - Trading Bot
   - Creates Lambda for algo orchestrator
   - Creates EventBridge scheduler (weekdays 4:30pm ET)
   - Prerequisites: app-infrastructure stack (for Alpaca secret)
```

#### Phase 1: Template Refactoring (Recommended)
- Keep 6 templates as-is
- No changes needed to CloudFormation

#### Phase 2: Workflow Improvements (Required)

**Create Master Orchestrator Workflow:**
```
.github/workflows/deploy-all-infrastructure.yml

Runs sequentially:
  1. Deploy Core
  2. Deploy App Infrastructure
  3. Deploy Webapp
  4. Deploy Algo Orchestrator
  
Allows selective deployment (skip some steps)
Pre-flight checks before each step
Rollback on any failure
```

**Rename for Clarity:**
- `deploy-app-infrastructure.yml` → `deploy-database-and-ecs.yml`
- `deploy-app-stocks.yml` → `deploy-loaders-and-tasks.yml`

---

## PRIORITIZED FIX ORDER

### Week 1 (Critical - Unblock All Deployments)
1. **FIX: Webapp CloudFormation Early Validation**
   - Audit template-webapp-lambda.yml imports
   - Verify template-core.yml exports all needed values
   - Test deployment sequence
   - Estimated: 1-2 hours

2. **FIX: Data Loaders Missing Modules**
   - Verify optimal_loader.py exists at root
   - Test Docker build locally
   - Rebuild ECR images
   - Test loader in ECS
   - Estimated: 1-2 hours

3. **FIX: Stack Ordering & Dependencies**
   - Add pre-flight stack checks to all workflows
   - Document required stack creation order
   - Create stack dependency diagram
   - Estimated: 2-3 hours

### Week 2 (Major - Improve Reliability)
4. **FIX: Workflow Naming & Documentation**
   - Create AWS_DEPLOYMENT_STRATEGY.md
   - Update CLAUDE.md with section on deployments
   - Rename workflows for clarity
   - Estimated: 1-2 hours

5. **FIX: Add Universal Cleanup Logic**
   - Add cleanup step to deploy-core, deploy-app-infrastructure, deploy-algo-orchestrator
   - Test rollback scenarios
   - Estimated: 2-3 hours

6. **FIX: Pre-Deployment Validation**
   - Add pre-flight check job to all workflows
   - Validate secrets, IAM roles, account limits
   - Estimated: 2-3 hours

7. **FIX: Node.js Version Updates**
   - Update action versions to support Node 24
   - Test on dev environment
   - Estimated: 1-2 hours

### Deferred (Before Prod Cutover)
8. **Security Hardening: VPC for Lambdas**
9. **Security Hardening: RDS in Private Subnet**
10. **Cost Optimization: NAT Gateway Setup**

---

## VALIDATION CHECKLIST

After fixes are applied:

- [ ] Run `deploy-core.yml` from scratch - succeeds
- [ ] Run `deploy-app-infrastructure.yml` - succeeds, has required outputs
- [ ] Run `deploy-webapp.yml` - succeeds, can access frontend
- [ ] Run `deploy-algo-orchestrator.yml` - succeeds, scheduler active
- [ ] Run `deploy-app-stocks.yml` manually - all loaders succeed
- [ ] Check RDS database has data from loaders
- [ ] Test webapp frontend loads and displays data
- [ ] Test algo Lambda can read from database
- [ ] Run full stack from scratch (simulate new AWS account setup)
- [ ] Document time-to-deploy for reference

---

## SUCCESS CRITERIA

✅ **Phase 1 Complete** when:
1. All 3 critical issues resolved
2. All workflows execute in correct dependency order
3. Freshly deployed stack passes validation checklist

✅ **Phase 2 Complete** when:
1. Documentation in CLAUDE.md is complete
2. Team can deploy without asking questions
3. No manual AWS console work needed

✅ **Ready for Prod** when:
1. VPC security fixes applied
2. RDS in private subnet
3. Loaders have private subnet + NAT
4. Full security audit passed
