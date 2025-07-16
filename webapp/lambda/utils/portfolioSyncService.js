/**
 * Portfolio Data Synchronization Service
 * Provides robust synchronization between database and broker APIs with conflict resolution
 */

const { query, safeQuery, transaction } = require('./database');
const { createRequestLogger } = require('./logger');
const { getTimeout } = require('./timeoutManager');
const AlpacaService = require('./alpacaService');
const crypto = require('crypto');

class PortfolioSyncService {
  constructor(options = {}) {
    this.options = {
      syncInterval: options.syncInterval || 300000, // 5 minutes default
      conflictResolutionStrategy: options.conflictResolutionStrategy || 'broker_priority',
      batchSize: options.batchSize || 100,
      maxRetries: options.maxRetries || 3,
      timeoutMs: options.timeoutMs || 30000,
      enablePerformanceTracking: options.enablePerformanceTracking || true,
      ...options
    };

    this.logger = createRequestLogger('portfolio-sync');
    this.syncStatus = new Map(); // userId -> sync status
    this.syncMetrics = {
      totalSyncs: 0,
      successfulSyncs: 0,
      failedSyncs: 0,
      conflictsResolved: 0,
      recordsProcessed: 0,
      avgSyncDuration: 0
    };

    this.logger.info('🚀 Portfolio Sync Service initialized', this.options);
  }

  /**
   * Sync portfolio data for a specific user
   */
  async syncUserPortfolio(userId, apiKeyService, options = {}) {
    const syncId = `sync_${userId}_${Date.now()}`;
    const syncStart = Date.now();

    try {
      this.logger.info('🔄 Starting portfolio sync', {
        syncId,
        userId: `${userId.substring(0, 8)}...`,
        options
      });

      // Update sync status
      this.syncStatus.set(userId, {
        status: 'in_progress',
        syncId,
        startTime: syncStart,
        stage: 'initializing'
      });

      // Get user's API credentials
      const credentials = await this.getUserCredentials(userId, apiKeyService);
      if (!credentials) {
        throw new Error('API credentials not found for user');
      }

      // Initialize Alpaca service
      const alpacaService = new AlpacaService(
        credentials.apiKey,
        credentials.apiSecret,
        credentials.isSandbox
      );

      // Execute sync stages
      const syncResult = await this.executeSyncStages(userId, alpacaService, syncId);

      // Update metrics
      const syncDuration = Date.now() - syncStart;
      this.updateSyncMetrics(true, syncDuration, syncResult);

      // Update sync status
      this.syncStatus.set(userId, {
        status: 'completed',
        syncId,
        startTime: syncStart,
        endTime: Date.now(),
        duration: syncDuration,
        result: syncResult
      });

      this.logger.info('✅ Portfolio sync completed successfully', {
        syncId,
        duration: `${syncDuration}ms`,
        result: syncResult.summary
      });

      return {
        success: true,
        syncId,
        duration: syncDuration,
        result: syncResult
      };

    } catch (error) {
      const syncDuration = Date.now() - syncStart;
      this.updateSyncMetrics(false, syncDuration);

      this.syncStatus.set(userId, {
        status: 'failed',
        syncId,
        startTime: syncStart,
        endTime: Date.now(),
        duration: syncDuration,
        error: error.message
      });

      this.logger.error('❌ Portfolio sync failed', {
        syncId,
        error: error.message,
        duration: `${syncDuration}ms`
      });

      throw error;
    }
  }

  /**
   * Get user credentials with error handling
   */
  async getUserCredentials(userId, apiKeyService) {
    try {
      const credentials = await apiKeyService.getDecryptedApiKey(userId, 'alpaca');
      
      if (!credentials || !credentials.apiKey || !credentials.apiSecret) {
        return null;
      }

      return credentials;
    } catch (error) {
      this.logger.error('Error retrieving user credentials', {
        userId: `${userId.substring(0, 8)}...`,
        error: error.message
      });
      return null;
    }
  }

