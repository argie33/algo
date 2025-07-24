/**
 * Unified API Key Database Service
 * Database integration layer for API key management
 * Provides fallback and migration support for existing database keys
 */

const databaseManager = require('./databaseConnectionManager');

class UnifiedApiKeyDatabaseService {
  constructor() {
    this.cache = new Map();
    this.cacheTTL = 2 * 60 * 1000; // 2 minutes (shorter than Parameter Store cache)
  }

  /**
   * Get API key from database (for migration and fallback)
   */
  async getApiKeyFromDatabase(userId, provider = 'alpaca') {
    try {
      const cacheKey = `db:${userId}:${provider}`;
      const cached = this.cache.get(cacheKey);
      
      if (cached && Date.now() - cached.timestamp < this.cacheTTL) {
        return cached.data;
      }

      const query = `
        SELECT 
          id,
          user_id,
          provider,
          broker_name,
          api_key_encrypted,
          secret_encrypted,
          encrypted_api_key,
          encrypted_api_secret,
          masked_api_key,
          is_sandbox,
          is_active,
          validation_status,
          created_at,
          updated_at,
          last_used
        FROM user_api_keys 
        WHERE user_id = $1 
          AND (provider = $2 OR broker_name = $2)
          AND is_active = true
        ORDER BY updated_at DESC
        LIMIT 1
      `;

      const result = await databaseManager.query(query, [userId, provider]);
      
      if (result.rows && result.rows.length > 0) {
        const apiKeyData = this.normalizeApiKeyData(result.rows[0]);
        
        // Cache the result
        this.cache.set(cacheKey, {
          data: apiKeyData,
          timestamp: Date.now()
        });
        
        console.log(`✅ Retrieved API key from database for user ${userId}`);
        return apiKeyData;
      }
      
      return null;
      
    } catch (error) {
      console.error(`❌ Database API key retrieval failed for user ${userId}:`, error);
      return null;
    }
  }

  /**
   * Save API key to database (for backup and migration tracking)
   */
  async saveApiKeyToDatabase(userId, provider, apiKey, secretKey, isSandbox = true) {
    try {
      // Note: This is for migration tracking only
      // Primary storage is AWS Parameter Store
      
      const maskedApiKey = this.maskApiKey(apiKey);
      
      const query = `
        INSERT INTO user_api_keys (
          user_id,
          provider,
          api_key_encrypted,
          secret_encrypted,
          masked_api_key,
          is_sandbox,
          is_active,
          validation_status,
          created_at,
          updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), NOW())
        ON CONFLICT (user_id, provider) 
        DO UPDATE SET
          api_key_encrypted = EXCLUDED.api_key_encrypted,
          secret_encrypted = EXCLUDED.secret_encrypted,
          masked_api_key = EXCLUDED.masked_api_key,
          is_sandbox = EXCLUDED.is_sandbox,
          is_active = EXCLUDED.is_active,
          validation_status = EXCLUDED.validation_status,
          updated_at = NOW()
        RETURNING id
      `;

      // Store hashed versions for tracking (not the actual keys)
      const hashedApiKey = `MIGRATED_TO_SSM_${Date.now()}`;
      const hashedSecret = `MIGRATED_TO_SSM_${Date.now()}`;

      const result = await databaseManager.query(query, [
        userId,
        provider,
        hashedApiKey,
        hashedSecret,
        maskedApiKey,
        isSandbox,
        true,
        'migrated_to_ssm'
      ]);

      // Clear cache
      this.cache.delete(`db:${userId}:${provider}`);
      
      console.log(`✅ API key migration tracking saved to database for user ${userId}`);
      return result.rows[0]?.id;
      
    } catch (error) {
      console.error(`❌ Database API key save failed for user ${userId}:`, error);
      throw error;
    }
  }

  /**
   * Mark API key as migrated in database
   */
  async markApiKeyAsMigrated(userId, provider = 'alpaca') {
    try {
      const query = `
        UPDATE user_api_keys 
        SET 
          validation_status = 'migrated_to_ssm',
          api_key_encrypted = 'MIGRATED_TO_SSM',
          secret_encrypted = 'MIGRATED_TO_SSM',
          updated_at = NOW()
        WHERE user_id = $1 
          AND (provider = $2 OR broker_name = $2)
          AND is_active = true
      `;

      const result = await databaseManager.query(query, [userId, provider]);
      
      // Clear cache
      this.cache.delete(`db:${userId}:${provider}`);
      
      console.log(`✅ Marked API key as migrated for user ${userId}`);
      return result.rowCount > 0;
      
    } catch (error) {
      console.error(`❌ Failed to mark API key as migrated for user ${userId}:`, error);
      return false;
    }
  }

