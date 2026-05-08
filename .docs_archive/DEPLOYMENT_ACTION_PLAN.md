# Deployment Action Plan - What to Fix & Why

**Purpose:** Clear list of what needs fixing, in order of impact.  
**Timeline:** Phase 1 (Critical) = this week. Phase 2 (Major) = following week.  
**Owner:** You + Claude

---

## Phase 1: CRITICAL (Unblock Deployments) - This Week

### Task C1.1: Fix Webapp CloudFormation Early Validation
**Problem:** Template references non-existent exports → "ResourceExistenceCheck failed"  
**Root Cause:** Missing or misspelled CloudFormation exports from core/app-infrastructure stacks

**Steps:**
1. Open `template-webapp-lambda.yml`
2. Find all `!ImportValue` lines
3. For each import, verify the export exists:
   - Check `template-core.yml` for outputs
   - Check `template-app-stocks.yml` for outputs
   - If missing, add the output to the source template
4. Add explicit dependency check to `deploy-webapp.yml`
5. Test deployment

**Files to Touch:**
- `template-webapp-lambda.yml` - verify imports
- `template-core.yml` - add missing outputs
- `template-app-stocks.yml` - add missing outputs  
- `.github/workflows/deploy-webapp.yml` - add pre-flight check

**Expected Result:** `deploy-webapp.yml` succeeds without early validation error

**Time Estimate:** 1-2 hours  
**Difficulty:** Medium (need to read CloudFormation templates)

---

### Task C1.2: Fix Data Loaders Missing Module Error
**Problem:** Docker image missing `optimal_loader.py` module → all loaders fail  
**Root Cause:** Dockerfile copies `*.py` but image not rebuilt after optimal_loader.py was added

**Steps:**
1. Verify `optimal_loader.py` exists at repo root: `ls -la optimal_loader.py`
2. Test Docker build locally:
   ```bash
   docker build -t test-loader:latest .
   docker run test-loader:latest python3 -c "from optimal_loader import OptimalLoader; print('OK')"
   ```
3. If it works locally, rebuild ECR image in AWS:
   - Run GitHub action `deploy-app-stocks.yml` with `force_all=true`
   - This rebuilds ECR image + triggers stocksymbols loader
4. Check loader logs in CloudWatch
5. Verify RDS database has data

**Files to Touch:**
- `Dockerfile` - verify COPY *.py line
- `requirements.txt` - verify all dependencies listed
- `optimal_loader.py` - should exist at root
- `.github/workflows/deploy-app-stocks.yml` - trigger rebuild

**Expected Result:** stocksymbols loader completes, writes data to RDS

**Time Estimate:** 1-2 hours  
**Difficulty:** Easy (straightforward debugging)

---

### Task C1.3: Add Stack Dependency Validation
**Problem:** Workflows don't check if dependent stacks exist → cascade failures  
**Root Cause:** No pre-flight checks validating dependency stacks

**Implementation:**
Add this step to EVERY workflow that depends on another stack:

```yaml
- name: Verify dependency stacks exist
  run: |
    # deploy-app-stocks.yml depends on app-infrastructure
    aws cloudformation describe-stacks \
      --stack-name "stocks-app-stack" \
      --region "${{ env.AWS_REGION }}" \
      --query 'Stacks[0].StackStatus' \
      --output text > /dev/null || \
      { echo "ERROR: stocks-app-stack must exist first"; exit 1; }
    
    # deploy-app-stocks.yml also depends on core
    aws cloudformation describe-stacks \
      --stack-name "stocks-core-stack" \
      --region "${{ env.AWS_REGION }}" \
      --query 'Stacks[0].StackStatus' \
      --output text > /dev/null || \
      { echo "ERROR: stocks-core-stack must exist first"; exit 1; }
    
    echo "✅ All dependency stacks exist"
```

**Add to These Workflows:**
- `.github/workflows/deploy-app-stocks.yml` (depends on app-infrastructure + core)
- `.github/workflows/deploy-webapp.yml` (depends on core)
- `.github/workflows/deploy-algo-orchestrator.yml` (depends on app-infrastructure)

