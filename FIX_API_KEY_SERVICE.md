# IMMEDIATE FIX: API Key Service 503 Errors

## Problem Diagnosis
- API key endpoints returning 503 "service unavailable"
- Encryption service using temporary keys instead of permanent AWS secrets
- Secret `stocks-app/api-key-encryption` does not exist in AWS Secrets Manager

## Root Cause
The `API_KEY_ENCRYPTION_SECRET` environment variable is not being loaded because the secret doesn't exist in AWS Secrets Manager.

## Immediate Solution Options

### Option 1: Create Secret via AWS Console (FASTEST)
1. Go to AWS Secrets Manager console
2. Create new secret:
   - Name: `stocks-app/api-key-encryption`
   - Type: "Other type of secret"
   - Key/value pairs:
     ```json
     {
       "API_KEY_ENCRYPTION_SECRET": "<64-character-random-string>"
     }
     ```
3. Restart Lambda function (redeploy)

### Option 2: Update Secrets Loader (TEMPORARY FIX)
Update the secrets loader to use the existing database secret for encryption until proper secret is created.

### Option 3: CloudFormation Deployment (PROPER FIX)
Deploy the `api-key-secret-cloudformation.yml` template to create secrets properly.

## Current Status
- ❌ API key encryption: Using temporary keys (data lost on restart)
- ❌ JWT secret: Missing (authentication may fail)
- ✅ Database: Working correctly
- ✅ Basic endpoints: Working correctly

## Impact
- Users cannot permanently store API keys
- API key setup wizard fails with 503 errors
- Portfolio integration cannot access user's broker APIs
- System falls back to demo data

## Next Steps
1. Create the missing secret in AWS Secrets Manager
2. Redeploy or restart Lambda to pick up secret
3. Test API key endpoints return 200 instead of 503
4. Verify end-to-end API key workflow

## Test Commands
```bash
# Check secrets status
curl "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/debug/secrets-status"

# Should show:
# "usingTempEncryption": false
# "hasApiKeySecret": true

# Test API key endpoint
curl "https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev/settings/api-keys" \
  -H "Authorization: Bearer mock-token"

# Should return 401 (auth required) not 503 (service unavailable)
```