  /**
   * Execute all sync stages
   */
  async executeSyncStages(userId, alpacaService, syncId) {
    const stages = [
      'account_sync',
      'positions_sync',
      'orders_sync',
      'portfolio_history_sync',
      'metadata_update'
    ];

    const stageResults = {};
    let totalRecordsProcessed = 0;
    let totalConflictsResolved = 0;

    for (const stage of stages) {
      try {
        this.updateSyncStage(userId, stage);
        
        this.logger.info(`📊 Executing sync stage: ${stage}`, { syncId });
        
        const stageResult = await this.executeSyncStage(
          stage, 
          userId, 
          alpacaService, 
          syncId
        );

        stageResults[stage] = {
          success: true,
          ...stageResult
        };

        totalRecordsProcessed += stageResult.recordsProcessed || 0;
        totalConflictsResolved += stageResult.conflictsResolved || 0;

        this.logger.info(`✅ Stage ${stage} completed`, {
          syncId,
          recordsProcessed: stageResult.recordsProcessed,
          conflictsResolved: stageResult.conflictsResolved
        });

      } catch (error) {
        stageResults[stage] = {
          success: false,
          error: error.message
        };

        this.logger.error(`❌ Stage ${stage} failed`, {
          syncId,
          error: error.message
        });

        // Continue with other stages unless it's a critical failure
        if (this.isCriticalStage(stage)) {
          throw error;
        }
      }
    }

    return {
      stages: stageResults,
      summary: {
        totalRecordsProcessed,
        totalConflictsResolved,
        successfulStages: Object.values(stageResults).filter(r => r.success).length,
        failedStages: Object.values(stageResults).filter(r => !r.success).length
      }
    };
  }

  /**
   * Execute a specific sync stage
   */
  async executeSyncStage(stage, userId, alpacaService, syncId) {
    switch (stage) {
      case 'account_sync':
        return await this.syncAccountData(userId, alpacaService, syncId);
      
      case 'positions_sync':
        return await this.syncPositionsData(userId, alpacaService, syncId);
      
      case 'orders_sync':
        return await this.syncOrdersData(userId, alpacaService, syncId);
      
      case 'portfolio_history_sync':
        return await this.syncPortfolioHistory(userId, alpacaService, syncId);
      
      case 'metadata_update':
        return await this.updatePortfolioMetadata(userId, syncId);
      
      default:
        throw new Error(`Unknown sync stage: ${stage}`);
    }
  }

  /**
   * Sync account data
   */
  async syncAccountData(userId, alpacaService, syncId) {
    const stageStart = Date.now();
    
    try {
      // Fetch account data from Alpaca
      const accountData = await alpacaService.getAccount();
      
      if (!accountData) {
        throw new Error('No account data received from Alpaca');
      }

      // Update database with account data
      const updateResult = await this.updateAccountInDatabase(userId, accountData, syncId);

      return {
        recordsProcessed: 1,
        conflictsResolved: updateResult.conflictsResolved,
        duration: Date.now() - stageStart,
        accountData: {
          equity: accountData.equity,
          buyingPower: accountData.buyingPower,
          cash: accountData.cash,
          portfolioValue: accountData.portfolioValue
        }
      };

    } catch (error) {
      this.logger.error('Account sync failed', {
        syncId,
        error: error.message
      });
      throw error;
    }
  }

  /**
   * Sync positions data
   */
  async syncPositionsData(userId, alpacaService, syncId) {
    const stageStart = Date.now();
    
    try {
      // Fetch positions from Alpaca
      const positions = await alpacaService.getPositions();
      
      if (!Array.isArray(positions)) {
        throw new Error('Invalid positions data received from Alpaca');
      }

      // Process positions in batches
      let totalRecordsProcessed = 0;
      let totalConflictsResolved = 0;
      
      for (let i = 0; i < positions.length; i += this.options.batchSize) {
        const batch = positions.slice(i, i + this.options.batchSize);
        
        const batchResult = await this.processPositionsBatch(userId, batch, syncId);
        totalRecordsProcessed += batchResult.recordsProcessed;
        totalConflictsResolved += batchResult.conflictsResolved;
      }

      // Clean up closed positions in database
      const cleanupResult = await this.cleanupClosedPositions(userId, positions, syncId);
      totalRecordsProcessed += cleanupResult.recordsProcessed;

      return {
        recordsProcessed: totalRecordsProcessed,
        conflictsResolved: totalConflictsResolved,
        duration: Date.now() - stageStart,
        positionsCount: positions.length
      };

    } catch (error) {
      this.logger.error('Positions sync failed', {
        syncId,
        error: error.message
      });
      throw error;
    }
  }

