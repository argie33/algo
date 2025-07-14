# CRITICAL: Fix 502 Errors - Missing Encryption Secret

## Current Issue

The API test results show **502 errors** across all Lambda endpoints. This indicates the Lambda functions are failing due to missing infrastructure components.

## Root Cause

The Lambda functions require `API_KEY_ENCRYPTION_SECRET` from AWS Secrets Manager, but this secret doesn't exist yet. Without it, the encryption service fails and causes 502 errors.

## Immediate Fix Required

### Step 1: Create the Missing Secret

Run this command to create the required encryption secret:

```bash
./setup-encryption-secret.sh
```

**Alternative**: If the secret already exists, update it instead:

```bash
# Generate new key
ENCRYPTION_KEY=$(openssl rand -hex 32)

# Update existing secret
aws secretsmanager update-secret \
    --secret-id "algo-trade-api-keys" \
    --secret-string "{\"API_KEY_ENCRYPTION_SECRET\":\"$ENCRYPTION_KEY\"}" \
    --region us-east-1
```

### Step 2: Redeploy the Application

After creating the secret, trigger a new deployment:

```bash
# Commit any remaining changes and push
git push origin loaddata

# The GitHub Actions workflow will automatically deploy
# OR manually trigger via GitHub Actions UI
```

### Step 3: Verify the Fix

Test the endpoints after deployment:

```bash
node test-auth-and-api-keys.js
```

## What This Fixes

- **502 Internal Server Error** → **200 OK** responses
- **Failed API key endpoints** → **Working encryption service**
- **Database connectivity issues** → **Proper secret management**

## Expected Results After Fix

```json
{
  "summary": {
    "passed": 6,
    "failed": 0
  },
  "infrastructure": {
    "secretsStatus": {
      "initialized": true,
      "hasApiKeySecret": true
    },
    "apiKeyStatus": {
      "encryptionEnabled": true,
      "setupRequired": false
    }
  }
}
```

## Security Notes

✅ **Secure Implementation**:
- 256-bit encryption key (32 bytes)
- Stored in AWS Secrets Manager (not environment variables)
- Automatic key rotation support
- Lambda IAM role has minimal required permissions

## Troubleshooting

If you still see 502 errors after creating the secret:

1. **Check CloudFormation Stack**: Ensure deployment completed successfully
2. **Verify Secret Access**: Lambda needs `secretsmanager:GetSecretValue` permission
3. **Check Region**: Secret must be in same region as Lambda (us-east-1)
4. **Test Secret**: `aws secretsmanager get-secret-value --secret-id algo-trade-api-keys`

## Next Steps After Fix

Once the 502 errors are resolved:

1. ✅ Test API key creation/deletion in frontend
2. ✅ Test portfolio data import with real API keys  
3. ✅ Verify user isolation and security
4. ✅ Complete end-to-end workflow testing

The application is fully ready once this critical infrastructure issue is resolved.