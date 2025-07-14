/**
 * Standardized User API Key Helper
 * 
 * This module provides consistent API key retrieval and user authentication
 * across all Lambda routes that need broker API integration.
 * 
 * Ensures user ID consistency and proper error handling.
 */

const { query } = require('./database');
const apiKeyService = require('./apiKeyService');

/**
 * Get user's decrypted API key for a specific broker with comprehensive debugging
 * @param {string} userId - The authenticated user's ID (from req.user.sub)
 * @param {string} broker - The broker name (e.g., 'alpaca', 'robinhood')
 * @param {string} keyId - Optional specific key ID to retrieve
 * @returns {Object} Decrypted API credentials or null if not found
 */
async function getUserApiKey(userId, broker, keyId = null) {
  console.log(`🔑 [API-KEY] Getting API key for user: ${userId}, broker: ${broker}, keyId: ${keyId || 'auto'}`);
  
  if (!userId) {
    console.error('❌ [API-KEY] No user ID provided');
    throw new Error('User ID is required for API key retrieval');
  }
  
  if (!broker) {
    console.error('❌ [API-KEY] No broker specified');
    throw new Error('Broker is required for API key retrieval');
  }
  
  try {
    // Debug: Check if API key service is enabled
    if (!apiKeyService.isEnabled) {
      console.error('❌ [API-KEY] API key service is disabled');
      throw new Error('API key service is not enabled');
    }
    
    // Debug: Check user's API keys in database
    const debugResult = await query(`
      SELECT id, provider, user_id, is_active, is_sandbox, created_at 
      FROM user_api_keys 
      WHERE user_id = $1
    `, [userId]);
    
    console.log(`🔍 [API-KEY] User has ${debugResult.rows.length} total API keys`);
    if (debugResult.rows.length > 0) {
      console.log(`🔍 [API-KEY] Available keys: ${debugResult.rows.length} keys found for ${broker || 'all brokers'}`);
    } else {
      console.log(`🔍 [API-KEY] No API keys found for user`);
      
      // Additional debug: Show all users with API keys to help troubleshoot
      const allUsersResult = await query(`
        SELECT DISTINCT user_id, COUNT(*) as key_count 
        FROM user_api_keys 
        GROUP BY user_id 
        ORDER BY key_count DESC 
        LIMIT 5
      `);
      console.log(`🔍 [API-KEY] Users with API keys in database:`, 
        allUsersResult.rows.map(u => `${u.user_id}(${u.key_count} keys)`)
      );
      
      return null;
    }
    
    // If specific key ID requested, get that specific key
    if (keyId) {
      console.log(`🔑 [API-KEY] Retrieving specific key ID: ${keyId}`);
      
      const specificKeyResult = await query(`
        SELECT 
          id, provider, encrypted_api_key, key_iv, key_auth_tag,
          encrypted_api_secret, secret_iv, secret_auth_tag,
          user_salt, is_sandbox, is_active
        FROM user_api_keys 
        WHERE id = $1 AND user_id = $2 AND provider = $3 AND is_active = true
      `, [keyId, userId, broker]);
      
      if (specificKeyResult.rows.length === 0) {
        console.log(`❌ [API-KEY] Specific key ${keyId} not found or inactive`);
        return null;
      }
      
      const keyData = specificKeyResult.rows[0];
      console.log(`✅ [API-KEY] Found specific key: ${broker} (sandbox: ${keyData.is_sandbox})`);
      
      // Decrypt the credentials with proper async handling and error handling
      let apiKey, apiSecret;
      try {
        apiKey = await apiKeyService.decryptApiKey({
          encrypted: keyData.encrypted_api_key,
          iv: keyData.key_iv,
          authTag: keyData.key_auth_tag
        }, keyData.user_salt);
        
        apiSecret = keyData.encrypted_api_secret ? await apiKeyService.decryptApiKey({
          encrypted: keyData.encrypted_api_secret,
          iv: keyData.secret_iv,
          authTag: keyData.secret_auth_tag
        }, keyData.user_salt) : null;
      } catch (decryptError) {
        console.error(`❌ [API-KEY] Failed to decrypt credentials for key ${keyId}:`, decryptError);
        return null;
      }
      
      return {
        id: keyData.id,
        provider: keyData.provider,
        apiKey: apiKey,
        apiSecret: apiSecret,
        isSandbox: keyData.is_sandbox,
        isActive: keyData.is_active
      };
    }
    
    // Default behavior: get any available key for the broker
    console.log(`🔑 [API-KEY] Getting default key for broker: ${broker}`);
    const credentials = await apiKeyService.getDecryptedApiKey(userId, broker);
    
    if (credentials) {
      console.log(`✅ [API-KEY] Retrieved credentials for ${broker} (sandbox: ${credentials.isSandbox})`);
      return credentials;
    } else {
      console.log(`❌ [API-KEY] No credentials found for user ${userId}, broker ${broker}`);
      return null;
    }
    
  } catch (error) {
    console.error(`❌ [API-KEY] Error retrieving API key:`, error.message);
    throw error;
  }
}

/**
 * Validate that a user is properly authenticated and has required user ID
 * @param {Object} req - Express request object
 * @returns {string} The validated user ID
 */
function validateUserAuthentication(req) {
  if (!req.user) {
    throw new Error('User not authenticated - missing req.user');
  }
  
  const userId = req.user.sub;
  if (!userId) {
    throw new Error('User ID not found in authentication token');
  }
  
  console.log(`👤 [AUTH] Validated user: ${userId}`);
  return userId;
}

/**
 * Standardized error response for API key issues
 * @param {Object} res - Express response object
 * @param {string} broker - The broker name
 * @param {string} userId - The user ID
 * @param {string} error - The error message
 */
function sendApiKeyError(res, broker, userId, error) {
  console.error(`❌ [API-KEY-ERROR] ${error} (user: ${userId}, broker: ${broker})`);
  
  return res.status(400).json({
    success: false,
    error: 'API key not found',
    message: `No API key configured for ${broker}. Please add your API key in Settings.`,
    debug: {
      userId: userId,
      broker: broker,
      timestamp: new Date().toISOString(),
      details: error
    }
  });
}

/**
 * Check if user has any API keys for debugging purposes
 * @param {string} userId - The user ID to check
 * @returns {Object} Summary of user's API keys
 */
async function getUserApiKeySummary(userId) {
  try {
    const result = await query(`
      SELECT provider, COUNT(*) as key_count, 
             SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active_keys,
             SUM(CASE WHEN is_sandbox THEN 1 ELSE 0 END) as sandbox_keys
      FROM user_api_keys 
      WHERE user_id = $1
      GROUP BY provider
    `, [userId]);
    
    const summary = {
      userId: userId,
      totalProviders: result.rows.length,
      providers: result.rows.map(row => ({
        provider: row.provider,
        totalKeys: parseInt(row.key_count),
        activeKeys: parseInt(row.active_keys),
        sandboxKeys: parseInt(row.sandbox_keys)
      }))
    };
    
    console.log(`📊 [API-KEY-SUMMARY] User ${userId}:`, summary);
    return summary;
  } catch (error) {
    console.error(`❌ [API-KEY-SUMMARY] Error getting summary:`, error.message);
    return { userId, error: error.message };
  }
}

module.exports = {
  getUserApiKey,
  validateUserAuthentication,
  sendApiKeyError,
  getUserApiKeySummary
};