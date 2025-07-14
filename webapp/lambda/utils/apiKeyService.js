const crypto = require('crypto');
const { query } = require('./database');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

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
    try {
      // Try to load from environment first (for local dev)
      this.secretKey = process.env.API_KEY_ENCRYPTION_SECRET;
      
      // If not found, load from Secrets Manager
      if (!this.secretKey) {
        this.secretKey = await loadEncryptionSecret();
      }

      if (!this.secretKey) {
        console.error('❌ CRITICAL: No encryption secret available');
        console.error('⚠️  API Key service will be disabled - encryption/decryption not available');
        this.isEnabled = false;
        return;
      }

      this.isEnabled = true;
      
      // Validate key has sufficient entropy
      if (this.secretKey.length < 32) {
        console.warn('⚠️  Encryption key should be at least 32 characters for security');
      }
      
      console.log('✅ API key encryption service initialized and enabled');
    } catch (error) {
      console.error('❌ Failed to initialize API key service:', error);
      this.isEnabled = false;
    }
  }

  async ensureInitialized() {
    await this.initPromise;
    if (!this.isEnabled) {
      throw new Error('API key encryption service is not available');
    }
  }

  // Decrypt API key using stored encryption data
  async decryptApiKey(encryptedData, userSalt) {
    await this.ensureInitialized();
    try {
      const key = crypto.scryptSync(this.secretKey, userSalt, 32);
      const iv = Buffer.from(encryptedData.iv, 'hex');
      const decipher = crypto.createDecipherGCM(ALGORITHM, key, iv);
      decipher.setAAD(Buffer.from(userSalt));
      decipher.setAuthTag(Buffer.from(encryptedData.authTag, 'hex'));
      
      let decrypted = decipher.update(encryptedData.encrypted, 'hex', 'utf8');
      decrypted += decipher.final('utf8');
      
      return decrypted;
    } catch (error) {
      console.error('Error decrypting API key:', error);
      throw new Error('Failed to decrypt API key');
    }
  }

  // Get decrypted API credentials for a user and provider
  async getDecryptedApiKey(userId, provider) {
    await this.ensureInitialized();
    try {
      console.log(`🔍 [API KEY SERVICE] Querying for userId=${userId}, provider=${provider}`);
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

      console.log(`🔍 [API KEY SERVICE] Query returned ${result.rows.length} rows`);
      
      if (result.rows.length === 0) {
        console.log(`🔍 [API KEY SERVICE] No API key found for user ${userId}, provider ${provider}`);
        return null;
      }

      const keyData = result.rows[0];
      
      // Decrypt API key
      const apiKey = await this.decryptApiKey({
        encrypted: keyData.encrypted_api_key,
        iv: keyData.key_iv,
        authTag: keyData.key_auth_tag
      }, keyData.user_salt);

      // Decrypt API secret if it exists
      let apiSecret = null;
      if (keyData.encrypted_api_secret) {
        apiSecret = await this.decryptApiKey({
          encrypted: keyData.encrypted_api_secret,
          iv: keyData.secret_iv,
          authTag: keyData.secret_auth_tag
        }, keyData.user_salt);
      }

      // Update last_used timestamp
      await query(`
        UPDATE user_api_keys 
        SET last_used = NOW() 
        WHERE id = $1
      `, [keyData.id]);

      return {
        id: keyData.id,
        provider: keyData.provider,
        apiKey,
        apiSecret,
        isSandbox: keyData.is_sandbox,
        isActive: keyData.is_active
      };
    } catch (error) {
      console.error('Error getting decrypted API key:', error);
      throw new Error('Failed to retrieve API key');
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
      console.error('Error getting user API keys:', error);
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
      console.error('Error checking API key existence:', error);
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
      console.error('Error getting active providers:', error);
      return [];
    }
  }
}

module.exports = new ApiKeyService();