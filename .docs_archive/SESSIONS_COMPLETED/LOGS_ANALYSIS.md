# Deployment Logs Analysis

## What We Found

### Old Deployment Log (deployment.log)
```
ERROR: User: arn:aws:iam::626216981288:user/reader is not authorized to 
perform: cloudformation:CreateStack
```

**Issue**: The old deployment was using a "reader" IAM user which only has read-only permissions.

**Status**: This is FIXED - GitHub Actions now uses `GitHubActionsDeployRole` with `AdministratorAccess`

---

## Current Issue: Validation Hook Error

Recent GitHub Actions runs show:
```
The following hook(s)/validation failed: [AWS::EarlyValidation::ResourceExistenceCheck]
```

This is different from the IAM permission error. It's happening AFTER authentication is successful.

---

## Commands to Run (Copy & Paste)

Run these in your AWS CLI terminal to diagnose the current issue:

### 1. Check if stocks-core stack exists and what state it's in
```bash
aws cloudformation describe-stacks \
  --stack-name stocks-core \
  --region us-east-1 \
  --query 'Stacks[0].[StackStatus,StackStatusReason]' \
  --output table
```

### 2. Get all recent stack events (see what failed)
```bash
aws cloudformation describe-stack-events \
  --stack-name stocks-core \
  --region us-east-1 \
  --max-items 30 \
  --query 'StackEvents[*].[Timestamp,LogicalResourceId,ResourceStatus,ResourceStatusReason]' \
  --output table
```

### 3. Check for CloudFormation hooks configured in account
```bash
aws cloudformation list-hooks --region us-east-1
```

### 4. If hooks are found, get details
```bash
aws cloudformation describe-hooks --region us-east-1
```

### 5. Check current AWS identity
```bash
aws sts get-caller-identity
```

---

## What These Will Tell Us

- **Command 1**: If stack exists, what state it's in (ROLLBACK_COMPLETE? CREATE_IN_PROGRESS? REVIEW_IN_PROGRESS?)
- **Command 2**: Exact error message and which resource failed
- **Command 3 & 4**: If there's an account-level validation hook causing the issue
- **Command 5**: Verify you're using the right AWS account and role

---

## Expected Results

If everything is working:
- Stack should either not exist (for first deployment) or be in `CREATE_COMPLETE` / `UPDATE_COMPLETE`
- No hooks should be listed
- Caller identity should show the GitHubActionsDeployRole

---

**Once you run these commands, share the output and we'll know exactly what's blocking the deployment.**
