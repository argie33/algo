# Credential Rotation Playbook

## Overview

This document describes how database and API credentials are rotated automatically and what to do if rotation fails.

**Rotation Schedule:**
- RDS Master Password: Every 30 days (automatic)
- Alpaca API Keys: Every 90 days (manual, documented below)
- Other API Keys: As needed when compromised

## RDS Credential Rotation

### Automatic Rotation (Secrets Manager + Lambda)

RDS credentials are automatically rotated every 30 days via AWS Secrets Manager and a Lambda function:

1. **Trigger**: Secrets Manager automatically invokes the rotation Lambda every 30 days
2. **Secret**: `<project>-db-credentials-<environment>` in Secrets Manager
3. **Lambda Function**: `<project>-rds-rotation-<environment>`
4. **Steps**:
   - `create`: Generate new password, create AWSPENDING secret version
   - `set`: Connect to RDS with old credentials, update password to new value
   - `finish`: Verify new credentials work, mark AWSPENDING as AWSCURRENT

### Monitoring Rotation Events

Check CloudWatch Logs for rotation status:

```bash
aws logs tail /aws/lambda/<project>-rds-rotation-<environment> --follow
```

Check CloudWatch Alarms:
- `<project>-rds-rotation-failed-<environment>`: Triggers if Lambda returns error
- `<project>-rds-rotation-slow-<environment>`: Triggers if rotation takes > 30 seconds (prod only)

### Automatic Rotation Failure

If automatic rotation fails, you'll receive SNS notification (if configured). Steps to remediate:

#### 1. Check Lambda Logs

```bash
aws logs get-log-events \
  --log-group-name /aws/lambda/<project>-rds-rotation-<environment> \
  --log-stream-name $(aws logs describe-log-streams \
    --log-group-name /aws/lambda/<project>-rds-rotation-<environment> \
    --order-by LastEventTime --descending --max-items 1 \
    --query 'logStreams[0].logStreamName' --output text) \
  --query 'events[].message' --output text
```

#### 2. Common Failure Causes

| Error | Cause | Fix |
|-------|-------|-----|
| `"Failed to connect to RDS"` | RDS security group missing port 5432 | Check SG ingress rules allow Lambda security group |
| `"Authentication failed"` | Current secret in Secrets Manager is wrong | Manually update secret with current password (see below) |
| `"ALTER USER failed"` | User doesn't exist or insufficient privileges | Verify master user exists in RDS |
| `"Timeout"` | Network connectivity issue from Lambda to RDS | Verify Lambda VPC subnet routing |

#### 3. Manual Password Reset

If you need to manually reset the RDS master password:

```bash
# 1. In AWS Console, set new password in RDS > Databases > <instance> > Modify
#    (or use AWS CLI below)

aws rds modify-db-instance \
  --db-instance-identifier <project>-db \
  --master-user-password <new-password> \
  --apply-immediately

# 2. Update Secrets Manager with the new password
aws secretsmanager put-secret-value \
  --secret-id <project>-db-credentials-<environment> \
  --secret-string '{
    "username": "postgres",
    "password": "<new-password>",
    "host": "<rds-endpoint>",
    "port": 5432,
    "dbname": "stocks",
    "engine": "postgresql"
  }'

# 3. Wait 5 minutes, then manually trigger rotation to sync Secrets Manager
aws secretsmanager rotate-secret \
  --secret-id <project>-db-credentials-<environment>
```

#### 4. Verify Rotation Completed

After manual reset or after automatic rotation retries:

```bash
# Check current secret version is AWSCURRENT
aws secretsmanager describe-secret \
  --secret-id <project>-db-credentials-<environment> \
  --query 'VersionIdsToStages' --output text

# Test connection with new credentials
psql -h <rds-endpoint> -U postgres -d stocks \
  -c "SELECT version();"
```

### Disable Automatic Rotation (Emergency Only)

If rotation is causing problems and you need to stop it temporarily:

```bash
# WARNING: Manual rotation management needed after disabling
aws secretsmanager rotate-secret \
  --secret-id <project>-db-credentials-<environment> \
  --rotation-rules '{"AutomaticallyAfterDays": 0}'
```

