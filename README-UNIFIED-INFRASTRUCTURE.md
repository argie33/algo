# Unified Financial Dashboard Infrastructure

## Overview

This document describes the unified infrastructure approach for the financial dashboard application, eliminating the previous issues with duplicate templates, V2 naming conflicts, and deployment inconsistencies.

## Architecture Summary

The unified infrastructure creates a complete, production-ready financial dashboard with the following components:

- **API Gateway**: HTTP API Gateway v2 with comprehensive CORS configuration
- **Lambda Function**: Node.js 18.x runtime with VPC integration and timeout management
- **Database**: PostgreSQL with SSL-free configuration and connection pooling
- **Authentication**: AWS Cognito User Pool with JWT validation
- **Frontend**: React application hosted on S3 with CloudFront distribution
- **Security**: API key encryption, audit logging, and circuit breaker patterns

## Key Files

### Infrastructure Templates

1. **`template-webapp-unified.yml`** - Single CloudFormation template that creates all infrastructure
2. **`.github/workflows/deploy-webapp-unified.yml`** - Single deployment workflow

### API Key System

1. **`webapp/lambda/utils/apiKeyService.js`** - Unified API key service with JWT integration
2. **`webapp/lambda/middleware/authEnhanced.js`** - Enhanced authentication middleware
3. **`webapp/lambda/routes/settingsEnhanced.js`** - JWT-validated settings routes
4. **`create_api_key_audit_table.sql`** - Audit logging table schema

### Testing & Monitoring

1. **`webapp/lambda/test-database-connectivity.js`** - Comprehensive database testing
2. **`webapp/lambda/routes/diagnostics.js`** - Production monitoring endpoints
3. **`webapp/lambda/validate-complete-flow.js`** - End-to-end validation script

## Deployment

### Prerequisites

1. AWS CLI configured with appropriate permissions
2. Node.js 18.x installed
3. Required AWS resources from core infrastructure stack

### Environment Variables

The following environment variables are required:

```bash
# Core Infrastructure (from existing stack)
DB_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789012:secret:stocks-db-secret
API_KEY_ENCRYPTION_SECRET_ARN=arn:aws:secretsmanager:us-east-1:123456789012:secret:api-key-encryption

# Cognito Configuration (created by unified template)
COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
COGNITO_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx

# Application Configuration
NODE_ENV=production
WEBAPP_AWS_REGION=us-east-1
```

### Deployment Steps

1. **Deploy Infrastructure**:
   ```bash
   # Trigger GitHub Actions workflow
   git push origin main
   
   # Or deploy manually
   aws cloudformation deploy \
     --stack-name financial-dashboard-unified \
     --template-file template-webapp-unified.yml \
     --parameter-overrides \
       LambdaCodeKey=api.zip \
       EnvironmentName=dev \
     --capabilities CAPABILITY_IAM
   ```

2. **Validate Deployment**:
   ```bash
   # Test complete flow
   node webapp/lambda/validate-complete-flow.js https://your-api-gateway.execute-api.us-east-1.amazonaws.com/dev
   
   # Test database connectivity
   node webapp/lambda/test-database-connectivity.js
   ```

3. **Monitor Health**:
   ```bash
   # Check API Gateway health
   curl https://your-api-gateway.execute-api.us-east-1.amazonaws.com/dev/api/health
   
   # Check diagnostic endpoints (requires authentication)
   curl -H "Authorization: Bearer $JWT_TOKEN" \
     https://your-api-gateway.execute-api.us-east-1.amazonaws.com/dev/api/diagnostics/health
   ```

## Security Features

### Authentication & Authorization

- **JWT Token Validation**: All protected routes require valid Cognito JWT tokens
- **Circuit Breaker Protection**: JWT validation includes circuit breaker patterns
- **Session Management**: Token caching with automatic invalidation
- **Role-Based Access Control**: Admin-only endpoints for sensitive operations

### API Key Management

