# Lambda Database Connectivity Fix Guide

## Root Cause Analysis

Your Lambda function is returning "Internal server error" because it cannot connect to the database. The issues identified:

1. **Missing Environment Variables**: Lambda needs `DB_SECRET_ARN` to access database credentials
2. **IAM Permissions**: Lambda execution role lacks `secretsmanager:GetSecretValue` permission  
3. **VPC Configuration**: Lambda may be in wrong subnets or missing security group access
4. **CloudFormation Template Gaps**: Missing required exports for Lambda security group and site bucket

## Fix Implementation

### 1. Updated CloudFormation Templates

#### A. Core Infrastructure (`template-core.yml`)
Added missing resources:
- **Lambda Security Group**: Allows outbound traffic for AWS services access
- **Site Code Bucket**: For frontend deployment
- **Required Exports**: `LambdaSecurityGroupId` and `SiteCodeBucketName`

#### B. Webapp Serverless (`template-webapp-serverless.yml`)  
Fixed critical networking:
- **Public Subnets**: Moved Lambda from private to public subnets (no NAT Gateway)
- **Correct Imports**: Fixed CloudFront S3 bucket reference
- **Environment Variables**: Proper `DB_SECRET_ARN` configuration

### 2. Deployment Scripts Created

#### A. `update-core-infrastructure.sh`
Updates existing core stack with missing Lambda security group and site bucket.

#### B. `deploy-fixed-webapp.sh`
Complete webapp deployment with:
- Lambda code packaging
- S3 upload with versioning
- Database secret discovery
- Stack deployment with proper parameters
- Comprehensive testing

#### C. `fix-existing-lambda.sh`
Direct Lambda configuration fix for immediate resolution:
- Finds existing Lambda function automatically
- Locates database secret ARN
- Updates environment variables
- Configures VPC/security groups
- Adds IAM permissions for Secrets Manager

## Key Configuration Changes

### Environment Variables Required
```bash
DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789012:secret:stocks-db-secrets-xxxxx
WEBAPP_AWS_REGION=us-east-1
NODE_ENV=production
AWS_DEFAULT_REGION=us-east-1
```

### IAM Policy for Secrets Manager
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
            ],
            "Resource": "arn:aws:secretsmanager:us-east-1:*:secret:stocks-db-secrets-*"
        }
    ]
}
```

### VPC Configuration
- **Subnets**: Use public subnets for internet access to AWS services
- **Security Group**: Allow all outbound traffic for Secrets Manager/RDS access
- **Database Access**: Ensure Lambda security group can reach RDS (port 5432)

## Immediate Action Steps

### Option 1: Quick Fix (Recommended)
Use the AWS Console or CLI to update the existing Lambda:

1. **Environment Variables**:
   - Go to Lambda Console → Your Function → Configuration → Environment Variables
   - Add: `DB_SECRET_ARN` with your database secret ARN

2. **IAM Role**:
   - Go to IAM Console → Roles → Your Lambda Execution Role
   - Attach policy: `SecretsManagerReadWrite` or create custom policy above

3. **VPC Config**:
   - Lambda Console → Configuration → VPC
   - Select public subnets and security group with outbound internet access

### Option 2: Infrastructure Update
Deploy updated CloudFormation templates:

```bash
# Update core infrastructure
aws cloudformation update-stack \
    --stack-name your-core-stack \
    --template-body file://template-core.yml \
    --capabilities CAPABILITY_IAM

# Deploy webapp with fixes
aws cloudformation deploy \
    --template-file template-webapp-serverless.yml \
    --stack-name your-webapp-stack \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides LambdaCodeKey=your-lambda.zip
```

## Testing Commands

Once fixed, test these endpoints:

```bash
# Basic connectivity
curl https://ye9syrnj8c.execute-api.us-east-1.amazonaws.com/dev/

# Health check (no DB required)
curl https://ye9syrnj8c.execute-api.us-east-1.amazonaws.com/dev/health?quick=true

# Database-dependent endpoint
curl https://ye9syrnj8c.execute-api.us-east-1.amazonaws.com/dev/api/stocks?limit=1
```

## Expected Results

After applying the fixes:
- ✅ Root endpoint returns API info (not "Internal server error")
- ✅ Health endpoint shows system status
- ✅ Stocks endpoint returns data from database
- ✅ All pages in your webapp display data correctly

## Database Connection Flow

1. **Lambda starts** → Reads `DB_SECRET_ARN` environment variable
2. **Gets credentials** → Calls Secrets Manager with IAM permission
3. **Connects to RDS** → Uses retrieved credentials through VPC
4. **Serves API** → Returns data to frontend

## Validation Checklist

- [ ] Lambda has `DB_SECRET_ARN` environment variable
- [ ] IAM role has Secrets Manager permissions
- [ ] Lambda is in public subnets or has NAT Gateway
- [ ] Security group allows outbound traffic
- [ ] Database secret exists and is accessible
- [ ] RDS instance is running and accessible
- [ ] API Gateway routes to Lambda correctly

The core issue is that your Lambda cannot reach AWS Secrets Manager to get database credentials. Once the networking and IAM permissions are fixed, your webapp will be able to display data from the database.