**Expected Result:** Workflows fail fast with clear error message if dependencies missing

**Time Estimate:** 1 hour  
**Difficulty:** Easy (copy/paste pattern)

---

## Phase 2: MAJOR (Improve Reliability) - Next 2 Weeks

### Task M2.1: Add Rollback Logic to All Workflows
**Problem:** Failed stacks get stuck in ROLLBACK_COMPLETE state  
**Solution:** Add automatic cleanup step when deployment fails

**Implementation:**
Copy pattern from `deploy-webapp.yml` to these workflows:

```yaml
- name: Handle failed deployment
  if: failure()
  run: |
    STACK_STATUS=$(aws cloudformation describe-stacks \
      --stack-name "${{ env.STACK_NAME }}" \
      --query 'Stacks[0].StackStatus' \
      --output text 2>/dev/null || echo "MISSING")
    
    if [[ "$STACK_STATUS" == "ROLLBACK_COMPLETE" || "$STACK_STATUS" == "CREATE_FAILED" || "$STACK_STATUS" == "UPDATE_ROLLBACK_FAILED" ]]; then
      echo "Cleaning up failed stack..."
      aws cloudformation delete-stack --stack-name "${{ env.STACK_NAME }}"
      
      echo "Waiting for deletion..."
      aws cloudformation wait stack-delete-complete \
        --stack-name "${{ env.STACK_NAME }}" || true
      
      echo "Stack cleanup complete. Manual retry required."
    fi
```

**Add to These Workflows:**
- `.github/workflows/deploy-core.yml`
- `.github/workflows/deploy-app-infrastructure.yml`
- `.github/workflows/deploy-algo-orchestrator.yml`
- `.github/workflows/deploy-loaders-lambda.yml`

**Expected Result:** Failed deployments automatically clean up, can retry without manual intervention

**Time Estimate:** 2 hours  
**Difficulty:** Easy (copy/paste)

---

### Task M2.2: Clarify Workflow Names & Purpose
**Problem:** `deploy-app-stocks` vs `deploy-app-infrastructure` confuses team

**Changes:**
```
RENAME:
  deploy-app-infrastructure.yml 
    → deploy-database-and-ecs.yml
  
  deploy-app-stocks.yml 
    → deploy-data-loaders-pipeline.yml
```

**Update These Files:**
- Rename workflow files in `.github/workflows/`
- Update trigger rules in workflows that reference each other
- Update any documentation links

**Expected Result:** Clear purpose of each workflow from the filename

**Time Estimate:** 1 hour  
**Difficulty:** Easy (rename + find/replace)

---

### Task M2.3: Create Orchestrator Workflow
**Problem:** Workflows must be run manually in specific order  
**Solution:** Single workflow that runs them sequentially

**Implementation:**
Create `.github/workflows/deploy-all-infrastructure.yml`:

```yaml
name: Deploy All Infrastructure

on:
  workflow_dispatch:
    inputs:
      skip_bootstrap:
        description: 'Skip bootstrap (only needed once)'
        default: 'false'
        type: choice
        options: ['true', 'false']

jobs:
  bootstrap:
    name: 1. Bootstrap OIDC
    if: ${{ github.event.inputs.skip_bootstrap != 'true' }}
    uses: ./.github/workflows/bootstrap-oidc.yml
    
  core:
    name: 2. Deploy Core Infrastructure
    needs: bootstrap
    uses: ./.github/workflows/deploy-core.yml
    
  app_infrastructure:
    name: 3. Deploy Database & ECS
    needs: core
    uses: ./.github/workflows/deploy-database-and-ecs.yml
    
  services:
    name: 4. Deploy Services (Parallel)
    needs: app_infrastructure
    strategy:
      matrix:
        service: [webapp, algo-orchestrator, loaders]
    uses: ./.github/workflows/deploy-${{ matrix.service }}.yml
```

**Expected Result:** Click "Run workflow" button → entire stack deploys in correct order

