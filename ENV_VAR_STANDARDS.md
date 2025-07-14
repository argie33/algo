# Environment Variable Standards

## Overview

This document defines standardized environment variable naming conventions across all CloudFormation templates, Lambda functions, and ECS tasks in the financial trading platform.

## Core Principles

1. **Consistency**: Same concepts use identical variable names across all templates
2. **Clarity**: Variable names clearly indicate their purpose and scope
3. **Maintainability**: Standardized patterns make troubleshooting easier
4. **Security**: Sensitive data uses appropriate mechanisms (Secrets Manager vs Environment Variables)

## Standard Environment Variables

### Database Configuration

Use these exact names across all templates:

```yaml
Environment:
  Variables:
    # Database connection
    DB_ENDPOINT: !ImportValue StocksApp-DBEndpoint
    DB_PORT: "5432"
    DB_NAME: "stocks_data"
    
    # Database credentials (via Secrets Manager)
    DB_SECRET_ARN: !ImportValue StocksApp-SecretArn
    
    # Connection tuning
    DB_CONNECT_TIMEOUT: "30000"
    DB_POOL_MAX: "3"
    DB_POOL_IDLE_TIMEOUT: "30000"
```

**❌ Deprecated patterns to avoid:**
- `DATABASE_ENDPOINT` or `DB_HOST`
- `DATABASE_SECRET_ARN`
- Inconsistent timeout variable names

### Authentication & Security

```yaml
Environment:
  Variables:
    # API key encryption (required for user settings)
    API_KEY_ENCRYPTION_SECRET_ARN: !ImportValue StocksApp-ApiKeyEncryptionSecretArn
    
    # JWT authentication
    JWT_SECRET_ARN: !ImportValue StocksApp-JwtSecretArn
    
    # Cognito configuration
    COGNITO_USER_POOL_ID: !ImportValue StocksApp-UserPoolId
    COGNITO_CLIENT_ID: !ImportValue StocksApp-UserPoolClientId
```

### AWS Configuration

```yaml
Environment:
  Variables:
    # AWS settings
    AWS_REGION: !Ref AWS::Region
    NODE_ENV: !Ref EnvironmentName
    ENVIRONMENT: !Ref EnvironmentName
```

**Note**: Use `NODE_ENV` for Node.js applications, `ENVIRONMENT` for general application configuration.

### WebSocket Configuration

```yaml
Environment:
  Variables:
    # WebSocket API Gateway endpoint
    WEBSOCKET_API_ENDPOINT: !Sub 'wss://${WebSocketApi}.execute-api.${AWS::Region}.amazonaws.com/${EnvironmentName}'
    
    # ElastiCache Redis
    ELASTICACHE_ENDPOINT: !GetAtt ElastiCacheCluster.PrimaryEndPoint.Address
    ELASTICACHE_PORT: !GetAtt ElastiCacheCluster.PrimaryEndPoint.Port
    
    # DynamoDB tables
    CONNECTIONS_TABLE: !Ref ConnectionsTable
    SUBSCRIPTIONS_TABLE: !Ref SubscriptionsTable
    MARKET_DATA_TABLE: !Ref MarketDataTable
```

### Frontend Configuration (Vite)

```bash
# API endpoints
VITE_API_URL=https://api-id.execute-api.region.amazonaws.com/stage
VITE_WS_URL=wss://websocket-api-id.execute-api.region.amazonaws.com/stage

# Authentication
VITE_COGNITO_USER_POOL_ID=region_xxxxxxxxx
VITE_COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxx
VITE_AWS_REGION=us-east-1

# Application settings
VITE_ENVIRONMENT=production
VITE_SERVERLESS=true

# Legacy support (for backward compatibility)
REACT_APP_WS_URL=wss://websocket-api-id.execute-api.region.amazonaws.com/stage
```

## CloudFormation Parameter Standards

### Standard Parameter Names

```yaml
Parameters:
  EnvironmentName:
    Type: String
    Default: dev
    AllowedValues: [dev, staging, prod]
    Description: Environment name for resource tagging and configuration
    
  DatabaseSecretArn:
    Type: String
    Description: ARN of the database credentials secret
    
  CognitoUserPoolId:
    Type: String
    Description: Cognito User Pool ID for authentication
    
  CognitoClientId:
    Type: String
    Description: Cognito User Pool Client ID
```

### Import/Export Standards

Use consistent export naming:

```yaml
Outputs:
  # Pattern: ${AWS::StackName}-ResourceName
  ApiKeyEncryptionSecretArn:
    Description: API key encryption secret ARN
    Value: !Ref ApiKeyEncryptionSecret
    Export:
      Name: !Sub '${AWS::StackName}-ApiKeyEncryptionSecretArn'
      
  DatabaseEndpoint:
    Description: RDS database endpoint
    Value: !GetAtt Database.Endpoint.Address
    Export:
      Name: !Sub '${AWS::StackName}-DBEndpoint'
```

