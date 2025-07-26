/**
 * Position Synchronization Service
 * Maintains real-time synchronization between internal positions and broker positions
 */

const { createLogger } = require('../utils/structuredLogger');
const { query } = require('../utils/database');
const AlpacaHFTService = require('./alpacaHFTService');

class PositionSyncService {
  constructor() {
    this.logger = createLogger('financial-platform', 'position-sync-service');
    this.correlationId = this.generateCorrelationId();
    
    // Service state
    this.isRunning = false;
    this.syncInterval = null;
    this.alpacaServices = new Map(); // userId -> AlpacaHFTService
    
    // Sync configuration
    this.config = {
      syncIntervalMs: 30000, // 30 seconds
      maxDiscrepancyThreshold: 0.01, // 1% variance allowed
      alertThreshold: 0.05, // 5% variance triggers alert
      batchSize: 50, // Max positions to sync per batch
      retryAttempts: 3
    };
    
    // Performance metrics
    this.metrics = {
      totalSyncs: 0,
      successfulSyncs: 0,
      discrepanciesFound: 0,
      positionsReconciled: 0,
      lastSyncTime: null,
      avgSyncTime: 0,
      errors: []
    };
    
    // Discrepancy tracking
    this.discrepancies = new Map(); // positionId -> discrepancy details
    this.reconciliationQueue = [];
  }

