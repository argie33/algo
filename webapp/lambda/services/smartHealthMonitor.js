/**
 * Smart Health Monitor - High-Performance Database Health System
 * Provides instant health checks with background data collection
 */

const { createLogger } = require('../utils/structuredLogger');
const { query } = require('../utils/database');

class SmartHealthMonitor {
  constructor() {
    this.logger = createLogger('financial-platform', 'smart-health-monitor');
    this.correlationId = this.generateCorrelationId();
    
    // In-memory health cache for instant responses
    this.healthCache = {
      lastUpdate: null,
      connectionStatus: 'unknown',
      tableStats: {},
      performanceMetrics: {},
      systemHealth: {},
      cacheValidUntil: 0
    };
    
    // Configuration
    this.config = {
      cacheValidityMs: 15 * 60 * 1000, // 15 minutes
      backgroundUpdateInterval: 5 * 60 * 1000, // 5 minutes
      deepAnalysisInterval: 30 * 60 * 1000, // 30 minutes
      maxCacheAge: 60 * 60 * 1000, // 1 hour max age
      emergencyFallback: true
    };
    
    // Background job tracking
    this.backgroundJobs = {
      statsUpdate: null,
      deepAnalysis: null,
      performanceMonitor: null
    };
    
    // Performance tracking
    this.metrics = {
      cacheHits: 0,
      cacheMisses: 0,
      backgroundUpdates: 0,
      errorCount: 0,
      avgResponseTime: 0
    };
    
    this.isInitialized = false;
  }

