# AWS CLI Setup for Data Verification

Your infrastructure includes a read-only IAM user `algo-developer` for local verification. This guide walks you through setting it up.

## Overview

| Component | Status | Purpose |
|-----------|--------|---------|
| **algo-developer IAM user** | ✅ Created | Read-only access (no write permissions) |
| **ReadOnlyAccess policy** | ✅ Attached | Can read all AWS resources |
| **Custom permissions** | ✅ Added | Lambda invoke, CloudWatch logs, Secrets access |
| **AWS CLI locally** | ⚠️ Need setup | Use to verify RDS, Lambda, and other resources |

## Why This Matters

- **Local development:** Verify AWS resources without needing full deployment credentials
- **Security:** Read-only prevents accidental changes
- **Audit trail:** All verification activities logged in CloudTrail
- **CI/CD separation:** GitHub Actions uses separate deployment credentials

## Step-by-Step Setup

### 1. Create Access Keys (AWS Console or CLI)

**Via AWS Console:**
1. Go to: https://console.aws.amazon.com/iam/
2. Click "Users" → `algo-developer`
3. Click "Create access key"
4. Choose "Command line interface (CLI)"
5. Copy **Access Key ID** (looks like `AKIA...`)
6. Copy **Secret Access Key** (shown only once - save securely!)

**Via AWS CLI** (if you have temp credentials):
```bash
aws iam create-access-key --user-name algo-developer
```

### 2. Save Credentials Locally

**Option A: Using `aws configure` (recommended)**

```bash
aws configure --profile algo-dev

# Prompts:
# AWS Access Key ID: [paste AKIA...]
# AWS Secret Access Key: [paste your secret]
# Default region: us-east-1
# Default output format: json
```

This creates `~/.aws/credentials` and `~/.aws/config`

**Option B: Manual (Windows)**

Create or edit `C:\Users\%USERNAME%\.aws\credentials`:
```
[algo-dev]
aws_access_key_id = AKIA...
aws_secret_access_key = abc123...
```

Create or edit `C:\Users\%USERNAME%\.aws\config`:
```
[profile algo-dev]
region = us-east-1
output = json
```

### 3. Verify Setup Works

Test that credentials are configured correctly:

```bash
# Should succeed (read-only operation)
aws ec2 describe-vpcs --region us-east-1 --profile algo-dev

# Should return "Access Denied" (write operation blocked)
aws ec2 delete-vpc --vpc-id vpc-0000 --profile algo-dev
```

If first command works → ✅ You're ready!

## Verification Commands

### Check RDS Database Status

```bash
# List all RDS instances
aws rds describe-db-instances \
  --region us-east-1 \
  --profile algo-dev \
  --query 'DBInstances[*].[DBInstanceIdentifier,DBInstanceStatus,Engine,EngineVersion]' \
  --output table

# Example output:
# |--------|--------|--------|--------|
# | algo-db| available | postgres | 14.6  |
# |--------|--------|--------|--------|
```

### Get RDS Connection Details

```bash
# Get RDS endpoint hostname
aws rds describe-db-instances \
  --region us-east-1 \
  --profile algo-dev \
  --db-instance-identifier algo-db \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text

# Example: algo-db.c9akciq32.us-east-1.rds.amazonaws.com
```

### Retrieve RDS Credentials from Secrets Manager

```bash
# Get database credentials
aws secretsmanager get-secret-value \
  --secret-id algo-rds-credentials \
  --region us-east-1 \
  --profile algo-dev \
  --query 'SecretString' \
  --output text | jq .

# Returns:
# {
#   "username": "postgres",
#   "password": "...",
#   "engine": "postgres",
#   "host": "algo-db.c9akciq32.us-east-1.rds.amazonaws.com",
#   "port": 5432,
#   "dbname": "stocks"
# }
```

### Connect to RDS Database

Once you have the endpoint and credentials:

```bash
# Install psql if needed
# macOS: brew install postgresql
# Windows: https://www.postgresql.org/download/windows/
# Ubuntu: sudo apt-get install postgresql-client

# Connect to RDS
psql \
  --host algo-db.c9akciq32.us-east-1.rds.amazonaws.com \
  --port 5432 \
  --username postgres \
  --dbname stocks

# Enter password when prompted (from Secrets Manager)

# Then check data:
SELECT COUNT(*) FROM stock_symbols;
SELECT MAX(date) FROM price_daily;
SELECT COUNT(*) FROM stock_scores;
```

### Check Lambda Functions

```bash
# List all Lambda functions
aws lambda list-functions \
  --region us-east-1 \
  --profile algo-dev \
  --query 'Functions[*].[FunctionName,Runtime,CodeSize]' \
  --output table
```

### Check EventBridge Rules

```bash
# List all EventBridge rules
aws scheduler list-schedules \
  --region us-east-1 \
  --profile algo-dev \
  --query 'Schedules[*].[Name,State,Schedule]' \
  --output table
```

## Permissions

The `algo-developer` user has:

```
✅ ReadOnlyAccess (AWS managed policy)
   - ec2:Describe*
   - rds:Describe*
   - lambda:Get*
   - s3:Get*
   - secretsmanager:GetSecretValue
   - kms:Decrypt
   - logs:*

❌ NO write/delete permissions
   - No ec2:Create/Delete
   - No rds:Delete
   - No lambda:Delete
   - No s3:Put/Delete
   - No iam:*
```

## Troubleshooting

**"Access Denied" when running commands?**
- Check credentials are saved in `~/.aws/credentials`
- Verify profile name matches (`--profile algo-dev`)
- Confirm region is correct (`us-east-1`)

**Can't see RDS instance?**
- Confirm RDS is deployed (check terraform.tfstate or AWS Console)
- Verify region is `us-east-1`
- Try: `aws rds describe-db-instances --region us-east-1 --profile algo-dev`

**Can't decrypt Secrets Manager values?**
- `algo-developer` needs KMS decrypt permission (should be included)
- Try: `aws secretsmanager get-secret-value --secret-id algo-rds-credentials --profile algo-dev`

## Next Steps

1. ✅ Set up credentials above
2. ✅ Run verification commands to confirm RDS is operational
3. ✅ Connect to RDS and check data freshness
4. ✅ Monitor CloudWatch logs for any issues

All logs are stored in CloudWatch and can be viewed via AWS Console.
