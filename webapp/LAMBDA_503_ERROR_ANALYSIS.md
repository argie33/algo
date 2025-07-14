# Lambda 503 Error Analysis and Resolution

## Issue Summary
The `/settings/api-keys` endpoint is returning a 503 Service Unavailable error with the message "Settings service is being loaded". This is a critical failure blocking the API key integration system.

## Root Cause Analysis

### Primary Issue: Missing Environment Variable
The Lambda function's `safeRequire` function is catching module loading failures and returning a 503 error. The settings route (`/routes/settings.js`) is failing to load because:

1. **Missing `API_KEY_ENCRYPTION_SECRET` environment variable**
   - The `ApiKeyService` class requires this environment variable for encryption
   - Without it, the module throws an error during initialization
   - This causes the `safeRequire` function to return a placeholder that responds with 503

### Multi-User Architecture is Correct
The current encryption approach is properly designed for multi-user scenarios:
- **Global encryption secret**: `API_KEY_ENCRYPTION_SECRET` environment variable (master key)
- **Per-user salt**: `userSalt` generated uniquely for each user (`crypto.randomBytes(16)`)
- **Final encryption key**: `crypto.scryptSync(secretKey, userSalt, 32)` - combines global secret with user salt
- **Result**: Each user's API keys are encrypted with a unique key, ensuring data isolation

### Secondary Issues Discovered

2. **Inadequate Error Handling**
   - The `safeRequire` function masks the actual error with a generic "service is being loaded" message
   - No proper fallback mechanism for missing environment variables

3. **Missing CloudFormation Parameters**
   - The deployment template doesn't include the required encryption secret parameter
   - No validation for required environment variables during deployment

4. **Insufficient Environment Variable Documentation**
   - No clear documentation of required environment variables
   - No `.env` template file for developers

## Solutions Implemented

### ✅ COMPLETED
1. **Fixed ApiKeyService to handle missing encryption secret gracefully**
   - Modified constructor to disable service instead of throwing error
   - Added proper warning messages when encryption is unavailable
   - Updated routes to handle disabled encryption service

2. **Updated settings routes to handle disabled encryption**
   - Added checks for `apiKeyService.isEnabled` before processing requests
   - Return appropriate error messages when encryption is unavailable
   - Graceful degradation with informative user messages

3. **Updated CloudFormation template**
   - Added `ApiKeyEncryptionSecret` parameter with validation
   - Added environment variable to Lambda function configuration
   - Set parameter as `NoEcho: true` for security

4. **Created deployment script with encryption support**
   - New script that generates or uses provided encryption secret
   - Proper parameter validation before deployment
   - Clear documentation of required environment variables

### 🔄 PENDING (See Todo List)
5. **Environment Variable Setup**
   - Need to deploy Lambda with proper `API_KEY_ENCRYPTION_SECRET`
   - Test endpoint functionality after deployment
   - Validate that all API key operations work correctly

6. **Additional Improvements**
   - Add startup validation for all required environment variables
   - Create `.env` template file for developers
   - Improve error messages in `safeRequire` function
   - Check other routes for similar environment variable dependencies

## Deployment Instructions

### Quick Fix (Set Environment Variable)
```bash
# Generate encryption secret
API_KEY_ENCRYPTION_SECRET=$(openssl rand -base64 32)

# Update Lambda function environment variable
aws lambda update-function-configuration \
    --function-name financial-dashboard-api-dev \
    --environment "Variables={API_KEY_ENCRYPTION_SECRET=$API_KEY_ENCRYPTION_SECRET,...other vars...}"
```

### Complete Deployment
```bash
# Set required environment variables
export DATABASE_SECRET_ARN="arn:aws:secretsmanager:us-east-1:123456789012:secret:db-secret"
export DATABASE_ENDPOINT="your-db-endpoint.rds.amazonaws.com"
export COGNITO_USER_POOL_ID="us-east-1_XXXXXXXXX"
export COGNITO_CLIENT_ID="your-client-id"
export API_KEY_ENCRYPTION_SECRET="your-32-char-secret"

# Deploy with new script
./deploy-with-encryption.sh
```

## Testing Plan

### 1. Test Settings Route Loading
```bash
# Test that settings module loads without error
node -e "try { require('./routes/settings'); console.log('SUCCESS'); } catch(e) { console.error('FAILED:', e.message); }"
```

### 2. Test API Endpoints
```bash
# Test health endpoint
curl https://your-api-url/health

# Test settings endpoint (should return graceful error or work with encryption)
curl https://your-api-url/settings/api-keys
```

### 3. Test API Key Operations
```bash
# Test adding API key (after authentication)
curl -X POST https://your-api-url/settings/api-keys \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"provider":"alpaca","apiKey":"test","isSandbox":true}'

# Test retrieving API keys
curl -H "Authorization: Bearer YOUR_TOKEN" https://your-api-url/settings/api-keys
```

## Files Modified
- `/webapp/lambda/utils/apiKeyService.js` - Added graceful handling for missing encryption secret
- `/webapp/lambda/routes/settings.js` - Added encryption service availability checks
- `/webapp/lambda/template-webapp-lambda.yml` - Added encryption secret parameter
- `/webapp/deploy-with-encryption.sh` - New deployment script with encryption support

## Environment Variables Required
- `API_KEY_ENCRYPTION_SECRET` - 32+ character secret for API key encryption
- `DATABASE_SECRET_ARN` - ARN of database credentials secret
- `DATABASE_ENDPOINT` - RDS database endpoint
- `COGNITO_USER_POOL_ID` - Cognito user pool ID
- `COGNITO_CLIENT_ID` - Cognito app client ID
- `NODE_ENV` - Environment name (dev/staging/prod)
- `DB_SECRET_ARN` - Same as DATABASE_SECRET_ARN
- `DB_ENDPOINT` - Same as DATABASE_ENDPOINT
- `WEBAPP_AWS_REGION` - AWS region for deployment

## Next Steps
1. Deploy Lambda with encryption secret using new deployment script
2. Test all API key endpoints to ensure they work correctly
3. Validate that users can add, retrieve, and manage API keys
4. Monitor for any other missing environment variables
5. Add comprehensive environment variable validation on startup

## Error Prevention
- Created deployment script with parameter validation
- Added graceful fallback for missing encryption service
- Implemented proper error messages for users
- Added CloudFormation parameter validation
- Documented all required environment variables