  generateCorrelationId() {
    return `health-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Initialize the smart health monitor
   */
  async initialize() {
    try {
      this.logger.info('Initializing Smart Health Monitor', {
        correlationId: this.correlationId
      });

      // Initial health cache population
      await this.updateHealthCache();
      
      // Start background monitoring jobs
      this.startBackgroundJobs();
      
      this.isInitialized = true;
      
      this.logger.info('Smart Health Monitor initialized successfully', {
        correlationId: this.correlationId
      });
      
      return { success: true, initialized: true };
      
    } catch (error) {
      this.logger.error('Failed to initialize Smart Health Monitor', {
        error: error.message,
        correlationId: this.correlationId
      });
      
      throw error;
    }
  }

  /**
   * Get instant health status (sub-100ms response)
   */
  async getInstantHealth() {
    const startTime = Date.now();
    
    try {
      // Check if cache is valid
      if (this.isCacheValid()) {
        this.metrics.cacheHits++;
        
        const health = {
          status: 'healthy',
          source: 'cache',
          responseTime: Date.now() - startTime,
          timestamp: new Date().toISOString(),
          cache: {
            lastUpdate: this.healthCache.lastUpdate,
            validUntil: new Date(this.healthCache.cacheValidUntil).toISOString(),
            age: Date.now() - new Date(this.healthCache.lastUpdate).getTime()
          },
          connection: {
            status: this.healthCache.connectionStatus,
            poolStats: await this.getConnectionPoolStats()
          },
          tables: this.healthCache.tableStats,
          performance: this.healthCache.performanceMetrics,
          system: this.healthCache.systemHealth
        };
        
        return health;
      }
      
      // Cache miss - get fresh data quickly
      this.metrics.cacheMisses++;
      return await this.getFreshHealthQuick();
      
    } catch (error) {
      this.metrics.errorCount++;
      this.logger.error('Instant health check failed', {
        error: error.message,
        correlationId: this.correlationId
      });
      
      return this.getEmergencyFallbackHealth(error);
    }
  }

  /**
   * Check if current cache is valid
   */
  isCacheValid() {
    return (
      this.healthCache.lastUpdate &&
      Date.now() < this.healthCache.cacheValidUntil &&
      this.healthCache.connectionStatus === 'connected'
    );
  }

  /**
   * Get fresh health data quickly (optimized queries)
   */
  async getFreshHealthQuick() {
    const startTime = Date.now();
    
    try {
      // Check if database query function is available
      if (!query || typeof query !== 'function') {
        throw new Error('Database query function not available');
      }

      // Ultra-fast connection test
      const [connectionTest] = await Promise.race([
        query('SELECT 1 as connected, NOW() as timestamp'),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Connection timeout')), 2000)
        )
      ]);
      
      // Quick table existence check (very fast)
      const criticalTables = ['stock_symbols', 'portfolio_holdings', 'api_keys', 'user_accounts'];
      const tableChecks = await Promise.allSettled(
        criticalTables.map(async (table) => {
          const [exists] = await query(`
            SELECT EXISTS (
              SELECT FROM information_schema.tables 
              WHERE table_schema = 'public' AND table_name = $1
            )
          `, [table]);
          return { table, exists: exists.exists };
        })
      );
      
      const tableStats = {};
      tableChecks.forEach(result => {
        if (result.status === 'fulfilled') {
          const { table, exists } = result.value;
          tableStats[table] = {
            exists,
            status: exists ? 'available' : 'missing',
            lastChecked: new Date().toISOString()
          };
        }
      });
      
      const health = {
        status: 'healthy',
        source: 'fresh',
        responseTime: Date.now() - startTime,
        timestamp: new Date().toISOString(),
        connection: {
          status: 'connected',
          serverTime: connectionTest.timestamp,
          responseTime: Date.now() - startTime
        },
        tables: tableStats,
        performance: {
          responseTime: Date.now() - startTime,
          queryCount: criticalTables.length + 1,
          cacheStatus: 'refreshed'
        },
        note: 'Quick health check - full analysis running in background'
      };
      
      // Update cache asynchronously
      this.updateHealthCacheAsync();
      
      return health;
      
    } catch (error) {
      throw error;
    }
  }

  /**
   * Emergency fallback when all else fails
   */
  getEmergencyFallbackHealth(error) {
    const fallbackHealth = {
      status: 'degraded',
      source: 'fallback',
      timestamp: new Date().toISOString(),
      connection: {
        status: 'failed',
        error: error ? error.message : 'Unknown error'
      },
      tables: {},
      performance: {
        responseTime: 0,
        error: 'Health check failed'
      },
      note: 'Emergency fallback - system may be experiencing issues'
    };

    // Ensure all values are JSON serializable
    try {
      JSON.stringify(fallbackHealth);
    } catch (jsonError) {
      // Return minimal safe fallback
      return {
        status: 'error',
        source: 'fallback',
        timestamp: new Date().toISOString(),
        connection: { status: 'failed' },
        tables: {},
        performance: { responseTime: 0 }
      };
    }

    return fallbackHealth;
  }

  /**
   * Update health cache with comprehensive data
   */
  async updateHealthCache() {
    const startTime = Date.now();
    
    try {
      this.logger.info('Updating health cache', {
        correlationId: this.correlationId
      });
      
      // Connection test
      const [connectionTest] = await query('SELECT 1 as connected, NOW() as timestamp');
      
      // Get table statistics (optimized queries)
      const tableStats = await this.getOptimizedTableStats();
      
      // Get performance metrics
      const performanceMetrics = await this.getPerformanceMetrics();
      
      // Get system health
      const systemHealth = await this.getSystemHealth();
      
      // Update cache
      this.healthCache = {
        lastUpdate: new Date().toISOString(),
        connectionStatus: 'connected',
        tableStats,
        performanceMetrics,
        systemHealth,
        cacheValidUntil: Date.now() + this.config.cacheValidityMs
      };
      
      this.metrics.backgroundUpdates++;
      
      const updateTime = Date.now() - startTime;
      this.logger.info('Health cache updated successfully', {
        updateTime,
        correlationId: this.correlationId
      });
      
    } catch (error) {
      this.logger.error('Failed to update health cache', {
        error: error.message,
        correlationId: this.correlationId
      });
      
      // Mark connection as failed but keep old cache if available
      this.healthCache.connectionStatus = 'failed';
    }
  }

  /**
   * Get optimized table statistics using database statistics
   */
  async getOptimizedTableStats() {
    try {
      // Use PostgreSQL statistics instead of COUNT(*) for better performance
      const statsQuery = `
        SELECT 
          schemaname,
          tablename,
          n_tup_ins as inserts,
          n_tup_upd as updates,
          n_tup_del as deletes,
          n_live_tup as estimated_rows,
          n_dead_tup as dead_rows,
          last_vacuum,
          last_autovacuum,
          last_analyze,
          last_autoanalyze
        FROM pg_stat_user_tables 
        WHERE schemaname = 'public'
        ORDER BY n_live_tup DESC
      `;
      
      const statsResult = await query(statsQuery);
      
      // Get table sizes efficiently
      const sizeQuery = `
        SELECT 
          tablename,
          pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
          pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
        FROM pg_tables 
        WHERE schemaname = 'public'
      `;
      
      const sizeResult = await query(sizeQuery);
      
      // Combine results
      const tableStats = {};
      const sizeMap = new Map(sizeResult.map(row => [row.tablename, row]));
      
      statsResult.forEach(row => {
        const sizeInfo = sizeMap.get(row.tablename) || {};
        
        tableStats[row.tablename] = {
          exists: true,
          estimatedRows: parseInt(row.estimated_rows) || 0,
          deadRows: parseInt(row.dead_rows) || 0,
          size: sizeInfo.size || 'unknown',
          sizeBytes: parseInt(sizeInfo.size_bytes) || 0,
          activity: {
            inserts: parseInt(row.inserts) || 0,
            updates: parseInt(row.updates) || 0,
            deletes: parseInt(row.deletes) || 0
          },
          maintenance: {
            lastVacuum: row.last_vacuum,
            lastAnalyze: row.last_analyze
          },
          status: 'healthy',
          lastChecked: new Date().toISOString()
        };
      });
      
      return tableStats;
      
    } catch (error) {
      this.logger.error('Failed to get optimized table stats', {
        error: error.message
      });
      return {};
    }
  }

  /**
   * Get database performance metrics
   */
  async getPerformanceMetrics() {
    try {
      const [dbStats] = await query(`
        SELECT 
          numbackends as active_connections,
          xact_commit as transactions_committed,
          xact_rollback as transactions_rolled_back,
          blks_read as blocks_read,
          blks_hit as blocks_hit,
          tup_returned as tuples_returned,
          tup_fetched as tuples_fetched,
          conflicts,
          temp_files,
          temp_bytes
        FROM pg_stat_database 
        WHERE datname = current_database()
      `);
      
      return {
        activeConnections: dbStats?.active_connections || 0,
        transactionStats: {
          committed: dbStats?.transactions_committed || 0,
          rolledBack: dbStats?.transactions_rolled_back || 0,
          rollbackRate: dbStats?.transactions_committed ? 
            (dbStats.transactions_rolled_back / dbStats.transactions_committed * 100).toFixed(2) + '%' : '0%'
        },
        cacheEfficiency: dbStats?.blocks_hit && dbStats?.blocks_read 
          ? Math.round((dbStats.blocks_hit / (dbStats.blocks_hit + dbStats.blocks_read)) * 100) + '%'
          : 'unknown',
        tempUsage: {
          tempFiles: dbStats?.temp_files || 0,
          tempBytes: dbStats?.temp_bytes || 0
        },
        lastUpdated: new Date().toISOString()
      };
      
    } catch (error) {
      return {
        error: 'Performance metrics unavailable',
        lastUpdated: new Date().toISOString()
      };
    }
  }

  /**
   * Get system health metrics
   */
  async getSystemHealth() {
    const pool = require('../utils/database').getPool?.();
    
    return {
      connectionPool: pool ? {
        total: pool.totalCount,
        idle: pool.idleCount,
        waiting: pool.waitingCount,
        max: pool.options?.max || 'unknown',
        utilization: pool.options?.max ? 
          Math.round((pool.totalCount / pool.options.max) * 100) + '%' : 'unknown'
      } : { error: 'Pool stats unavailable' },
      memory: process.memoryUsage(),
      uptime: process.uptime(),
      environment: process.env.NODE_ENV || 'unknown',
      lastUpdated: new Date().toISOString()
    };
  }

  /**
   * Get connection pool statistics quickly
   */
  async getConnectionPoolStats() {
    try {
      const pool = require('../utils/database').getPool?.();
      
      if (!pool) {
        return { error: 'Pool not available' };
      }
      
      return {
        total: pool.totalCount,
        idle: pool.idleCount,
        waiting: pool.waitingCount,
        max: pool.options?.max || 'unknown'
      };
    } catch (error) {
      return { error: 'Pool stats unavailable' };
    }
  }

  /**
   * Start background monitoring jobs
   */
  startBackgroundJobs() {
    // Regular cache updates
    this.backgroundJobs.statsUpdate = setInterval(() => {
      this.updateHealthCacheAsync();
    }, this.config.backgroundUpdateInterval);
    
    // Deep analysis
    this.backgroundJobs.deepAnalysis = setInterval(() => {
      this.performDeepAnalysis();
    }, this.config.deepAnalysisInterval);
    
    this.logger.info('Background health monitoring jobs started', {
      correlationId: this.correlationId
    });
  }

  /**
   * Update health cache asynchronously (non-blocking)
   */
  async updateHealthCacheAsync() {
    try {
      await this.updateHealthCache();
    } catch (error) {
      this.logger.error('Background cache update failed', {
        error: error.message
      });
    }
  }

  /**
   * Perform deep analysis (background)
   */
  async performDeepAnalysis() {
    try {
      this.logger.info('Starting deep analysis', {
        correlationId: this.correlationId
      });
      
      // Deep analysis logic here
      // - Table fragmentation analysis
      // - Query performance analysis
      // - Index usage statistics
      // - Long-running query detection
      
    } catch (error) {
      this.logger.error('Deep analysis failed', {
        error: error.message
      });
    }
  }

  /**
   * Get health monitoring metrics
   */
  getMonitoringMetrics() {
    return {
      ...this.metrics,
      cacheHitRate: this.metrics.cacheHits > 0 ? 
        (this.metrics.cacheHits / (this.metrics.cacheHits + this.metrics.cacheMisses) * 100).toFixed(2) + '%' : '0%',
      isInitialized: this.isInitialized,
      backgroundJobsActive: Object.values(this.backgroundJobs).filter(job => job !== null).length,
      cacheAge: this.healthCache.lastUpdate ? 
        Date.now() - new Date(this.healthCache.lastUpdate).getTime() : null
    };
  }

  /**
   * Shutdown monitoring
   */
  shutdown() {
    Object.values(this.backgroundJobs).forEach(job => {
      if (job) clearInterval(job);
    });
    
    this.logger.info('Smart Health Monitor shut down', {
      correlationId: this.correlationId
    });
  }
}

module.exports = SmartHealthMonitor;