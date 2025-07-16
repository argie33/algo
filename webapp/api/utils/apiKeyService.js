const crypto = require('crypto');
const { query } = require('./database');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const logger = require('./logger');

const ALGORITHM = 'aes-256-gcm';

// Configure AWS SDK for Secrets Manager
const secretsManager = new SecretsManagerClient({
  region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
});

// Cache for loaded secrets
let encryptionSecretCache = null;

/**
 * Load encryption secret from AWS Secrets Manager
 */
async function loadEncryptionSecret() {
  if (encryptionSecretCache) {
    return encryptionSecretCache;
  }

  try {
    const secretArn = process.env.API_KEY_ENCRYPTION_SECRET_ARN;
    if (!secretArn) {
      console.error('❌ API_KEY_ENCRYPTION_SECRET_ARN environment variable not set');
      // Fallback to environment variable for development
      const fallbackSecret = process.env.API_KEY_ENCRYPTION_SECRET;
      if (fallbackSecret) {
        console.log('🔧 Using fallback encryption secret from environment');
        encryptionSecretCache = fallbackSecret;
        return fallbackSecret;
      }
      return null;
    }

    console.log('🔐 Loading API key encryption secret from AWS Secrets Manager...');
    const command = new GetSecretValueCommand({ SecretId: secretArn });
    const response = await secretsManager.send(command);
    
    if (!response.SecretString) {
      throw new Error('Secret value is empty');
    }

    const secretData = JSON.parse(response.SecretString);
    const encryptionKey = secretData.API_KEY_ENCRYPTION_SECRET;
    
    if (!encryptionKey) {
      throw new Error('API_KEY_ENCRYPTION_SECRET not found in secret data');
    }

    encryptionSecretCache = encryptionKey;
    console.log('✅ API key encryption secret loaded successfully');
    return encryptionKey;
    
  } catch (error) {
    console.error('❌ Failed to load encryption secret:', error);
    return null;
  }
}

class ApiKeyService {
  constructor() {
    this.secretKey = null;
    this.isEnabled = false;
    this.initPromise = this.initialize();
  }

  async initialize() {
    const initStartTime = Date.now();
    
    try {
      logger.info('🔐 Initializing API key encryption service', {
        environment: process.env.NODE_ENV,
        hasEnvSecret: !!process.env.API_KEY_ENCRYPTION_SECRET,
        hasSecretsManagerArn: !!process.env.API_KEY_ENCRYPTION_SECRET_ARN
      });

      // Try to load from environment first (for local dev)
      this.secretKey = process.env.API_KEY_ENCRYPTION_SECRET;
      
      // If not found, load from Secrets Manager
      if (!this.secretKey) {
        logger.info('📡 Loading encryption secret from AWS Secrets Manager');
        this.secretKey = await loadEncryptionSecret();
      }

      if (!this.secretKey) {
        // Fallback: Generate a temporary key for development (NOT for production)
        if (process.env.NODE_ENV !== 'production') {
          logger.warn('⚠️ No encryption secret configured - generating temporary development key', {
            environment: process.env.NODE_ENV,
            securityWarning: 'This is NOT secure for production use!'
          });
          this.secretKey = crypto.randomBytes(32).toString('hex');
          logger.info('🔐 Temporary encryption key generated for development');
        } else {
          logger.error('❌ CRITICAL: No encryption secret available in production', {
            environment: process.env.NODE_ENV,
            hasEnvSecret: !!process.env.API_KEY_ENCRYPTION_SECRET,
            hasSecretsManagerArn: !!process.env.API_KEY_ENCRYPTION_SECRET_ARN,
            initializationTime: Date.now() - initStartTime
          });
          this.isEnabled = false;
          return;
        }
      }

      this.isEnabled = true;
      
      // Validate key has sufficient entropy
      if (this.secretKey.length < 32) {
        logger.warn('⚠️ Encryption key should be at least 32 characters for security', {
          currentLength: this.secretKey.length,
          recommendedLength: 32
        });
      }
      
      logger.info('✅ API key encryption service initialized and enabled', {
        initializationTime: Date.now() - initStartTime,
        keyLength: this.secretKey.length,
        environment: process.env.NODE_ENV
      });
      
    } catch (error) {
      logger.error('❌ Failed to initialize API key service', {
        error: error.message,
        errorStack: error.stack,
        initializationTime: Date.now() - initStartTime,
        environment: process.env.NODE_ENV
      });
      this.isEnabled = false;
    }
  }

  async ensureInitialized() {
    await this.initPromise;
    if (!this.isEnabled) {
      throw new Error('API key encryption service is not available');
    }
  }

