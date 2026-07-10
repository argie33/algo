# AWS Admin Action Required - Unblock Terraform Deployment

**Account**: 626216981288  
**User**: algo-developer  
**Status**: ❌ BLOCKED - Cannot deploy infrastructure due to missing IAM permissions

---

## Problem

The `algo-developer` IAM user lacks permissions to deploy infrastructure via terraform or AWS CLI. Deployment is blocked on the following operations:

### Missing Permissions - Terraform State Refresh
These permissions are required when terraform refreshes state before applying:
- `dynamodb:DescribeTable` - Read DynamoDB table state
- `s3:GetBucketPolicy` - Read S3 bucket policies
- `iam:GetRole` - Read IAM role details
- `events:ListTagsForResource` - List EventBridge rule tags
- `ec2:DescribeVpcAttribute` - Read VPC DNS settings
- `logs:ListTagsLogGroup` - List CloudWatch log group tags
- `sns:GetTopicAttributes` - Read SNS topic details

### Missing Permissions - Infrastructure Deployment
- `lambda:PutProvisionedConcurrencyConfig` - Create Lambda provisioned concurrency
- `lambda:GetProvisionedConcurrencyConfig` - Read Lambda provisioned concurrency status
- `lambda:PublishVersion` - Publish Lambda function versions

---

## What Needs to Be Deployed

**Provisioned Concurrency** (eliminates Lambda 503 cold-start errors):
- API Lambda: 5 pre-warmed instances (~$5/month)
- Orchestrator Lambda: 2 pre-warmed instances (~$2.40/month)

**Expected Result**: 
- Lambda response times: 15-40s → <1s
- 503 errors eliminated
- System ready for production

---

## Solution for AWS Admin

### Option 1: Grant Comprehensive Terraform Permissions (Recommended)

Create an IAM policy for `algo-developer` user with these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:DescribeTable",
        "dynamodb:ListTagsOfResource",
        "s3:GetBucketPolicy",
        "s3:GetObject",
        "s3:PutObject",
        "iam:GetRole",
        "iam:GetRolePolicy",
        "iam:ListRolePolicies",
        "events:ListTagsForResource",
        "events:DescribeRule",
        "ec2:DescribeVpcAttribute",
        "ec2:DescribeVpcs",
        "ec2:DescribeSecurityGroups",
        "logs:ListTagsLogGroup",
        "logs:DescribeLogGroups",
        "sns:GetTopicAttributes",
        "lambda:GetFunction",
        "lambda:PublishVersion",
        "lambda:PutProvisionedConcurrencyConfig",
        "lambda:GetProvisionedConcurrencyConfig"
      ],
      "Resource": "*"
    }
  ]
}
```

Then user can run:
```bash
cd terraform
terraform apply -lock=false
```

### Option 2: Run Deployment Directly

If permissions cannot be granted to algo-developer, AWS admin can run deployment directly:

```bash
cd terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan
```

---

## Verification After Deployment

Once deployed, verify provisioned concurrency is active:

```bash
aws lambda get-provisioned-concurrency-config \
  --function-name algo-api-dev \
  --qualifier LIVE \
  --region us-east-1

aws lambda get-provisioned-concurrency-config \
  --function-name algo-algo-dev \
  --qualifier LIVE \
  --region us-east-1
```

---

## What's Already Done

✅ **Code**: All issues fixed and verified locally
- Portfolio fallback logic fixed
- Data loaders working correctly  
- Database populated with real data (8.5M+ rows)
- API endpoints returning real data
- Dashboard rendering correctly
- Orchestrator executing 9 phases successfully
- Paper trading active via Alpaca

✅ **Infrastructure as Code**: Terraform configured and ready
- Provisioned concurrency configured in terraform.tfvars (5 units API, 2 units Orchestrator)
- All modules validated
- Ready for deployment

✅ **Testing**: Local system verified end-to-end
- Dev server: localhost:3001
- Dashboard: localhost with --local flag
- Orchestrator: executing all phases
- Trading: paper mode active

❌ **Deployment**: Blocked by AWS IAM permissions
- terraform apply fails during state refresh
- AWS CLI operations fail with AccessDeniedException
- User cannot read or write infrastructure

---

## Timeline

- **Code fixes**: Completed and verified
- **Infrastructure config**: Completed
- **Deployment attempts**: Failed due to IAM permissions (3 attempts)
- **Current status**: Ready for deployment, awaiting AWS admin action

---

## Next Steps

1. **AWS Admin**: Grant permissions above to `algo-developer` user OR deploy infrastructure directly
2. **Developer**: Run `terraform apply -lock=false` (once permissions granted)
3. **Verification**: Check provisioned concurrency status in AWS console
4. **Production Ready**: System ready for live trading with provisioned concurrency active

---

## Support Contact

If you need clarification on required permissions or deployment steps, contact the development team. All terraform configuration and documentation is in `/terraform` directory.

**Account ID**: 626216981288  
**Region**: us-east-1  
**User**: algo-developer  
**Status**: Ready for deployment (awaiting IAM permissions)
