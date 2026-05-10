# CloudFormation Deployment Best Practices & Fixes

## What We Just Fixed

**Problem**: Stacks were stuck in `REVIEW_IN_PROGRESS` state because changesets were created but never executed or deleted.

**Root Causes**:
1. `aws cloudformation deploy` was creating changesets with no execution
2. Workflows didn't have proper changeset execution or rollback on failure
3. Multiple stack names (stocks-core vs stocks-core-stack) caused confusion

**Solution Implemented**:
✓ Deleted all stuck stacks (stocks-core, stocks-data, stocks-loaders-lambda-stack)
✓ Cleaned up old stacks with circular dependencies
✓ All workflows now have consistent error handling

---

## Best Practices Going Forward

### 1. **CloudFormation Deploy - Always Execute Changesets**

**Wrong (can leave stacks in REVIEW_IN_PROGRESS):**
```bash
aws cloudformation deploy \
  --template-file template.yml \
  --stack-name mystack \
  --no-fail-on-empty-changeset
```

**Right (explicitly handle changesets):**
```bash
aws cloudformation deploy \
  --template-file template.yml \
  --stack-name mystack \
  --no-fail-on-empty-changeset \
  --capabilities CAPABILITY_NAMED_IAM

# Always check for REVIEW_IN_PROGRESS after deploy
STATUS=$(aws cloudformation describe-stacks \
  --stack-name mystack \
  --query 'Stacks[0].StackStatus' --output text)

if [[ "$STATUS" == "REVIEW_IN_PROGRESS" ]]; then
  echo "ERROR: Changeset not executed. Deleting stack to recover."
  aws cloudformation delete-stack --stack-name mystack
  exit 1
fi
```

### 2. **Stack Naming Convention**

**Convention**: `{product}-{component}[-{env}]`

Examples:
- `stocks-oidc` (not `stocks-oidc-bootstrap`)
- `stocks-core` (not `stocks-core-stack`)
- `stocks-data` (not `stocks-app-stack`)
- `stocks-loaders` (not `stocks-ecs-tasks-stack`)
- `stocks-webapp-dev` (includes env)
- `stocks-algo-dev` (includes env)

**Why**: Consistent naming prevents naming conflicts, makes exports predictable, matches templates/workflows.

### 3. **Deployment Workflow Structure**

Every workflow MUST have these jobs in order:

```yaml
jobs:
  pre-flight:
    # 1. Verify dependencies exist
    # 2. Check all exports available
    # 3. Verify secrets configured
    
  deploy:
    needs: pre-flight
    # 1. Deploy CloudFormation stack
    # 2. Check stack status after deployment
    # 3. If REVIEW_IN_PROGRESS or failed: DELETE and exit
    # 4. Verify stack outputs exist
    
  rollback-on-failure:
    needs: [deploy]
    if: failure()
    # 1. Check stack status
    # 2. Delete if in FAILED/ROLLBACK state
    # 3. Clean up any partially created resources
```

### 4. **Stack Status Validation After Deploy**

```bash
# After aws cloudformation deploy completes:
FINAL_STATUS=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].StackStatus' --output text)

case "$FINAL_STATUS" in
  CREATE_COMPLETE | UPDATE_COMPLETE)
    echo "Success: Stack deployed"
    ;;
  REVIEW_IN_PROGRESS)
    echo "ERROR: Changeset not executed - deleting stack"
    aws cloudformation delete-stack --stack-name "$STACK_NAME"
    exit 1
    ;;
  CREATE_FAILED | ROLLBACK_COMPLETE | UPDATE_ROLLBACK_COMPLETE)
    echo "ERROR: Stack in failed state - rolling back"
    aws cloudformation delete-stack --stack-name "$STACK_NAME"
    exit 1
    ;;
  *)
    echo "ERROR: Unexpected status: $FINAL_STATUS"
    exit 1
    ;;
esac
```

### 5. **IAM Role & Credentials**

**For GitHub Actions**:
- Always use `GitHubActionsDeployRole` (has AdministratorAccess)
- Never use personal IAM users like `reader`
- OIDC-based authentication (no hardcoded credentials)

**For Local Testing**:
- Use AWS profile with CloudFormation permissions
- Never test with read-only users
- Verify `aws sts get-caller-identity` shows correct role

### 6. **Handling Old Stacks**

When renaming stacks (e.g., `stocks-core-stack` → `stocks-core`):

```bash
# Step 1: Create exports with predictable names in new stack
# Step 2: Update downstream stacks to import from new exports
# Step 3: Delete old stack once no consumers reference it

# Check for dependencies before deleting
aws cloudformation list-exports \
  --query "Exports[?starts_with(Name, 'StocksCore')]"
```

### 7. **Deployment Order**

**Always deploy in this sequence:**

```
1. stocks-oidc (one-time only)
   ↓
2. stocks-core (VPC, networking, storage)
   ↓
3. stocks-data (RDS, ECS cluster, secrets)
   ├→ 4a. stocks-loaders (ECS task definitions, EventBridge)
   ├→ 4b. stocks-webapp-dev (Lambda API, CloudFront)
   └→ 4c. stocks-algo-dev (Algo Lambda, scheduler)
```

**Why**: Later stacks depend on exports from earlier stacks.

---

## Monitoring & Alerts

### Add to all workflows:

```bash
# After deployment, verify no stacks are stuck
STUCK_STACKS=$(aws cloudformation list-stacks \
  --stack-status-filter REVIEW_IN_PROGRESS \
  --query 'StackSummaries[*].StackName' \
  --output text)

if [[ -n "$STUCK_STACKS" ]]; then
  echo "ALERT: Stacks stuck in REVIEW_IN_PROGRESS: $STUCK_STACKS"
  # Send alert to monitoring system
  exit 1
fi
```

---

## Checklist for Every Stack Deployment

- [ ] Stack naming follows convention: `{product}-{component}[-{env}]`
- [ ] All parameters have defaults or are provided
- [ ] All exports are prefixed correctly (e.g., `StocksCore-`, `StocksApp-`)
- [ ] All imports use correct export names
- [ ] Pre-flight job verifies dependencies
- [ ] Deploy job checks status after deployment
- [ ] Rollback job deletes stacks on failure
- [ ] No hardcoded values from other stacks
- [ ] IAM role has CloudFormation permissions
- [ ] Deployment triggered with correct credentials

---

## Recovery Procedure (for future issues)

If a stack gets stuck in REVIEW_IN_PROGRESS:

```bash
# 1. Reject any pending changesets
aws cloudformation delete-change-set \
  --stack-name $STACK_NAME \
  --change-set-name $CHANGESET_NAME

# 2. Delete the stuck stack
aws cloudformation delete-stack \
  --stack-name $STACK_NAME

# 3. Wait for deletion
aws cloudformation wait stack-delete-complete \
  --stack-name $STACK_NAME

# 4. Redeploy fresh
aws cloudformation deploy \
  --template-file template.yml \
  --stack-name $STACK_NAME \
  --capabilities CAPABILITY_NAMED_IAM
```

---

## Architecture Decision: Why These Practices?

1. **Pre-flight checks**: Fail fast before investing time in deployment
2. **Explicit error handling**: CloudFormation doesn't always fail visibly; we must check
3. **Consistent naming**: Prevents naming conflicts, makes exports predictable
4. **Rollback on failure**: Clean state for retry (vs manual cleanup)
5. **Proper IAM**: Prevents permission errors mid-deployment
6. **Dependency order**: Stacks deployed in correct order ensures imports resolve
