# Credential Rotation Setup Guide

This document walks through deploying the automatic credential rotation system.

## What Gets Rotated

| Credential | Frequency | Method | Owner |
|-----------|-----------|--------|-------|
| RDS Master Password | Every 30 days | Automatic (Lambda) | AWS Secrets Manager |
| Alpaca API Keys | Every 90 days | Manual | You (in Alpaca dashboard) |
| SMTP Credentials | On change | Manual | You (via email provider) |

## Architecture

```
Secrets Manager (stores credentials)
    ↓ (every 30 days)
Lambda Rotation Function
    ↓ (3 steps: create → set → finish)
RDS (updates master user password)
    ↓ (stored back in)
Secrets Manager (new version marked AWSCURRENT)
```

## Pre-Deployment Checklist

- [ ] AWS Region configured: `echo $AWS_REGION`
- [ ] AWS Account ID known: `aws sts get-caller-identity --query Account`
- [ ] PostgreSQL 14 RDS instance running
- [ ] RDS instance has security group allowing Lambda access (port 5432)
- [ ] Secrets Manager has credentials already stored (created by database module)

## Step 1: Build psycopg2 Lambda Layer

The Lambda function needs the `psycopg2` PostgreSQL driver, which requires compilation.

```bash
# Navigate to database module
cd terraform/modules/database

# Build the layer
bash build-psycopg2-layer.sh

# Verify output
ls -lh python-psycopg2-layer.zip
```

Expected output: `python-psycopg2-layer.zip` (~30-50MB)

### Troubleshooting Layer Build

If build fails, ensure you have:
- Python 3.11 installed: `python3.11 --version`
- pip available: `pip --version`
- Write access to directory: `ls -w terraform/modules/database/`

## Step 2: Configure Secrets Manager

Ensure the RDS credentials are stored in Secrets Manager:

```bash
# Check existing secret
aws secretsmanager describe-secret \
  --secret-id <project>-db-credentials-<environment>

# If it exists, verify the secret value has correct format:
aws secretsmanager get-secret-value \
  --secret-id <project>-db-credentials-<environment> \
  --query SecretString --output text | jq .
```

Expected secret format:
```json
{
  "username": "postgres",
  "password": "***actual-password***",
  "host": "project-db.xxxxx.us-east-1.rds.amazonaws.com",
  "port": 5432,
  "dbname": "stocks",
  "engine": "postgresql"
}
```

## Step 3: Deploy Terraform

Apply the database module with rotation infrastructure:

```bash
cd terraform

# Plan to review changes
terraform plan -target=module.database

# Apply rotation infrastructure
terraform apply -target=module.database

# Verify Lambda function created
aws lambda get-function \
  --function-name <project>-rds-rotation-<environment>
```

## Step 4: Verify Rotation Setup

Test that everything is connected:

```bash
# Test RDS connection with stored credentials
python credential_rotation_utils.py \
  --region us-east-1 \
  --environment <environment> \
  test-connection \
  --secret-name <project>-db-credentials-<environment>

# Should output: "✓ Connection successful"
```

## Step 5: Verify Lambda Has Permissions

Test that Lambda can read/write Secrets Manager:

```bash
# Check Lambda can assume its role
aws lambda get-function-concurrency \
  --function-name <project>-rds-rotation-<environment>

# Invoke Lambda with test event
aws lambda invoke \
  --function-name <project>-rds-rotation-<environment> \
  --payload '{
    "ClientRequestToken": "test-token",
    "SecretId": "<project>-db-credentials-<environment>",
    "Step": "create",
    "SecretVersion": "test-version"
  }' \
  /tmp/lambda-response.json

cat /tmp/lambda-response.json
```

## Step 6: Enable Automatic Rotation

Secrets Manager will automatically trigger Lambda every 30 days. Verify it's configured:

```bash
aws secretsmanager describe-secret \
  --secret-id <project>-db-credentials-<environment> \
  --query 'RotationRules'

# Expected output:
# {
#   "AutomaticallyAfterDays": 30
# }
```

## Step 7: Monitor Rotation Events

Set up CloudWatch alarms to notify on rotation failures:

```bash
# View current alarms
aws cloudwatch describe-alarms \
  --alarm-names <project>-rds-rotation-failed-<environment>

# Check Lambda logs
aws logs tail /aws/lambda/<project>-rds-rotation-<environment> --follow
```

## Testing Rotation (Optional)

To manually test rotation before the 30-day interval:

```bash
# Trigger immediate rotation
aws secretsmanager rotate-secret \
  --secret-id <project>-db-credentials-<environment> \
  --rotation-lambda-arn arn:aws:lambda:...:function:<project>-rds-rotation-<environment>

# Watch logs as rotation happens
aws logs tail /aws/lambda/<project>-rds-rotation-<environment> --follow
```

### Expected Log Output

```
[INFO] Rotation step: create for secret project-db-credentials-prod
[INFO] Created new secret version abc123...
[INFO] Rotation step: set for secret project-db-credentials-prod
[INFO] Successfully updated RDS password
[INFO] Rotation step: finish for secret project-db-credentials-prod
[INFO] Marked version abc123 as AWSCURRENT
```

## Handling Rotation Failures

If rotation fails:

1. **Check Lambda Logs**: `aws logs tail /aws/lambda/<project>-rds-rotation-<environment>`
2. **Verify Security Group**: Lambda security group must allow port 5432 to RDS
3. **Verify VPC**: Lambda must be in same VPC as RDS
4. **Check Secrets Manager**: Ensure secret has correct current password
5. **Manual Recovery**: See `CREDENTIAL_ROTATION_PLAYBOOK.md`

## Operational Tasks

### Monthly: Check Rotation Status

```bash
# View rotation history
python credential_rotation_utils.py \
  view-history \
  --secret-name <project>-db-credentials-<environment>

# Should show versions with AWSCURRENT stage updated monthly
```

### Quarterly: Rotate Alpaca Keys

```bash
# Follow playbook steps to generate new keys, then:
python credential_rotation_utils.py \
  rotate-alpaca-keys \
  --secret-name <project>-algo-secrets-<environment> \
  --key-id <new-key-from-alpaca> \
  --secret-key <new-secret-from-alpaca>
```

### On Incident: Emergency Password Reset

```bash
# See CREDENTIAL_ROTATION_PLAYBOOK.md section: "Incident: Compromised Credential"
# TL;DR: Use credential_rotation_utils.py with manual password
```

## Troubleshooting

### "Permission Denied" on Lambda Invoke

Ensure your IAM user has:
```json
{
  "Effect": "Allow",
  "Action": ["lambda:InvokeFunction"],
  "Resource": "arn:aws:lambda:*:*:function:<project>-rds-rotation-*"
}
```

### "Secret not found" in Lambda Logs

Verify secret name matches exactly:
```bash
aws secretsmanager list-secrets \
  --filters Key=name,Values=<project>-db-credentials
```

### "Connection refused" from Lambda

Check Lambda is in private subnet with route to RDS:
```bash
# View Lambda VPC config
aws lambda get-function-concurrency \
  --function-name <project>-rds-rotation-<environment>

# Verify RDS security group allows Lambda security group:
aws ec2 describe-security-groups \
  --group-ids <rds-sg-id>
```

### "psycopg2 module not found"

Ensure Lambda layer was attached. Check:
```bash
aws lambda get-function-configuration \
  --function-name <project>-rds-rotation-<environment> \
  --query Layers
```

Should list the psycopg2 layer.

## Security Best Practices

1. **Least Privilege**: Lambda role only has access to specific secrets
2. **Network Isolation**: Lambda runs in private subnet, can only reach RDS
3. **Audit Logging**: All rotations logged in CloudWatch and CloudTrail
4. **Secrets Rotation**: Passwords never stored in code or Lambda environment
5. **Version Control**: Secret versions tracked in Secrets Manager

## Files Created

- `terraform/modules/database/rds_rotation_lambda.py` - Rotation function
- `terraform/modules/database/build-psycopg2-layer.sh` - Build script for dependencies
- `credential_rotation_utils.py` - CLI for manual management
- `CREDENTIAL_ROTATION_PLAYBOOK.md` - Operational procedures
- `test_credential_rotation.py` - Validation tests

## Next Steps

1. Complete this checklist
2. Run: `bash terraform/modules/database/build-psycopg2-layer.sh`
3. Run: `terraform apply -target=module.database`
4. Test: `python credential_rotation_utils.py test-connection --secret-name ...`
5. Monitor: Watch CloudWatch logs for first automatic rotation (in 30 days)

## Support

For issues:
1. Check `CREDENTIAL_ROTATION_PLAYBOOK.md` for operational procedures
2. Review CloudWatch Logs: `/aws/lambda/<project>-rds-rotation-<environment>`
3. Check Secrets Manager rotation history in AWS Console
4. Run test script: `python test_credential_rotation.py --all`
