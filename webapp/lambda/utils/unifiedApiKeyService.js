/**
 * Unified API Key Service
 * Simplified, reliable API key management focused on Alpaca
 * Single source of truth with graceful error handling
 */

const apiKeyService = require('./apiKeyService');
const unifiedApiKeyDatabaseService = require('./unifiedApiKeyDatabaseService');

class UnifiedApiKeyService {
  constructor() {
    // Multi-tier caching for thousands of users
    this.cache = new Map();
    this.cacheTTL = 5 * 60 * 1000; // 5 minutes
    this.maxCacheSize = 10000; // Limit memory usage
    this.cacheHits = 0;
    this.cacheMisses = 0;
    
    // Performance monitoring
    this.lastCleanup = Date.now();
    this.cleanupInterval = 10 * 60 * 1000; // 10 minutes
  }

  /**
   * Get user's Alpaca API key with optimized caching and fallback support
   */
  async getAlpacaKey(userId) {
    try {
      // Auto-cleanup cache if needed
      this._performCacheCleanup();
      
      // Check cache first
      const cacheKey = `alpaca:${userId}`;
      const cached = this.cache.get(cacheKey);
      
      if (cached && Date.now() - cached.timestamp < this.cacheTTL) {
        this.cacheHits++;
        // Update access time for LRU behavior
        cached.lastAccess = Date.now();
        console.log(`✅ Cache hit for user ${userId} (${this.cacheHits}/${this.cacheHits + this.cacheMisses})`);
        return cached.data;
      }

      this.cacheMisses++;
      
      // Primary: Try Parameter Store first
      let apiKeyData = await apiKeyService.getApiKey(userId, 'alpaca');
      
      // Fallback: Try database if Parameter Store fails
      if (!apiKeyData) {
        console.log(`ℹ️ Attempting database fallback for user ${userId}`);
        const dbKeyData = await unifiedApiKeyDatabaseService.getApiKeyFromDatabase(userId, 'alpaca');
        
        if (dbKeyData && dbKeyData.validationStatus !== 'migrated_to_ssm') {
          console.log(`🔄 Found unmigrated API key in database for user ${userId}`);
          
          // Try to migrate to Parameter Store
          if (dbKeyData.apiKey && dbKeyData.secretKey) {
            try {
              await this.saveAlpacaKey(userId, dbKeyData.apiKey, dbKeyData.secretKey, dbKeyData.isSandbox);
              await unifiedApiKeyDatabaseService.markApiKeyAsMigrated(userId, 'alpaca');
              
              // Retry Parameter Store after migration
              apiKeyData = await apiKeyService.getApiKey(userId, 'alpaca');
              console.log(`✅ Auto-migrated API key for user ${userId}`);
            } catch (migrationError) {
              console.error(`❌ Auto-migration failed for user ${userId}:`, migrationError);
              // Return database data as fallback
              apiKeyData = {
                keyId: dbKeyData.apiKey,
                secretKey: dbKeyData.secretKey,
                created: dbKeyData.createdAt
              };
            }
          }
        }
      }
      
      if (!apiKeyData) {
        console.log(`ℹ️ No Alpaca API key found for user ${userId}`);
        return null;
      }

      // Cache with LRU management
      this._addToCache(cacheKey, apiKeyData);

      console.log(`✅ Retrieved Alpaca API key for user ${userId}`);
      return apiKeyData;
      
    } catch (error) {
      console.error(`❌ Error getting Alpaca key for user ${userId}:`, error);
      return null; // Graceful degradation
    }
  }

  /**
   * Save user's Alpaca API key with database tracking
   */
  async saveAlpacaKey(userId, apiKey, secretKey, isSandbox = true) {
    try {
      // Validate inputs
      if (!userId || !apiKey || !secretKey) {
        throw new Error('User ID, API key, and secret are required');
      }

      // Store in Parameter Store (primary)
      const success = await apiKeyService.storeApiKey(userId, 'alpaca', apiKey, secretKey);
      
      if (success) {
        // Update database tracking record
        try {
          await unifiedApiKeyDatabaseService.saveApiKeyToDatabase(userId, 'alpaca', apiKey, secretKey, isSandbox);
          console.log(`📊 Database tracking updated for user ${userId}`);
        } catch (dbError) {
          console.warn(`⚠️ Database tracking failed for user ${userId}:`, dbError.message);
          // Don't fail the entire operation for database tracking issues
        }
        
        // Clear cache to force refresh
        this.cache.delete(`alpaca:${userId}`);
        console.log(`✅ Saved Alpaca API key for user ${userId}`);
        return { success: true, message: 'API key saved successfully' };
      } else {
        throw new Error('Failed to store API key in Parameter Store');
      }
      
    } catch (error) {
      console.error(`❌ Error saving Alpaca key for user ${userId}:`, error);
      throw error;
    }
  }

