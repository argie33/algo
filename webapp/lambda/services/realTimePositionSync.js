/**
 * Real-Time Position Synchronization Service
 * Provides immediate position synchronization triggers and event-driven updates
 */

const EventEmitter = require('events');
const { createLogger } = require('../utils/structuredLogger');
const { query } = require('../utils/database');
const PositionSyncService = require('./positionSyncService');

class RealTimePositionSync extends EventEmitter {
  constructor() {
    super();
    this.logger = createLogger('financial-platform', 'realtime-position-sync');
    this.correlationId = this.generateCorrelationId();
    
    // Real-time sync configuration
    this.config = {
      immediateSync: true,
      syncDelayMs: 1000, // 1 second delay for batching
      maxBatchSize: 20,
      criticalThresholdPercent: 5.0, // 5% discrepancy triggers immediate sync
      enableWebSocketUpdates: true,
      syncOnOrderFill: true,
      syncOnPositionChange: true
    };
    
    // State management
    this.isActive = false;
    this.pendingSyncs = new Map(); // userId -> pendingSync details
    this.syncTimers = new Map(); // userId -> timer reference
    this.positionSyncService = new PositionSyncService();
    
    // Real-time metrics
    this.metrics = {
      realTimeSyncs: 0,
      immediateSync: 0,
      batchedSyncs: 0,
      criticalSyncs: 0,
      avgSyncLatency: 0,
      totalSyncLatency: 0,
      lastRealTimeSync: null
    };
    
    // Set up event handlers
    this.setupEventHandlers();
  }

