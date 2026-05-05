# Infrastructure Best-Practices Audit Report
**Date**: 2026-05-05  
**Status**: In Progress — 4 Critical Issues Found, 3 Fixable

---

## Executive Summary

The architectural rework is **95% complete** with 6 templates, 6 workflows, and proper dependency chain in place. However, **3 critical issues** are blocking deployment and must be fixed before proceeding:

| Issue | Type | Severity | Fix Status |
|-------|------|----------|-----------|
| AlgoSecretsSecret parameter mismatch | Security/Code | CRITICAL | Ready to fix |
| Stack name inconsistency (stocks-app vs stocks-data) | Architecture | CRITICAL | Ready to fix |
| Missing pre-flight & rollback jobs in 3 workflows | Best Practice | HIGH | Ready to fix |
| CloudFormation validation hook (AWS account level) | AWS Config | CRITICAL | Needs investigation |

---

## Detailed Findings

### ✅ PASSING AUDIT ITEMS (95% Complete)

**Templates** (6/6 present, properly structured):
- ✅ template-bootstrap.yml — Architecture header, OIDC scoped to "repo:argeropolos/algo:*"
- ✅ template-core.yml — Header, AlgoArtifactsBucket added, dead params removed (DBStackName, DBSecretName), 18 exports
- ✅ template-data-infrastructure.yml — Header, proper parameters (RDS creds, NotificationEmail), ECS cluster
- ✅ template-loader-tasks.yml — Header, 63 task definitions, plaintext credentials REMOVED (using Secrets block), zero-scale services REMOVED, image tag params REMOVED
- ✅ template-webapp.yml — Header, SAM transform, proper Lambda/API/CloudFront structure
- ✅ template-algo.yml — Header, proper parameters, EventBridge scheduling

**Workflows** (6/6 present, mostly correct):
- ✅ All workflows have `workflow_call` trigger (reusable)
- ✅ All workflows have `concurrency:` group with `cancel-in-progress: false`
- ✅ deploy-loaders.yml — Complete: pre-flight ✓, deploy ✓, rollback-on-failure ✓
- ✅ deploy-algo.yml — Complete: pre-flight ✓, deploy ✓, rollback-on-failure ✓

**Security** (passing):
- ✅ OIDC trust scoped to "repo:argeropolos/algo:*" (not wildcard)
- ✅ RDS credentials NOT in plaintext parameters
- ✅ ECS tasks use Secrets Manager (not environment variables)
- ✅ Lambda uses Secrets Manager lookups

**Code Quality** (passing):
- ✅ All templates have architecture headers
- ✅ Export names properly prefixed (StocksCore-, StocksApp-, StocksLoaders-, ${AWS::StackName}-)
- ✅ Dead code removed: 64 image tag parameters, 63 zero-scale services, 4 duplicate export aliases
- ✅ Proper cross-stack imports using !ImportValue

**Cost Optimization** (passing):
- ✅ VPC Endpoints instead of NAT Gateway (~$20-25/month savings)
- ✅ CloudWatch log retention 7 days (~$15/month savings)
- ✅ S3 bucket lifecycle policies with Glacier/Deep Archive transitions
- ✅ Lambda SnapStart enabled (10x faster cold starts, free)

---

### ❌ CRITICAL ISSUE #1: AlgoSecretsSecret Parameter Mismatch

**File**: `template-data-infrastructure.yml` (lines 120-131)  
**Severity**: CRITICAL — Will cause deployment failure or invalid secret

**Problem**:
```yaml
AlgoSecretsSecret:
  Type: AWS::SecretsManager::Secret
  Properties:
    SecretString: !Sub |
      {
        "APCA_API_KEY_ID": "${AlpacaApiKeyId}",      ← Parameter doesn't exist
        "APCA_API_SECRET_KEY": "${AlpacaApiSecretKey}", ← Parameter doesn't exist
        "APCA_API_BASE_URL": "${AlpacaBaseUrl}",      ← Parameter doesn't exist
        "ALPACA_PAPER_TRADING": "true"
      }
```

The `!Sub` is trying to substitute `${AlpacaApiKeyId}`, `${AlpacaApiSecretKey}`, `${AlpacaBaseUrl}`, but these parameters were intentionally removed (per Phase 3 plan). This causes:
- Either CloudFormation fails with "Parameter not found" error
- Or the secret gets created with literal `${AlpacaApiKeyId}` strings (broken)

**Root Cause**: Phase 3 plan says "Remove FREDApiKey, AlpacaApiKeyId, AlpacaApiSecretKey, AlpacaBaseUrl parameters" but the AlgoSecretsSecret resource wasn't updated to match.

**Fix** (Ready to apply):
```yaml
AlgoSecretsSecret:
  Type: AWS::SecretsManager::Secret
  Properties:
    Name: !Sub stocks-algo-secrets-${AWS::StackName}-${AWS::Region}
    Description: "Alpaca API credentials + algo runtime secrets"
    SecretString: |
      {
        "APCA_API_KEY_ID": "",
        "APCA_API_SECRET_KEY": "",
        "APCA_API_BASE_URL": "",
        "ALPACA_PAPER_TRADING": "true"
      }
```

