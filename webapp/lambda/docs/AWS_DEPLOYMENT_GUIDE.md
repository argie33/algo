# AWS Deployment Guide: Database Secret Configuration

## Issue Resolution: Stock Explorer Showing Mock Data

This guide resolves the issue where Stock Explorer displays only 10 mock stocks instead of real loadinfo data in AWS deployment.

## Root Cause

The CloudFormation template was missing the database credentials secret, causing the application to fall back to mock data when database connection fails.

## Solution Implementation

### 1. CloudFormation Template Update

The AWS services stack now includes a new database credentials secret:

```yaml
DatabaseCredentials:
  Type: AWS::SecretsManager::Secret
  Properties:
    Name: !Sub 'database-credentials-${EnvironmentName}'
    Description: 'PostgreSQL database connection credentials for stocks webapp'
    SecretString: !Sub |
      {
        "host": "PLACEHOLDER_DB_HOST_REPLACE_MANUALLY",
        "port": "5432", 
        "dbname": "stocks",
        "username": "PLACEHOLDER_DB_USERNAME_REPLACE_MANUALLY",
        "password": "PLACEHOLDER_DB_PASSWORD_REPLACE_MANUALLY"
      }
```

### 2. IAM Permissions Update

The Lambda execution role now includes access to the database secret:

```yaml
Resource:
  - !Ref DatabaseCredentials  # Added to existing secret permissions
```

### 3. CloudFormation Output

The template exports the database secret ARN for use in deployment:

```yaml
DatabaseCredentialsArn:
  Description: 'ARN of database credentials secret'
  Value: !Ref DatabaseCredentials
  Export:
    Name: !Sub '${AWS::StackName}-DatabaseCredentialsArn'
```

## Deployment Steps

### Step 1: Update CloudFormation Stack

Deploy the updated CloudFormation template:

```bash
aws cloudformation update-stack \
  --stack-name your-aws-services-stack \
  --template-body file://cloudformation/aws-services-stack.yml \
  --parameters ParameterKey=EnvironmentName,ParameterValue=prod \
               ParameterKey=VpcId,ParameterValue=vpc-xxxxxx \
               ParameterKey=SubnetIds,ParameterValue=subnet-xxxxx,subnet-yyyyy \
  --capabilities CAPABILITY_IAM
```

### Step 2: Configure Database Secret

After stack deployment, manually update the database secret with actual credentials:

```bash
# Get the secret ARN from stack outputs
SECRET_ARN=$(aws cloudformation describe-stacks \
  --stack-name your-aws-services-stack \
  --query 'Stacks[0].Outputs[?OutputKey==`DatabaseCredentialsArn`].OutputValue' \
  --output text)

# Update secret with actual database credentials
aws secretsmanager update-secret \
  --secret-id $SECRET_ARN \
  --secret-string '{
    "host": "your-actual-db-host.rds.amazonaws.com",
    "port": "5432",
    "dbname": "stocks", 
    "username": "your-db-username",
    "password": "your-db-password"
  }'
```

### Step 3: Update Lambda Environment Variables

In your GitHub workflow deployment, reference the database secret:

```yaml
environment:
  variables:
    NODE_ENV: production
    WEBAPP_AWS_REGION: us-east-1
    # Other environment variables...
  
  # Add database secret ARN
  DB_SECRET_ARN: 
    Fn::ImportValue: !Sub "${ServicesStackName}-DatabaseCredentialsArn"
```

### Step 4: Verify Database Connection

After deployment, test the database connection:

```bash
# Test the health endpoint
curl https://your-api-domain/api/health

# Test the screen endpoint (should show real data)
curl https://your-api-domain/api/screen
```

## Configuration Verification

### Database Connection Priority

The application follows this authentication priority:

1. **Direct Environment Variables** (development only)
   - `DB_HOST`, `DB_USER`, `DB_PASSWORD`
   - Only active when `NODE_ENV=development`

2. **AWS Secrets Manager** (production priority)
   - Uses `DB_SECRET_ARN` environment variable
   - Retrieves full database configuration from secret

3. **Stub Configuration** (error fallback)
   - Returns mock data when database unavailable
   - Indicates configuration issues

### Expected Behavior After Fix

- ✅ **Stock Explorer shows real loadinfo data** (not just 10 mock stocks)
- ✅ **API endpoints return actual database records**
- ✅ **Health check reports database connectivity**
- ✅ **No fallback to sample data store**

## Monitoring and Troubleshooting

### CloudWatch Logs

Monitor Lambda logs for database connection status:

```
✅ Database config loaded from AWS Secrets Manager (XXXms)
✅ Database connection successful, using real data
📊 Stock Explorer will show REAL data from your loadinfo script!
```

### Error Patterns

Watch for these error patterns indicating configuration issues:

```
❌ Invalid DB_SECRET_ARN detected - returning stub configuration
⚠️ Database unavailable, using comprehensive sample data
❌ User: arn:aws:iam::xxx:user/xxx is not authorized to perform: secretsmanager:GetSecretValue
```

### Health Check Endpoint

Use the health endpoint to verify configuration:

```bash
curl https://your-api-domain/api/health
```

Expected response for successful configuration:
```json
{
  "status": "healthy",
  "database": "stocks",
  "note": "Database connection verified with circuit breaker protection"
}
```

## Security Considerations

### Secret Management

- Database credentials are stored in AWS Secrets Manager
- IAM role provides least-privilege access to secrets
- No credentials are exposed in environment variables or logs
- Automatic rotation can be configured if needed

### Network Security

- Database should be in private subnets
- Security groups restrict access to Lambda functions only
- VPC configuration ensures network isolation

## Testing

### Unit Tests

Test database configuration locally:

```bash
cd /home/stocks/algo/webapp/lambda
node test-database-connection.js
```

### Integration Tests

Verify complete flow:

```bash
# Test Stock Explorer endpoint
curl "https://your-api-domain/api/screen?limit=5" | jq '.data | length'
# Should return count > 10 (not just mock data)
```

## Rollback Plan

If issues occur, temporarily use environment variables:

1. Set direct database environment variables in Lambda
2. Ensure `NODE_ENV=development` 
3. Redeploy with direct credentials
4. Fix Secrets Manager configuration
5. Switch back to production mode

## Next Steps

1. Deploy the updated CloudFormation template
2. Configure the database secret with actual credentials
3. Update your GitHub workflow to reference the secret ARN
4. Test the Stock Explorer to verify real data display
5. Monitor CloudWatch logs for successful database connections

This resolves the core issue where Stock Explorer was showing mock data instead of real loadinfo data due to missing database secret configuration in the AWS deployment.