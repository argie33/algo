# Multi-User API Key Architecture Fix

## Problem Statement

The current Lambda environment variable approach for API keys is fundamentally flawed for a multi-user platform. Each user has their own broker API keys stored in the `user_api_keys` table, and these must be retrieved dynamically at runtime based on the authenticated user context.

## Current Wrong Approach ❌

```javascript
// WRONG: Using Lambda environment variables
const alpacaApiKey = process.env.ALPACA_API_KEY;  // Single key for all users
const alpacaSecret = process.env.ALPACA_SECRET;   // Single secret for all users
```

**Issues:**
- Only supports one user's API keys
- Cannot scale to multiple users
- Violates security isolation between users
- Hardcoded in Lambda environment

## Correct Multi-User Approach ✅

### 1. Database-Driven API Key Retrieval

```javascript
// CORRECT: Per-user API key retrieval
const getUserApiCredentials = async (userId, provider) => {
  const result = await query(`
    SELECT encrypted_api_key, key_iv, key_auth_tag,
           encrypted_api_secret, secret_iv, secret_auth_tag,
           user_salt, is_sandbox
    FROM user_api_keys 
    WHERE user_id = $1 AND provider = $2 AND is_active = true
  `, [userId, provider]);
  
  if (result.rows.length === 0) {
    throw new Error(`No active ${provider} API keys found for user ${userId}`);
  }
  
  return decryptUserApiKeys(result.rows[0]);
};
```

### 2. Request-Scoped API Client Creation

```javascript
// CORRECT: Create API client per request with user's keys
const createUserAlpacaClient = async (userId) => {
  const credentials = await getUserApiCredentials(userId, 'alpaca');
  
  return new AlpacaService(
    credentials.apiKey,
    credentials.apiSecret,
    credentials.isSandbox
  );
};
```

### 3. Authentication-First API Design

```javascript
// CORRECT: All API routes start with user authentication
router.get('/portfolio/holdings', authenticateToken, async (req, res) => {
  try {
    // 1. Get authenticated user ID
    const userId = req.user.sub || req.user.userId;
    
    // 2. Get user's API credentials
    const alpacaClient = await createUserAlpacaClient(userId);
    
    // 3. Fetch user-specific data
    const holdings = await alpacaClient.getPositions();
    
    res.json({ success: true, data: holdings });
  } catch (error) {
    if (error.message.includes('No active alpaca API keys')) {
      return res.status(400).json({
        success: false,
        error: 'API_KEYS_REQUIRED',
        message: 'Please configure your Alpaca API keys in Settings'
      });
    }
    throw error;
  }
});
```

## Implementation Changes Required

### 1. Remove Environment Variable Dependencies

**Files to Update:**
- `webapp/lambda/utils/alpacaService.js` - Remove env var fallbacks
- `webapp/lambda/routes/*.js` - Use user-specific API key retrieval
- `template-webapp-lambda.yml` - Remove hardcoded API key environment variables

### 2. Enhance User API Key Service

**File**: `webapp/lambda/utils/apiKeyService.js`

```javascript
class UserApiKeyService {
  async getUserCredentials(userId, provider) {
    // Get user's encrypted credentials from database
    const dbResult = await this.getEncryptedCredentials(userId, provider);
    
    // Decrypt using user-specific salt and master key
    return await this.decryptCredentials(dbResult);
  }
  
  async validateUserCredentials(userId, provider) {
    try {
      const credentials = await this.getUserCredentials(userId, provider);
      // Test credentials with broker API
      return await this.testBrokerConnection(credentials, provider);
    } catch (error) {
      return { valid: false, error: error.message };
    }
  }
}
```

### 3. Update All API Routes

**Pattern to Apply:**
```javascript
// Before: Wrong approach
router.get('/endpoint', authenticateToken, async (req, res) => {
  const alpaca = new AlpacaService(process.env.ALPACA_KEY, process.env.ALPACA_SECRET);
  // ...
});

// After: Correct approach
router.get('/endpoint', authenticateToken, async (req, res) => {
  const userId = req.user.sub;
  const credentials = await getUserApiCredentials(userId, 'alpaca');
  const alpaca = new AlpacaService(credentials.apiKey, credentials.apiSecret);
  // ...
});
```

## Database Schema Validation

### Current Schema (Correct ✅)
```sql
CREATE TABLE user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    encrypted_api_key TEXT NOT NULL,
    key_iv TEXT NOT NULL,
    key_auth_tag TEXT NOT NULL,
    encrypted_api_secret TEXT,
    secret_iv TEXT,
    secret_auth_tag TEXT,
    user_salt TEXT NOT NULL,
    is_sandbox BOOLEAN DEFAULT true,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(user_id, provider)
);
```

## Security Implications

### ✅ Correct Security Model
- Each user's API keys are encrypted with user-specific salts
- No cross-user data access possible
- Keys are decrypted only when needed for that user's requests
- Failed decryption affects only that user, not the entire system

### ❌ Wrong Security Model (Current)
- Single API key in environment variables
- All users would use the same broker account
- Complete violation of user data isolation
- Single point of failure for all users

## Performance Considerations

### Optimization Strategies
1. **Connection Pooling**: Cache decrypted credentials for the duration of a request
2. **Lazy Loading**: Only decrypt API keys when broker API calls are needed
3. **Batch Operations**: Group multiple API calls within a single user session
4. **Circuit Breakers**: Per-user circuit breakers for broker API failures

### Example Optimized Implementation
```javascript
class RequestScopedApiKeyCache {
  constructor() {
    this.cache = new Map(); // userId -> { provider -> credentials }
  }
  
  async getUserCredentials(userId, provider) {
    const cacheKey = `${userId}:${provider}`;
    
    if (!this.cache.has(cacheKey)) {
      const credentials = await getUserApiCredentials(userId, provider);
      this.cache.set(cacheKey, credentials);
    }
    
    return this.cache.get(cacheKey);
  }
}
```

## Migration Steps

1. **Immediate**: Update all routes to use user-specific API key retrieval
2. **Remove**: Environment variable dependencies for API keys
3. **Test**: Ensure each user only sees their own data
4. **Deploy**: Gradual rollout with user-by-user testing
5. **Monitor**: Track API key retrieval performance and errors

## Error Handling Patterns

```javascript
// Standard error handling for missing API keys
const handleApiKeyError = (error, res) => {
  if (error.message.includes('No active') && error.message.includes('API keys')) {
    return res.status(400).json({
      success: false,
      error: 'API_KEYS_REQUIRED',
      message: 'Please configure your broker API keys in Settings',
      action: 'REDIRECT_TO_SETTINGS'
    });
  }
  
  if (error.message.includes('Invalid API credentials')) {
    return res.status(400).json({
      success: false,
      error: 'INVALID_API_KEYS',
      message: 'Your API keys appear to be invalid. Please check your settings.',
      action: 'VALIDATE_SETTINGS'
    });
  }
  
  throw error; // Re-throw unexpected errors
};
```

This architecture fix ensures proper multi-user support with secure, isolated API key management.