  // Encrypt API key for storage
  async encryptApiKey(apiKey, userSalt, userId = null, provider = null) {
    const operationStartTime = Date.now();
    
    try {
      await this.ensureInitialized();
      
      // Validate inputs
      if (!apiKey || typeof apiKey !== 'string') {
        throw new Error('Invalid API key provided for encryption');
      }
      
      if (!userSalt || typeof userSalt !== 'string') {
        throw new Error('Invalid user salt provided for encryption');
      }
      
      if (apiKey.length < 8) {
        throw new Error('API key is too short for security');
      }
      
      logger.info('🔐 Starting API key encryption', {
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
        provider: provider || 'unknown',
        apiKeyLength: apiKey.length,
        saltLength: userSalt.length,
        algorithm: ALGORITHM
      });

      // Generate key from secret + salt
      logger.debug('🔑 Generating encryption key', {
        secretKeyLength: this.secretKey.length,
        saltLength: userSalt.length
      });
      
      const key = crypto.scryptSync(this.secretKey, userSalt, 32);
      
      logger.debug('🔑 Key generated, preparing cipher', {
        keyLength: key.length,
        algorithm: ALGORITHM
      });
      
      const iv = crypto.randomBytes(12); // GCM typically uses 12-byte IV
      const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
      
      logger.debug('🔐 Starting encryption process');
      
      let encrypted = cipher.update(apiKey, 'utf8', 'hex');
      
      logger.debug('🔐 Encryption update complete, finalizing');
      
      encrypted += cipher.final('hex');
      
      // Get auth tag for GCM mode
      const authTag = cipher.getAuthTag();
      
      logger.debug('🔐 Encryption finalized', {
        encryptedLength: encrypted.length,
        authTagLength: authTag.length
      });
      
      const result = {
        encrypted: encrypted,
        iv: iv.toString('hex'),
        authTag: authTag.toString('hex')
      };
      
      logger.info('✅ API key encrypted successfully', {
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
        provider: provider || 'unknown',
        encryptionTime: Date.now() - operationStartTime,
        encryptedLength: encrypted.length,
        ivLength: result.iv.length
      });
      
      return result;
      
    } catch (error) {
      logger.error('❌ API key encryption failed', {
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
        provider: provider || 'unknown',
        error: error.message,
        errorStack: error.stack,
        encryptionTime: Date.now() - operationStartTime,
        apiKeyLength: apiKey ? apiKey.length : 0,
        saltLength: userSalt ? userSalt.length : 0
      });
      
      throw new Error(`Failed to encrypt API key: ${error.message}`);
    }
  }

  // Decrypt API key using stored encryption data
  async decryptApiKey(encryptedData, userSalt, userId = null, provider = null) {
    const operationStartTime = Date.now();
    
    try {
      await this.ensureInitialized();
      
      // Validate inputs
      if (!encryptedData || typeof encryptedData !== 'object') {
        throw new Error('Invalid encrypted data provided for decryption');
      }
      
      if (!encryptedData.encrypted || typeof encryptedData.encrypted !== 'string') {
        throw new Error('Invalid encrypted value in encrypted data');
      }
      
      if (!encryptedData.iv || typeof encryptedData.iv !== 'string') {
        throw new Error('Invalid IV in encrypted data');
      }
      
      if (!userSalt || typeof userSalt !== 'string') {
        throw new Error('Invalid user salt provided for decryption');
      }
      
      logger.info('🔓 Starting API key decryption', {
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
        provider: provider || 'unknown',
        encryptedLength: encryptedData.encrypted.length,
        ivLength: encryptedData.iv.length,
        saltLength: userSalt.length,
        hasAuthTag: !!encryptedData.authTag,
        algorithm: ALGORITHM
      });

      // Generate key from secret + salt
      logger.debug('🔑 Generating decryption key', {
        secretKeyLength: this.secretKey.length,
        saltLength: userSalt.length
      });
      
      const key = crypto.scryptSync(this.secretKey, userSalt, 32);
      
      logger.debug('🔑 Key generated, preparing decipher', {
        keyLength: key.length,
        algorithm: ALGORITHM
      });
      
      const iv = Buffer.from(encryptedData.iv, 'hex');
      const decipher = crypto.createDecipheriv(ALGORITHM, key, iv);
      
      // Handle auth tag for GCM mode
      if (encryptedData.authTag) {
        logger.debug('🔐 Setting auth tag for GCM mode', {
          authTagLength: encryptedData.authTag.length
        });
        decipher.setAuthTag(Buffer.from(encryptedData.authTag, 'hex'));
      }
      
      logger.debug('🔓 Starting decryption process');
      
      let decrypted = decipher.update(encryptedData.encrypted, 'hex', 'utf8');
      
      logger.debug('🔓 Decryption update complete, finalizing');
      
      decrypted += decipher.final('utf8');
      
      logger.debug('🔓 Decryption finalized', {
        decryptedLength: decrypted.length,
        firstChars: decrypted.substring(0, 4) + '...'
      });
      
      // Validate decrypted result
      if (!decrypted || decrypted.length < 8) {
        throw new Error('Decrypted API key is invalid or too short');
      }
      
      logger.info('✅ API key decrypted successfully', {
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
        provider: provider || 'unknown',
        decryptionTime: Date.now() - operationStartTime,
        decryptedLength: decrypted.length
      });
      
      return decrypted;
      
    } catch (error) {
      logger.error('❌ API key decryption failed', {
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
        provider: provider || 'unknown',
        error: error.message,
        errorStack: error.stack,
        decryptionTime: Date.now() - operationStartTime,
        encryptedDataValid: !!(encryptedData && encryptedData.encrypted),
        ivValid: !!(encryptedData && encryptedData.iv),
        saltLength: userSalt ? userSalt.length : 0
      });
      
      // Security: Only log error message, not full error object or decrypted content
      throw new Error(`Failed to decrypt API key: ${error.message}`);
    }
  }

