# GitHub Actions Workflow Issues Found

## CRITICAL BLOCKERS

### 1. Missing AWS CloudFormation Exports
The workflow expects this export to exist:
```
StocksCore-CfTemplatesBucketName
```

**Problem**: This comes from the `stocks-core` CloudFormation stack that must be deployed first.

**Impact**: Phase C, D, E jobs will FAIL when trying to upload templates to S3 bucket.

**Fix**: Ensure the core infrastructure stack is deployed:
```bash
aws cloudformation describe-stacks \
    --stack-name stocks-core \
    --query 'Stacks[0].StackStatus'
```

If not deployed, deploy it first:
```bash
aws cloudformation deploy \
    --stack-name stocks-core \
    --template-file template-core.yml \
    --capabilities CAPABILITY_IAM
```

### 2. Missing GitHub Secrets
The workflow references these GitHub secrets that must be configured:

Required Secrets:
- `AWS_ACCOUNT_ID` - Your AWS account number
- `RDS_USERNAME` - Database username
- `RDS_PASSWORD` - Database password
- `FRED_API_KEY` - Optional API key
- `IBKR_USERNAME` - Optional broker username
- `IBKR_PASSWORD` - Optional broker password

**Impact**: Deployment will fail if any required secret is missing.

**Fix**: Go to GitHub → Settings → Secrets and Variables → Actions → Add these secrets:
```
AWS_ACCOUNT_ID = (your 12-digit AWS account ID)
RDS_USERNAME = stocks
RDS_PASSWORD = (your database password)
```

### 3. Missing IAM Role
The workflow references this IAM role:
```
arn:aws:iam::{AWS_ACCOUNT_ID}:role/GitHubActionsDeployRole
```

**Problem**: This role must exist and have permissions to:
- Deploy CloudFormation stacks
- Create Lambda functions
- Create DynamoDB tables
- Create Step Functions
- Create EventBridge rules

**Impact**: AWS credential configuration will fail if role doesn't exist.

**Fix**: Create the IAM role in AWS:
```bash
aws iam create-role \
    --role-name GitHubActionsDeployRole \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Principal": {
            "Federated": "arn:aws:iam::AWS_ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com"
          },
          "Action": "sts:AssumeRoleWithWebIdentity",
          "Condition": {
            "StringEquals": {
              "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
            },
            "StringLike": {
              "token.actions.githubusercontent.com:sub": "repo:YOUR_GITHUB_ORG/YOUR_REPO:*"
            }
          }
        }
      ]
    }'
```

Then attach these policies:
```bash
aws iam attach-role-policy \
    --role-name GitHubActionsDeployRole \
    --policy-arn arn:aws:iam::aws:policy/AdministratorAccess
```

### 4. Missing CloudFormation Templates Bucket
The workflow uploads templates to S3 before deploying.

**Problem**: The S3 bucket specified in the export must exist and be accessible.

**Impact**: Phase C/D/E jobs will fail when uploading templates.

**Fix**: Create S3 bucket:
```bash
aws s3api create-bucket \
    --bucket stocks-cf-templates-${AWS_ACCOUNT_ID} \
    --region us-east-1
```

Then export it for CloudFormation:
```bash
aws cloudformation create-stack \
    --stack-name stocks-core-exports \
    --template-body '{
      "AWSTemplateFormatVersion": "2010-09-09",
      "Resources": {
        "CfTemplatesBucket": {
          "Type": "AWS::S3::Bucket",
          "Properties": {
            "BucketName": "stocks-cf-templates-'${AWS_ACCOUNT_ID}'"
          }
        }
      },
      "Outputs": {
        "CfTemplatesBucketName": {
          "Value": {"Ref": "CfTemplatesBucket"},
          "Export": {"Name": "StocksCore-CfTemplatesBucketName"}
        }
      }
    }'
```

---

## SECONDARY ISSUES

### 5. RDS Database Must Be Accessible
Lambda orchestrator needs to query `stock_symbols` table.

**Check**: 
```bash
psql -h ${DB_HOST} -U ${DB_USER} -d ${DB_NAME} -c "SELECT COUNT(*) FROM stock_symbols;"
```

### 6. ECS Cluster Must Exist
Step Functions references ECS cluster for other loader execution.

**Check**:
```bash
aws ecs describe-clusters --clusters stocks-cluster
```

---

## DEPLOYMENT SEQUENCE (Correct Order)

1. **Deploy Core Infrastructure** (if not already done)
   ```bash
   aws cloudformation deploy \
       --stack-name stocks-core \
       --template-file template-core.yml
   ```

2. **Configure GitHub Secrets**
   - Go to GitHub repo settings
   - Add AWS_ACCOUNT_ID, RDS_USERNAME, RDS_PASSWORD

3. **Create IAM Role for GitHub Actions**
   - Create GitHubActionsDeployRole
   - Attach CloudFormation, Lambda, DynamoDB, StepFunctions permissions

4. **Create S3 Templates Bucket**
   - Or ensure StocksCore-CfTemplatesBucketName export exists

5. **Verify RDS Access**
   - Test connection from local machine
   - Ensure stock_symbols table exists

6. **Push to Main**
   ```bash
   git push origin main
   ```
   This will trigger GitHub Actions deployment

---

## WHY THINGS AREN'T WORKING

The workflow can't run because it's missing:
1. AWS IAM credentials/role
2. GitHub secrets configuration
3. Core infrastructure stack
4. S3 templates bucket
5. Database accessibility

**Fix all 5 items above, then push to main.**

