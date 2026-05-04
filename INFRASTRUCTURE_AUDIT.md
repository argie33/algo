# Infrastructure Audit & Organization

**Last Updated:** 2026-05-04 (After Algo Orchestrator Secret Fix)

---

## TIER 1: Core Foundation (Essential - Deploy in Order)

### 1. bootstrap-oidc.yml → template-bootstrap.yml
- **Purpose:** One-time GitHub OIDC setup for AWS authentication
- **Status:** ✅ Essential - Run once at start
- **Deployment:** Manual: `aws cloudformation deploy --template-file template-bootstrap.yml --stack-name stocks-bootstrap`

### 2. deploy-core.yml → template-core.yml
- **Purpose:** VPC, networking, Lambda execution role, bastion host
- **Status:** ✅ Essential - Infrastructure foundation
- **Dependencies:** None (deploy first)
- **Deployment:** Automatic on push to main

### 3. deploy-app-stocks.yml → template-app-stocks.yml
- **Purpose:** RDS database, **creates database credentials secret**, ECS cluster, task roles
- **Status:** ✅ Essential - Where all data lives, creates secrets for other services
- **Dependencies:** deploy-core.yml (needs VPC)
- **CRITICAL:** Creates secret `stocks-db-secrets-{StackName}-{Region}-001` and exports as `StocksApp-SecretArn`
- **Deployment:** Automatic on push to main

---

## TIER 2: Application Deployment

### 4. deploy-webapp.yml → template-webapp-lambda.yml
- **Purpose:** Frontend Lambda functions, Cognito auth, React dashboard
- **Status:** ✅ Active application
- **Dependencies:** deploy-app-stocks.yml (needs database)
- **Issue Found:** Hardcoded localhost in Cognito CallbackURLs (should be environment-aware)
- **Deployment:** Automatic when webapp files change

### 5. deploy-algo-orchestrator.yml → template-algo-orchestrator.yml
- **Purpose:** Algo execution engine, EventBridge scheduler (5:30pm ET daily)
- **Status:** ✅ Just fixed - now properly retrieves secrets from CloudFormation exports
- **Dependencies:** deploy-app-stocks.yml (needs database credentials)
- **Recent Fixes:**
  - ✅ Workflow now retrieves secret ARN from CloudFormation exports (`StocksApp-SecretArn`)
  - ✅ Template passes secret ARNs as environment variables to Lambda
  - ✅ Lambda function uses environment variables instead of hardcoded secret names
- **Deployment:** Automatic when algo_*.py files change

---

## TIER 3: Optimizations (Non-Critical)

### 6. deploy-tier1-optimizations.yml → template-tier1-api-lambda.yml + template-tier1-cost-optimization.yml
- **Purpose:** API Gateway HTTP API migration, cost optimizations (S3 Intelligent-Tiering, CloudWatch sampling)
- **Status:** ⚠️ Enhancement, not required for core functionality
- **Issue Found:** Hardcoded localhost:5174
- **Question:** Is this actively maintained?

---

## UNCLEAR / NEEDS CLARIFICATION

### deploy-infrastructure.yml
- **Status:** ❓ What does this deploy? No clear template match
- **Action:** User must clarify purpose

### optimize-data-loading.yml
- **Status:** ❓ Purpose unclear (data loading optimization? manual trigger?)
- **Action:** User must clarify if this is still needed

### algo-verify.yml
- **Purpose:** Verify algo components on push/PR
- **Status:** ⚠️ Hardcoded database fallbacks (localhost), CI testing without real database
- **Action:** Either integrate into deploy-algo-orchestrator.yml or fix database fallbacks

---

## ORPHANED TEMPLATES (No Workflows Deploy These)

### Delete These - They're AI-Generated Slop

1. **template-app-ecs-tasks.yml** (196KB - SUSPICIOUS SIZE)
   - Purpose: Unclear, possibly duplicate ECS logic from template-app-stocks.yml
   - Action: Investigate if logic is already in template-app-stocks.yml, then delete

2. **template-eventbridge-scheduling.yml**
   - Purpose: EventBridge scheduling (belongs IN template-algo-orchestrator.yml)
   - Status: Orphaned - no workflow deploys this
   - Action: Delete - functionality should be in template-algo-orchestrator.yml

3. **template-lambda-phase-c.yml**
   - Status: Abandoned Phase C template
   - Action: Delete

4. **template-phase-e-dynamodb.yml**
   - Status: Abandoned Phase E template
   - Action: Delete

5. **template-step-functions-phase-d.yml**
   - Status: Abandoned Phase D template
   - Action: Delete

6. **template-optimize-database.yml**
   - Status: Abandoned optimization template
   - Action: Delete

---

## Issues Found & Fixed

### ✅ FIXED: Algo Orchestrator Secret Retrieval
```
Problem:      deploy-algo-orchestrator.yml looked for 'stocks-db-credentials' (doesn't exist)
Root Cause:   template-app-stocks.yml creates secret with dynamic name, exports as StocksApp-SecretArn
Solution:     Workflow now retrieves secret from CloudFormation exports (proper IaC pattern)
Files Changed: .github/workflows/deploy-algo-orchestrator.yml
```

### ✅ FIXED: Hardcoded Secret Name in Lambda
```
Problem:      lambda_function.py hardcoded SecretId='stocks-db-credentials'
Solution:     Now uses DATABASE_SECRET_ARN environment variable from CloudFormation
Files Changed: template-algo-orchestrator.yml, lambda/algo_orchestrator/lambda_function.py
```

### ⚠️ ISSUES REMAINING

1. **Hardcoded localhost in CORS/Cognito**
   - Location: template-webapp-lambda.yml
   - Impact: Would expose localhost in production
   - Fix: Make environment-aware

2. **CI Verification Broken**
   - Location: algo-verify.yml
   - Impact: Can't test database connectivity in CI without real database
   - Fix: Either use test database or remove hardcoded fallbacks

---

## What We Know About Architecture

- **Core 5 Workflows/Templates are clean and working**
- **Secrets are properly created by template-app-stocks.yml** (done right!)
- **Algo orchestrator now properly retrieves secrets** (just fixed)
- **Too many orphaned/Phase templates** (need to delete)
- **Some unclear workflows** (need user decision)
- **Hardcoded localhost in some templates** (need fixing)

---

## Recommended Action Plan

### Phase 1: Clean Up (Delete Orphaned Templates)
```
🗑️ template-app-ecs-tasks.yml - after investigating if logic is elsewhere
🗑️ template-eventbridge-scheduling.yml
🗑️ template-lambda-phase-c.yml
🗑️ template-phase-e-dynamodb.yml
🗑️ template-step-functions-phase-d.yml
🗑️ template-optimize-database.yml
```

### Phase 2: Clarify With User
```
❓ Is deploy-tier1-optimizations.yml actively used?
❓ What is deploy-infrastructure.yml supposed to do?
❓ What is optimize-data-loading.yml supposed to do?
❓ Should algo-verify.yml be kept or integrated elsewhere?
```

### Phase 3: Fix Remaining Issues
```
⚠️ Make localhost URLs environment-aware (dev ✓, prod ✗)
⚠️ Fix CI verification workflow
```

### Phase 4: Test Deployment
```
🧪 Deploy algo orchestrator to Lambda
🧪 Verify EventBridge rule executes daily at 5:30pm ET
🧪 Verify algo tables are created and populated
```
