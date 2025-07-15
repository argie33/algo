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
        saltLength: userSalt.length
      });

      const key = crypto.scryptSync(this.secretKey, userSalt, 32);
      const iv = crypto.randomBytes(12); // GCM typically uses 12-byte IV
      const cipher = crypto.createCipher('aes-256-cbc', key);
      
      let encrypted = cipher.update(apiKey, 'utf8', 'hex');
      encrypted += cipher.final('hex');
      
      const result = {
        encrypted: encrypted,
        iv: iv.toString('hex'),
        authTag: null  // Not used in CBC mode
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
        saltLength: userSalt.length
      });

      const key = crypto.scryptSync(this.secretKey, userSalt, 32);
      const iv = Buffer.from(encryptedData.iv, 'hex');
      const decipher = crypto.createDecipher('aes-256-cbc', key);
      
      let decrypted = decipher.update(encryptedData.encrypted, 'hex', 'utf8');
      decrypted += decipher.final('utf8');
      
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
}

module.exports = new ApiKeyService();