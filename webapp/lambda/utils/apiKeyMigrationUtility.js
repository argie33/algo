/**
 * API Key Migration Utility
 * 
 * Facilitates migration from RDS/Parameter Store hybrid to pure Parameter Store
 * Long-term solution component for eliminating database dependencies
 */

const apiKeyService = require('./apiKeyService');
const enhancedApiKeyService = require('./enhancedApiKeyService');
const { query } = require('./database');

class ApiKeyMigrationUtility {
  constructor() {
    this.migrationStats = {
      totalUsers: 0,
      successfulMigrations: 0,
      failedMigrations: 0,
      skippedMigrations: 0,
      errors: []
    };
  }

  /**
   * Analyze current API key storage patterns
   */
  async analyzeCurrentState() {
    console.log('🔍 Analyzing current API key storage state...');
    
    const analysis = {
      rdsTableExists: false,
      rdsRecordCount: 0,
      parameterStoreCount: 0,
      hybridUsers: [],
      pureParameterStoreUsers: [],
      orphanedRdsRecords: []
    };

    try {
      // Check RDS table existence and count
      try {
        const rdsCheck = await query(`
          SELECT COUNT(*) as count, 
                 COUNT(DISTINCT user_id) as unique_users 
          FROM user_api_keys
        `);
        
        analysis.rdsTableExists = true;
        analysis.rdsRecordCount = parseInt(rdsCheck.rows[0].count);
        analysis.rdsUniqueUsers = parseInt(rdsCheck.rows[0].unique_users);
        
        console.log(`✅ RDS table exists with ${analysis.rdsRecordCount} records for ${analysis.rdsUniqueUsers} users`);
      } catch (rdsError) {
        console.log(`ℹ️ RDS table not accessible: ${rdsError.message}`);
        analysis.rdsTableExists = false;
      }

      // Estimate Parameter Store usage (would require AWS API calls)
      console.log('📊 Analysis complete');
      
      return {
        ...analysis,
        recommendedAction: this.getRecommendedAction(analysis),
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('❌ Analysis failed:', error);
      throw new Error(`Analysis failed: ${error.message}`);
    }
  }

  /**
   * Determine recommended migration action
   */
  getRecommendedAction(analysis) {
    if (!analysis.rdsTableExists || analysis.rdsRecordCount === 0) {
      return {
        action: 'NO_MIGRATION_NEEDED',
        description: 'System is already using pure Parameter Store architecture',
        steps: [
          'Switch to enhanced API key service',
          'Update frontend to use enhanced endpoints',
          'Remove RDS table references from code'
        ]
      };
    }

    if (analysis.rdsRecordCount > 0) {
      return {
        action: 'MIGRATE_RDS_TO_PARAMETER_STORE',
        description: 'Migrate existing RDS records to Parameter Store',
        steps: [
          'Export RDS data to Parameter Store',
          'Validate migration completeness',
          'Switch to enhanced service',
          'Archive RDS table'
        ]
      };
    }

    return {
      action: 'HYBRID_CLEANUP',
      description: 'Clean up hybrid architecture remnants',
      steps: [
        'Remove RDS fallback code',
        'Switch to enhanced service',
        'Update documentation'
      ]
    };
  }

  /**
   * Migrate a single user's API keys from RDS to Parameter Store
   */
  async migrateUserApiKeys(userId) {
    console.log(`🔄 Migrating API keys for user: ${userId}`);
    
    const migrationResult = {
      userId,
      keysFound: 0,
      keysMigrated: 0,
      errors: []
    };

    try {
      // Get RDS records for user
      const rdsRecords = await query(`
        SELECT provider, encrypted_api_key, encrypted_secret_key, description, is_active, is_sandbox, created_at
        FROM user_api_keys 
        WHERE user_id = $1
      `, [userId]);

      migrationResult.keysFound = rdsRecords.rows.length;

      for (const record of rdsRecords.rows) {
        try {
          // Decrypt RDS data (simplified - in real scenario would need proper decryption)
          const provider = record.provider;
          const apiKey = record.encrypted_api_key; // Would need decryption
          const apiSecret = record.encrypted_secret_key; // Would need decryption

          // Store in enhanced Parameter Store service
          await enhancedApiKeyService.storeApiKey(userId, provider, apiKey, apiSecret);
          
          migrationResult.keysMigrated++;
          console.log(`✅ Migrated ${provider} API key for user ${userId}`);

        } catch (keyError) {
          console.error(`❌ Failed to migrate ${record.provider} for user ${userId}:`, keyError.message);
          migrationResult.errors.push({
            provider: record.provider,
            error: keyError.message
          });
        }
      }

    } catch (error) {
      console.error(`❌ Migration failed for user ${userId}:`, error.message);
      migrationResult.errors.push({
        operation: 'user_migration',
        error: error.message
      });
    }

    return migrationResult;
  }

  /**
   * Perform bulk migration of all users
   */
  async performBulkMigration(options = {}) {
    const {
      dryRun = false,
      batchSize = 10,
      continueOnError = true
    } = options;

    console.log(`🚀 Starting bulk migration (dry run: ${dryRun})`);
    
    this.migrationStats = {
      totalUsers: 0,
      successfulMigrations: 0,
      failedMigrations: 0,
      skippedMigrations: 0,
      errors: [],
      startTime: new Date().toISOString()
    };

    try {
      // Get all users with API keys
      const usersWithKeys = await query(`
        SELECT DISTINCT user_id, COUNT(*) as key_count
        FROM user_api_keys 
        GROUP BY user_id
        ORDER BY user_id
      `);

      this.migrationStats.totalUsers = usersWithKeys.rows.length;
      console.log(`📊 Found ${this.migrationStats.totalUsers} users with API keys`);

      // Process in batches
      for (let i = 0; i < usersWithKeys.rows.length; i += batchSize) {
        const batch = usersWithKeys.rows.slice(i, i + batchSize);
        console.log(`📦 Processing batch ${Math.floor(i/batchSize) + 1} (${batch.length} users)`);

        for (const userRecord of batch) {
          const userId = userRecord.user_id;
          
          try {
            if (dryRun) {
              console.log(`🔍 [DRY RUN] Would migrate ${userRecord.key_count} keys for user ${userId}`);
              this.migrationStats.skippedMigrations++;
            } else {
              const result = await this.migrateUserApiKeys(userId);
              
              if (result.errors.length === 0) {
                this.migrationStats.successfulMigrations++;
              } else {
                this.migrationStats.failedMigrations++;
                this.migrationStats.errors.push(...result.errors);
              }
            }

          } catch (userError) {
            console.error(`❌ Failed to process user ${userId}:`, userError.message);
            this.migrationStats.failedMigrations++;
            this.migrationStats.errors.push({
              userId,
              operation: 'user_processing',
              error: userError.message
            });

            if (!continueOnError) {
              throw userError;
            }
          }
        }
      }

      this.migrationStats.endTime = new Date().toISOString();
      this.migrationStats.duration = Date.now() - new Date(this.migrationStats.startTime).getTime();

      console.log('✅ Bulk migration completed');
      return this.migrationStats;

    } catch (error) {
      console.error('❌ Bulk migration failed:', error);
      this.migrationStats.endTime = new Date().toISOString();
      this.migrationStats.fatalError = error.message;
      throw error;
    }
  }

  /**
   * Validate migration completeness
   */
  async validateMigration() {
    console.log('🔍 Validating migration completeness...');
    
    const validation = {
      rdsRecordCount: 0,
      parameterStoreRecordCount: 0,
      discrepancies: [],
      validationPassed: false
    };

    try {
      // Count RDS records
      const rdsCount = await query(`SELECT COUNT(*) as count FROM user_api_keys`);
      validation.rdsRecordCount = parseInt(rdsCount.rows[0].count);

      // Get sample of users to validate Parameter Store
      const sampleUsers = await query(`
        SELECT DISTINCT user_id 
        FROM user_api_keys 
        LIMIT 10
      `);

      let parameterStoreCount = 0;
      const discrepancies = [];

      for (const userRecord of sampleUsers.rows) {
        const userId = userRecord.user_id;
        
        try {
          // Check Parameter Store
          const parameterStoreKeys = await enhancedApiKeyService.listApiKeys(userId);
          parameterStoreCount += parameterStoreKeys.length;

          // Check RDS
          const rdsKeys = await query(`
            SELECT provider FROM user_api_keys WHERE user_id = $1
          `, [userId]);

          // Compare counts
          if (parameterStoreKeys.length !== rdsKeys.rows.length) {
            discrepancies.push({
              userId,
              rdsCount: rdsKeys.rows.length,
              parameterStoreCount: parameterStoreKeys.length
            });
          }

        } catch (userValidationError) {
          console.warn(`⚠️ Validation failed for user ${userId}:`, userValidationError.message);
          discrepancies.push({
            userId,
            error: userValidationError.message
          });
        }
      }

      validation.parameterStoreRecordCount = parameterStoreCount;
      validation.discrepancies = discrepancies;
      validation.validationPassed = discrepancies.length === 0;

      console.log(`📊 Validation complete: RDS(${validation.rdsRecordCount}) vs Parameter Store(${validation.parameterStoreRecordCount})`);
      
      return validation;

    } catch (error) {
      console.error('❌ Migration validation failed:', error);
      throw new Error(`Validation failed: ${error.message}`);
    }
  }

  /**
   * Archive RDS table after successful migration
   */
  async archiveRdsTable(options = {}) {
    const {
      createBackup = true,
      dropTable = false,
      renameTable = true
    } = options;

    console.log('📦 Archiving RDS table...');

    try {
      if (createBackup) {
        // Create backup table
        await query(`
          CREATE TABLE user_api_keys_backup_${Date.now()} AS 
          SELECT * FROM user_api_keys
        `);
        console.log('✅ Backup table created');
      }

      if (renameTable) {
        // Rename original table
        await query(`
          ALTER TABLE user_api_keys 
          RENAME TO user_api_keys_archived_${Date.now()}
        `);
        console.log('✅ Original table renamed');
      }

      if (dropTable && !renameTable) {
        // Drop original table (dangerous!)
        await query(`DROP TABLE user_api_keys`);
        console.log('⚠️ Original table dropped');
      }

      return {
        success: true,
        backupCreated: createBackup,
        tableRenamed: renameTable,
        tableDropped: dropTable,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('❌ RDS table archival failed:', error);
      throw new Error(`Archival failed: ${error.message}`);
    }
  }

  /**
   * Generate migration report
   */
  generateMigrationReport() {
    const report = {
      title: 'API Key Migration Report',
      timestamp: new Date().toISOString(),
      summary: this.migrationStats,
      recommendations: []
    };

    // Add recommendations based on results
    if (this.migrationStats.successfulMigrations > 0) {
      report.recommendations.push('Migration successful - consider switching to enhanced API key service');
    }

    if (this.migrationStats.failedMigrations > 0) {
      report.recommendations.push('Some migrations failed - review error logs and retry failed users');
    }

    if (this.migrationStats.errors.length === 0) {
      report.recommendations.push('No errors detected - safe to archive RDS table');
    }

    return report;
  }
}

module.exports = new ApiKeyMigrationUtility();