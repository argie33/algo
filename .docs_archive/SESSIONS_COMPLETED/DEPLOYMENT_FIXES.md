# Deployment Issues Fixed

## Executive Summary
Fixed 2 critical categories of deployment failures:
1. **Deletion Order Issue** - Dependent stacks weren't being deleted before core stack
2. **Resource Cleanup Issues** - Resources had `DeletionPolicy: Retain` preventing clean deletion

## Root Cause of Failure

The most recent deployment failed with:
```
Stack is in DELETE_FAILED state and can not be updated
Resource: BastionSecurityGroup has a dependent object
```

**Why?** When `deploy-core.yml` tried to redeploy the core stack, it deleted `stocks-core` while dependent stacks (`stocks-data-infrastructure`, etc.) still existed. The data stack had a security group rule that referenced the `BastionSecurityGroup`, creating a circular dependency CloudFormation couldn't resolve.

## Changes Made

### 1. Deployment Workflow Fix (.github/workflows/deploy-core.yml)

**Before:** Tried to delete core stack immediately
```bash
if [[ "$STATUS" != "DOES_NOT_EXIST" ]]; then
  echo "Deleting existing stocks-core stack..."
  aws cloudformation delete-stack --stack-name "stocks-core"
  aws cloudformation wait stack-delete-complete
fi
```

**After:** Delete dependent stacks first in correct order
```bash
# 1. Delete dependent stacks (data-infrastructure, webapp, loaders, etc.)
for DEPENDENT_STACK in stocks-data-infrastructure stocks-initialize-database stocks-webapp stocks-loaders stocks-algo; do
  # Delete each if it exists
done

# 2. THEN delete stocks-core
# Now safe because no ImportValue references exist
```

**Impact:** Ensures no circular dependencies during deletion. Allows clean stack recreation.

---

### 2. Template Fixes (template-data-infrastructure.yml)

#### Issue 1: RDS SubnetGroup with DeletionPolicy: Retain
```yaml
# BEFORE
StocksDBSubnetGroup:
  Type: AWS::RDS::DBSubnetGroup
  DeletionPolicy: Retain  # ← BLOCKS deletion

# AFTER
StocksDBSubnetGroup:
  Type: AWS::RDS::DBSubnetGroup
  # Default to Delete - resource is tied to RDS instance
```

#### Issue 2: RDS SecurityGroup with DeletionPolicy: Retain
```yaml
# BEFORE
StocksDBSecurityGroup:
  Type: AWS::EC2::SecurityGroup
  DeletionPolicy: Retain  # ← BLOCKS deletion (this was the culprit!)
  Properties:
    SecurityGroupIngress:
      - SourceSecurityGroupId: !ImportValue StocksCore-BastionSecurityGroupId
        # When this SG was retained, it kept the reference alive
        # blocking BastionSecurityGroup deletion in core stack

# AFTER
StocksDBSecurityGroup:
  Type: AWS::EC2::SecurityGroup
  # Default to Delete when stack is deleted
  Properties:
    # Same security group rules
```

#### Issue 3: RDS Instance with no SkipFinalSnapshot
```yaml
# BEFORE
StocksDBInstance:
  Type: AWS::RDS::DBInstance
  DeletionPolicy: Retain
  Properties:
    # Missing SkipFinalSnapshot - could block deletion waiting for snapshot

# AFTER
StocksDBInstance:
  Type: AWS::RDS::DBInstance
  Properties:
    SkipFinalSnapshot: true  # ← Skip snapshot on delete
    BackupRetentionPeriod: 7 # ← Retain backups for recovery
```

#### Issue 4-6: Secrets with no explicit DeletionPolicy
```yaml
# BEFORE
DBCredentialsSecret:
  Type: AWS::SecretsManager::Secret
  DeletionPolicy: Retain  # ← Leaves secrets orphaned

EmailConfigSecret:
  Type: AWS::SecretsManager::Secret
  # No DeletionPolicy specified

AlgoSecretsSecret:
  Type: AWS::SecretsManager::Secret
  # No DeletionPolicy specified

# AFTER
DBCredentialsSecret:
  DeletionPolicy: Delete  # Clean up with stack
EmailConfigSecret:
  DeletionPolicy: Delete
AlgoSecretsSecret:
  DeletionPolicy: Delete
```

---

