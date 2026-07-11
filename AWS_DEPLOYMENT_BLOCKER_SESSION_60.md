# CRITICAL BLOCKER: IAM Permissions Required for Terraform Deployment

**Status:** AWS Deployment BLOCKED by insufficient IAM permissions  
**User:** algo-developer (arn:aws:iam::626216981288:user/algo-developer)  
**Account:** 626216981288

## Problem

The terraform deployment is blocked because the `algo-developer` IAM user lacks permissions to:

1. **DynamoDB** - Cannot read Terraform state lock table
   - `dynamodb:DescribeTable` on `arn:aws:dynamodb:us-east-1:626216981288:table/stocks-terraform-locks`
   - `dynamodb:DescribeTable` on `arn:aws:dynamodb:us-east-1:626216981288:table/algo-*-dev`

2. **IAM** - Cannot read roles and OIDC providers
   - `iam:GetRole`
   - `iam:GetOpenIDConnectProvider`

3. **DynamoDB (Tables)** - Cannot read existing state
   - All algo_* DynamoDB tables

4. **S3** - Cannot read bucket policies
   - `s3:GetBucketPolicy` on all algo-* buckets

5. **EC2** - Cannot read VPC attributes
   - `ec2:DescribeVpcAttribute`

6. **CloudFront** - Cannot read managed policies
   - `cloudfront:ListCachePolicies`
   - `cloudfront:ListOriginRequestPolicies`

7. **EventBridge** - Cannot read event rules
   - `events:ListTagsForResource`

## Solution

The AWS account admin must add the following permissions to the `algo-developer` user policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TerraformStateManagement",
      "Effect": "Allow",
      "Action": [
        "dynamodb:DescribeTable",
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:DeleteItem",
        "dynamodb:ListStateFiles"
      ],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:626216981288:table/stocks-terraform-locks",
        "arn:aws:dynamodb:us-east-1:*:table/algo*"
      ]
    },
    {
      "Sid": "IAMReadPermissions",
      "Effect": "Allow",
      "Action": [
        "iam:GetRole",
        "iam:GetPolicy",
        "iam:GetOpenIDConnectProvider",
        "iam:ListRolePolicies",
        "iam:ListAttachedRolePolicies"
      ],
      "Resource": [
        "arn:aws:iam::626216981288:role/*",
        "arn:aws:iam::626216981288:policy/*",
        "arn:aws:iam::626216981288:oidc-provider/*"
      ]
    },
    {
      "Sid": "S3BucketPolicies",
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketPolicy",
        "s3:PutBucketPolicy",
        "s3:GetBucketVersioning",
        "s3:GetBucketTagging"
      ],
      "Resource": "arn:aws:s3:::algo-*"
    },
    {
      "Sid": "EC2VPCOperations",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeVpcAttribute",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSubnets",
        "ec2:DescribeNetworkInterfaces"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudFrontOperations",
      "Effect": "Allow",
      "Action": [
        "cloudfront:ListCachePolicies",
        "cloudfront:ListOriginRequestPolicies",
        "cloudfront:ListResponseHeadersPolicies",
        "cloudfront:GetCachePolicy",
        "cloudfront:GetOriginRequestPolicy",
        "cloudfront:GetResponseHeadersPolicy"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EventBridgeOperations",
      "Effect": "Allow",
      "Action": [
        "events:ListTagsForResource",
        "events:DescribeRule"
      ],
      "Resource": "arn:aws:events:*:626216981288:rule/*"
    },
    {
      "Sid": "LambdaOperations",
      "Effect": "Allow",
      "Action": [
        "lambda:UpdateFunctionConfiguration",
        "lambda:CreateProvisionedConcurrencyConfig",
        "lambda:UpdateProvisionedConcurrencyConfig",
        "lambda:DeleteProvisionedConcurrencyConfig",
        "lambda:ListProvisionedConcurrencyConfigs",
        "lambda:GetFunctionConfiguration"
      ],
      "Resource": "arn:aws:lambda:*:626216981288:function:*"
    }
  ]
}
```

## Alternative: Use AWS Root or Admin Role

If adding permissions to the user is not possible, you can deploy using:

```bash
# Using AWS root account (if available)
aws configure --profile admin  # Configure with root credentials
terraform -chdir=terraform apply -auto-approve

# OR using an IAM role with broader permissions
assume-role AdminRole  # If your organization uses role assumption
terraform -chdir=terraform apply -auto-approve
```

## Current System Status

✅ **Local System:**
- All data corruption fixed
- Database clean (8.5M+ prices, fresh scores)
- API dev server operational
- Dashboard working locally
- Orchestrator running

✅ **Code Ready:**
- Terraform configuration updated (provisioned concurrency enabled)
- All deployment scripts created
- Documentation complete

⏳ **Blocked:**
- Cannot deploy to AWS due to IAM permissions
- Provisioned concurrency fix not yet deployed
- EventBridge Scheduler not yet verified
- Dashboard not yet tested against AWS API
- Live trading not yet verified

## Next Steps

1. **AWS Admin Action Required:**
   - Add the above permissions to `algo-developer` user policy, OR
   - Provide credentials for an admin-level IAM role

2. **After Permissions are Added:**
   ```bash
   # Try terraform deployment again
   terraform -chdir=terraform apply -auto-approve
   ```

3. **Verify Deployment:**
   ```bash
   # Check if provisioned concurrency is active
   aws lambda list-provisioned-concurrency-configs \
     --function-name algo-api-dev \
     --region us-east-1
   
   # Should return: ProvisionedConcurrentExecutions: 1
   ```

4. **Complete End-to-End Testing:**
   - Run dashboard locally: `python -m dashboard --local`
   - Run dashboard against AWS: `python -m dashboard`
   - Verify orchestrator runs
   - Confirm live trading executes

## Why This is Critical

Without these permissions:
- Terraform cannot acquire the state lock
- Terraform cannot read existing resources  
- Terraform cannot create or update resources
- **The entire infrastructure deployment is blocked**

This is not a code issue - the system is ready to deploy. This is an **infrastructure/permissions issue** that requires AWS account administrator action.

## Escalation Path

1. Contact AWS account administrator
2. Provide them with this file and the required permissions JSON
3. Ask them to add these permissions to the `algo-developer` IAM user
4. Once complete, run: `terraform -chdir=terraform apply -auto-approve`