  /**
   * Remove user's Alpaca API key from all storage locations
   */
  async removeAlpacaKey(userId) {
    try {
      let parameterStoreSuccess = false;
      let databaseSuccess = false;
      
      // Remove from Parameter Store (primary)
      try {
        parameterStoreSuccess = await apiKeyService.deleteApiKey(userId, 'alpaca');
      } catch (paramError) {
        console.warn(`⚠️ Parameter Store removal failed for user ${userId}:`, paramError.message);
      }
      
      // Remove from database (tracking)
      try {
        databaseSuccess = await unifiedApiKeyDatabaseService.removeApiKeyFromDatabase(userId, 'alpaca');
      } catch (dbError) {
        console.warn(`⚠️ Database removal failed for user ${userId}:`, dbError.message);
      }
      
      // Clear cache regardless
      this.cache.delete(`alpaca:${userId}`);
      
      if (parameterStoreSuccess || databaseSuccess) {
        console.log(`✅ Removed Alpaca API key for user ${userId}`);
        return { success: true, message: 'API key removed successfully' };
      } else {
        console.warn(`⚠️ API key removal had issues for user ${userId}`);
        return { success: true, message: 'API key removal completed with warnings' };
      }
      
    } catch (error) {
      console.error(`❌ Error removing Alpaca key for user ${userId}:`, error);
      throw error;
    }
  }

  /**
   * Check if user has a valid Alpaca API key
   */
  async hasAlpacaKey(userId) {
    try {
      const keyData = await this.getAlpacaKey(userId);
      return !!keyData;
    } catch (error) {
      console.error(`❌ Error checking Alpaca key for user ${userId}:`, error);
      return false;
    }
  }

  /**
   * Get API key summary for UI display
   */
  async getApiKeySummary(userId) {
    try {
      const keyData = await this.getAlpacaKey(userId);
      
      if (!keyData) {
        return [];
      }

      return [{
        id: `alpaca-${userId}`,
        provider: 'alpaca',
        name: 'Alpaca Markets',
        description: 'Commission-free stock trading with API access',
        masked_api_key: this.maskApiKey(keyData.keyId),
        is_sandbox: true, // Default for now
        is_active: true,
        created_at: keyData.created,
        status: 'active'
      }];
      
    } catch (error) {
      console.error(`❌ Error getting API key summary for user ${userId}:`, error);
      return []; // Return empty array for graceful degradation
    }
  }

  /**
   * Mask API key for display
   */
  maskApiKey(apiKey) {
    if (!apiKey || apiKey.length < 8) return '****';
    return apiKey.substring(0, 4) + '****' + apiKey.substring(apiKey.length - 4);
  }

  /**
   * Intelligent cache management for high-scale operations
   */
  _addToCache(cacheKey, data) {
    // Check if cache is at capacity
    if (this.cache.size >= this.maxCacheSize) {
      this._evictLeastRecentlyUsed();
    }
    
    this.cache.set(cacheKey, {
      data,
      timestamp: Date.now(),
      lastAccess: Date.now()
    });
  }
  
  /**
   * LRU cache eviction for memory management
   */
  _evictLeastRecentlyUsed() {
    let oldestKey = null;
    let oldestTime = Date.now();
    
    for (const [key, value] of this.cache.entries()) {
      if (value.lastAccess < oldestTime) {
        oldestTime = value.lastAccess;
        oldestKey = key;
      }
    }
    
    if (oldestKey) {
      this.cache.delete(oldestKey);
      console.log(`🗑️ Evicted LRU cache entry: ${oldestKey}`);
    }
  }
  
  /**
   * Periodic cache cleanup for expired entries
   */
  _performCacheCleanup() {
    const now = Date.now();
    
    // Only run cleanup every 10 minutes
    if (now - this.lastCleanup < this.cleanupInterval) {
      return;
    }
    
    let expiredCount = 0;
    const expiredKeys = [];
    
    for (const [key, value] of this.cache.entries()) {
      if (now - value.timestamp > this.cacheTTL) {
        expiredKeys.push(key);
      }
    }
    
    expiredKeys.forEach(key => {
      this.cache.delete(key);
      expiredCount++;
    });
    
    if (expiredCount > 0) {
      console.log(`🧹 Cleaned up ${expiredCount} expired cache entries`);
    }
    
    this.lastCleanup = now;
  }
  
  /**
   * Clear cache for specific user or all users
   */
  clearCache(userId = null) {
    if (userId) {
      this.cache.delete(`alpaca:${userId}`);
      console.log(`🗑️ Cleared cache for user ${userId}`);
    } else {
      this.cache.clear();
      this.cacheHits = 0;
      this.cacheMisses = 0;
      console.log(`🗑️ Cleared all API key cache and reset metrics`);
    }
  }

