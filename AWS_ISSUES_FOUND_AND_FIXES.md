# 🔍 AWS INFRASTRUCTURE ISSUES - COMPLETE ANALYSIS & FIXES

## Executive Summary

Found **3 Critical Issues** causing AWS deployment failure:

| Issue | Severity | Status | Impact |
|-------|----------|--------|--------|
| ECS Task Definition Missing Container CPU/Memory | 🔴 CRITICAL | FOUND | 7 services failed to start |
| CloudFormation Stack Rollback | 🔴 CRITICAL | ACTIVE | All ECS resources deleted |
| ECR Images Outdated | 🟡 MEDIUM | WARNING | May contain old code |

---

## 🔴 ISSUE #1: ECS Task Definition Configuration (ROOT CAUSE)

### Problem
Container definitions in CloudFormation template are missing CPU and Memory specifications.

**File**: `/home/stocks/algo/template-app-ecs-tasks.yml`

**Example - GrowthMetricsTaskDefinition (Lines 2843-2879)**:
```yaml
# ❌ CURRENT (BROKEN)
GrowthMetricsTaskDefinition:
  Type: AWS::ECS::TaskDefinition
  Properties:
    Family: growth-metrics-calculator
    Cpu: "1024"        # ✅ Task-level CPU (OK)
    Memory: "2048"     # ✅ Task-level Memory (OK)
    ContainerDefinitions:
      - Name: growthmetrics-loader
        Image: !Join [":", [!ImportValue StocksCore-ContainerRepositoryUri, !Ref GrowthMetricsImageTag]]
        Essential: true
        # ❌ MISSING: Cpu and Memory at container level
        Environment: [...]
        LogConfiguration: [...]
```

### Why This Fails
1. Fargate requires **both task-level AND container-level CPU/Memory**
2. Without container-level specs, ECS validation fails
3. CloudFormation tries to create service → ECS rejects task → service times out
4. "Exceeded attempts to wait" error triggers stack ROLLBACK
5. All 7 dependent services cascade into CREATE_FAILED

### Affected Services (All 7)
1. GrowthMetricsService (growth-metrics-calculator:22) - **FIRST TO FAIL**
2. FactormetricsLoaderService (factormetrics-loader:21)
3. StockScoresService (stock-scores:73)
4. MomentumLoaderService (momentum-loader:19)
5. QualityMetricsService (quality-metrics-calculator:31)
6. ValueMetricsService (value-metrics-calculator:26)
7. PositioningLoaderService (positioning-loader:17)

---

## ✅ FIX #1: Add Container CPU/Memory to Template

### Solution
Add CPU and Memory to each container definition in the template.

**Required Changes** (for each task definition):

```yaml
# ✅ CORRECTED
GrowthMetricsTaskDefinition:
  Type: AWS::ECS::TaskDefinition
  Properties:
    Family: growth-metrics-calculator
    Cpu: "1024"
    Memory: "2048"
    ContainerDefinitions:
      - Name: growthmetrics-loader
        Image: !Join [":", [!ImportValue StocksCore-ContainerRepositoryUri, !Ref GrowthMetricsImageTag]]
        Cpu: 1024           # ✅ ADD THIS - must equal task CPU for single container
        Memory: 2048        # ✅ ADD THIS - must equal task Memory for single container
        Essential: true
        Environment: [...]
        LogConfiguration: [...]
```

### Implementation Steps

**Step 1: Backup Original Template**
```bash
cp /home/stocks/algo/template-app-ecs-tasks.yml /home/stocks/algo/template-app-ecs-tasks.yml.backup
```

**Step 2: Find All Container Definitions Missing CPU/Memory**
```bash
grep -n "ContainerDefinitions:" /home/stocks/algo/template-app-ecs-tasks.yml
# Shows all container definition sections that need fixing
```

**Step 3: Edit Template - Add CPU/Memory to Each Container**

The following sections need updating (search for these in the template):
- Line ~2855: `growthmetrics-loader` - Add `Cpu: 1024` and `Memory: 2048`
- Line ~2916: `value-metrics-calculator` - Add `Cpu: 1024` and `Memory: 2048`
- Line ~2983: `quality-metrics-calculator` - Add `Cpu: 512` and `Memory: 1024`
- Line ~3050: `positioning-loader` - Add `Cpu: 512` and `Memory: 1024`
- Line ~3117: `momentum-loader` - Add `Cpu: 512` and `Memory: 1024`
- Line ~3184: `factormetrics-loader` - Add `Cpu: 1024` and `Memory: 2048`
- Line ~3250: `stock-scores` - Add `Cpu: 2048` and `Memory: 4096`

**Pattern to add after `Image:` line in each container**:
```yaml
        Image: !Join [":", [!ImportValue ..., !Ref ...]]
        Cpu: <TASK_CPU>          # ← ADD THIS
        Memory: <TASK_MEMORY>    # ← ADD THIS
        Essential: true
```

**Step 4: Validate Template**
```bash
aws cloudformation validate-template \
  --template-body file://template-app-ecs-tasks.yml \
  --region us-east-1
```

**Step 5: Create New Stack or Update Existing**
```bash
# OPTION A: Delete broken stack and create new
aws cloudformation delete-stack --stack-name stocks-ecs-tasks-stack --region us-east-1
aws cloudformation wait stack-delete-complete --stack-name stocks-ecs-tasks-stack --region us-east-1

# Then deploy with fixed template (GitHub Actions will trigger this automatically)

# OPTION B: Try stack update (if CloudFormation allows)
aws cloudformation update-stack \
  --stack-name stocks-ecs-tasks-stack \
  --template-body file://template-app-ecs-tasks.yml \
  --region us-east-1 \
  --capabilities CAPABILITY_NAMED_IAM
```