  /**
   * Process a batch of positions
   */
  async processPositionsBatch(userId, positions, syncId) {
    return await transaction(async (client) => {
      let recordsProcessed = 0;
      let conflictsResolved = 0;

      for (const position of positions) {
        try {
          // Check for existing position in database
          const existingPosition = await this.getExistingPosition(
            client, 
            userId, 
            position.symbol
          );

          if (existingPosition) {
            // Resolve conflicts and update
            const conflictResult = await this.resolvePositionConflict(
              client,
              existingPosition,
              position,
              userId,
              syncId
            );
            
            if (conflictResult.conflictResolved) {
              conflictsResolved++;
            }
          } else {
            // Insert new position
            await this.insertNewPosition(client, userId, position, syncId);
          }

          recordsProcessed++;

        } catch (error) {
          this.logger.error('Error processing position', {
            syncId,
            symbol: position.symbol,
            error: error.message
          });
          // Continue with other positions
        }
      }

      return { recordsProcessed, conflictsResolved };
    });
  }

  /**
   * Get existing position from database
   */
  async getExistingPosition(client, userId, symbol) {
    const result = await client.query(`
      SELECT * FROM portfolio_holdings 
      WHERE user_id = $1 AND symbol = $2
    `, [userId, symbol]);

    return result.rows[0] || null;
  }

  /**
   * Resolve position conflict between database and API data
   */
  async resolvePositionConflict(client, existingPosition, apiPosition, userId, syncId) {
    const conflicts = this.detectPositionConflicts(existingPosition, apiPosition);
    
    if (conflicts.length === 0) {
      // No conflicts, just update timestamp
      await client.query(`
        UPDATE portfolio_holdings 
        SET updated_at = NOW()
        WHERE user_id = $1 AND symbol = $2
      `, [userId, apiPosition.symbol]);

      return { conflictResolved: false };
    }

    this.logger.info('Position conflicts detected', {
      syncId,
      symbol: apiPosition.symbol,
      conflicts: conflicts.map(c => c.field)
    });

    // Apply conflict resolution strategy
    const resolvedData = this.applyConflictResolution(
      existingPosition,
      apiPosition,
      conflicts
    );

    // Update position with resolved data
    await this.updatePositionWithResolution(
      client,
      userId,
      apiPosition.symbol,
      resolvedData,
      conflicts
    );

    return { conflictResolved: true, conflicts };
  }

  /**
   * Detect conflicts between database and API position data
   */
  detectPositionConflicts(dbPosition, apiPosition) {
    const conflicts = [];
    const tolerance = 0.01; // 1 cent tolerance for price comparisons

    // Check quantity conflicts
    if (Math.abs(parseFloat(dbPosition.quantity || 0) - parseFloat(apiPosition.quantity || 0)) > 0.0001) {
      conflicts.push({
        field: 'quantity',
        dbValue: dbPosition.quantity,
        apiValue: apiPosition.quantity,
        severity: 'high'
      });
    }

    // Check market value conflicts
    if (Math.abs(parseFloat(dbPosition.market_value || 0) - parseFloat(apiPosition.marketValue || 0)) > tolerance) {
      conflicts.push({
        field: 'market_value',
        dbValue: dbPosition.market_value,
        apiValue: apiPosition.marketValue,
        severity: 'medium'
      });
    }

    // Check cost basis conflicts
    if (Math.abs(parseFloat(dbPosition.cost_basis || 0) - parseFloat(apiPosition.costBasis || 0)) > tolerance) {
      conflicts.push({
        field: 'cost_basis',
        dbValue: dbPosition.cost_basis,
        apiValue: apiPosition.costBasis,
        severity: 'medium'
      });
    }

    // Check unrealized P&L conflicts
    if (Math.abs(parseFloat(dbPosition.unrealized_pl || 0) - parseFloat(apiPosition.unrealizedPL || 0)) > tolerance) {
      conflicts.push({
        field: 'unrealized_pl',
        dbValue: dbPosition.unrealized_pl,
        apiValue: apiPosition.unrealizedPL,
        severity: 'low'
      });
    }

    return conflicts;
  }