  generateCorrelationId() {
    return `pos-sync-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Initialize position synchronization service
   */
  async initialize() {
    try {
      this.logger.info('Initializing Position Sync Service', {
        syncInterval: this.config.syncIntervalMs,
        correlationId: this.correlationId
      });

      // Load active users with HFT strategies
      const activeUsers = await this.getActiveHFTUsers();
      
      this.logger.info('Found active HFT users', {
        userCount: activeUsers.length,
        correlationId: this.correlationId
      });

      // Initialize Alpaca services for each user
      for (const user of activeUsers) {
        await this.initializeUserAlpacaService(user);
      }

      return { success: true, activeUsers: activeUsers.length };

    } catch (error) {
      this.logger.error('Failed to initialize Position Sync Service', {
        error: error.message,
        correlationId: this.correlationId
      });
      
      return { success: false, error: error.message };
    }
  }

  /**
   * Get users with active HFT strategies
   */
  async getActiveHFTUsers() {
    const sql = `
      SELECT DISTINCT u.id, u.email, uk.api_key, uk.api_secret, uk.is_sandbox
      FROM users u
      JOIN user_api_keys uk ON u.id = uk.user_id
      JOIN hft_strategies hs ON u.id = hs.user_id
      WHERE uk.provider = 'alpaca'
        AND hs.enabled = true
        AND uk.api_key IS NOT NULL
        AND uk.api_secret IS NOT NULL
    `;

    const result = await query(sql);
    return result.rows;
  }

  /**
   * Initialize Alpaca service for a user
   */
  async initializeUserAlpacaService(user) {
    try {
      const alpacaService = new AlpacaHFTService(
        user.api_key,
        user.api_secret,
        user.is_sandbox
      );

      const initResult = await alpacaService.initialize();
      
      if (initResult.success) {
        this.alpacaServices.set(user.id, alpacaService);
        
        this.logger.info('Alpaca service initialized for user', {
          userId: user.id,
          isPaper: user.is_sandbox,
          correlationId: this.correlationId
        });
      } else {
        this.logger.error('Failed to initialize Alpaca service for user', {
          userId: user.id,
          error: initResult.error,
          correlationId: this.correlationId
        });
      }

    } catch (error) {
      this.logger.error('Error initializing user Alpaca service', {
        userId: user.id,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Start position synchronization
   */
  async start() {
    if (this.isRunning) {
      return { success: false, error: 'Position sync already running' };
    }

    try {
      this.logger.info('Starting Position Sync Service', {
        correlationId: this.correlationId
      });

      // Perform initial sync
      await this.performFullSync();

      // Schedule periodic sync
      this.syncInterval = setInterval(() => {
        this.performFullSync().catch(error => {
          this.logger.error('Scheduled sync failed', {
            error: error.message,
            correlationId: this.correlationId
          });
        });
      }, this.config.syncIntervalMs);

      this.isRunning = true;

      return { success: true, message: 'Position sync started' };

    } catch (error) {
      this.logger.error('Failed to start Position Sync Service', {
        error: error.message,
        correlationId: this.correlationId
      });
      
      return { success: false, error: error.message };
    }
  }

  /**
   * Stop position synchronization
   */
  async stop() {
    if (!this.isRunning) {
      return { success: false, error: 'Position sync not running' };
    }

    try {
      this.logger.info('Stopping Position Sync Service', {
        correlationId: this.correlationId
      });

      // Clear sync interval
      if (this.syncInterval) {
        clearInterval(this.syncInterval);
        this.syncInterval = null;
      }

      // Disconnect Alpaca services
      for (const [userId, alpacaService] of this.alpacaServices) {
        try {
          await alpacaService.disconnect();
        } catch (error) {
          this.logger.error('Error disconnecting Alpaca service', {
            userId,
            error: error.message,
            correlationId: this.correlationId
          });
        }
      }

      this.alpacaServices.clear();
      this.isRunning = false;

      return { success: true, message: 'Position sync stopped' };

    } catch (error) {
      this.logger.error('Failed to stop Position Sync Service', {
        error: error.message,
        correlationId: this.correlationId
      });
      
      return { success: false, error: error.message };
    }
  }

  /**
   * Perform full position synchronization for all users
   */
  async performFullSync() {
    const startTime = Date.now();
    
    try {
      this.logger.info('Starting full position sync', {
        userCount: this.alpacaServices.size,
        correlationId: this.correlationId
      });

      let totalSynced = 0;
      let totalDiscrepancies = 0;

      // Sync positions for each user
      for (const [userId, alpacaService] of this.alpacaServices) {
        try {
          const result = await this.syncUserPositions(userId, alpacaService);
          totalSynced += result.synced;
          totalDiscrepancies += result.discrepancies;

        } catch (error) {
          this.logger.error('User position sync failed', {
            userId,
            error: error.message,
            correlationId: this.correlationId
          });
          
          this.metrics.errors.push({
            userId,
            error: error.message,
            timestamp: Date.now()
          });
        }
      }

      // Process reconciliation queue
      await this.processReconciliationQueue();

      // Update metrics
      const syncTime = Date.now() - startTime;
      this.updateSyncMetrics(syncTime, totalSynced, totalDiscrepancies);

      this.logger.info('Full position sync completed', {
        totalSynced,
        totalDiscrepancies,
        syncTime,
        correlationId: this.correlationId
      });

    } catch (error) {
      this.logger.error('Full position sync failed', {
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Sync positions for a specific user
   */
  async syncUserPositions(userId, alpacaService) {
    try {
      // Get broker positions
      const brokerPositions = await alpacaService.getPositions();
      
      // Get internal positions
      const internalPositions = await this.getInternalPositions(userId);
      
      // Compare and reconcile
      const comparison = this.comparePositions(internalPositions, brokerPositions);
      
      // Handle discrepancies
      await this.handleDiscrepancies(userId, comparison.discrepancies);
      
      // Update internal positions with current broker data
      await this.updateInternalPositions(userId, brokerPositions);

      return {
        synced: comparison.matched.length,
        discrepancies: comparison.discrepancies.length
      };

    } catch (error) {
      this.logger.error('User position sync error', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      
      throw error;
    }
  }

  /**
   * Get internal positions from database
   */
  async getInternalPositions(userId) {
    const sql = `
      SELECT p.*, s.name as strategy_name
      FROM hft_positions p
      JOIN hft_strategies s ON p.strategy_id = s.id
      WHERE p.user_id = $1 AND p.status = 'OPEN'
      ORDER BY p.symbol, p.opened_at
    `;

    const result = await query(sql, [userId]);
    return result.rows;
  }

  /**
   * Compare internal positions with broker positions
   */
  comparePositions(internalPositions, brokerPositions) {
    const matched = [];
    const discrepancies = [];
    const brokerPositionMap = new Map();

    // Create map of broker positions by symbol
    brokerPositions.forEach(pos => {
      const key = `${pos.symbol}`;
      brokerPositionMap.set(key, pos);
    });

    // Compare each internal position
    internalPositions.forEach(internalPos => {
      const key = `${internalPos.symbol}`;
      const brokerPos = brokerPositionMap.get(key);

      if (!brokerPos) {
        // Internal position exists but not in broker
        discrepancies.push({
          type: 'MISSING_BROKER',
          internal: internalPos,
          broker: null,
          severity: 'HIGH'
        });
      } else {
        // Compare quantities
        const quantityDiff = Math.abs(
          parseFloat(internalPos.quantity) - Math.abs(brokerPos.quantity)
        );
        const quantityThreshold = Math.abs(brokerPos.quantity) * this.config.maxDiscrepancyThreshold;

        if (quantityDiff > quantityThreshold) {
          discrepancies.push({
            type: 'QUANTITY_MISMATCH',
            internal: internalPos,
            broker: brokerPos,
            difference: quantityDiff,
            threshold: quantityThreshold,
            severity: quantityDiff > Math.abs(brokerPos.quantity) * this.config.alertThreshold ? 'HIGH' : 'MEDIUM'
          });
        } else {
          matched.push({
            internal: internalPos,
            broker: brokerPos
          });
        }

        // Remove from broker map to track unmatched broker positions
        brokerPositionMap.delete(key);
      }
    });

    // Check for broker positions not in internal system
    brokerPositionMap.forEach(brokerPos => {
      discrepancies.push({
        type: 'MISSING_INTERNAL',
        internal: null,
        broker: brokerPos,
        severity: 'MEDIUM'
      });
    });

    return { matched, discrepancies };
  }

  /**
   * Handle position discrepancies
   */
  async handleDiscrepancies(userId, discrepancies) {
    for (const discrepancy of discrepancies) {
      try {
        this.logger.warn('Position discrepancy detected', {
          userId,
          type: discrepancy.type,
          severity: discrepancy.severity,
          correlationId: this.correlationId
        });

        // Log discrepancy to database
        await this.logDiscrepancy(userId, discrepancy);

        // Add to reconciliation queue if high severity
        if (discrepancy.severity === 'HIGH') {
          this.reconciliationQueue.push({
            userId,
            discrepancy,
            attempts: 0,
            addedAt: Date.now()
          });
        }

        this.metrics.discrepanciesFound++;

      } catch (error) {
        this.logger.error('Error handling discrepancy', {
          userId,
          discrepancy: discrepancy.type,
          error: error.message,
          correlationId: this.correlationId
        });
      }
    }
  }

  /**
   * Log discrepancy to database
   */
  async logDiscrepancy(userId, discrepancy) {
    const sql = `
      INSERT INTO hft_risk_events (
        user_id, event_type, severity, symbol, description, metadata, created_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7)
    `;

    const symbol = discrepancy.internal?.symbol || discrepancy.broker?.symbol;
    const description = this.getDiscrepancyDescription(discrepancy);

    await query(sql, [
      userId,
      'POSITION_DISCREPANCY',
      discrepancy.severity,
      symbol,
      description,
      JSON.stringify({
        type: discrepancy.type,
        internal: discrepancy.internal,
        broker: discrepancy.broker,
        difference: discrepancy.difference,
        threshold: discrepancy.threshold
      }),
      new Date()
    ]);
  }

  /**
   * Get human-readable discrepancy description
   */
  getDiscrepancyDescription(discrepancy) {
    switch (discrepancy.type) {
      case 'MISSING_BROKER':
        return `Internal position for ${discrepancy.internal.symbol} (${discrepancy.internal.quantity}) not found in broker account`;
      
      case 'MISSING_INTERNAL':
        return `Broker position for ${discrepancy.broker.symbol} (${discrepancy.broker.quantity}) not found in internal system`;
      
      case 'QUANTITY_MISMATCH':
        return `Position quantity mismatch for ${discrepancy.internal.symbol}: Internal=${discrepancy.internal.quantity}, Broker=${discrepancy.broker.quantity}`;
      
      default:
        return `Unknown discrepancy type: ${discrepancy.type}`;
    }
  }

  /**
   * Update internal positions with broker data
   */
  async updateInternalPositions(userId, brokerPositions) {
    for (const brokerPos of brokerPositions) {
      try {
        const sql = `
          UPDATE hft_positions 
          SET 
            current_price = $1,
            unrealized_pnl = $2,
            updated_at = CURRENT_TIMESTAMP
          WHERE user_id = $3 
            AND symbol = $4 
            AND status = 'OPEN'
        `;

        await query(sql, [
          brokerPos.currentPrice,
          brokerPos.unrealizedPL,
          userId,
          brokerPos.symbol
        ]);

      } catch (error) {
        this.logger.error('Error updating internal position', {
          userId,
          symbol: brokerPos.symbol,
          error: error.message,
          correlationId: this.correlationId
        });
      }
    }
  }

  /**
   * Process reconciliation queue
   */
  async processReconciliationQueue() {
    const itemsToProcess = this.reconciliationQueue.splice(0, this.config.batchSize);
    
    for (const item of itemsToProcess) {
      try {
        await this.reconcileDiscrepancy(item);
        this.metrics.positionsReconciled++;

      } catch (error) {
        this.logger.error('Reconciliation failed', {
          userId: item.userId,
          error: error.message,
          correlationId: this.correlationId
        });

        // Retry logic
        item.attempts++;
        if (item.attempts < this.config.retryAttempts) {
          this.reconciliationQueue.push(item);
        } else {
          this.logger.error('Max reconciliation attempts reached', {
            userId: item.userId,
            discrepancy: item.discrepancy.type,
            correlationId: this.correlationId
          });
        }
      }
    }
  }

  /**
   * Reconcile a specific discrepancy
   */
  async reconcileDiscrepancy(item) {
    const { userId, discrepancy } = item;
    
    switch (discrepancy.type) {
      case 'MISSING_BROKER':
        // Close internal position that doesn't exist in broker
        await this.closeInternalPosition(discrepancy.internal.id, 'BROKER_SYNC');
        break;
      
      case 'MISSING_INTERNAL':
        // Create internal position for broker position
        await this.createInternalPosition(userId, discrepancy.broker);
        break;
      
      case 'QUANTITY_MISMATCH':
        // Update internal position quantity to match broker
        await this.updateInternalPositionQuantity(
          discrepancy.internal.id,
          discrepancy.broker.quantity
        );
        break;
    }
  }

  /**
   * Close internal position
   */
  async closeInternalPosition(positionId, reason) {
    const sql = `
      UPDATE hft_positions 
      SET 
        status = 'CLOSED',
        closed_at = CURRENT_TIMESTAMP,
        metadata = COALESCE(metadata, '{}')::jsonb || $2::jsonb
      WHERE id = $1
    `;

    await query(sql, [
      positionId,
      JSON.stringify({ closedReason: reason, closedBy: 'position_sync' })
    ]);
  }

  /**
   * Create internal position from broker position
   */
  async createInternalPosition(userId, brokerPosition) {
    const sql = `
      INSERT INTO hft_positions (
        user_id, symbol, position_type, quantity, entry_price, 
        current_price, unrealized_pnl, status, alpaca_position_id, metadata
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    `;

    await query(sql, [
      userId,
      brokerPosition.symbol,
      brokerPosition.side.toUpperCase(),
      Math.abs(brokerPosition.quantity),
      brokerPosition.avgEntryPrice,
      brokerPosition.currentPrice,
      brokerPosition.unrealizedPL,
      'OPEN',
      brokerPosition.symbol, // Use symbol as identifier
      JSON.stringify({ 
        createdBy: 'position_sync',
        syncedFromBroker: true 
      })
    ]);
  }

  /**
   * Update internal position quantity
   */
  async updateInternalPositionQuantity(positionId, newQuantity) {
    const sql = `
      UPDATE hft_positions 
      SET 
        quantity = $2,
        updated_at = CURRENT_TIMESTAMP,
        metadata = COALESCE(metadata, '{}')::jsonb || $3::jsonb
      WHERE id = $1
    `;

    await query(sql, [
      positionId,
      Math.abs(newQuantity),
      JSON.stringify({ 
        quantityUpdatedBy: 'position_sync',
        quantityUpdatedAt: new Date().toISOString()
      })
    ]);
  }

  /**
   * Update synchronization metrics
   */
  updateSyncMetrics(syncTime, synced, discrepancies) {
    this.metrics.totalSyncs++;
    this.metrics.successfulSyncs++;
    this.metrics.lastSyncTime = Date.now();
    
    // Calculate average sync time
    this.metrics.avgSyncTime = (
      (this.metrics.avgSyncTime * (this.metrics.totalSyncs - 1) + syncTime) / 
      this.metrics.totalSyncs
    );

    // Keep only recent errors
    this.metrics.errors = this.metrics.errors.slice(-10);
  }

  /**
   * Get synchronization metrics
   */
  getMetrics() {
    return {
      ...this.metrics,
      isRunning: this.isRunning,
      activeUsers: this.alpacaServices.size,
      queuedReconciliations: this.reconciliationQueue.length,
      config: this.config
    };
  }

  /**
   * Force sync for specific user
   */
  async forceSyncUser(userId) {
    const alpacaService = this.alpacaServices.get(userId);
    
    if (!alpacaService) {
      throw new Error(`No Alpaca service found for user ${userId}`);
    }

    return await this.syncUserPositions(userId, alpacaService);
  }
}

module.exports = PositionSyncService;