  /**
   * Remove API key from database
   */
  async removeApiKeyFromDatabase(userId, provider = 'alpaca') {
    try {
      const query = `
        UPDATE user_api_keys 
        SET 
          is_active = false,
          validation_status = 'deleted',
          updated_at = NOW()
        WHERE user_id = $1 
          AND (provider = $2 OR broker_name = $2)
          AND is_active = true
      `;

      const result = await databaseManager.query(query, [userId, provider]);
      
      // Clear cache
      this.cache.delete(`db:${userId}:${provider}`);
      
      console.log(`✅ Removed API key from database for user ${userId}`);
      return result.rowCount > 0;
      
    } catch (error) {
      console.error(`❌ Failed to remove API key from database for user ${userId}:`, error);
      return false;
    }
  }

  /**
   * Get all API keys for migration discovery
   */
  async getAllApiKeysForMigration() {
    try {
      const query = `
        SELECT 
          user_id,
          provider,
          broker_name,
          api_key_encrypted,
          secret_encrypted,
          encrypted_api_key,
          encrypted_api_secret,
          is_sandbox,
          created_at,
          validation_status
        FROM user_api_keys 
        WHERE is_active = true 
          AND validation_status != 'migrated_to_ssm'
          AND (provider = 'alpaca' OR broker_name = 'alpaca')
        ORDER BY user_id, created_at DESC
      `;

      const result = await databaseManager.query(query);
      
      if (result.rows && result.rows.length > 0) {
        console.log(`📊 Found ${result.rows.length} API keys for migration`);
        return result.rows.map(row => this.normalizeApiKeyData(row));
      }
      
      return [];
      
    } catch (error) {
      console.error('❌ Failed to get API keys for migration:', error);
      return [];
    }
  }

  /**
   * Normalize API key data from database
   */
  normalizeApiKeyData(dbRow) {
    return {
      id: dbRow.id,
      userId: dbRow.user_id,
      provider: dbRow.provider || dbRow.broker_name || 'alpaca',
      
      // Handle both old and new column names
      apiKey: dbRow.api_key_encrypted || dbRow.encrypted_api_key,
      secretKey: dbRow.secret_encrypted || dbRow.encrypted_api_secret,
      
      maskedApiKey: dbRow.masked_api_key,
      isSandbox: dbRow.is_sandbox !== false, // default to true
      isActive: dbRow.is_active,
      validationStatus: dbRow.validation_status,
      createdAt: dbRow.created_at,
      updatedAt: dbRow.updated_at,
      lastUsed: dbRow.last_used
    };
  }

  /**
   * Mask API key for display
   */
  maskApiKey(apiKey) {
    if (!apiKey || apiKey.length < 8) return '****';
    return apiKey.substring(0, 4) + '****' + apiKey.substring(apiKey.length - 4);
  }

  /**
   * Health check for database connection
   */
  async healthCheck() {
    try {
      const result = await databaseManager.query('SELECT 1 as health_check');
      
      return {
        healthy: result.rows && result.rows.length > 0,
        connection: 'active',
        cacheSize: this.cache.size,
        timestamp: new Date().toISOString()
      };
      
    } catch (error) {
      return {
        healthy: false,
        connection: 'failed',
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Get migration statistics
   */
  async getMigrationStats() {
    try {
      const statsQuery = `
        SELECT 
          validation_status,
          COUNT(*) as count
        FROM user_api_keys 
        WHERE is_active = true 
          AND (provider = 'alpaca' OR broker_name = 'alpaca')
        GROUP BY validation_status
      `;

      const result = await databaseManager.query(statsQuery);
      
      const stats = {
        total: 0,
        migrated: 0,
        pending: 0,
        failed: 0
      };

      if (result.rows) {
        result.rows.forEach(row => {
          const count = parseInt(row.count);
          stats.total += count;
          
          if (row.validation_status === 'migrated_to_ssm') {
            stats.migrated += count;
          } else if (row.validation_status === 'failed') {
            stats.failed += count;
          } else {
            stats.pending += count;
          }
        });
      }

      return stats;
      
    } catch (error) {
      console.error('❌ Failed to get migration stats:', error);
      return { total: 0, migrated: 0, pending: 0, failed: 0 };
    }
  }

  /**
   * Clear cache
   */
  clearCache() {
    this.cache.clear();
    console.log('🗑️ Database API key cache cleared');
  }
}

// Export singleton instance
module.exports = new UnifiedApiKeyDatabaseService();