  /**
   * Apply conflict resolution strategy
   */
  applyConflictResolution(dbPosition, apiPosition, conflicts) {
    const resolvedData = { ...dbPosition };

    conflicts.forEach(conflict => {
      switch (this.options.conflictResolutionStrategy) {
        case 'broker_priority':
          // Always prefer broker/API data
          resolvedData[this.mapApiFieldToDb(conflict.field)] = conflict.apiValue;
          break;

        case 'database_priority':
          // Keep database data (no change needed)
          break;

        case 'latest_timestamp':
          // Use data with latest timestamp
          const dbTimestamp = new Date(dbPosition.updated_at || 0).getTime();
          const apiTimestamp = new Date(apiPosition.lastUpdated || Date.now()).getTime();
          
          if (apiTimestamp > dbTimestamp) {
            resolvedData[this.mapApiFieldToDb(conflict.field)] = conflict.apiValue;
          }
          break;

        case 'severity_based':
          // Prefer API data for high severity conflicts, database for low
          if (conflict.severity === 'high') {
            resolvedData[this.mapApiFieldToDb(conflict.field)] = conflict.apiValue;
          }
          break;

        default:
          // Default to broker priority
          resolvedData[this.mapApiFieldToDb(conflict.field)] = conflict.apiValue;
      }
    });

    return resolvedData;
  }

  /**
   * Map API field names to database field names
   */
  mapApiFieldToDb(apiField) {
    const mapping = {
      'quantity': 'quantity',
      'market_value': 'market_value',
      'cost_basis': 'cost_basis',
      'unrealized_pl': 'unrealized_pl'
    };

    return mapping[apiField] || apiField;
  }

  /**
   * Update position with conflict resolution
   */
  async updatePositionWithResolution(client, userId, symbol, resolvedData, conflicts) {
    // Build dynamic update query based on resolved data
    const updateFields = [];
    const updateValues = [];
    let paramIndex = 3; // Start after userId and symbol

    conflicts.forEach(conflict => {
      const dbField = this.mapApiFieldToDb(conflict.field);
      updateFields.push(`${dbField} = $${paramIndex}`);
      updateValues.push(resolvedData[dbField]);
      paramIndex++;
    });

    // Always update the timestamp and conflict resolution info
    updateFields.push('updated_at = NOW()');
    updateFields.push(`last_sync_conflicts = $${paramIndex}`);
    updateValues.push(JSON.stringify(conflicts.map(c => c.field)));

    const updateQuery = `
      UPDATE portfolio_holdings 
      SET ${updateFields.join(', ')}
      WHERE user_id = $1 AND symbol = $2
    `;

    await client.query(updateQuery, [userId, symbol, ...updateValues]);
  }

  /**
   * Insert new position
   */
  async insertNewPosition(client, userId, position, syncId) {
    await client.query(`
      INSERT INTO portfolio_holdings (
        user_id, symbol, quantity, market_value, cost_basis, 
        unrealized_pl, unrealized_plpc, current_price, 
        average_entry_price, side, created_at, updated_at,
        sync_id
      ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NOW(), $11
      ) ON CONFLICT (user_id, symbol) DO UPDATE SET
        quantity = EXCLUDED.quantity,
        market_value = EXCLUDED.market_value,
        cost_basis = EXCLUDED.cost_basis,
        unrealized_pl = EXCLUDED.unrealized_pl,
        unrealized_plpc = EXCLUDED.unrealized_plpc,
        current_price = EXCLUDED.current_price,
        average_entry_price = EXCLUDED.average_entry_price,
        updated_at = NOW(),
        sync_id = EXCLUDED.sync_id
    `, [
      userId,
      position.symbol,
      position.quantity,
      position.marketValue,
      position.costBasis,
      position.unrealizedPL,
      position.unrealizedPLPercent,
      position.currentPrice,
      position.averageEntryPrice,
      position.side,
      syncId
    ]);
  }

  /**
   * Clean up positions that are closed in the broker but still in database
   */
  async cleanupClosedPositions(userId, apiPositions, syncId) {
    const apiSymbols = new Set(apiPositions.map(p => p.symbol));
    
    // Get all positions from database
    const dbPositions = await safeQuery(`
      SELECT symbol FROM portfolio_holdings WHERE user_id = $1
    `, [userId]);

    let recordsProcessed = 0;

    for (const dbPosition of dbPositions.rows) {
      if (!apiSymbols.has(dbPosition.symbol)) {
        // Position exists in database but not in API - mark as closed
        await safeQuery(`
          UPDATE portfolio_holdings 
          SET quantity = 0, market_value = 0, unrealized_pl = 0,
              status = 'closed', updated_at = NOW(), sync_id = $3
          WHERE user_id = $1 AND symbol = $2
        `, [userId, dbPosition.symbol, syncId]);

        recordsProcessed++;

        this.logger.info('Position marked as closed', {
          syncId,
          symbol: dbPosition.symbol,
          reason: 'not_in_broker_api'
        });
      }
    }

    return { recordsProcessed };
  }

