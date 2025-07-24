/**
 * API Key Migration Service
 * Migrate from old fragmented API key system to unified service
 * Handles data migration, validation, and rollback capabilities
 */

const unifiedApiKeyService = require('./unifiedApiKeyService');
const databaseManager = require('./databaseConnectionManager');

class ApiKeyMigrationService {
  constructor() {
    this.migrationStatus = {
      total: 0,
      migrated: 0,
      failed: 0,
      skipped: 0,
      errors: []
    };
  }

  /**
   * Discover existing API keys from old system
   */
  async discoverLegacyApiKeys() {
    console.log('🔍 Discovering legacy API keys...');
    
    const legacyKeys = [];
    
    try {
      // Check database for API keys (old portfolio system)
      const dbQuery = `
        SELECT DISTINCT 
          user_id,
          api_key,
          secret_key,
          provider,
          created_at,
          is_sandbox
        FROM api_keys 
        WHERE provider = 'alpaca' AND deleted_at IS NULL
        ORDER BY user_id, created_at DESC
      `;
      
      const dbResult = await databaseManager.query(dbQuery);
      
      if (dbResult.rows && dbResult.rows.length > 0) {
        console.log(`📊 Found ${dbResult.rows.length} API keys in database`);
        
        dbResult.rows.forEach(row => {
          legacyKeys.push({
            source: 'database',
            userId: row.user_id,
            apiKey: row.api_key,
            secretKey: row.secret_key,
            provider: row.provider,
            isSandbox: row.is_sandbox || true,
            createdAt: row.created_at
          });
        });
      }
      
    } catch (error) {
      console.error('❌ Error querying database for legacy API keys:', error);
      this.migrationStatus.errors.push({
        type: 'database_query',
        error: error.message
      });
    }
    
    try {
      // Check Parameter Store for existing keys (settings system)
      const apiKeyService = require('./apiKeyService');
      
      // This would require iterating through Parameter Store keys
      // For now, we'll rely on the database discovery
      console.log('ℹ️ Parameter Store discovery requires AWS SSM list operations');
      
    } catch (error) {
      console.error('❌ Error checking Parameter Store:', error);
      this.migrationStatus.errors.push({
        type: 'parameter_store_check',
        error: error.message
      });
    }
    
    // Remove duplicates (prefer most recent)
    const uniqueKeys = this.deduplicateApiKeys(legacyKeys);
    
    console.log(`✅ Discovered ${legacyKeys.length} total keys, ${uniqueKeys.length} unique users`);
    
    this.migrationStatus.total = uniqueKeys.length;
    return uniqueKeys;
  }

  /**
   * Remove duplicate API keys, keeping the most recent
   */
  deduplicateApiKeys(apiKeys) {
    const userMap = new Map();
    
    apiKeys.forEach(key => {
      const existing = userMap.get(key.userId);
      
      if (!existing || new Date(key.createdAt) > new Date(existing.createdAt)) {
        userMap.set(key.userId, key);
      }
    });
    
    return Array.from(userMap.values());
  }

  /**
   * Migrate a single API key to unified system
   */
  async migrateSingleApiKey(legacyKey) {
    try {
      console.log(`🔄 Migrating API key for user: ${legacyKey.userId}`);
      
      // Validate legacy key format
      if (!this.validateLegacyKey(legacyKey)) {
        console.warn(`⚠️ Invalid legacy key format for user ${legacyKey.userId}, skipping`);
        this.migrationStatus.skipped++;
        return { success: false, reason: 'invalid_format' };
      }
      
      // Check if key already exists in unified system
      const existingKey = await unifiedApiKeyService.getAlpacaKey(legacyKey.userId);
      
      if (existingKey) {
        console.log(`ℹ️ User ${legacyKey.userId} already has key in unified system, skipping`);
        this.migrationStatus.skipped++;
        return { success: false, reason: 'already_exists' };
      }
      
      // Migrate to unified system
      const result = await unifiedApiKeyService.saveAlpacaKey(
        legacyKey.userId,
        legacyKey.apiKey,
        legacyKey.secretKey,
        legacyKey.isSandbox
      );
      
      if (result.success) {
        console.log(`✅ Successfully migrated API key for user: ${legacyKey.userId}`);
        this.migrationStatus.migrated++;
        return { success: true };
      } else {
        throw new Error(result.message || 'Migration failed');
      }
      
    } catch (error) {
      console.error(`❌ Failed to migrate API key for user ${legacyKey.userId}:`, error);
      this.migrationStatus.failed++;
      this.migrationStatus.errors.push({
        type: 'migration_error',
        userId: legacyKey.userId,
        error: error.message
      });
      return { success: false, reason: 'migration_error', error: error.message };
    }
  }

  /**
   * Validate legacy API key format
   */
  validateLegacyKey(legacyKey) {
    if (!legacyKey.userId || !legacyKey.apiKey || !legacyKey.secretKey) {
      return false;
    }
    
    // Validate Alpaca format
    if (!legacyKey.apiKey.startsWith('PK') || legacyKey.apiKey.length < 20) {
      return false;
    }
    
    if (legacyKey.secretKey.length < 20 || legacyKey.secretKey.length > 80) {
      return false;
    }
    
    return true;
  }