**Time Estimate:** 3-4 hours  
**Difficulty:** Medium (GitHub Actions workflow composition)

---

### Task M2.4: Create Deployment Runbook
**Problem:** New team members don't know how to deploy from scratch  
**Solution:** Step-by-step runbook in CLAUDE.md

**Implementation:**
Add to `CLAUDE.md` under new section "## AWS Deployment":

```markdown
### Fresh AWS Account Setup

**Prerequisites:**
- AWS account with permissions to create CloudFormation stacks, IAM roles, RDS, ECS, Lambda
- GitHub repository access
- Secrets configured: AWS_ACCOUNT_ID, FRED_API_KEY, APCA_API_KEY_ID, APCA_API_SECRET_KEY

**Time Required:** 45-60 minutes (mostly waiting for stack creation)

**Steps:**

1. **Set up GitHub OIDC Provider** (one-time)
   - Go to `Actions` → `Workflows` → Run `bootstrap-oidc.yml`
   - Wait for completion (2-3 minutes)
   - Creates IAM role for GitHub Actions

2. **Deploy Core Infrastructure**
   - Run `deploy-core.yml` manually
   - This creates: VPC, subnets, IAM roles, S3 bucket
   - Wait for completion (5-10 minutes)
   - Check AWS console: CloudFormation → Stacks → stocks-core-stack (CREATE_COMPLETE)

3. **Deploy Database & ECS Cluster**
   - Run `deploy-database-and-ecs.yml` manually
   - This creates: RDS PostgreSQL, ECS cluster, Secrets Manager
   - Wait for completion (10-15 minutes)
   - Check AWS console for stocks-app-stack (CREATE_COMPLETE)

4. **Verify Database Connection**
   ```bash
   # Get RDS endpoint from CloudFormation stack outputs
   aws cloudformation describe-stacks \
     --stack-name stocks-app-stack \
     --query 'Stacks[0].Outputs'
   
   # Connect to RDS (from bastion or via tunnel)
   psql -h <endpoint> -U postgres -d stocks
   \dt  # Should see empty schema
   ```

5. **Deploy Data Loaders**
   - Run `deploy-data-loaders-pipeline.yml` with `force_all=true`
   - This: builds Docker image, pushes to ECR, runs all loaders
   - Wait for completion (30-45 minutes)
   - Check RDS: loaders should have populated tables

6. **Deploy Webapp**
   - Run `deploy-webapp.yml` manually
   - This creates: Lambda function, API Gateway, CloudFront
   - Wait for completion (3-5 minutes)
   - Check CloudFormation for stocks-webapp-dev (CREATE_COMPLETE)

7. **Deploy Algo Orchestrator**
   - Run `deploy-algo-orchestrator.yml` manually
   - This creates: Lambda function, EventBridge scheduler
   - Wait for completion (2-3 minutes)
   - Check EventBridge: should see rule running weekdays at 4:30pm ET

8. **Verify Everything Works**
   - Access webapp frontend via CloudFront URL (from CloudFormation outputs)
   - Data should be visible from loaders
   - Algo Lambda should be scheduled and ready

**Troubleshooting:**

| Error | Cause | Fix |
|-------|-------|-----|
| Stack doesn't exist | Previous workflow failed | Check CloudFormation console for failed stack, delete it |
| ResourceExistenceCheck failed | Missing export from dependent stack | Run dependent workflow again (e.g., deploy-core before deploy-webapp) |
| ModuleNotFoundError: optimal_loader | ECR image out of date | Re-run loaders workflow to rebuild image |
| Stack stuck in ROLLBACK_COMPLETE | Deployment failed, cleanup incomplete | Delete stack manually in AWS console, retry deploy |

**To Deploy All at Once (After First Setup):**
```
Run: deploy-all-infrastructure.yml
This runs all steps 1-7 in correct order automatically.
```
```

**Expected Result:** Any team member can follow this and deploy to a fresh AWS account

**Time Estimate:** 2-3 hours (mostly writing + testing)  
**Difficulty:** Easy (documentation)

---