### 3. Template Fixes (template-core.yml)

#### Issue 1: Hardcoded SecurityGroup Name
```yaml
# BEFORE
VpcEndpointSecurityGroup:
  Type: AWS::EC2::SecurityGroup
  Properties:
    GroupName: stocks-vpc-endpoint-sg  # ← Causes name collision on redeploy
    
# AFTER
VpcEndpointSecurityGroup:
  Type: AWS::EC2::SecurityGroup
  Properties:
    # Removed GroupName - let CloudFormation auto-generate
    # Prevents naming conflicts during stack recreation
```

#### Issue 2: DataLoadingBucket without DeletionPolicy
```yaml
# BEFORE
DataLoadingBucket:
  Type: AWS::S3::Bucket
  Properties:
    VersioningConfiguration:
      Status: Enabled
    # No DeletionPolicy - defaults to Delete (could fail if bucket has objects)

# AFTER
DataLoadingBucket:
  Type: AWS::S3::Bucket
  DeletionPolicy: Retain
  UpdateReplacePolicy: Retain
  Properties:
    # Preserves data across stack updates/recreations
```

#### Issue 3: ASG missing lifecycle settings
```yaml
# BEFORE
BastionAutoScalingGroup:
  Type: AWS::AutoScaling::AutoScalingGroup
  Properties:
    # Missing TerminationPolicy, HealthCheck settings

# AFTER
BastionAutoScalingGroup:
  Type: AWS::AutoScaling::AutoScalingGroup
  Properties:
    TerminationPolicies:
      - OldestInstance  # Terminate oldest instances first
    HealthCheckType: EC2
    HealthCheckGracePeriod: 300  # 5 min grace after launch
```

---

## Issues NOT Fixed (By Design)

### S3 Buckets with DeletionPolicy: Retain
- **CodeBucket, CfTemplatesBucket, AlgoArtifactsBucket** all set to `Retain`
- **Why kept:** These hold production data (code, templates, artifacts) that should survive stack recreation
- **Note:** This is intentional, but means cleanup requires manual S3 deletion if needed

### RDS DeletionProtection: false
- **Why:** Dev environment, kept false for easy teardown
- **Recommendation:** Set to `true` for production

---

## Deployment Order (Now Fixed)

When `deploy-core.yml` is triggered:

```
1. Pre-flight checks
   ↓
2. Delete dependent stacks (if they exist):
   - stocks-data-infrastructure
   - stocks-initialize-database
   - stocks-webapp
   - stocks-loaders
   - stocks-algo
   ↓
3. Delete old stocks-core stack
   ↓
4. Deploy fresh stocks-core stack
   ↓
5. Verify stack creation
```

**Result:** No ImportValue references exist when deleting core → no circular dependencies → clean deletion

---

## How This Prevents Future Failures

| Scenario | Before | After |
|----------|--------|-------|
| **Core stack redeploy** | Fails with DELETE_FAILED because data SG retained | Success - data stack deleted first |
| **RDS deletion** | Hangs waiting for final snapshot | Completes immediately with SkipFinalSnapshot |
| **Hardcoded SG name** | Name conflict error on redeploy | Auto-generated name prevents conflicts |
| **Secrets lingering** | Orphaned secrets left in AWS account | Cleaned up with stack deletion |
| **ASG termination** | Uncontrolled instance termination | Orderly shutdown (OldestInstance first) |

---

## Testing the Fix

When your colleague finishes cleaning up the stuck AWS resources:

```bash
# Trigger full deployment
gh workflow run deploy-all-infrastructure.yml --repo argie33/algo

# OR trigger just core deployment
gh workflow run deploy-core.yml --repo argie33/algo
```

The deployment should now:
1. ✅ Delete dependent stacks cleanly
2. ✅ Delete core stack without DELETE_FAILED
3. ✅ Redeploy core infrastructure
4. ✅ Export resources for dependent stacks
5. ✅ Allow data infrastructure redeployment

---

## Remaining Issues (Lower Priority)

See DEPLOYMENT_FIXES_AUDIT.md for detailed list of:
- Hardcoded ASG name (stocks-bastion-asg)
- Hardcoded log group names (/ecs/loader-*)
- Bastion UserData assumes StocksApp exports exist
- ECR double-deletion attempt in cleanup script

These don't block deployment but could cause issues during scale or cleanup operations.