**Must re-enable** by setting `AutomaticallyAfterDays: 30` once issue is resolved.

## Alpaca API Key Rotation

### Manual Rotation (Not Automated Yet)

Alpaca API keys should be rotated every 90 days. To rotate:

#### 1. Generate New Key in Alpaca Dashboard

- Login to broker.alpaca.markets
- Account > Settings > API Keys
- Generate new API key pair
- Save the new KEY and SECRET

#### 2. Update Secrets Manager

```bash
aws secretsmanager put-secret-value \
  --secret-id <project>-algo-secrets-<environment> \
  --secret-string '{
    "APCA_API_KEY_ID": "<new-key>",
    "APCA_API_SECRET_KEY": "<new-secret>",
    "APCA_API_BASE_URL": "https://paper-api.alpaca.markets",
    "ALPACA_PAPER_TRADING": "true"
  }'
```

#### 3. Test New Credentials

```bash
# Deploy a loader with new key to verify it works
python loadstocksymbols.py --test-only

# If successful, delete old key from Alpaca dashboard
```

#### 4. Alert

- No downtime needed (app picks up new secret on next container start)
- Existing running containers continue with old key until restart
- New containers use new key immediately
- For zero-downtime, use rolling deployment (one task at a time)

## Email Configuration Rotation

Email SMTP credentials should be rotated with SMTP provider:

```bash
aws secretsmanager put-secret-value \
  --secret-id <project>-email-config-<environment> \
  --secret-string '{
    "contact_notification_email": "ops@example.com",
    "email_from": "noreply@bullseyefinancial.com",
    "smtp_username": "<new-username>",
    "smtp_password": "<new-password>",
    "smtp_host": "smtp.mailgun.org",
    "smtp_port": 587
  }'
```

## Credential Lifecycle Events

Monitor these CloudWatch Events for all credential operations:

- `Secrets Manager Secret Created`
- `Secrets Manager Secret Updated`
- `Secrets Manager Secret Rotated`
- `RDS Database Modified` (tracks password changes)

View in CloudWatch:

```bash
aws events list-rules --query 'Rules[?Name=`*credential*` || Name=`*rotation*`]'
```

## Audit & Compliance

### View Rotation History

```bash
aws secretsmanager describe-secret \
  --secret-id <project>-db-credentials-<environment> \
  --query 'VersionIdsToStages' --output table
```

### CloudTrail Audit

All credential operations are logged to CloudTrail:

```bash
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=ResourceName,AttributeValue=<project>-db-credentials-<environment> \
  --max-results 20
```

### Rotation Frequency Audit

```bash
# List all secrets with rotation enabled
aws secretsmanager list-secrets \
  --query 'SecretList[?RotationEnabled==`true`].{Name:Name,Enabled:RotationEnabled,Days:RotationRules.AutomaticallyAfterDays}' \
  --output table
```

## Incident: Compromised Credential

If a credential is suspected to be compromised:

1. **Immediately rotate** the credential (don't wait for scheduled rotation)
2. **Check CloudTrail** for unauthorized access
3. **Review RDS logs** for suspicious queries
4. **Notify ops team** and update incident response system
5. **Post-rotation**: Monitor for 7 days for re-compromise attempts

### Emergency Rotation

```bash
# For RDS password
aws rds modify-db-instance \
  --db-instance-identifier <project>-db \
  --master-user-password $(openssl rand -base64 32) \
  --apply-immediately

# Update Secrets Manager immediately after
# (follow manual reset steps above)
```

## Testing Rotation Locally

To test rotation logic without AWS:

```python
from credential_manager import get_credential_manager

# Verify credential manager loads from Secrets Manager
cred_mgr = get_credential_manager()
db_creds = cred_mgr.get_db_credentials()
print(f"Connected via {db_creds['host']}")

# Verify password rotation Lambda function locally
# (requires mock boto3 and psycopg2)
python -m pytest test_rotation_lambda.py
```

## References

- AWS Docs: [Secrets Manager Rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotating-secrets.html)
- AWS Docs: [RDS Password Management](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html)
- Alpaca API: [Key Management](https://docs.alpaca.markets/api-references/broker-api#creating-api-keys)
