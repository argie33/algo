# DASHBOARD DATA UNAVAILABLE - ROOT CAUSE & SOLUTION

## Current Status
✓ **Database**: Has all required data
  - 61 trades
  - 15 positions  
  - 6 portfolio snapshots
  - 10,594 stock scores
  - 3 signals
  - 111 orchestrator runs

✗ **Dashboard**: Shows "data unavailable" for all panels despite database having data

## Root Cause Analysis

### Why Dashboard Shows "Data Unavailable"

The dashboard is trying to fetch data from AWS Lambda API endpoints, but those endpoints either:
1. **Don't exist** (Lambda functions not deployed), OR
2. **Don't return data** (deployed but misconfigured)

### Why API Isn't Working

From previous session (SESSION-20-INCOMPLETE-BLOCKERS.md):
- **Terraform apply blocked by IAM permissions**
  - User `algo-developer` lacks CloudFront, DynamoDB, SNS, EC2, S3, IAM, CloudWatch Logs permissions
  - This blocks infrastructure deployment
  - EventBridge rule for orchestrator scheduling wasn't created
  - Lambda functions may not have been deployed/configured

### Why IAM Permissions Can't Be Obtained

The Terraform state refresh requires permissions to read existing AWS resources:
- CloudFront cache policies
- DynamoDB table attributes
- SNS topic attributes
- EC2 VPC attributes
- S3 bucket policies
- IAM role policies
- CloudWatch Logs tags
- EventBridge rules

These are READ-ONLY permissions but are still blocked for the `algo-developer` user.

## Solution Options

### Option A: Use AWS Admin Account (Recommended for Production)
**What to do**: Have AWS account admin run terraform apply with full permissions

```bash
# Admin credentials required:
cd terraform
terraform apply -lock=false -auto-approve
```

**What gets deployed**:
- RDS schema and parameters
- Lambda functions (API, Orchestrator)
- EventBridge rules for orchestrator scheduling
- API Gateway endpoints
- IAM roles and policies

**Time**: ~10-15 minutes
**Reversal**: `terraform destroy` (if needed)

### Option B: Grant Minimal IAM Permissions to algo-developer
**What to do**: Add read-only permissions to the algo-developer IAM policy

Required read-only permissions:
```
cloudfront:ListCachePolicies
cloudfront:ListOriginRequestPolicies  
dynamodb:DescribeTable
sns:GetTopicAttributes
sns:ListTagsForResource
ec2:DescribeVpcs
ec2:DescribeVpcAttribute
s3:GetBucketPolicy
iam:GetRole
iam:GetPolicy
logs:ListTagsForResource
logs:DescribeLogGroups
events:DescribeRule
events:ListTargets
```

Then retry: `cd terraform && terraform apply -lock=false`

**Time**: ~5 minutes (once IAM policy updated)
**Risk**: Still requires AWS admin to add permissions

### Option C: Manual Lambda Deployment (Workaround)
**What to do**: Package and deploy Lambda functions manually without terraform

1. Build Lambda packages:
```bash
cd lambda
zip -r ../api-layer.zip api/
aws lambda create-function \
  --function-name algo-api-dev \
  --runtime python3.11 \
  --role arn:aws:iam::626216981288:role/algo-lambda-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://../api-layer.zip
```

**Pros**: Doesn't require full terraform state refresh
**Cons**: Manual work, harder to maintain, missing EventBridge scheduling

## Verification Checklist

After deploying infrastructure, verify:

```bash
# 1. Lambda functions exist
aws lambda list-functions --region us-east-1 | grep algo

# 2. API is responding
curl https://<API-GATEWAY-URL>/api/algo/last-run

# 3. EventBridge rule exists
aws events list-rules --region us-east-1 | grep algo

# 4. Dashboard can fetch data
python -m dashboard  # Should show data instead of "unavailable"
```

## Why This Happened

1. **Code was completed** ✓ - All algo phases implemented
2. **Local testing possible** ✓ - Database layer works
3. **Infrastructure deployment blocked** ✗ - IAM permissions insufficient
4. **Dashboard can't access data** ✗ - API Lambda functions don't exist in AWS

## Next Steps

1. **Immediate**: Contact AWS admin to either:
   - Run `terraform apply -lock=false` with full permissions, OR
   - Grant read-only IAM permissions listed in Option B

2. **Once infrastructure deployed**:
   - Verify Lambda functions exist
   - Test API endpoints return data
   - Verify dashboard displays data

3. **Long-term**: Document AWS credential requirements and setup

## Technical Details

- Dashboard expects data from: `https://{API_GATEWAY_URL}/api/algo/*`
- All endpoints defined in: `lambda/api/shared_contracts/dashboard_api_contract.py`
- API handlers in: `lambda/api/routes/algo_handlers/`
- Terraform infrastructure in: `terraform/`