  generateCorrelationId() {
    return `rt-pos-sync-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Setup event handlers for real-time synchronization
   */
  setupEventHandlers() {
    // Order execution events
    this.on('orderFilled', this.handleOrderFilled.bind(this));
    this.on('orderRejected', this.handleOrderRejected.bind(this));
    
    // Position change events
    this.on('positionOpened', this.handlePositionOpened.bind(this));
    this.on('positionClosed', this.handlePositionClosed.bind(this));
    this.on('positionModified', this.handlePositionModified.bind(this));
    
    // Market data events
    this.on('significantPriceChange', this.handleSignificantPriceChange.bind(this));
    
    // System events
    this.on('connectionRestored', this.handleConnectionRestored.bind(this));
    this.on('systemRecovery', this.handleSystemRecovery.bind(this));
  }

  /**
   * Initialize real-time position synchronization
   */
  async initialize() {
    try {
      this.logger.info('Initializing Real-Time Position Sync', {
        correlationId: this.correlationId
      });

      // Initialize base position sync service
      const initResult = await this.positionSyncService.initialize();
      if (!initResult.success) {
        throw new Error(`Failed to initialize position sync service: ${initResult.error}`);
      }

      // Start base position sync service
      const startResult = await this.positionSyncService.start();
      if (!startResult.success) {
        throw new Error(`Failed to start position sync service: ${startResult.error}`);
      }

      this.isActive = true;

      this.logger.info('Real-Time Position Sync initialized successfully', {
        correlationId: this.correlationId,
        config: this.config
      });

      return { success: true, message: 'Real-time position sync active' };

    } catch (error) {
      this.logger.error('Failed to initialize Real-Time Position Sync', {
        error: error.message,
        correlationId: this.correlationId
      });

      return { success: false, error: error.message };
    }
  }

  /**
   * Trigger immediate position sync for user
   */
  async triggerImmediateSync(userId, reason = 'manual', metadata = {}) {
    if (!this.isActive) {
      throw new Error('Real-time position sync not active');
    }

    const startTime = Date.now();
    
    try {
      this.logger.info('Triggering immediate position sync', {
        userId,
        reason,
        correlationId: this.correlationId
      });

      // Cancel any pending batched sync for this user
      this.cancelPendingSync(userId);

      // Perform immediate sync
      const syncResult = await this.positionSyncService.forceSyncUser(userId);
      
      const syncLatency = Date.now() - startTime;
      this.updateRealTimeMetrics(syncLatency, 'immediate');

      // Record sync event
      await this.recordSyncEvent(userId, 'IMMEDIATE', reason, syncLatency, syncResult, metadata);

      this.logger.info('Immediate position sync completed', {
        userId,
        reason,
        syncLatency,
        synced: syncResult.synced,
        discrepancies: syncResult.discrepancies,
        correlationId: this.correlationId
      });

      return {
        success: true,
        syncLatency,
        synced: syncResult.synced,
        discrepancies: syncResult.discrepancies
      };

    } catch (error) {
      this.logger.error('Immediate position sync failed', {
        userId,
        reason,
        error: error.message,
        correlationId: this.correlationId
      });

      throw error;
    }
  }

  /**
   * Schedule delayed position sync for user (batching)
   */
  scheduleDelayedSync(userId, reason = 'batched', metadata = {}) {
    if (!this.isActive || !this.config.immediateSync) {
      return;
    }

    // Cancel existing timer for this user
    this.cancelPendingSync(userId);

    // Store pending sync details
    this.pendingSyncs.set(userId, {
      reason,
      metadata,
      scheduledAt: Date.now()
    });

    // Schedule sync
    const timer = setTimeout(async () => {
      try {
        await this.executePendingSync(userId);
      } catch (error) {
        this.logger.error('Scheduled sync execution failed', {
          userId,
          error: error.message,
          correlationId: this.correlationId
        });
      }
    }, this.config.syncDelayMs);

    this.syncTimers.set(userId, timer);

    this.logger.debug('Scheduled delayed position sync', {
      userId,
      reason,
      delay: this.config.syncDelayMs,
      correlationId: this.correlationId
    });
  }

  /**
   * Execute pending sync for user
   */
  async executePendingSync(userId) {
    const pendingSync = this.pendingSyncs.get(userId);
    if (!pendingSync) {
      return;
    }

    const startTime = Date.now();

    try {
      this.logger.info('Executing pending position sync', {
        userId,
        reason: pendingSync.reason,
        correlationId: this.correlationId
      });

      // Perform sync
      const syncResult = await this.positionSyncService.forceSyncUser(userId);
      
      const syncLatency = Date.now() - startTime;
      this.updateRealTimeMetrics(syncLatency, 'batched');

      // Record sync event
      await this.recordSyncEvent(
        userId, 
        'BATCHED', 
        pendingSync.reason, 
        syncLatency, 
        syncResult, 
        pendingSync.metadata
      );

      // Clean up
      this.pendingSyncs.delete(userId);
      this.syncTimers.delete(userId);

      this.logger.info('Pending position sync completed', {
        userId,
        syncLatency,
        synced: syncResult.synced,
        discrepancies: syncResult.discrepancies,
        correlationId: this.correlationId
      });

    } catch (error) {
      this.logger.error('Pending position sync failed', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });

      // Clean up even on failure
      this.pendingSyncs.delete(userId);
      this.syncTimers.delete(userId);
    }
  }

  /**
   * Cancel pending sync for user
   */
  cancelPendingSync(userId) {
    const timer = this.syncTimers.get(userId);
    if (timer) {
      clearTimeout(timer);
      this.syncTimers.delete(userId);
      this.pendingSyncs.delete(userId);
    }
  }

  /**
   * Handle order filled event
   */
  async handleOrderFilled(event) {
    const { userId, orderId, symbol, quantity, fillPrice, side } = event;

    this.logger.info('Order filled - triggering position sync', {
      userId,
      orderId,
      symbol,
      quantity,
      side,
      correlationId: this.correlationId
    });

    if (this.config.syncOnOrderFill) {
      // Immediate sync for order fills
      try {
        await this.triggerImmediateSync(userId, 'order_filled', {
          orderId,
          symbol,
          quantity,
          fillPrice,
          side
        });
      } catch (error) {
        this.logger.error('Order filled sync failed', {
          userId,
          orderId,
          error: error.message,
          correlationId: this.correlationId
        });
      }
    }
  }

  /**
   * Handle order rejected event
   */
  async handleOrderRejected(event) {
    const { userId, orderId, symbol, reason } = event;

    this.logger.warn('Order rejected - checking position consistency', {
      userId,
      orderId,
      symbol,
      reason,
      correlationId: this.correlationId
    });

    // Schedule delayed sync to check for any inconsistencies
    this.scheduleDelayedSync(userId, 'order_rejected', {
      orderId,
      symbol,
      reason
    });
  }

  /**
   * Handle position opened event
   */
  async handlePositionOpened(event) {
    const { userId, positionId, symbol, quantity, entryPrice } = event;

    this.logger.info('Position opened - triggering position sync', {
      userId,
      positionId,
      symbol,
      quantity,
      correlationId: this.correlationId
    });

    if (this.config.syncOnPositionChange) {
      await this.triggerImmediateSync(userId, 'position_opened', {
        positionId,
        symbol,
        quantity,
        entryPrice
      });
    }
  }

  /**
   * Handle position closed event
   */
  async handlePositionClosed(event) {
    const { userId, positionId, symbol, quantity, exitPrice, pnl } = event;

    this.logger.info('Position closed - triggering position sync', {
      userId,
      positionId,
      symbol,
      quantity,
      pnl,
      correlationId: this.correlationId
    });

    if (this.config.syncOnPositionChange) {
      await this.triggerImmediateSync(userId, 'position_closed', {
        positionId,
        symbol,
        quantity,
        exitPrice,
        pnl
      });
    }
  }

  /**
   * Handle position modified event
   */
  async handlePositionModified(event) {
    const { userId, positionId, symbol, changes } = event;

    this.logger.info('Position modified - scheduling position sync', {
      userId,
      positionId,
      symbol,
      changes,
      correlationId: this.correlationId
    });

    // Schedule delayed sync for position modifications
    this.scheduleDelayedSync(userId, 'position_modified', {
      positionId,
      symbol,
      changes
    });
  }

  /**
   * Handle significant price change event
   */
  async handleSignificantPriceChange(event) {
    const { symbol, oldPrice, newPrice, changePercent, affectedUsers } = event;

    this.logger.info('Significant price change - updating position valuations', {
      symbol,
      oldPrice,
      newPrice,
      changePercent,
      affectedUsersCount: affectedUsers.length,
      correlationId: this.correlationId
    });

    // Schedule sync for all affected users if change is critical
    if (Math.abs(changePercent) >= this.config.criticalThresholdPercent) {
      for (const userId of affectedUsers) {
        await this.triggerImmediateSync(userId, 'critical_price_change', {
          symbol,
          oldPrice,
          newPrice,
          changePercent
        });
        this.metrics.criticalSyncs++;
      }
    } else {
      // Schedule delayed sync for less critical changes
      for (const userId of affectedUsers) {
        this.scheduleDelayedSync(userId, 'price_change', {
          symbol,
          oldPrice,
          newPrice,
          changePercent
        });
      }
    }
  }

  /**
   * Handle connection restored event
   */
  async handleConnectionRestored(event) {
    const { userId, connectionType } = event;

    this.logger.info('Connection restored - triggering position sync', {
      userId,
      connectionType,
      correlationId: this.correlationId
    });

    // Immediate sync after connection restoration
    await this.triggerImmediateSync(userId, 'connection_restored', {
      connectionType,
      restoredAt: Date.now()
    });
  }

  /**
   * Handle system recovery event
   */
  async handleSystemRecovery(event) {
    const { affectedUsers, recoveryType } = event;

    this.logger.info('System recovery - triggering position sync for affected users', {
      affectedUsersCount: affectedUsers.length,
      recoveryType,
      correlationId: this.correlationId
    });

    // Immediate sync for all affected users
    for (const userId of affectedUsers) {
      try {
        await this.triggerImmediateSync(userId, 'system_recovery', {
          recoveryType,
          recoveredAt: Date.now()
        });
      } catch (error) {
        this.logger.error('System recovery sync failed', {
          userId,
          error: error.message,
          correlationId: this.correlationId
        });
      }
    }
  }

  /**
   * Record sync event in database
   */
  async recordSyncEvent(userId, syncType, reason, latency, result, metadata = {}) {
    try {
      const sql = `
        INSERT INTO hft_sync_events (
          user_id, sync_type, reason, latency_ms, synced_count, 
          discrepancy_count, metadata, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
      `;

      await query(sql, [
        userId,
        syncType,
        reason,
        latency,
        result.synced || 0,
        result.discrepancies || 0,
        JSON.stringify(metadata),
        new Date()
      ]);

    } catch (error) {
      this.logger.error('Failed to record sync event', {
        userId,
        syncType,
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Update real-time metrics
   */
  updateRealTimeMetrics(latency, syncType) {
    this.metrics.realTimeSyncs++;
    this.metrics.totalSyncLatency += latency;
    this.metrics.avgSyncLatency = this.metrics.totalSyncLatency / this.metrics.realTimeSyncs;
    this.metrics.lastRealTimeSync = Date.now();

    if (syncType === 'immediate') {
      this.metrics.immediateSync++;
    } else if (syncType === 'batched') {
      this.metrics.batchedSyncs++;
    }
  }

  /**
   * Get real-time sync metrics
   */
  getMetrics() {
    const baseSyncMetrics = this.positionSyncService.getMetrics();
    
    return {
      ...baseSyncMetrics,
      realTime: {
        ...this.metrics,
        isActive: this.isActive,
        pendingSyncs: this.pendingSyncs.size,
        activeTimers: this.syncTimers.size,
        config: this.config
      }
    };
  }

  /**
   * Stop real-time position synchronization
   */
  async stop() {
    try {
      this.logger.info('Stopping Real-Time Position Sync', {
        correlationId: this.correlationId
      });

      // Cancel all pending syncs
      for (const userId of this.syncTimers.keys()) {
        this.cancelPendingSync(userId);
      }

      // Stop base position sync service
      await this.positionSyncService.stop();

      this.isActive = false;

      this.logger.info('Real-Time Position Sync stopped', {
        correlationId: this.correlationId
      });

      return { success: true, message: 'Real-time position sync stopped' };

    } catch (error) {
      this.logger.error('Failed to stop Real-Time Position Sync', {
        error: error.message,
        correlationId: this.correlationId
      });

      return { success: false, error: error.message };
    }
  }
}

module.exports = RealTimePositionSync;