  // Get decrypted API credentials for a user and provider
  async getDecryptedApiKey(userId, provider) {
    const operationStartTime = Date.now();
    
    try {
      await this.ensureInitialized();
      
      // Validate inputs
      if (!userId || typeof userId !== 'string') {
        throw new Error('Invalid user ID provided');
      }
      
      if (!provider || typeof provider !== 'string') {
        throw new Error('Invalid provider provided');
      }
      
      logger.info('🔍 Querying for API key credentials', {
        userId: userId.substring(0, 8) + '...',
        provider: provider
      });

      const result = await query(`
        SELECT 
          id,
          provider,
          encrypted_api_key,
          key_iv,
          key_auth_tag,
          encrypted_api_secret,
          secret_iv,
          secret_auth_tag,
          user_salt,
          is_sandbox,
          is_active
        FROM user_api_keys 
        WHERE user_id = $1 AND provider = $2 AND is_active = true
        ORDER BY created_at DESC
        LIMIT 1
      `, [userId, provider]);

      if (result.rows.length === 0) {
        logger.warn('🔍 No API key found for requested user/provider', {
          userId: userId.substring(0, 8) + '...',
          provider: provider,
          queryTime: Date.now() - operationStartTime
        });
        return null;
      }

      const keyData = result.rows[0];
      
      logger.info('📋 API key found, starting decryption', {
        userId: userId.substring(0, 8) + '...',
        provider: provider,
        keyId: keyData.id,
        hasSecret: !!keyData.encrypted_api_secret,
        isSandbox: keyData.is_sandbox
      });
      
      // Decrypt API key
      const apiKey = await this.decryptApiKey({
        encrypted: keyData.encrypted_api_key,
        iv: keyData.key_iv,
        authTag: keyData.key_auth_tag
      }, keyData.user_salt, userId, provider);

      // Decrypt API secret if it exists
      let apiSecret = null;
      if (keyData.encrypted_api_secret) {
        apiSecret = await this.decryptApiKey({
          encrypted: keyData.encrypted_api_secret,
          iv: keyData.secret_iv,
          authTag: keyData.secret_auth_tag
        }, keyData.user_salt, userId, provider);
      }

      // Update last_used timestamp
      await query(`
        UPDATE user_api_keys 
        SET last_used = NOW() 
        WHERE id = $1
      `, [keyData.id]);

      logger.info('✅ API key retrieved and decrypted successfully', {
        userId: userId.substring(0, 8) + '...',
        provider: provider,
        keyId: keyData.id,
        hasSecret: !!apiSecret,
        isSandbox: keyData.is_sandbox,
        totalTime: Date.now() - operationStartTime
      });

      return {
        id: keyData.id,
        provider: keyData.provider,
        apiKey,
        apiSecret,
        isSandbox: keyData.is_sandbox,
        isActive: keyData.is_active
      };
      
    } catch (error) {
      logger.error('❌ Failed to retrieve API key', {
        userId: userId ? userId.substring(0, 8) + '...' : 'unknown',
        provider: provider || 'unknown',
        error: error.message,
        errorStack: error.stack,
        totalTime: Date.now() - operationStartTime
      });
      
      // Security: Only log error message, not full error object
      throw new Error(`Failed to retrieve API key: ${error.message}`);
    }
  }

