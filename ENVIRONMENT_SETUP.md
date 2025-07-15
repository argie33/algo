# Environment Variables Setup Guide
*Updated 2025-07-15 | Portfolio Performance Optimization Complete*

## Overview

This guide explains how to properly configure environment variables for the Financial Trading Platform deployment. The environment variables are automatically configured through CloudFormation templates, but must be deployed in the correct order.

## Recent Performance Improvements

The following optimizations have been implemented to resolve memory and performance issues:

### Database Performance
- **Portfolio Indexes**: Added comprehensive indexes in webapp-db-init.js for portfolio_holdings and user_api_keys tables
- **Query Optimization**: Implemented pagination and specific column selection
- **Connection Pooling**: Fixed pool exhaustion issues with batch processing

### Memory Management
- **Node.js Heap**: Resolved JavaScript heap out of memory errors
- **Conditional Logging**: Implemented LOG_LEVEL environment variable for memory optimization
- **Circular Buffers**: Fixed memory leaks in poolMetrics arrays

### Required Node.js Memory Configuration
For environments with large datasets, configure Node.js memory limits:
```bash
export NODE_OPTIONS="--max-old-space-size=4096"  # 4GB heap limit
export LOG_LEVEL="WARN"  # Reduce logging in production
```

### Mock Data Elimination
All mock data and fallback mechanisms have been removed and replaced with proper error handling:
- **Portfolio Analytics**: Now uses real factor analysis calculations
- **Dashboard Components**: Proper error states instead of fallback mock data
- **Performance Metrics**: Real-time calculations from live data
- **Risk Analysis**: Institutional-grade algorithms for factor exposures

## Deployment Order

### 1. Core Infrastructure Stack
Deploy the core infrastructure first:
```bash
aws cloudformation deploy \
  --template-file template-core.yml \
  --stack-name stocks-core \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

### 2. Main Application Stack
Deploy the main application stack (database, secrets):
```bash
aws cloudformation deploy \
  --template-file template-app-stocks.yml \
  --stack-name stocks-app \
  --capabilities CAPABILITY_IAM \
  --region us-east-1 \
  --parameter-overrides \
    RDSUsername=stocksadmin \
    RDSPassword=<SECURE_PASSWORD> \
    FREDApiKey=<FRED_API_KEY>
```

### 3. Webapp Lambda Stack
Deploy the webapp Lambda function:
```bash
aws cloudformation deploy \
  --template-file template-webapp-lambda.yml \
  --stack-name stocks-webapp-lambda \
  --capabilities CAPABILITY_IAM \
  --region us-east-1 \
  --parameter-overrides \
    DatabaseSecretArn=arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:stocks-app-db-secret \
    DatabaseEndpoint=<RDS_ENDPOINT>
```

## Environment Variables Configured

The following environment variables are automatically configured by CloudFormation:

### Required Variables (Set by CloudFormation)

| Variable | Source | Description |
|----------|--------|-------------|
| `DB_SECRET_ARN` | CloudFormation Parameter | ARN of database credentials secret |
| `DB_ENDPOINT` | CloudFormation Parameter | RDS database endpoint |
| `API_KEY_ENCRYPTION_SECRET_ARN` | CloudFormation Import | ARN of API key encryption secret |
| `WEBAPP_AWS_REGION` | CloudFormation Built-in | AWS region (us-east-1) |
| `COGNITO_USER_POOL_ID` | CloudFormation Resource | Cognito User Pool ID |
| `COGNITO_CLIENT_ID` | CloudFormation Resource | Cognito App Client ID |

### Optional Variables (Set by CloudFormation)

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_ENV` | development | Node.js environment |
| `ENVIRONMENT` | dev | Deployment environment |
| `DB_CONNECT_TIMEOUT` | 30000 | Database connection timeout |
| `DB_POOL_MAX` | 3 | Database connection pool max |
| `DB_POOL_IDLE_TIMEOUT` | 30000 | Database idle timeout |

## Manual Environment Variable Setup (If Needed)

If you need to set environment variables manually (e.g., for local development), create a `.env` file:

```env
# Database Configuration
DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:stocks-app-db-secret
DB_ENDPOINT=stocks-db.cluster-xyz.us-east-1.rds.amazonaws.com
DB_CONNECT_TIMEOUT=30000
DB_POOL_MAX=3
DB_POOL_IDLE_TIMEOUT=30000

# API Key Encryption
API_KEY_ENCRYPTION_SECRET_ARN=arn:aws:secretsmanager:us-east-1:ACCOUNT:secret:stocks-app-api-key-encryption

# AWS Configuration
WEBAPP_AWS_REGION=us-east-1
AWS_REGION=us-east-1

# Cognito Authentication
COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
COGNITO_CLIENT_ID=abcdefghijklmnopqrstuvwxyz

# Environment
NODE_ENV=development
ENVIRONMENT=dev

# Alpaca Trading (Optional)
ALPACA_PAPER_TRADING=true
```

## Verification Commands

### Check CloudFormation Outputs
```bash
# Check main app stack outputs
aws cloudformation describe-stacks \
  --stack-name stocks-app \
  --query 'Stacks[0].Outputs'

# Check webapp Lambda stack outputs
aws cloudformation describe-stacks \
  --stack-name stocks-webapp-lambda \
  --query 'Stacks[0].Outputs'
```

### Check Lambda Environment Variables
```bash
aws lambda get-function-configuration \
  --function-name financial-dashboard-api-dev \
  --query 'Environment.Variables'
```

### Test Database Connection
```bash
# Run health check
curl https://API_GATEWAY_URL/api/health

# Check database status
curl https://API_GATEWAY_URL/api/health/database
```

## Troubleshooting

### Missing Environment Variables

If environment variables are missing:

1. **Check CloudFormation Stack Status**:
   ```bash
   aws cloudformation describe-stacks --stack-name stocks-app
   aws cloudformation describe-stacks --stack-name stocks-webapp-lambda
   ```

2. **Verify Stack Dependencies**:
   - Ensure `stocks-core` stack is deployed first
   - Ensure `stocks-app` stack is deployed second
   - Ensure `stocks-webapp-lambda` references correct outputs

3. **Update Lambda Configuration**:
   ```bash
   aws lambda update-function-configuration \
     --function-name financial-dashboard-api-dev \
     --environment Variables='{
       "DB_SECRET_ARN":"arn:aws:secretsmanager:...",
       "DB_ENDPOINT":"stocks-db.cluster-xyz.us-east-1.rds.amazonaws.com",
       "WEBAPP_AWS_REGION":"us-east-1"
     }'
   ```

### Common Issues

1. **Stack Not Found Error**: Deploy stacks in correct order
2. **Import Value Not Found**: Check that referenced stack outputs exist
3. **Secrets Manager Access Denied**: Ensure Lambda execution role has proper permissions
4. **Database Connection Timeout**: Verify security groups and VPC configuration

## Secrets Manager Configuration

### Database Secret Format
The database secret should contain:
```json
{
  "username": "stocksadmin",
  "password": "secure_password",
  "engine": "postgres",
  "host": "stocks-db.cluster-xyz.us-east-1.rds.amazonaws.com",
  "port": 5432,
  "dbname": "stocks"
}
```

### API Key Encryption Secret Format
The API key encryption secret should contain:
```json
{
  "encryptionKey": "base64_encoded_32_byte_key",
  "algorithm": "aes-256-gcm"
}
```

## Monitoring and Logs

### CloudWatch Logs
- Lambda logs: `/aws/lambda/financial-dashboard-api-dev`
- Database init logs: `/aws/ecs/stocks-webapp-db-init`

### Environment Variable Validation
The application includes environment variable validation that runs on startup:

```bash
# Check validation results in CloudWatch logs
aws logs filter-log-events \
  --log-group-name /aws/lambda/financial-dashboard-api-dev \
  --filter-pattern "Environment Variable Validation"
```

## Security Best Practices

1. **Never Commit Secrets**: All sensitive values are stored in AWS Secrets Manager
2. **Least Privilege**: Lambda execution role has minimal required permissions
3. **Encryption**: All secrets are encrypted at rest and in transit
4. **Rotation**: Database and API key secrets support automatic rotation
5. **Monitoring**: CloudWatch monitors all environment variable access

## Support

If you encounter issues with environment variable configuration:

1. Check the environment variable validation logs in CloudWatch
2. Verify all CloudFormation stacks are in CREATE_COMPLETE or UPDATE_COMPLETE status
3. Ensure Lambda function has the latest environment variable configuration
4. Test database connectivity using the health endpoints

For deployment automation, see the `DEPLOYMENT_GUIDE.md` file.