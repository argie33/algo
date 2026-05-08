# Fix Workflow Deployment Failure

**Problem:** Deploy Algo Orchestrator workflow fails at "Configure AWS credentials" step

**Root Cause:** GitHub secret `AWS_ACCOUNT_ID` is not set

---

## What's Broken

**Workflow file line 40:**
```yaml
AWS_ACCOUNT_ID: ${{ secrets.AWS_ACCOUNT_ID }}
```

**Workflow file line 41:**
```yaml
AWS_ROLE_ARN: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/GitHubActionsDeployRole
```

When `AWS_ACCOUNT_ID` secret is missing:
- Role ARN becomes: `arn:aws:iam::::role/GitHubActionsDeployRole` (invalid)
- OIDC authentication fails
- Deployment job fails

---

## How to Fix

### Step 1: Find Your AWS Account ID

Run this in your AWS account (via AWS CLI or console):
```bash
aws sts get-caller-identity --query Account --output text
```

Or go to: https://console.aws.amazon.com/iam/home#/security_credentials

It's a 12-digit number like: `123456789012`

### Step 2: Set the GitHub Secret

1. Go to: https://github.com/argie33/algo/settings/secrets/actions
2. Click "New repository secret"
3. Name: `AWS_ACCOUNT_ID`
4. Value: (your 12-digit account ID)
5. Click "Add secret"

### Step 3: Verify the IAM Role Exists

The workflow assumes this IAM role exists:
- **Role name:** `GitHubActionsDeployRole`
- **Region:** us-east-1
- **Trust relationship:** Must trust GitHub OIDC provider

To verify it exists:
```bash
aws iam get-role --role-name GitHubActionsDeployRole
```

If it doesn't exist, you'll need to create it. The `bootstrap-oidc` workflow should have created it, but it may have failed.

### Step 4: Re-run the Workflow

1. Go to: https://github.com/argie33/algo/actions/workflows/deploy-algo-orchestrator.yml
2. Click "Run workflow"
3. Click green "Run workflow" button
4. Watch the execution

**Expected result:** Workflow succeeds ✅

---

## Verification Checklist

After applying the fix, verify:

- [ ] GitHub secret `AWS_ACCOUNT_ID` is set
- [ ] IAM role `GitHubActionsDeployRole` exists in AWS
- [ ] Bootstrap workflow succeeded (created OIDC provider)
- [ ] Re-run deploy-algo-orchestrator workflow
- [ ] Workflow turns green ✅
- [ ] CloudFormation stack `stocks-algo-orchestrator` appears in AWS Console
- [ ] Lambda function `algo-orchestrator` appears in AWS Console
- [ ] EventBridge rule `algo-eod-orchestrator` appears in AWS Console (ENABLED)

---

## If Still Failing

If the workflow still fails after setting the secret, check:

1. **GitHub Actions logs:** https://github.com/argie33/algo/actions
   - Click on the failed run
   - Click on "Deploy Lambda Function + EventBridge" job
   - Look for error messages

2. **AWS CloudFormation stacks:** https://console.aws.amazon.com/cloudformation
   - Look for `stocks-algo-orchestrator` stack
   - If it shows ROLLBACK_COMPLETE, click "Events" tab
   - Error message will show what failed

3. **CloudFormation Template:** 
   - Template syntax appears correct (uses !ImportValue for secrets)
   - Ensure `StocksApp-SecretArn` and `StocksApp-AlgoSecretsSecretArn` exports exist
   - Check `template-app-stocks.yml` created these exports

---

## Summary

**Immediate action needed:**
1. Set GitHub secret `AWS_ACCOUNT_ID` = your 12-digit AWS account ID
2. Verify IAM role `GitHubActionsDeployRole` exists
3. Re-run the workflow

**Once fixed:**
- Algo orchestrator will deploy to Lambda
- EventBridge scheduler will be created
- Algo will execute automatically at 5:30pm ET every day
- Database will get `algo_trades`, `algo_positions`, `algo_audit_log` tables

