const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { query } = require('./database');
const crypto = require('crypto');

/**
 * Resilient API Key Service with comprehensive error handling and fallback mechanisms
 * Provides encrypted storage and retrieval of user API keys with circuit breaker patterns
 */

class ApiKeyServiceResilient {
  constructor() {
    this.secretsManager = new SecretsManagerClient({
      region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
    });
    
    // Circuit breaker state
    this.circuitBreaker = {
      failures: 0,
      lastFailureTime: 0,
      state: 'CLOSED', // CLOSED, OPEN, HALF_OPEN
      maxFailures: 5,
      timeout: 60000 // 1 minute
    };
    
    // Cache for encryption key
    this.encryptionKey = null;
    this.keyCache = new Map();
    this.cacheTimeout = 300000; // 5 minutes
  }

  /**
   * Get encryption key from AWS Secrets Manager with caching
   */
  async getEncryptionKey() {
    if (this.encryptionKey) {
      return this.encryptionKey;
    }

    try {
      const secretArn = process.env.API_KEY_ENCRYPTION_SECRET_ARN;
      if (!secretArn) {
        throw new Error('API_KEY_ENCRYPTION_SECRET_ARN environment variable not set');
      }

      const command = new GetSecretValueCommand({ SecretId: secretArn });
      const result = await this.secretsManager.send(command);
      const secret = JSON.parse(result.SecretString);
      
      this.encryptionKey = secret.encryptionKey;
      return this.encryptionKey;
      
    } catch (error) {
      console.error('Failed to get encryption key:', error.message);
      throw new Error('Encryption key not available');
    }
  }

  /**
   * Check circuit breaker state
   */
  checkCircuitBreaker() {
    const now = Date.now();
    
    if (this.circuitBreaker.state === 'OPEN') {
      if (now - this.circuitBreaker.lastFailureTime > this.circuitBreaker.timeout) {
        this.circuitBreaker.state = 'HALF_OPEN';
        console.log('Circuit breaker entering HALF_OPEN state');
      } else {
        throw new Error('Circuit breaker is OPEN - API key service temporarily unavailable');
      }
    }
  }

  /**
   * Record success for circuit breaker
   */
  recordSuccess() {
    if (this.circuitBreaker.state === 'HALF_OPEN') {
      this.circuitBreaker.state = 'CLOSED';
      this.circuitBreaker.failures = 0;
      console.log('Circuit breaker reset to CLOSED state');
    }
  }

  /**
   * Record failure for circuit breaker
   */
  recordFailure(error) {
    this.circuitBreaker.failures++;
    this.circuitBreaker.lastFailureTime = Date.now();
    
    if (this.circuitBreaker.failures >= this.circuitBreaker.maxFailures) {
      this.circuitBreaker.state = 'OPEN';
      console.error(`Circuit breaker OPENED after ${this.circuitBreaker.failures} failures:`, error.message);
    }
  }

  /**
   * Encrypt API key data
   */
  encryptApiKey(data, userSalt) {
    try {
      const algorithm = 'aes-256-gcm';
      const key = crypto.scryptSync(this.encryptionKey, userSalt, 32);
      const iv = crypto.randomBytes(16);
      
      const cipher = crypto.createCipher(algorithm, key);
      cipher.setAAD(Buffer.from(userSalt));
      
      let encrypted = cipher.update(JSON.stringify(data), 'utf8', 'hex');
      encrypted += cipher.final('hex');
      
      const authTag = cipher.getAuthTag();
      
      return {
        encrypted,
        iv: iv.toString('hex'),
        authTag: authTag.toString('hex'),
        algorithm
      };
    } catch (error) {
      console.error('Encryption error:', error);
      throw new Error('Failed to encrypt API key data');
    }
  }