  // Get all active API keys for a user (without decryption)
  async getUserApiKeys(userId) {
    try {
      const result = await query(`
        SELECT 
          id,
          provider,
          description,
          is_sandbox as "isSandbox",
          is_active as "isActive",
          created_at as "createdAt",
          last_used as "lastUsed"
        FROM user_api_keys 
        WHERE user_id = $1 AND is_active = true
        ORDER BY created_at DESC
      `, [userId]);

      return result.rows;
    } catch (error) {
      console.error('Error getting user API keys:', error.message); // Security: Only log error message
      throw new Error('Failed to retrieve user API keys');
    }
  }

  // Check if user has active API key for provider
  async hasActiveApiKey(userId, provider) {
    try {
      const result = await query(`
        SELECT COUNT(*) as count
        FROM user_api_keys 
        WHERE user_id = $1 AND provider = $2 AND is_active = true
      `, [userId, provider]);

      return parseInt(result.rows[0].count) > 0;
    } catch (error) {
      console.error('Error checking API key existence:', error.message); // Security: Only log error message
      return false;
    }
  }

  // Get active providers for user
  async getActiveProviders(userId) {
    try {
      const result = await query(`
        SELECT DISTINCT provider
        FROM user_api_keys 
        WHERE user_id = $1 AND is_active = true
      `, [userId]);

      return result.rows.map(row => row.provider);
    } catch (error) {
      console.error('Error getting active providers:', error.message); // Security: Only log error message
      return [];
    }
  }

  /**
   * Validate API key format for different providers
   * @param {string} provider - API provider name
   * @param {string} apiKey - API key to validate
   * @param {string} apiSecret - API secret to validate (optional)
   * @returns {Object} Validation result with valid flag and error message
   */
  validateApiKeyFormat(provider, apiKey, apiSecret = null) {
    if (!provider || !apiKey) {
      return {
        valid: false,
        error: 'Provider and API key are required',
        details: { provider, apiKey: apiKey ? '[PROVIDED]' : '[MISSING]' }
      };
    }

    const providerLower = provider.toLowerCase().trim();
    
    switch (providerLower) {
      case 'alpaca':
        // Alpaca API key validation
        if (apiKey.length < 20 || apiKey.length > 50) {
          return {
            valid: false,
            error: 'Alpaca API key must be 20-50 characters',
            details: { provider, length: apiKey.length }
          };
        }
        
        if (!/^[A-Za-z0-9]+$/.test(apiKey)) {
          return {
            valid: false,
            error: 'Alpaca API key must contain only alphanumeric characters',
            details: { provider, pattern: 'alphanumeric' }
          };
        }
        
        // Alpaca API secret validation (if provided)
        if (apiSecret) {
          if (apiSecret.length < 20 || apiSecret.length > 80) {
            return {
              valid: false,
              error: 'Alpaca API secret must be 20-80 characters',
              details: { provider, secretLength: apiSecret.length }
            };
          }
          
          if (!/^[A-Za-z0-9/+=]+$/.test(apiSecret)) {
            return {
              valid: false,
              error: 'Alpaca API secret contains invalid characters',
              details: { provider, allowedChars: 'A-Z, a-z, 0-9, /, +, =' }
            };
          }
        }
        break;
        
      case 'tdameritrade':
        // TD Ameritrade API key validation (more flexible length)
        if (apiKey.length < 20 || apiKey.length > 40) {
          return {
            valid: false,
            error: 'TD Ameritrade API key must be 20-40 characters',
            details: { provider, length: apiKey.length, expected: '20-40' }
          };
        }
        
        if (!/^[A-Za-z0-9]+$/.test(apiKey)) {
          return {
            valid: false,
            error: 'TD Ameritrade API key must contain only alphanumeric characters',
            details: { provider, pattern: 'alphanumeric' }
          };
        }
        break;
        
      case 'interactivebrokers':
        // Interactive Brokers API key validation (more lenient)
        if (apiKey.length < 8 || apiKey.length > 100) {
          return {
            valid: false,
            error: 'Interactive Brokers API key must be 8-100 characters',
            details: { provider, length: apiKey.length }
          };
        }
        break;
        
      default:
        // Generic validation for unknown providers
        if (apiKey.length < 8 || apiKey.length > 200) {
          return {
            valid: false,
            error: 'API key must be 8-200 characters',
            details: { provider, length: apiKey.length }
          };
        }
        
        // Reject obvious placeholder values
        const placeholders = ['password', '123456', 'test', 'apikey', 'key'];
        if (placeholders.includes(apiKey.toLowerCase())) {
          return {
            valid: false,
            error: 'API key appears to be a placeholder value',
            details: { provider, placeholder: apiKey.toLowerCase() }
          };
        }
        break;
    }

    return {
      valid: true,
      error: null,
      details: { provider, keyLength: apiKey.length }
    };
  }
}

module.exports = new ApiKeyService();