  /**
   * Comprehensive health check with performance metrics and database status
   */
  async healthCheck() {
    try {
      const isEnabled = apiKeyService.isEnabled;
      const backendHealth = await apiKeyService.healthCheck();
      const databaseHealth = await unifiedApiKeyDatabaseService.healthCheck();
      const migrationStats = await unifiedApiKeyDatabaseService.getMigrationStats();
      
      const hitRate = this.cacheHits + this.cacheMisses > 0 ? 
        (this.cacheHits / (this.cacheHits + this.cacheMisses) * 100).toFixed(2) : 0;
      
      return {
        healthy: isEnabled && backendHealth.healthy,
        backend: {
          parameterStore: {
            healthy: backendHealth.healthy,
            enabled: isEnabled
          },
          database: {
            healthy: databaseHealth.healthy,
            connection: databaseHealth.connection,
            cacheSize: databaseHealth.cacheSize
          }
        },
        cache: {
          size: this.cache.size,
          maxSize: this.maxCacheSize,
          hits: this.cacheHits,
          misses: this.cacheMisses,
          hitRate: `${hitRate}%`,
          utilizationPercent: ((this.cache.size / this.maxCacheSize) * 100).toFixed(2)
        },
        migration: {
          total: migrationStats.total,
          migrated: migrationStats.migrated,
          pending: migrationStats.pending,
          failed: migrationStats.failed,
          completionRate: migrationStats.total > 0 ? 
            ((migrationStats.migrated / migrationStats.total) * 100).toFixed(2) + '%' : '0%'
        },
        performance: {
          lastCleanup: new Date(this.lastCleanup).toISOString(),
          memoryEfficient: this.cache.size < this.maxCacheSize * 0.8
        },
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      return {
        healthy: false,
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }
  
  /**
   * Get cache performance metrics
   */
  getCacheMetrics() {
    const hitRate = this.cacheHits + this.cacheMisses > 0 ? 
      (this.cacheHits / (this.cacheHits + this.cacheMisses) * 100).toFixed(2) : 0;
      
    return {
      size: this.cache.size,
      maxSize: this.maxCacheSize,
      hits: this.cacheHits,
      misses: this.cacheMisses,
      hitRate: `${hitRate}%`,
      utilizationPercent: ((this.cache.size / this.maxCacheSize) * 100).toFixed(2),
      memoryEfficient: this.cache.size < this.maxCacheSize * 0.8
    };
  }
  
  /**
   * Get migration status for monitoring
   */
  async getMigrationStatus() {
    try {
      return await unifiedApiKeyDatabaseService.getMigrationStats();
    } catch (error) {
      console.error('❌ Failed to get migration status:', error);
      return { total: 0, migrated: 0, pending: 0, failed: 0 };
    }
  }
  
  /**
   * Force migration of a specific user
   */
  async migrateUserApiKey(userId) {
    try {
      const dbKeyData = await unifiedApiKeyDatabaseService.getApiKeyFromDatabase(userId, 'alpaca');
      
      if (!dbKeyData || dbKeyData.validationStatus === 'migrated_to_ssm') {
        return { success: false, message: 'No API key found or already migrated' };
      }
      
      if (!dbKeyData.apiKey || !dbKeyData.secretKey) {
        return { success: false, message: 'Invalid API key data in database' };
      }
      
      // Migrate to Parameter Store
      await this.saveAlpacaKey(userId, dbKeyData.apiKey, dbKeyData.secretKey, dbKeyData.isSandbox);
      await unifiedApiKeyDatabaseService.markApiKeyAsMigrated(userId, 'alpaca');
      
      console.log(`✅ Successfully migrated API key for user ${userId}`);
      return { success: true, message: 'API key migrated successfully' };
      
    } catch (error) {
      console.error(`❌ Failed to migrate API key for user ${userId}:`, error);
      throw error;
    }
  }

  /**
   * Get API key with account type support for paper trading
   */
  async getApiKeyWithAccountType(userId, provider, accountType = 'paper') {
    try {
      let credentials;
      
      // Use optimized method for Alpaca
      if (provider === 'alpaca') {
        credentials = await this.getAlpacaKey(userId);
      } else {
        credentials = await this.databaseService.getApiKey(userId, provider);
      }
      
      if (!credentials) return null;
      
      return {
        apiKey: credentials.keyId,
        apiSecret: credentials.secretKey,
        isSandbox: accountType === 'paper' || credentials.version === '1.0',
        accountType: accountType,
        provider: provider,
        supportsLive: credentials.version !== '1.0', // v1.0 is paper-only
        supportsPaper: true // Alpaca always supports paper
      };
    } catch (error) {
      console.error(`Failed to get API key with account type for ${provider}:`, error);
      throw error;
    }
  }

  /**
   * Validate if user has access to specific account type
   */
  async validateAccountTypeAccess(userId, provider, requestedAccountType) {
    try {
      let credentials;
      
      // Use optimized method for Alpaca
      if (provider === 'alpaca') {
        credentials = await this.getAlpacaKey(userId);
      } else {
        credentials = await this.databaseService.getApiKey(userId, provider);
      }
      
      if (!credentials) return false;
      
      // Paper trading always allowed
      if (requestedAccountType === 'paper') return true;
      
      // Live trading only if not restricted to paper-only
      if (requestedAccountType === 'live') {
        return credentials.version !== '1.0';
      }
      
      return false;
    } catch (error) {
      console.error(`Failed to validate account type access:`, error);
      return false;
    }
  }
}

// Export singleton instance
module.exports = new UnifiedApiKeyService();