  /**
   * Decrypt API key data
   */
  decryptApiKey(encryptedData, userSalt) {
    try {
      const { encrypted /*, iv */, authTag, algorithm } = encryptedData;
      const key = crypto.scryptSync(this.encryptionKey, userSalt, 32);
      
      const decipher = crypto.createDecipher(algorithm, key);
      decipher.setAAD(Buffer.from(userSalt));
      decipher.setAuthTag(Buffer.from(authTag, 'hex'));
      
      let decrypted = decipher.update(encrypted, 'hex', 'utf8');
      decrypted += decipher.final('utf8');
      
      return JSON.parse(decrypted);
    } catch (error) {
      console.error('Decryption error:', error);
      throw new Error('Failed to decrypt API key data');
    }
  }

  /**
   * Store encrypted API key for user with comprehensive error handling
   */
  async storeApiKey(userId, provider, apiKeyData) {
    this.checkCircuitBreaker();
    
    try {
      await this.getEncryptionKey();
      
      // Generate user-specific salt
      const userSalt = crypto.randomBytes(32).toString('hex');
      
      // Encrypt the API key data
      const encryptedData = this.encryptApiKey(apiKeyData, userSalt);
      
      // Store in database
      const result = await query(`
        INSERT INTO user_api_keys (user_id, provider, encrypted_data, user_salt, created_at, updated_at)
        VALUES ($1, $2, $3, $4, NOW(), NOW())
        ON CONFLICT (user_id, provider) 
        DO UPDATE SET 
          encrypted_data = EXCLUDED.encrypted_data,
          user_salt = EXCLUDED.user_salt,
          updated_at = NOW()
        RETURNING id
      `, [userId, provider, JSON.stringify(encryptedData), userSalt]);
      
      // Clear cache for this user/provider
      const cacheKey = `${userId}:${provider}`;
      this.keyCache.delete(cacheKey);
      
      this.recordSuccess();
      
      return {
        success: true,
        id: result.rows[0].id,
        provider: provider,
        encrypted: true
      };
      
    } catch (error) {
      this.recordFailure(error);
      console.error('API key storage error:', error);
      throw new Error(`Failed to store API key for ${provider}: ${error.message}`);
    }
  }

  /**
   * Retrieve and decrypt API key for user with caching and error handling
   */
  async getDecryptedApiKey(userId, provider) {
    this.checkCircuitBreaker();
    
    const cacheKey = `${userId}:${provider}`;
    const cached = this.keyCache.get(cacheKey);
    
    // Return cached result if still valid
    if (cached && Date.now() - cached.timestamp < this.cacheTimeout) {
      return cached.data;
    }
    
    try {
      await this.getEncryptionKey();
      
      // Get encrypted data from database
      const result = await query(`
        SELECT encrypted_data, user_salt, updated_at
        FROM user_api_keys 
        WHERE user_id = $1 AND provider = $2
      `, [userId, provider]);
      
      if (result.rows.length === 0) {
        this.recordSuccess();
        return null; // No API key found
      }
      
      const { encrypted_data, user_salt } = result.rows[0];
      const encryptedData = JSON.parse(encrypted_data);
      
      // Decrypt the data
      const decryptedData = this.decryptApiKey(encryptedData, user_salt);
      
      // Cache the result
      this.keyCache.set(cacheKey, {
        data: decryptedData,
        timestamp: Date.now()
      });
      
      this.recordSuccess();
      
      return decryptedData;
      
    } catch (error) {
      this.recordFailure(error);
      console.error('API key retrieval error:', error);
      
      // Return null instead of throwing for graceful degradation
      if (error.message.includes('Circuit breaker')) {
        throw error; // Re-throw circuit breaker errors
      }
      
      console.warn(`API key retrieval failed for user ${userId}, provider ${provider}:`, error.message);
      return null;
    }
  }