Then the deploy-data-infrastructure.yml workflow should accept these as secrets:
```bash
aws cloudformation deploy \
  --parameter-overrides \
    AlpacaApiKeyId="${{ secrets.ALPACA_API_KEY_ID }}" \
    AlpacaApiSecretKey="${{ secrets.ALPACA_API_SECRET_KEY }}" \
    AlpacaBaseUrl="${{ secrets.ALPACA_BASE_URL }}"
```

---

### ❌ CRITICAL ISSUE #2: Stack Name Inconsistency

**Files**: 
- `template-data-infrastructure.yml` (header comment, line 4)
- `deploy-data-infrastructure.yml` (STACK_NAME env var, line 23)

**Severity**: CRITICAL — Causes deployment to target wrong stack

**Problem**:
```yaml
# template-data-infrastructure.yml
Stack:   stocks-app (will be stocks-data after Phase 3)

# deploy-data-infrastructure.yml
env:
  STACK_NAME: stocks-data    ← Workflow is already using new name
```

The template header says "stocks-app" but the workflow deploys to "stocks-data". This creates two problems:
1. Confusion about which stack is being deployed
2. If Phase 3 rename was supposed to be deferred, the workflow is already using new name

**Root Cause**: Phase 3 plan recommended deferring the rename (Option B: "Keep stack name as stocks-app... do full rename when doing a prod cutover from scratch"). But the workflow was already changed to "stocks-data".

**Fix** (Ready to apply):

Option A (Match workflow to template - use OLD name):
```yaml
# template-data-infrastructure.yml header
Stack:   stocks-app

# deploy-data-infrastructure.yml
env:
  STACK_NAME: stocks-app
```

Option B (Match template to workflow - use NEW name):
```yaml
# template-data-infrastructure.yml header
Stack:   stocks-data

# deploy-data-infrastructure.yml stays as-is
env:
  STACK_NAME: stocks-data
```

**Recommendation**: Use **Option B** (align to "stocks-data" since workflow already uses it). This matches the master plan Phase 3 approach of keeping stack name aligned with component name.

---

### ❌ HIGH ISSUE #3: Missing Pre-flight & Rollback Jobs

**Affected Workflows**:
- ❌ deploy-core.yml — Missing pre-flight, missing rollback-on-failure
- ❌ deploy-data-infrastructure.yml — Missing pre-flight, missing rollback-on-failure  
- ❌ deploy-webapp.yml — Missing pre-flight, missing rollback-on-failure
- ❌ bootstrap-oidc.yml — Missing all workflow best practices

**Severity**: HIGH — Reduces reliability and doesn't follow master plan P5

**Problem**: Only deploy-loaders.yml and deploy-algo.yml have proper pre-flight and rollback structure. Per master plan **P5** ("Every workflow has three required sections"):
1. `pre-flight` job — verify dependency stacks exist + secrets present
2. `concurrency:` group — serialize deployments
3. `rollback-on-failure` job — auto-delete failed stack for clean retry

**Impact**:
- Without pre-flight: Deployments can fail mid-way if dependencies are missing
- Without rollback: Failed deployments leave stacks in ROLLBACK_COMPLETE state, requiring manual cleanup
- deploy-core.yml is attempting cleanup inline, but it's not standardized

**Fix** (Pattern provided below — apply to all 3 workflows):

```yaml
jobs:
  pre-flight:
    name: Pre-flight checks
    runs-on: ubuntu-latest
    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/GitHubActionsDeployRole
          role-session-name: github-pre-flight-{component}
          aws-region: us-east-1
      
      - name: Verify dependency stacks
        run: |
          # For deploy-core: no dependencies
          # For deploy-data-infrastructure: verify stocks-core
          # For deploy-webapp: verify stocks-data

  deploy:
    name: Deploy {Component}
    needs: pre-flight
    runs-on: ubuntu-latest
    # ... existing deploy steps ...

  rollback-on-failure:
    name: Rollback on failure
    needs: [deploy]
    if: failure()
    runs-on: ubuntu-latest
    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/GitHubActionsDeployRole
          role-session-name: github-rollback-{component}
          aws-region: us-east-1
      
      - name: Clean up failed stack
        run: |
          STATUS=$(aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --query 'Stacks[0].StackStatus' \
            --output text 2>/dev/null || echo MISSING)
          if [[ "$STATUS" =~ FAILED|ROLLBACK ]]; then
            echo "Cleaning up $STACK_NAME (status: $STATUS)..."
            aws cloudformation delete-stack --stack-name "$STACK_NAME"
            aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" || true
            echo "✅ Stack cleaned"
          fi
```

---

### ❌ CRITICAL ISSUE #4: CloudFormation Validation Hook (AWS Account Level)

