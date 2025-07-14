# API Key Integration Deployment Guide

## Overview

This guide documents the proper deployment order and troubleshooting steps for the API key integration system. This system enables secure storage and management of user broker API keys for portfolio tracking and trading functionality.

## Critical Stack Dependencies

### Required Deployment Order

1. **StocksCore** → 2. **StocksApp** → 3. **Webapp**

#### 1. StocksCore Stack (`template-core.yml`)
- **Provides**: VPC, networking, IAM roles, security groups
- **Critical Resources**:
  - `LambdaExecutionRole` - Now includes API key encryption secret access
  - VPC and subnet configuration
  - Basic infrastructure
- **Exports**:
  - `StocksCore-LambdaExecutionRoleArn`
  - `StocksCore-VPCId`
  - Network and security group IDs

#### 2. StocksApp Stack (`template-app-stocks.yml`)
- **Provides**: Database, secrets, ECS cluster
- **Critical Resources**:
  - `ApiKeyEncryptionSecret` - AES-256-GCM encryption key
  - `JwtSecret` - JWT signing key
  - RDS PostgreSQL database
  - ECS cluster for data processing
- **Exports**:
  - `StocksApp-ApiKeyEncryptionSecretArn` ⭐ **REQUIRED for webapp**
  - `StocksApp-SecretArn` (database credentials)
  - `StocksApp-DBEndpoint`
- **Recent Fixes**:
  - Fixed YAML escaping: `ExcludeCharacters: '"@/\\`'` (was causing JSON parse errors)
  - Fixed JSON templates in `SecretStringTemplate`

#### 3. Webapp Stack (`template-webapp-lambda.yml` or serverless variants)
- **Provides**: Lambda functions, API Gateway, frontend
- **Dependencies**: Requires exports from both StocksCore and StocksApp
- **Critical Environment Variables**:
  - `API_KEY_ENCRYPTION_SECRET_ARN: !ImportValue StocksApp-ApiKeyEncryptionSecretArn`
  - Database connection parameters
  - Cognito configuration

## Database Schema Requirements

### Required Tables for API Key System

All tables are created by `comprehensive-webapp-db-init.js`:

```sql
-- Core API key storage with AES-256-GCM encryption
CREATE TABLE user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    provider VARCHAR(50) NOT NULL,
    encrypted_api_key TEXT NOT NULL,
    key_iv VARCHAR(32) NOT NULL,
    key_auth_tag VARCHAR(32) NOT NULL,
    encrypted_api_secret TEXT,
    secret_iv VARCHAR(32),
    secret_auth_tag VARCHAR(32),
    user_salt VARCHAR(32) NOT NULL,
    is_sandbox BOOLEAN DEFAULT true,
    is_active BOOLEAN DEFAULT true,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    UNIQUE(user_id, provider)
);

-- Portfolio holdings from broker APIs
CREATE TABLE portfolio_holdings (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    api_key_id INTEGER,
    symbol VARCHAR(10) NOT NULL,
    quantity DECIMAL(15,4) NOT NULL,
    avg_cost DECIMAL(12,4),
    current_price DECIMAL(12,4),
    market_value DECIMAL(15,2),
    -- ... additional fields
    UNIQUE(user_id, api_key_id, symbol)
);

-- Portfolio metadata and summary information
CREATE TABLE portfolio_metadata (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    api_key_id INTEGER,
    total_equity DECIMAL(15,2),
    total_market_value DECIMAL(15,2),
    -- ... additional fields
    UNIQUE(user_id, api_key_id)
);

-- Portfolio data refresh tracking
CREATE TABLE portfolio_data_refresh_requests (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    symbols JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    UNIQUE(user_id)
);
```

## Environment Variables

### Lambda Functions
```bash
# Required for API key encryption
API_KEY_ENCRYPTION_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:stocks-app-api-key-encryption-stack

# Database connectivity
DB_SECRET_ARN=arn:aws:secretsmanager:region:account:secret:stocks-db-secrets-stack
DB_ENDPOINT=stocks.xxxxx.region.rds.amazonaws.com

# Authentication
COGNITO_USER_POOL_ID=region_xxxxxxxxx
COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxx

# AWS Configuration
AWS_REGION=us-east-1
ENVIRONMENT=dev|staging|prod
```

### Frontend (Vite)
```bash
# API Configuration
VITE_API_URL=https://api-id.execute-api.region.amazonaws.com/stage

# WebSocket Configuration (for live data)
VITE_WS_URL=wss://websocket-api-id.execute-api.region.amazonaws.com/stage

# Authentication
VITE_COGNITO_USER_POOL_ID=region_xxxxxxxxx
VITE_COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxx
VITE_AWS_REGION=us-east-1

# Deployment
VITE_ENVIRONMENT=production
VITE_SERVERLESS=true
```

## Troubleshooting Common Issues

### 1. CloudFormation Deployment Failures

#### "No export named StocksApp-ApiKeyEncryptionSecretArn found"
**Cause**: StocksApp stack not deployed or failed
**Solution**:
```bash
# Check if StocksApp stack exists and is in good state
aws cloudformation describe-stacks --stack-name stocks-app-stack

# If in failed state, check events
aws cloudformation describe-stack-events --stack-name stocks-app-stack

# Deploy/redeploy StocksApp stack first
```