  /**
   * Validate API key configuration
   */
  async validateApiKey(userId, provider, testConnection = false) {
    try {
      const apiKeyData = await this.getDecryptedApiKey(userId, provider);
      
      if (!apiKeyData) {
        return {
          valid: false,
          error: 'API key not configured',
          provider: provider
        };
      }
      
      // Basic validation
      const requiredFields = this.getRequiredFields(provider);
      const missingFields = requiredFields.filter(field => !apiKeyData[field]);
      
      if (missingFields.length > 0) {
        return {
          valid: false,
          error: `Missing required fields: ${missingFields.join(', ')}`,
          provider: provider,
          missingFields
        };
      }
      
      // Optional connection test
      if (testConnection && provider === 'alpaca') {
        try {
          const AlpacaService = require('./alpacaService');
          const alpacaService = new AlpacaService(
            apiKeyData.apiKey,
            apiKeyData.apiSecret,
            apiKeyData.isSandbox
          );
          
          const testResult = await alpacaService.validateCredentials();
          return {
            valid: testResult.valid,
            error: testResult.error,
            provider: provider,
            environment: testResult.environment,
            connectionTest: true
          };
        } catch (testError) {
          return {
            valid: false,
            error: `Connection test failed: ${testError.message}`,
            provider: provider,
            connectionTest: true
          };
        }
      }
      
      return {
        valid: true,
        provider: provider,
        environment: apiKeyData.isSandbox ? 'sandbox' : 'live'
      };
      
    } catch (error) {
      console.error('API key validation error:', error);
      return {
        valid: false,
        error: error.message,
        provider: provider
      };
    }
  }

  /**
   * Get required fields for a provider
   */
  getRequiredFields(provider) {
    const fieldMap = {
      'alpaca': ['apiKey', 'apiSecret'],
      'polygon': ['apiKey'],
      'finnhub': ['apiKey'],
      'alpha_vantage': ['apiKey']
    };
    
    return fieldMap[provider] || ['apiKey'];
  }

  /**
   * Delete API key for user
   */
  async deleteApiKey(userId, provider) {
    this.checkCircuitBreaker();
    
    try {
      const result = await query(`
        DELETE FROM user_api_keys 
        WHERE user_id = $1 AND provider = $2
        RETURNING id
      `, [userId, provider]);
      
      // Clear cache
      const cacheKey = `${userId}:${provider}`;
      this.keyCache.delete(cacheKey);
      
      this.recordSuccess();
      
      return {
        success: true,
        deleted: result.rowCount > 0,
        provider: provider
      };
      
    } catch (error) {
      this.recordFailure(error);
      console.error('API key deletion error:', error);
      throw new Error(`Failed to delete API key for ${provider}: ${error.message}`);
    }
  }

  /**
   * List configured providers for user
   */
  async listProviders(userId) {
    this.checkCircuitBreaker();
    
    try {
      const result = await query(`
        SELECT provider, updated_at, created_at
        FROM user_api_keys 
        WHERE user_id = $1
        ORDER BY provider
      `, [userId]);
      
      this.recordSuccess();
      
      return result.rows.map(row => ({
        provider: row.provider,
        configured: true,
        lastUpdated: row.updated_at,
        createdAt: row.created_at
      }));
      
    } catch (error) {
      this.recordFailure(error);
      console.error('Provider listing error:', error);
      return []; // Return empty array for graceful degradation
    }
  }

  /**
   * Get service health status
   */
  getHealthStatus() {
    return {
      circuitBreaker: {
        state: this.circuitBreaker.state,
        failures: this.circuitBreaker.failures,
        lastFailureTime: this.circuitBreaker.lastFailureTime
      },
      cache: {
        size: this.keyCache.size,
        timeout: this.cacheTimeout
      },
      encryptionAvailable: !!this.encryptionKey
    };
  }
}

// Export singleton instance
const apiKeyServiceResilient = new ApiKeyServiceResilient();

module.exports = {
  storeApiKey: (userId, provider, apiKeyData) => apiKeyServiceResilient.storeApiKey(userId, provider, apiKeyData),
  getDecryptedApiKey: (userId, provider) => apiKeyServiceResilient.getDecryptedApiKey(userId, provider),
  validateApiKey: (userId, provider, testConnection) => apiKeyServiceResilient.validateApiKey(userId, provider, testConnection),
  deleteApiKey: (userId, provider) => apiKeyServiceResilient.deleteApiKey(userId, provider),
  listProviders: (userId) => apiKeyServiceResilient.listProviders(userId),
  getHealthStatus: () => apiKeyServiceResilient.getHealthStatus()
};