---

## 🟡 ISSUE #2: CloudFormation Stack in ROLLBACK_COMPLETE

### Problem
Stack creation failed and rolled back, deleting all resources.

**Current Status**:
```
Stack: stocks-ecs-tasks-stack
Status: ROLLBACK_COMPLETE
Resources: All DELETE_COMPLETE (7 services, log groups, task definitions deleted)
```

### Why It Happened
1. GitHub Actions triggered CloudFormation deployment
2. CloudFormation tried to create ECS services
3. First service (GrowthMetricsService) failed due to CPU/Memory issue
4. All other services cascaded to CREATE_FAILED
5. CloudFormation initiated rollback
6. All resources deleted

### Impact
- ❌ No ECS services running
- ❌ GitHub Actions deployment blocked (no task definitions to query)
- ❌ No ECS-based data loaders operational

### Recovery
Once container CPU/Memory are fixed in template, redeploy stack:
```bash
# GitHub Actions will automatically redeploy when you push the fixed template
git add template-app-ecs-tasks.yml
git commit -m "fix: Add container CPU/Memory to ECS task definitions"
git push origin main
# GitHub Actions will trigger and redeploy the stack
```

---

## ⚠️ ISSUE #3: ECR Images Are 5+ Months Old

### Problem
Latest images in ECR are from Sept 2025 (5 months old relative to Jan 2026).

```bash
# Check image dates
aws ecr describe-images --repository-name stocks-app-registry --region us-east-1 \
  --query 'imageDetails[*].[imageTags,imagePushedAt]' --output text | sort -k2
# Shows July-September 2025 push dates
```

### Risk
- Images may contain old Python code
- Database timeout fixes may not be included
- Task definitions reference `:latest` tag (unreliable)

### Solution
Rebuild and push Docker images with latest code:
```bash
# 1. Verify Python loaders have all fixes (they do ✅)
# 2. Rebuild Docker images with latest code
# 3. Push to ECR with version tags (e.g., :v1.2.3)
# 4. Update template to use specific tags instead of :latest
```

**Currently Not Critical** because:
- Local Python loaders have all fixes ✅
- ECS services aren't running anyway (stack rolled back)
- Priority is fixing template first

---

## 📊 CURRENT SYSTEM STATUS

### ✅ Working
- Local API (Express): http://localhost:3001 - **WORKING**
- Local Loaders (Python): 9 concurrent processes - **RUNNING**
- Database: RDS connected - **OPERATIONAL**
- Lambda: Configuration set - **PARTIAL** (needs recycle)

### ❌ Broken
- AWS ECS Stack: ROLLBACK_COMPLETE - **FAILED**
- GitHub Actions: Can't deploy (no exports) - **BLOCKED**
- ECS Services: All 7 failed - **DOWN**

### ⏳ Pending
- Lambda instance recycle (needs manual action)

---

## 🚀 NEXT STEPS (IN ORDER)

### Step 1: Fix CloudFormation Template
1. Open `/home/stocks/algo/template-app-ecs-tasks.yml`
2. Add `Cpu` and `Memory` to each container definition
3. Commit and push to GitHub
4. Verify GitHub Actions redeploys stack

### Step 2: Verify Stack Creation
```bash
# Check stack status
aws cloudformation describe-stacks --stack-name stocks-ecs-tasks-stack \
  --region us-east-1 --query 'Stacks[0].StackStatus'

# Should show: CREATE_COMPLETE (not ROLLBACK_COMPLETE)
```

### Step 3: Verify Services Running
```bash
# Check all 7 services
aws ecs list-services --cluster stocks-cluster --region us-east-1

# Should list all 7 services with ACTIVE status
```

### Step 4: Verify GitHub Actions Can Deploy
- GitHub Actions will now successfully query CloudFormation exports
- Deployment pipeline will complete without "No task definition found" errors

### Step 5: Recycle Lambda (Separate Task)
- Once ECS issues resolved, recycle Lambda to load new timeout config
- This makes AWS API fully operational

---

## 📋 VERIFICATION CHECKLIST

After implementing fixes:

- [ ] Template validates without errors
- [ ] Stack status: CREATE_COMPLETE (not ROLLBACK_COMPLETE)
- [ ] All 7 services listed: `aws ecs list-services --cluster stocks-cluster`
- [ ] Services have DesiredCount: 1 and RunningCount: 1
- [ ] GitHub Actions workflow completes without errors
- [ ] No "No task definition found" errors in workflow logs
- [ ] Lambda is recycled and AWS API works

---

## 📝 SUMMARY OF FINDINGS

**Root Cause**: Container definitions missing CPU and Memory specifications in CloudFormation template

**Solution**: Add Cpu and Memory to each container definition in template-app-ecs-tasks.yml

**Files to Fix**: 
- `/home/stocks/algo/template-app-ecs-tasks.yml` (primary)

**Estimated Fix Time**: 30-45 minutes
- 15 min: Edit template (add CPU/Memory to 7 containers)
- 10 min: Validate and test
- 10 min: Commit, push, verify GitHub Actions

**Testing After Fix**: 5-10 minutes
- Verify stack creation: `aws cloudformation describe-stacks`
- Verify services running: `aws ecs list-services`
- Verify GitHub Actions passes

