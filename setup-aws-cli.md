# AWS CLI Setup for Data Verification

Your `algo-developer` IAM user exists in AWS with **ReadOnlyAccess** permissions, perfect for verifying RDS and other AWS resources.

## Step 1: Get Your Access Keys

You need to retrieve the access keys from AWS IAM. Run this command in AWS Console or through AWS CLI (if you have temporary credentials):

```bash
# If you already have AWS credentials:
aws iam create-access-key --user-name algo-developer

# This will output:
# {
#   "AccessKey": {
#     "UserName": "algo-developer",
#     "AccessKeyId": "AKIA...",
#     "Status": "Active",
#     "SecretAccessKey": "abc123...",
#     "CreateDate": "..."
#   }
# }
```

**IMPORTANT:** Save these securely. The SecretAccessKey is only shown once.

## Step 2: Configure AWS CLI Locally

```bash
aws configure --profile algo-dev

# Prompts:
# AWS Access Key ID: [paste your AKIA... from above]
# AWS Secret Access Key: [paste your secret key]
# Default region: us-east-1
# Default output format: json
```

## Step 3: Verify Setup Works

```bash
# Test read-only access (should work)
aws rds describe-db-instances --region us-east-1 --profile algo-dev

# Test write access (should be denied)
aws rds delete-db-instance --db-instance-identifier algo-db --profile algo-dev
# Expected: Access Denied
```

## Step 4: Check RDS Database State

Once verified, you can check:

```bash
# List all RDS instances
aws rds describe-db-instances --region us-east-1 --profile algo-dev --query 'DBInstances[*].[DBInstanceIdentifier,DBInstanceStatus,Engine,EngineVersion]' --output table

# Get specific RDS endpoint
aws rds describe-db-instances --region us-east-1 --profile algo-dev --query 'DBInstances[0].Endpoint' --output json

# Check RDS security group
aws ec2 describe-security-groups --region us-east-1 --profile algo-dev --filters "Name=group-name,Values=algo-rds-*" --query 'SecurityGroups[*].[GroupName,GroupId]' --output table
```

## Step 5: Connect to RDS Database (Optional)

Once you have the RDS endpoint:

```bash
# Get RDS credentials from Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id algo-rds-credentials \
  --region us-east-1 \
  --profile algo-dev \
  --query 'SecretString' \
  --output text | jq .

# Then connect with psql:
psql -h <rds-endpoint> -U postgres -d stocks -p 5432
```

---

## Terraform Output Alternative

If you have Terraform state access, you can also get the outputs directly:

```bash
cd terraform/
terraform output developer_user_name
terraform output developer_console_login_url
```

This will show the developer IAM user name without requiring AWS CLI setup.