- **Per-User Encryption**: Each user's API keys encrypted with unique salt
- **AWS Secrets Manager**: Encryption keys stored in AWS Secrets Manager
- **Audit Logging**: All API key operations logged for compliance
- **Connection Testing**: Validate API keys with actual provider connections

### Network Security

- **VPC Integration**: Lambda functions run in private subnets
- **Security Groups**: Restrictive security group rules
- **HTTPS Only**: All communications over HTTPS
- **CORS Configuration**: Proper CORS headers for browser security

## Monitoring & Diagnostics

### Health Checks

- **`/api/health`** - Quick health check without database dependency
- **`/api/health?quick=false`** - Full health check including database
- **`/api/diagnostics/health`** - Comprehensive health status (auth required)

### Diagnostic Endpoints

- **`/api/diagnostics/database-connectivity`** - Database connection testing
- **`/api/diagnostics/system-info`** - System information
- **`/api/diagnostics/lambda-info`** - Lambda function details
- **`/api/diagnostics/external-services`** - External service connectivity

### Circuit Breaker Monitoring

- **API Key Service**: Monitors API key operations
- **JWT Validation**: Monitors authentication operations
- **Database Connection**: Monitors database connectivity

## Database Configuration

### SSL Configuration

The database is configured with `ssl: false` based on successful ECS task patterns:

```javascript
const config = {
  host: secret.host,
  port: secret.port,
  database: secret.database,
  user: secret.username,
  password: secret.password,
  ssl: false,  // No SSL for RDS in VPC
  connectionTimeoutMillis: 10000,
  idleTimeoutMillis: 30000,
  max: 10
};
```

### Connection Pooling

- **Initial Pool Size**: 2 connections
- **Maximum Pool Size**: 10 connections
- **Connection Timeout**: 10 seconds
- **Idle Timeout**: 30 seconds

### Required Tables

```sql
-- Core tables
user_api_keys          -- API key storage
stock_symbols          -- Stock symbol data
stock_prices          -- Price data
technical_indicators  -- Technical analysis data

-- Audit tables
api_key_audit_log     -- API key operation audit trail
```

## API Key System

### Supported Providers

- **Alpaca**: Trading API (requires apiKey and apiSecret)
- **Polygon**: Market data API (requires apiKey)
- **Finnhub**: Financial data API (requires apiKey)
- **Alpha Vantage**: Market data API (requires apiKey)

### API Key Operations

```javascript
// Store API key
await storeApiKey(jwtToken, 'alpaca', {
  apiKey: 'PKXXXXXX',
  apiSecret: 'XXXXXXXXXXXX',
  isSandbox: true,
  description: 'Alpaca trading account'
});

// Retrieve API key
const apiKey = await getApiKey(jwtToken, 'alpaca');

// Validate API key
const validation = await validateApiKey(jwtToken, 'alpaca', true);

// Delete API key
await deleteApiKey(jwtToken, 'alpaca');
```

### Security Features

- **AES-256-GCM Encryption**: All API keys encrypted before database storage
- **User-Specific Salts**: Each user has unique encryption salt
- **Audit Logging**: All operations logged with user and session information
- **Connection Testing**: Validate API keys with actual provider connections

## Frontend Configuration

### Build Process

The deployment workflow automatically configures the frontend with real CloudFormation outputs:

```javascript
// Generated configuration
const config = {
  API_URL: 'https://abc123.execute-api.us-east-1.amazonaws.com/dev',
  USER_POOL_ID: 'us-east-1_XXXXXXXXX',
  CLIENT_ID: 'xxxxxxxxxxxxxxxxxxxxxxxxxx',
  COGNITO_DOMAIN: 'https://financial-dashboard-dev-123456789012.auth.us-east-1.amazoncognito.com',
  ENVIRONMENT: 'production'
};
```

### CloudFront Configuration

- **Origin Access Control**: Secure S3 access
- **Cache Behaviors**: Optimized for SPA routing
- **SSL Certificate**: HTTPS-only access
- **Custom Error Pages**: 404/403 redirect to index.html

## Performance Optimization