#### "Failed to parse SecretStringTemplate as JSON"
**Cause**: YAML escaping issue in secret generation
**Solution**: Ensure `ExcludeCharacters: '"@/\\`'` (not `'"@/\\'''`)

#### Stack in "UPDATE_ROLLBACK_COMPLETE" state
**Cause**: Previous deployment failed and rolled back
**Solution**:
```bash
# Stack is functional but last update failed - can proceed with new deployment
# Check what failed in the previous attempt:
aws cloudformation describe-stack-events --stack-name your-stack-name
```

### 2. API Key Service Issues

#### 503 "Settings service is being loaded"
**Cause**: API key service failed to initialize
**Diagnosis**:
```bash
# Check health endpoint
curl https://your-api.execute-api.region.amazonaws.com/stage/health/api-services

# Check CloudWatch logs for Lambda function
aws logs filter-log-events --log-group-name /aws/lambda/your-function-name
```

**Common Causes**:
- `API_KEY_ENCRYPTION_SECRET_ARN` environment variable not set
- Lambda doesn't have permissions to access secrets
- Secret doesn't exist or is in wrong format

#### 422 "API key encryption service unavailable"
**Cause**: Service is configured but can't access encryption secret
**Solution**: Check IAM permissions and secret accessibility

### 3. WebSocket Configuration Issues

#### "WebSocket URL not configured. Live data service disabled"
**Cause**: Frontend missing WebSocket URL configuration
**Solution**:
```bash
# Deploy WebSocket stack first
# Then ensure frontend has VITE_WS_URL set to WebSocket API Gateway endpoint
```

### 4. Database Issues

#### Missing tables
**Solution**: Run database initialization
```bash
node comprehensive-webapp-db-init.js
```

#### Permission errors
**Solution**: Check RDS security groups and Lambda VPC configuration

## Health Check Endpoints

### Infrastructure Health
```bash
GET /health                    # Full database and infrastructure check
GET /health?quick=true        # Quick check without database
GET /health/ready             # Application readiness check
GET /health/api-services      # API key service specific health
```

### Health Check Response Examples

#### Healthy API Services
```json
{
  "status": "healthy",
  "services": {
    "apiKeyService": {
      "status": "healthy",
      "enabled": true,
      "features": {
        "encryption": true,
        "secretsManager": true
      }
    },
    "database": {
      "status": "healthy",
      "tables": {
        "user_api_keys": { "exists": true, "status": "healthy", "count": 5 },
        "portfolio_holdings": { "exists": true, "status": "healthy", "count": 23 }
      }
    },
    "secrets": {
      "status": "healthy",
      "configured": true,
      "message": "Secrets Manager access is working"
    }
  }
}
```

#### Service Degraded
```json
{
  "status": "degraded",
  "services": {
    "apiKeyService": {
      "status": "failed",
      "enabled": false,
      "error": "API key encryption service is not available"
    }
  }
}
```

## Security Architecture

### API Key Encryption
- **Algorithm**: AES-256-GCM with user-specific salts
- **Master Secret**: Stored in AWS Secrets Manager
- **Per-User Encryption**: Each user's API keys encrypted with derived keys
- **Salt Storage**: User-specific salts stored with encrypted data
- **Key Derivation**: Uses `crypto.scryptSync()` for key derivation

### IAM Permissions
Lambda execution role needs:
```json
{
  "Effect": "Allow",
  "Action": [
    "secretsmanager:GetSecretValue",
    "secretsmanager:DescribeSecret"
  ],
  "Resource": [
    "arn:aws:secretsmanager:region:account:secret:stocks-db-secrets-*",
    "arn:aws:secretsmanager:region:account:secret:stocks-app-*",
    "arn:aws:secretsmanager:region:account:secret:*-stocks-*"
  ]
}
```

## Monitoring and Alerting

### Key Metrics to Monitor
- API key service initialization failures
- Secret access failures
- Database connection issues
- WebSocket connection failures
- Health check failures

### CloudWatch Alarms
Set up alarms for:
- Lambda function errors
- Health check endpoint failures
- Database connection failures
- Secrets Manager access failures

## Recovery Procedures

### API Key Service Recovery
1. Check CloudFormation stack status
2. Verify environment variables are set
3. Test secret access manually
4. Restart Lambda functions if needed
5. Run health checks to verify recovery

### Database Recovery
1. Check RDS instance status
2. Verify security group rules
3. Test connectivity from Lambda
4. Re-run database initialization if needed

### Frontend Recovery
1. Verify API Gateway deployment
2. Check CloudFront cache invalidation
3. Validate environment variables
4. Test WebSocket connectivity

## Development vs Production

### Development
- Use local database or dev RDS instance
- Test API key encryption with dev secrets
- Enable debug logging
- Use sandbox broker APIs

### Production
- Ensure all secrets are properly configured
- Monitor health checks continuously
- Use production broker APIs
- Enable proper logging and alerting
- Regular backup of encrypted API keys

---

**Last Updated**: 2025-07-14
**Version**: 1.0.0
**Environment**: Production-ready API key integration system