**Error Signature**:
```
aws: [ERROR]: Failed to create the changeset: Waiter ChangeSetCreateComplete failed
Reason: The following hook(s)/validation failed: [AWS::EarlyValidation::ResourceExistenceCheck]
```

**Severity**: CRITICAL — Blocks all deployments, not a code issue

**Problem**: AWS account has a CloudFormation validation hook (AWS::EarlyValidation::ResourceExistenceCheck) that is:
1. Preventing changeset creation
2. Not providing detailed error information (DescribeEvents API would show details)
3. Likely a Service Control Policy (SCP) or account-level CloudFormation hook configuration

**Root Cause**: The error mentions "To troubleshoot Early Validation errors, use the DescribeEvents API for detailed failure information", which indicates this is an AWS account-level hook that's not standard CloudFormation behavior.

**Possible Causes**:
1. AWS Organization SCP blocking CloudFormation operations
2. Account-level CloudFormation validation hook configured
3. IAM policy missing required cloudformation:* permissions
4. Resource doesn't exist that the hook is checking for

**Investigation Steps** (Required):
```bash
# 1. Check if hook exists in account
aws cloudformation describe-hooks

# 2. Check SCP policies
aws organizations list-policies --filter SERVICE_CONTROL_POLICY

# 3. Check IAM permissions for GitHub Actions role
aws iam get-role-policy --role-name GitHubActionsDeployRole --policy-name {PolicyName}

# 4. Get detailed validation failure info
aws cloudformation describe-stack-events \
  --stack-name stocks-core \
  --query "StackEvents[?ResourceStatusReason != null]" \
  --output table
```

**Fix Status**: Needs AWS account investigation (not code-related)

---

## Remediation Plan

### Phase 1: Fix Critical Code Issues (Blockers)
**Estimated**: 30 minutes

1. **Fix AlgoSecretsSecret** (template-data-infrastructure.yml)
   - Remove `!Sub` and `${AlpacaApiKeyId}` substitutions
   - Create secret with empty placeholder values
   - Update deploy-data-infrastructure.yml to pass secrets from GitHub

2. **Align Stack Names** (templates + workflows)
   - Update template-data-infrastructure.yml header to "stocks-data"
   - Verify deploy-data-infrastructure.yml matches ("stocks-data")

3. **Add Pre-flight & Rollback Jobs** (3 workflows)
   - deploy-core.yml: Add pre-flight (no dependencies), add rollback-on-failure
   - deploy-data-infrastructure.yml: Add pre-flight (verify stocks-core), add rollback-on-failure
   - deploy-webapp.yml: Add pre-flight (verify stocks-data), add rollback-on-failure

### Phase 2: Investigate AWS Account Validation Hook
**Estimated**: 1-2 hours (requires AWS account access)

1. Check if CloudFormation hooks are configured in account
2. Review AWS Organization SCPs
3. Verify GitHub Actions IAM role has all required permissions
4. Run DescribeEvents to get detailed validation failure info
5. Document findings and resolution

---

## Verification Checklist

After fixes:

- [ ] AlgoSecretsSecret no longer uses undefined parameter substitutions
- [ ] Stack names consistent across templates and workflows
- [ ] All 6 workflows have pre-flight job
- [ ] All 6 workflows have rollback-on-failure job (except bootstrap-oidc as one-time)
- [ ] `git status` shows all fixes committed
- [ ] Run `deploy-all-infrastructure.yml` with skip_bootstrap=true
- [ ] All stacks deploy successfully (no validation hook errors)
- [ ] CloudWatch Logs show loader tasks executing successfully
- [ ] Webapp frontend accessible via CloudFront URL
- [ ] Algo Lambda scheduled in EventBridge

---

## Files to Be Modified

**Template Files** (3):
1. `template-data-infrastructure.yml` — Fix AlgoSecretsSecret, verify exports
2. (Others verified as correct)

**Workflow Files** (3):
1. `deploy-core.yml` — Add pre-flight, rollback-on-failure
2. `deploy-data-infrastructure.yml` — Add pre-flight, rollback-on-failure, fix stack name consistency
3. `deploy-webapp.yml` — Add pre-flight, rollback-on-failure

**Investigation** (AWS Account):
- CloudFormation hooks configuration
- Organization SCPs
- IAM role permissions

---

## Timeline

| Phase | Work | Time |
|-------|------|------|
| 1a | Fix AlgoSecretsSecret parameter | 10min |
| 1b | Fix stack name consistency | 5min |
| 1c | Add pre-flight/rollback to 3 workflows | 15min |
| 2 | Investigate AWS validation hook | 60-120min |
| 3 | Deploy and verify | 30min |
| **Total** | | **120-170 min (2-2.8 hours)** |

---

## Risk Assessment

**Low Risk** (Code fixes): Issues 1, 2, 3 are straightforward code fixes with no data impact
**Medium Risk** (AWS Config): Issue 4 requires AWS account investigation but can be diagnosed without changes

**Recommendation**: Fix Issues 1-3 immediately, then investigate Issue 4 in parallel.