## IAM Permissions Standards

### Secrets Manager Access

All services requiring secrets access should use this pattern:

```yaml
Policies:
  - PolicyName: SecretsManagerAccess
    PolicyDocument:
      Version: '2012-10-17'
      Statement:
        - Effect: Allow
          Action:
            - secretsmanager:GetSecretValue
            - secretsmanager:DescribeSecret
          Resource:
            - !Sub 'arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:stocks-db-secrets-*'
            - !Sub 'arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:stocks-app-*'
            - !Sub 'arn:aws:secretsmanager:${AWS::Region}:${AWS::AccountId}:secret:*-stocks-*'
```

## Template-Specific Standards

### Lambda Functions

```yaml
Environment:
  Variables:
    # Core application
    NODE_ENV: !Ref EnvironmentName
    AWS_REGION: !Ref AWS::Region
    
    # Database
    DB_SECRET_ARN: !Ref DatabaseSecretArn
    DB_ENDPOINT: !Ref DatabaseEndpoint
    DB_CONNECT_TIMEOUT: '30000'
    DB_POOL_MAX: '3'
    
    # Security
    API_KEY_ENCRYPTION_SECRET_ARN: !ImportValue StocksApp-ApiKeyEncryptionSecretArn
    JWT_SECRET_ARN: !ImportValue StocksApp-JwtSecretArn
    
    # Authentication
    COGNITO_USER_POOL_ID: !Ref CognitoUserPoolId
    COGNITO_CLIENT_ID: !Ref CognitoClientId
```

### ECS Tasks

```yaml
Environment:
  # Use same variable names as Lambda for consistency
  - Name: NODE_ENV
    Value: production
  - Name: DB_ENDPOINT
    Value: !ImportValue StocksApp-DBEndpoint
  - Name: API_KEY_ENCRYPTION_SECRET_ARN
    Value: !ImportValue StocksApp-ApiKeyEncryptionSecretArn
    
Secrets:
  - Name: DB_SECRET_ARN
    ValueFrom: !ImportValue StocksApp-SecretArn
```

## Migration Guidelines

### Updating Existing Templates

1. **Database variables**: Change `DB_HOST` → `DB_ENDPOINT`
2. **Secret variables**: Standardize to `*_SECRET_ARN` pattern
3. **Environment**: Use `NODE_ENV` for Node.js, `ENVIRONMENT` for general config
4. **AWS Region**: Standardize to `AWS_REGION`

### Backwards Compatibility

When updating templates:
- Keep old variable names temporarily with deprecation warnings
- Use gradual migration approach
- Update application code to handle both old and new variable names
- Remove deprecated variables only after all deployments are updated

## Validation

### Required Variables by Service Type

**Webapp Lambda/ECS**:
- ✅ `DB_SECRET_ARN`, `DB_ENDPOINT`
- ✅ `API_KEY_ENCRYPTION_SECRET_ARN`
- ✅ `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`
- ✅ `AWS_REGION`, `NODE_ENV`

**WebSocket Services**:
- ✅ `ELASTICACHE_ENDPOINT`, `ELASTICACHE_PORT`
- ✅ `CONNECTIONS_TABLE`, `SUBSCRIPTIONS_TABLE`
- ✅ Database variables (if needed)

**Data Processing**:
- ✅ `DB_SECRET_ARN`, `DB_ENDPOINT`
- ✅ Service-specific variables

### Health Check Integration

Use the `/health/api-services` endpoint to validate:
- Environment variables are properly set
- Secrets are accessible
- Services can initialize correctly

```bash
curl https://your-api.execute-api.region.amazonaws.com/stage/health/api-services
```

## Common Issues

### Missing Environment Variables
**Symptom**: 503 "Service temporarily unavailable" errors
**Solution**: Check CloudFormation template has all required variables

### Inconsistent Naming
**Symptom**: Application can't find configuration
**Solution**: Use exact variable names from this document

### Secret Access Issues
**Symptom**: "Cannot access encryption secret" errors
**Solution**: Verify IAM permissions include proper secret ARN patterns

### Frontend Configuration
**Symptom**: "WebSocket URL not configured" or API connection failures
**Solution**: Ensure Vite variables are set during build process

## Implementation Status

### ✅ Completed Templates
- `template-webapp-lambda.yml` - Fully standardized
- `webapp/template-webapp-lambda.yml` - Updated with all variables
- `template-webapp.yml` - ECS template standardized
- `template-core.yml` - IAM permissions updated

### 🔄 In Progress
- WebSocket templates - Variables consistent, need validation
- HFT templates - Need review and standardization

### ⏳ Pending
- Legacy templates requiring migration
- Third-party integration templates

---

**Last Updated**: 2025-07-14
**Version**: 1.0.0
**Status**: Production-ready environment variable standards