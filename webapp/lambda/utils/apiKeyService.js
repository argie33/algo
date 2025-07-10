const crypto = require('crypto');
const { query } = require('./database');

const ALGORITHM = 'aes-256-gcm';

class ApiKeyService {
  constructor() {
    this.secretKey = process.env.API_KEY_ENCRYPTION_SECRET;
    if (!this.secretKey) {
      console.warn('API_KEY_ENCRYPTION_SECRET environment variable not set. API key encryption features will be disabled.');
      this.isEnabled = false;
      return;
    }
    this.isEnabled = true;
    // Validate key has sufficient entropy (minimum 32 bytes when base64 decoded)
    try {
      const keyBuffer = Buffer.from(this.secretKey, 'base64');
      if (keyBuffer.length < 32) {
        throw new Error('API_KEY_ENCRYPTION_SECRET must be at least 256 bits (32 bytes)');
      }
    } catch (error) {
      throw new Error('API_KEY_ENCRYPTION_SECRET must be a valid base64 encoded key');
    }
  }

  // Decrypt API key using stored encryption data
  decryptApiKey(encryptedData, userSalt) {
    if (!this.isEnabled) {
      throw new Error('API key encryption service is not available');
    }
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
    if (!this.isEnabled) {
      console.warn('API key service disabled - returning null');
      return null;
    }
    try {
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
        return null;
      }

      const keyData = result.rows[0];
      
      // Decrypt API key
      const apiKey = this.decryptApiKey({
        encrypted: keyData.encrypted_api_key,
        iv: keyData.key_iv,
        authTag: keyData.key_auth_tag
      }, keyData.user_salt);

      // Decrypt API secret if it exists
      let apiSecret = null;
      if (keyData.encrypted_api_secret) {
        apiSecret = this.decryptApiKey({
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