  /**
   * Run complete migration process
   */
  async runMigration(options = {}) {
    const { 
      dryRun = false, 
      batchSize = 10, 
      delayBetweenBatches = 1000 
    } = options;
    
    console.log('🚀 Starting API key migration...');
    console.log(`Mode: ${dryRun ? 'DRY RUN' : 'LIVE MIGRATION'}`);
    
    try {
      // Reset migration status
      this.migrationStatus = {
        total: 0,
        migrated: 0,
        failed: 0,
        skipped: 0,
        errors: []
      };
      
      // Discover legacy keys
      const legacyKeys = await this.discoverLegacyApiKeys();
      
      if (legacyKeys.length === 0) {
        console.log('ℹ️ No legacy API keys found to migrate');
        return this.migrationStatus;
      }
      
      // Process in batches
      const batches = this.chunkArray(legacyKeys, batchSize);
      
      console.log(`📦 Processing ${legacyKeys.length} keys in ${batches.length} batches`);
      
      for (let i = 0; i < batches.length; i++) {
        const batch = batches[i];
        console.log(`🔄 Processing batch ${i + 1}/${batches.length} (${batch.length} keys)`);
        
        if (dryRun) {
          // Dry run - just validate
          batch.forEach(key => {
            if (this.validateLegacyKey(key)) {
              this.migrationStatus.migrated++;
            } else {
              this.migrationStatus.skipped++;
            }
          });
        } else {
          // Live migration
          const promises = batch.map(key => this.migrateSingleApiKey(key));
          await Promise.all(promises);
        }
        
        // Delay between batches to avoid overwhelming AWS
        if (i < batches.length - 1) {
          await this.sleep(delayBetweenBatches);
        }
      }
      
      console.log('✅ Migration complete!');
      this.printMigrationSummary();
      
      return this.migrationStatus;
      
    } catch (error) {
      console.error('❌ Migration failed:', error);
      this.migrationStatus.errors.push({
        type: 'migration_failure',
        error: error.message
      });
      return this.migrationStatus;
    }
  }

  /**
   * Print migration summary
   */
  printMigrationSummary() {
    console.log('\n📊 Migration Summary:');
    console.log(`Total keys discovered: ${this.migrationStatus.total}`);
    console.log(`Successfully migrated: ${this.migrationStatus.migrated}`);
    console.log(`Failed: ${this.migrationStatus.failed}`);
    console.log(`Skipped: ${this.migrationStatus.skipped}`);
    console.log(`Errors: ${this.migrationStatus.errors.length}`);
    
    if (this.migrationStatus.errors.length > 0) {
      console.log('\n❌ Errors encountered:');
      this.migrationStatus.errors.forEach((error, index) => {
        console.log(`  ${index + 1}. ${error.type}: ${error.error}`);
      });
    }
  }

  /**
   * Rollback migration (remove migrated keys from unified system)
   */
  async rollbackMigration(userIds = []) {
    console.log('🔄 Starting migration rollback...');
    
    let rollbackCount = 0;
    const errors = [];
    
    try {
      // If no specific user IDs provided, discover from database
      if (userIds.length === 0) {
        const legacyKeys = await this.discoverLegacyApiKeys();
        userIds = legacyKeys.map(key => key.userId);
      }
      
      console.log(`📋 Rolling back ${userIds.length} users`);
      
      for (const userId of userIds) {
        try {
          const result = await unifiedApiKeyService.removeAlpacaKey(userId);
          
          if (result.success) {
            rollbackCount++;
            console.log(`✅ Rolled back user: ${userId}`);
          } else {
            console.warn(`⚠️ Could not rollback user ${userId}: ${result.message}`);
          }
          
        } catch (error) {
          console.error(`❌ Error rolling back user ${userId}:`, error);
          errors.push({ userId, error: error.message });
        }
      }
      
      console.log(`✅ Rollback complete: ${rollbackCount} users processed`);
      
      if (errors.length > 0) {
        console.log(`❌ Rollback errors: ${errors.length}`);
        errors.forEach(err => {
          console.log(`  User ${err.userId}: ${err.error}`);
        });
      }
      
      return { rollbackCount, errors };
      
    } catch (error) {
      console.error('❌ Rollback failed:', error);
      return { rollbackCount, errors: [{ error: error.message }] };
    }
  }

  /**
   * Utility functions
   */
  chunkArray(array, chunkSize) {
    const chunks = [];
    for (let i = 0; i < array.length; i += chunkSize) {
      chunks.push(array.slice(i, i + chunkSize));
    }
    return chunks;
  }

  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  /**
   * Get migration status
   */
  getStatus() {
    return this.migrationStatus;
  }
}

// Export singleton instance
module.exports = new ApiKeyMigrationService();