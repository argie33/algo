# Algo Orchestrator Deployment Diagnostics

## Current Status
- GitHub Actions workflow: `deploy-algo-orchestrator.yml`
- Target template: `template-algo-lambda-minimal.yml`
- Deployment status: **FAILING at CloudFormation deploy step**
- Error visibility: **BLOCKED - need CloudFormation error message**

## How to Get the CloudFormation Error Message

### Option 1: AWS Console (Recommended - Fastest)
1. Go to: https://console.aws.amazon.com/cloudformation/home?region=us-east-1
2. Find stack: **stocks-algo-orchestrator**
3. Click **Events** tab
4. Look for **red error message** at the top
5. Copy the full error text and share it

### Option 2: GitHub Actions Logs
1. Go to: https://github.com/argie33/algo/actions/workflows/deploy-algo-orchestrator.yml
2. Click **latest run** that failed
3. Click **Deploy Lambda Function + EventBridge** job
4. Scroll to bottom for CloudFormation error
5. Copy the error and share it

### Option 3: AWS CLI (if available locally)
```bash
aws cloudformation describe-stack-events \
  --stack-name stocks-algo-orchestrator \
  --region us-east-1 \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`]' \
  --output text
```

## What We Know Works
✅ GitHub Actions OIDC authentication (bootstrap-oidc.yml)
✅ All algo_*.py files present and valid
✅ lambda_function.py exists with valid lambda_handler
✅ Template-algo-lambda-minimal.yml is syntactically valid
✅ GitHub Actions role has AdministratorAccess permissions
✅ All required parameters are being passed correctly
✅ S3 bucket creation works
✅ Lambda code packaging works

## What Could Be Failing

### Most Likely (Order of Probability)
1. **Secrets don't exist in Secrets Manager**
   - Looking for: `stocks-db-secrets`, `algo-alpaca-credentials`
   - Check: AWS Secrets Manager console
   - Fix: Create these secrets with proper values

2. **IAM policy Resource ARN format is invalid**
   - The `!Sub` syntax might not be resolving correctly
   - Check: CloudFormation Events for "Resource must be in ARN format"

3. **Lambda function zip file is invalid or corrupted**
   - The S3 object might not contain proper lambda_function.py
   - Check: CloudFormation Events for "InvalidParameterValueException"

4. **SNS topic name contains invalid characters**
   - Environment parameter might be expanding to invalid chars
   - Check: CloudFormation Events for "Invalid TopicName"

5. **Stack already exists in ROLLBACK_COMPLETE state**
   - CloudFormation can't update a failed stack
   - Check: AWS CloudFormation console for stack status
   - Fix: The workflow should auto-cleanup, but may have failed

### Less Likely
- CloudFormation quota exceeded
- Lambda timeout during deployment
- Network connectivity issue in GitHub Actions
- Malformed JSON in IAM policies

## Next Steps (After Getting Error Message)

Once you have the CloudFormation error message:

1. **Reply with the exact error text**
2. I'll diagnose the root cause
3. We'll apply a targeted fix
4. Re-test the deployment

## Test Deployment Command (Manual)
If you can access AWS credentials locally:

```bash
aws cloudformation deploy \
  --template-file template-algo-lambda-minimal.yml \
  --stack-name stocks-algo-test \
  --parameter-overrides \
    LambdaFunctionCodeBucket="test-bucket" \
    LambdaFunctionCodeKey="test-key.zip" \
    DatabaseSecretArn="arn:aws:secretsmanager:us-east-1:626216981288:secret:test" \
    AlpacaSecretsArn="arn:aws:secretsmanager:us-east-1:626216981288:secret:test" \
    DryRunMode="true" \
    Environment="dev" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

This will show the exact CloudFormation error message.

## Files Involved
- `.github/workflows/deploy-algo-orchestrator.yml` - GitHub Actions workflow
- `template-algo-lambda-minimal.yml` - CloudFormation template
- `lambda/algo_orchestrator/lambda_function.py` - Lambda handler
- `algo_orchestrator.py` + other `algo_*.py` files - Algo logic
- `run_eod_loaders.sh` - EOD execution script

## Architecture Overview
```
GitHub Actions Workflow
  ↓
1. Validate algo components exist
2. Build Python dependencies
3. Package Lambda function (zip)
4. Upload to S3
5. Deploy CloudFormation stack
    ├─ SNS Topic
    ├─ Lambda Function (from S3)
    ├─ IAM Roles & Policies
    ├─ EventBridge Rule (daily 5:30pm ET)
    └─ CloudWatch Alarms + Logs
6. Verify EventBridge rule
7. Summary
```
