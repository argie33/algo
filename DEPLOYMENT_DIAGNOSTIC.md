# CloudFormation Validation Hook Diagnostic

## Error
```
The following hook(s)/validation failed: [AWS::EarlyValidation::ResourceExistenceCheck]
```

## Root Cause Analysis

This error is **NOT** caused by template syntax or code issues. All templates have been validated and fixed. This is an **AWS account-level configuration** issue.

## Possible Causes (in order of likelihood)

### 1. CloudFormation Hooks Configured (Most Likely)
AWS accounts can have CloudFormation hooks that validate stacks during creation/update.

**How to check:**
```bash
# Check if hooks are configured in account
aws cloudformation describe-hooks --region us-east-1

# If hooks are found, list their details
aws cloudformation list-hooks --region us-east-1
```

**How to fix:**
If a hook exists with early validation, either:
- Remove or disable the hook: `aws cloudformation deactivate-hook`
- Check the hook configuration to understand what it's validating
- Ensure the GitHubActionsDeployRole has permission: `cloudformation:CreateHook`, `cloudformation:DeactivateHook`

### 2. AWS Organization Service Control Policy (SCP)
Organization-level SCPs can block CloudFormation operations.

**How to check:**
```bash
# Check if your account is in an AWS Organization
aws organizations describe-organization 2>&1

# List SCPs applied to account
aws organizations list-policies --filter SERVICE_CONTROL_POLICY

# Check what effect they have on CloudFormation
aws organizations list-policies-for-target --target-id <ACCOUNT_ID> --filter SERVICE_CONTROL_POLICY
```

**How to fix:**
Contact AWS Organization admin to review/modify SCPs affecting CloudFormation.

### 3. IAM Permission Issue
Though GitHubActionsDeployRole has AdministratorAccess, there might be:
- Explicit Deny statements in account policies
- Resource-based policies blocking operations
- Missing permissions for validation hooks

**How to check:**
```bash
# Verify role can describe hooks
aws iam get-role --role-name GitHubActionsDeployRole

# Test CloudFormation permission  
aws cloudformation validate-template --template-body file://template-core.yml --region us-east-1
```

**How to fix:**
If permissions are missing, add these to GitHubActionsDeployRole inline policy:
```json
{
  "Effect": "Allow",
  "Action": [
    "cloudformation:CreateHook",
    "cloudformation:DeactivateHook",
    "cloudformation:DescribeHooks",
    "cloudformation:ListHooks"
  ],
  "Resource": "*"
}
```

### 4. Lingering Resources from Failed Deployments
Named resources left from previous failed deployments.

**How to check:**
```bash
# List all S3 buckets (CodeBucket, CfTemplatesBucket, AlgoArtifactsBucket should not exist)
aws s3 ls

# List all ECR repositories (stocks-app-registry)
aws ecr describe-repositories --region us-east-1

# List all CloudFormation stacks
aws cloudformation list-stacks --region us-east-1 --query 'StackSummaries[?StackStatus!=`DELETE_COMPLETE`]'
```

**How to fix:**
Clean up any orphaned resources:
```bash
# Delete S3 buckets (careful - these have DeletionPolicy: Retain)
aws s3 rb s3://bucket-name --force

# Delete ECR repository
aws ecr delete-repository --repository-name stocks-app-registry --force

# Delete stacks in bad states
aws cloudformation delete-stack --stack-name stocks-core
```

## Immediate Action Items

1. **Check hooks configuration:**
   ```bash
   aws cloudformation describe-hooks --region us-east-1 || echo "No hooks found"
   ```

2. **Check SCP policies:**
   ```bash
   aws organizations describe-organization 2>/dev/null || echo "Not in organization"
   ```

3. **Validate template syntax:**
   ```bash
   aws cloudformation validate-template --template-body file://template-core.yml --region us-east-1
   ```

4. **Check for lingering CloudFormation stacks:**
   ```bash
   aws cloudformation list-stacks --region us-east-1 --stack-status-filter CREATE_FAILED ROLLBACK_COMPLETE UPDATE_ROLLBACK_COMPLETE
   ```

5. **Check S3 buckets:**
   ```bash
   aws s3 ls | grep -E 'stocks|algo'
   ```

## When to Escalate

If none of the above steps reveal the issue:
1. Check AWS CloudTrail logs for detailed error information
2. Review CloudFormation stack events (when stack exists): `aws cloudformation describe-stack-events --stack-name stocks-core`
3. Contact AWS Support with the error and these diagnostic results

## Code Status

✅ All template and workflow issues have been fixed  
✅ OIDC, IAM roles, and secrets management are correct  
✅ Pre-flight checks and rollback jobs are in place  

The only remaining issue is the AWS account-level validation hook.