  /**
   * Sync orders data (placeholder - similar pattern to positions)
   */
  async syncOrdersData(userId, alpacaService, syncId) {
    // Similar implementation to positions sync
    return {
      recordsProcessed: 0,
      conflictsResolved: 0,
      duration: 0
    };
  }

  /**
   * Sync portfolio history (placeholder)
   */
  async syncPortfolioHistory(userId, alpacaService, syncId) {
    // Implementation for syncing portfolio performance history
    return {
      recordsProcessed: 0,
      conflictsResolved: 0,
      duration: 0
    };
  }

  /**
   * Update portfolio metadata
   */
  async updatePortfolioMetadata(userId, syncId) {
    const stageStart = Date.now();

    try {
      await safeQuery(`
        UPDATE portfolio_metadata 
        SET last_sync = NOW(), last_sync_id = $2, updated_at = NOW()
        WHERE user_id = $1
      `, [userId, syncId]);

      return {
        recordsProcessed: 1,
        conflictsResolved: 0,
        duration: Date.now() - stageStart
      };

    } catch (error) {
      this.logger.error('Metadata update failed', {
        syncId,
        error: error.message
      });
      throw error;
    }
  }

  /**
   * Update account data in database
   */
  async updateAccountInDatabase(userId, accountData, syncId) {
    return await transaction(async (client) => {
      // Check for existing metadata record
      const existingMetadata = await client.query(`
        SELECT * FROM portfolio_metadata WHERE user_id = $1
      `, [userId]);

      if (existingMetadata.rows.length > 0) {
        // Update existing record
        await client.query(`
          UPDATE portfolio_metadata 
          SET total_equity = $2, buying_power = $3, cash = $4,
              account_status = $5, last_sync = NOW(), 
              last_sync_id = $6, updated_at = NOW()
          WHERE user_id = $1
        `, [
          userId,
          accountData.equity,
          accountData.buyingPower,
          accountData.cash,
          accountData.status,
          syncId
        ]);
      } else {
        // Insert new record
        await client.query(`
          INSERT INTO portfolio_metadata (
            user_id, total_equity, buying_power, cash, 
            account_status, account_type, last_sync, 
            last_sync_id, created_at, updated_at
          ) VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7, NOW(), NOW())
        `, [
          userId,
          accountData.equity,
          accountData.buyingPower,
          accountData.cash,
          accountData.status,
          accountData.environment || 'paper',
          syncId
        ]);
      }

      return { conflictsResolved: 0 };
    });
  }

  /**
   * Update sync stage
   */
  updateSyncStage(userId, stage) {
    const currentStatus = this.syncStatus.get(userId);
    if (currentStatus) {
      currentStatus.stage = stage;
      this.syncStatus.set(userId, currentStatus);
    }
  }

  /**
   * Check if stage is critical
   */
  isCriticalStage(stage) {
    const criticalStages = ['account_sync', 'positions_sync'];
    return criticalStages.includes(stage);
  }

  /**
   * Update sync metrics
   */
  updateSyncMetrics(success, duration, result = null) {
    this.syncMetrics.totalSyncs++;
    
    if (success) {
      this.syncMetrics.successfulSyncs++;
      if (result && result.summary) {
        this.syncMetrics.recordsProcessed += result.summary.totalRecordsProcessed || 0;
        this.syncMetrics.conflictsResolved += result.summary.totalConflictsResolved || 0;
      }
    } else {
      this.syncMetrics.failedSyncs++;
    }

    // Update average duration
    if (this.syncMetrics.avgSyncDuration === 0) {
      this.syncMetrics.avgSyncDuration = duration;
    } else {
      this.syncMetrics.avgSyncDuration = 
        (this.syncMetrics.avgSyncDuration + duration) / 2;
    }
  }

  /**
   * Get sync status for user
   */
  getSyncStatus(userId) {
    return this.syncStatus.get(userId) || null;
  }

  /**
   * Get service metrics
   */
  getMetrics() {
    const successRate = this.syncMetrics.totalSyncs > 0 
      ? (this.syncMetrics.successfulSyncs / this.syncMetrics.totalSyncs) * 100 
      : 0;

    return {
      ...this.syncMetrics,
      successRate: successRate.toFixed(2),
      avgSyncDurationFormatted: `${this.syncMetrics.avgSyncDuration}ms`,
      activeSyncs: Array.from(this.syncStatus.values()).filter(
        status => status.status === 'in_progress'
      ).length
    };
  }
}

module.exports = { PortfolioSyncService };