### Task M2.5: Document CloudFormation Exports
**Problem:** Implicit dependencies between stacks  
**Solution:** Explicit table showing what exports where

**Implementation:**
Add to `CLAUDE.md`:

```markdown
### CloudFormation Stack Exports & Imports

**Critical:** Every import must have corresponding export in source template.

| Stack Name | Template | Exports | Consumed By | Status |
|-----------|----------|---------|-------------|--------|
| stocks-bootstrap | template-bootstrap.yml | (none - one-time) | N/A | ✅ |
| stocks-core-stack | template-core.yml | TBD | app-infrastructure, webapp-lambda | ⚠️ Review |
| stocks-app-stack | template-app-stocks.yml | TBD | loaders, algo | ⚠️ Review |
| stocks-ecs-tasks-* | template-app-ecs-tasks.yml | (none) | N/A | ✅ |
| stocks-webapp-dev | template-webapp-lambda.yml | (none) | N/A | ✅ |
| stocks-algo-* | template-algo-orchestrator.yml | (none) | N/A | ✅ |

**How to Check Exports:**
```bash
aws cloudformation describe-stacks \
  --stack-name stocks-core-stack \
  --query 'Stacks[0].Outputs'
```

**How to Check Imports in Template:**
```bash
grep -r "!ImportValue" template-*.yml
```

**If Import Missing Export:**
- Check CloudFormation console for error: "Template error: instance of Fn::ImportValue references undefined export"
- Add Output to source template: `Outputs: { ExportName: !Sub "stocks-${Component}-${Key}": ... }`
- Redeploy source stack
- Retry dependent stack deployment
```

**Expected Result:** Clear documentation of stack dependencies

**Time Estimate:** 1 hour  
**Difficulty:** Easy (grep + document findings)

---

## Phase 3: OPTIONAL (Before Production) - Week 3-4

### Task P3.1: VPC Security Hardening
**Problem:** RDS publicly accessible, Lambdas not in VPC  
**Solution:** Move resources to private subnets

**Effort:** 6-8 hours  
**Benefit:** Production-grade security  
**Timeline:** Before prod cutover

---

### Task P3.2: Disaster Recovery Runbook
**Problem:** No documented recovery procedures  
**Solution:** Runbook for common failure scenarios

**Effort:** 2-3 hours  
**Benefit:** Faster incident response  
**Timeline:** Before prod cutover

---

## Summary: What to Do This Week

| Task | Effort | Impact | Owner |
|------|--------|--------|-------|
| C1.1: Fix webapp CF export validation | 1-2h | CRITICAL | Claude |
| C1.2: Fix loader module error | 1-2h | CRITICAL | Claude |
| C1.3: Add stack dependency checks | 1h | CRITICAL | Claude |
| M2.1: Add rollback logic | 2h | Major | Claude |
| M2.2: Rename workflows | 1h | Major | Claude |
| M2.3: Create orchestrator | 3-4h | Major | Claude |
| M2.4: Create runbook | 2-3h | Major | Claude |
| M2.5: Document exports | 1h | Major | Claude |

**Total This Week:** 12-17 hours  
**Result:** Fully automated deployments, clear documentation, zero manual AWS console work

---

## How to Proceed

1. **Start with C1.1** → Fix webapp validation error
2. **Then C1.2** → Fix loader module error  
3. **Then C1.3** → Add dependency validation
4. **Test everything** → Can deploy from scratch
5. **Then M2.1-M2.5** → Add automation + docs

Each task should be **1 commit with clear message** explaining the fix.

After each task, we validate it works before moving to next.

---

## Success Criteria (Weekly Review)

- [ ] All 3 critical issues resolved
- [ ] `deploy-app-stocks.yml` succeeds and loads data
- [ ] `deploy-webapp.yml` succeeds and frontend accessible
- [ ] Dependency validation prevents wrong-order deployments
- [ ] CLAUDE.md has complete deployment section
- [ ] New team member can deploy from scratch using runbook

When all above ✅ → Ready for Phase 2 (security hardening)