### Caching Strategy

- **API Key Cache**: 5-minute cache for decrypted API keys
- **Session Cache**: 5-minute cache for JWT token validation
- **Database Connection Pooling**: Efficient connection reuse
- **CloudFront CDN**: Global content delivery

### Circuit Breaker Patterns

- **API Key Service**: 5 failures trigger 60-second timeout
- **JWT Validation**: 3 failures trigger 30-second timeout
- **Database Connection**: 5 failures trigger 60-second timeout

## Troubleshooting

### Common Issues

1. **Database Connection Errors**:
   ```bash
   # Check database connectivity
   node webapp/lambda/test-database-connectivity.js
   
   # Check SSL configuration
   curl -H "Authorization: Bearer $JWT_TOKEN" \
     https://your-api-gateway.execute-api.us-east-1.amazonaws.com/dev/api/diagnostics/database-connectivity
   ```

2. **CORS Issues**:
   ```bash
   # Test CORS preflight
   curl -X OPTIONS \
     -H "Origin: https://your-frontend.com" \
     -H "Access-Control-Request-Method: GET" \
     -H "Access-Control-Request-Headers: authorization" \
     https://your-api-gateway.execute-api.us-east-1.amazonaws.com/dev/api/health
   ```

3. **Authentication Issues**:
   ```bash
   # Check Cognito configuration
   curl https://your-api-gateway.execute-api.us-east-1.amazonaws.com/dev/api/diagnostics/system-info
   ```

### Log Locations

- **Lambda Logs**: `/aws/lambda/financial-dashboard-api-dev`
- **API Gateway Logs**: `/aws/apigateway/financial-dashboard-dev`
- **CloudFront Logs**: S3 bucket (if enabled)

## Best Practices

### Development

1. **Use Enhanced Services**: Always use the enhanced API key service and authentication middleware
2. **Follow Security Guidelines**: Never log sensitive information
3. **Test Thoroughly**: Use validation scripts before deployment
4. **Monitor Health**: Regularly check health endpoints

### Production

1. **Environment Variables**: Use AWS Secrets Manager for sensitive configuration
2. **SSL Configuration**: Follow the working database SSL configuration
3. **Circuit Breakers**: Monitor circuit breaker status
4. **Audit Logging**: Review audit logs regularly

### Maintenance

1. **Regular Updates**: Keep dependencies updated
2. **Security Patches**: Apply security patches promptly
3. **Performance Monitoring**: Monitor response times and error rates
4. **Database Maintenance**: Regular database maintenance and optimization

## Migration from Legacy System

### API Key Migration

The unified system includes migration logic for legacy API keys:

```javascript
// Legacy format migration
const legacyData = {
  encrypted_api_key: 'legacy_encrypted_data',
  key_iv: 'legacy_iv',
  key_auth_tag: 'legacy_auth_tag',
  user_salt: 'legacy_salt'
};

// Migrated to unified format
const unifiedData = {
  encrypted: 'unified_encrypted_data',
  iv: 'unified_iv',
  authTag: 'unified_auth_tag',
  algorithm: 'aes-256-gcm',
  version: '2.0'
};
```

### Route Updates

Replace legacy route usage with enhanced versions:

```javascript
// Old
const { authenticateToken } = require('./middleware/auth');
const settingsRoutes = require('./routes/settings');

// New
const { authenticateToken } = require('./middleware/authEnhanced');
const settingsRoutes = require('./routes/settingsEnhanced');
```

## Conclusion

The unified infrastructure approach provides a comprehensive, production-ready financial dashboard with:

- **Single Source of Truth**: One template, one workflow, one deployment
- **Enhanced Security**: JWT validation, API key encryption, audit logging
- **Comprehensive Monitoring**: Health checks, diagnostics, circuit breakers
- **Production Ready**: Tested, validated, and optimized for production use

This approach eliminates the previous issues with duplicate templates, V2 naming conflicts, and deployment inconsistencies while providing a robust, scalable foundation for the financial dashboard application.